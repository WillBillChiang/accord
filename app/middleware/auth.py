"""
Firebase Auth authentication middleware.

Verifies Firebase ID tokens for all protected endpoints.
Extracts user identity and attaches it to the request state.
Enforces TOTP MFA — requests without MFA are rejected for protected routes.
"""
import os
import logging
from typing import Optional

from fastapi import Request, HTTPException
from starlette.middleware.base import BaseHTTPMiddleware

logger = logging.getLogger("accord.auth")

FIREBASE_PROJECT_ID = os.environ.get("FIREBASE_PROJECT_ID", "")

# Paths that don't require authentication
PUBLIC_PATHS = {"/health", "/docs", "/openapi.json", "/api/v1/attestation"}

# Firebase Admin SDK — initialized lazily
_firebase_initialized = False


def _ensure_firebase_initialized():
    """Initialize Firebase Admin SDK if not already done."""
    global _firebase_initialized
    if _firebase_initialized:
        return

    try:
        import firebase_admin
        from firebase_admin import credentials

        if not firebase_admin._apps:
            # Use Application Default Credentials (ADC) in GCP,
            # or GOOGLE_APPLICATION_CREDENTIALS env var locally
            cred_path = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS")
            if cred_path:
                cred = credentials.Certificate(cred_path)
                firebase_admin.initialize_app(cred)
            else:
                firebase_admin.initialize_app()
            logger.info("Firebase Admin SDK initialized")

        _firebase_initialized = True
    except Exception as e:
        logger.warning(f"Firebase Admin SDK initialization failed: {e}")


class FirebaseAuthMiddleware(BaseHTTPMiddleware):
    """Middleware that validates Firebase Auth ID tokens and enforces TOTP MFA."""

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
            request.state.user_id = claims.get("uid", "")
            request.state.email = claims.get("email", "")
            # Firebase custom claims for groups/roles
            request.state.groups = claims.get("groups", [])
            if claims.get("admin"):
                request.state.groups = list(set(request.state.groups + ["admin"]))
        except Exception as e:
            logger.warning(f"Auth failed: {e}")
            raise HTTPException(status_code=401, detail="Invalid or expired token")

        return await call_next(request)


async def verify_token(token: str) -> dict:
    """Verify a Firebase ID token and return claims."""
    if not FIREBASE_PROJECT_ID:
        # Development mode: skip verification
        logger.warning("FIREBASE_PROJECT_ID not set — skipping token verification")
        return {"uid": "dev-user", "email": "dev@localhost", "groups": ["admin"]}

    _ensure_firebase_initialized()

    try:
        from firebase_admin import auth

        # verify_id_token checks signature, expiry, audience, and issuer
        # check_revoked=True also checks if the token has been revoked
        decoded_token = auth.verify_id_token(token, check_revoked=True)

        # Enforce TOTP MFA for protected endpoints
        firebase_claims = decoded_token.get("firebase", {})
        sign_in_second_factor = firebase_claims.get("sign_in_second_factor")

        if sign_in_second_factor != "totp":
            logger.warning(
                f"MFA not completed for user {decoded_token.get('uid')}: "
                f"sign_in_second_factor={sign_in_second_factor}"
            )
            raise ValueError("TOTP MFA is required for all protected endpoints")

        return decoded_token
    except ImportError:
        logger.error("firebase_admin not installed")
        raise ValueError("Firebase Admin SDK not available")
    except Exception as e:
        raise ValueError(f"Token verification failed: {e}")
