"""
Cognito JWT authentication middleware.

Verifies JWT tokens issued by AWS Cognito for all protected endpoints.
Extracts user identity and attaches it to the request state.
"""
import os
import json
import logging
import time
from typing import Optional

import httpx
from fastapi import Request, HTTPException
from starlette.middleware.base import BaseHTTPMiddleware
from jose import jwt, JWTError, jwk

logger = logging.getLogger("accord.parent.auth")

COGNITO_REGION = os.environ.get("COGNITO_REGION", "us-east-1")
COGNITO_USER_POOL_ID = os.environ.get("COGNITO_USER_POOL_ID", "")
COGNITO_APP_CLIENT_ID = os.environ.get("COGNITO_APP_CLIENT_ID", "")

# Paths that don't require authentication
PUBLIC_PATHS = {"/health", "/docs", "/openapi.json", "/api/v1/attestation"}

# JWKS cache
_jwks_cache: Optional[dict] = None
_jwks_cache_time: float = 0
JWKS_CACHE_TTL = 3600  # 1 hour


class CognitoAuthMiddleware(BaseHTTPMiddleware):
    """Middleware that validates Cognito JWT tokens."""

    async def dispatch(self, request: Request, call_next):
        # Skip auth for public paths
        path = request.url.path
        if any(path.startswith(p) for p in PUBLIC_PATHS):
            return await call_next(request)

        # Skip auth for WebSocket (handled separately)
        if request.url.path.startswith("/ws/"):
            return await call_next(request)

        # Extract token
        auth_header = request.headers.get("Authorization", "")
        if not auth_header.startswith("Bearer "):
            raise HTTPException(status_code=401, detail="Missing authorization token")

        token = auth_header[7:]

        try:
            claims = await verify_token(token)
            request.state.user_id = claims.get("sub", "")
            request.state.email = claims.get("email", "")
            request.state.groups = claims.get("cognito:groups", [])
        except Exception as e:
            logger.warning(f"Auth failed: {e}")
            raise HTTPException(status_code=401, detail="Invalid or expired token")

        return await call_next(request)


async def verify_token(token: str) -> dict:
    """Verify a Cognito JWT token and return claims."""
    if not COGNITO_USER_POOL_ID:
        # Development mode: skip verification
        logger.warning("COGNITO_USER_POOL_ID not set — skipping token verification")
        try:
            return jwt.get_unverified_claims(token)
        except JWTError:
            return {"sub": "dev-user", "email": "dev@localhost"}

    jwks = await _get_jwks()

    try:
        # Get the key ID from the token header
        unverified_header = jwt.get_unverified_header(token)
        kid = unverified_header.get("kid")

        # Find the matching key
        key = None
        for k in jwks.get("keys", []):
            if k["kid"] == kid:
                key = k
                break

        if not key:
            raise JWTError("Key not found in JWKS")

        # Verify the token
        issuer = f"https://cognito-idp.{COGNITO_REGION}.amazonaws.com/{COGNITO_USER_POOL_ID}"
        claims = jwt.decode(
            token,
            key,
            algorithms=["RS256"],
            audience=COGNITO_APP_CLIENT_ID,
            issuer=issuer,
        )
        return claims
    except JWTError as e:
        raise ValueError(f"Token verification failed: {e}")


async def _get_jwks() -> dict:
    """Fetch and cache Cognito JWKS."""
    global _jwks_cache, _jwks_cache_time

    if _jwks_cache and (time.time() - _jwks_cache_time) < JWKS_CACHE_TTL:
        return _jwks_cache

    jwks_url = (
        f"https://cognito-idp.{COGNITO_REGION}.amazonaws.com/"
        f"{COGNITO_USER_POOL_ID}/.well-known/jwks.json"
    )

    async with httpx.AsyncClient() as client:
        response = await client.get(jwks_url, timeout=10)
        response.raise_for_status()
        _jwks_cache = response.json()
        _jwks_cache_time = time.time()

    return _jwks_cache
