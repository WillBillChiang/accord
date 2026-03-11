"""
Accord Parent Application — FastAPI Server.

Runs on the parent EC2 instance alongside the Nitro Enclave.
Handles external TLS connections from negotiating parties,
relays messages to/from the enclave via vsock, and provides
WebSocket updates for real-time negotiation monitoring.

SECURITY: The parent NEVER sees plaintext confidential data.
All confidential data is encrypted with the enclave's
attestation-bound KMS key before reaching this server.
"""
import uuid
import logging
import sys
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware

from routes import sessions, onboard, negotiate, attestation, audit
from middleware.auth import CognitoAuthMiddleware
from middleware.audit import AuditLogMiddleware
from middleware.rate_limit import RateLimitMiddleware
from websocket_manager import WebSocketManager

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(name)s] %(levelname)s: %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("accord.parent")

ws_manager = WebSocketManager()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler."""
    logger.info("Accord Parent Application starting...")
    yield
    logger.info("Accord Parent Application shutting down...")
    await ws_manager.shutdown()


app = FastAPI(
    title="Accord Negotiation Engine",
    description="TEE-based AI negotiation engine API",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure per environment
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Request ID middleware
@app.middleware("http")
async def add_request_id(request: Request, call_next):
    request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))
    request.state.request_id = request_id
    response = await call_next(request)
    response.headers["X-Request-ID"] = request_id
    return response


# Register middleware
app.add_middleware(AuditLogMiddleware)
app.add_middleware(RateLimitMiddleware, requests_per_minute=60)

# Register routes
app.include_router(sessions.router, prefix="/api/v1", tags=["Sessions"])
app.include_router(onboard.router, prefix="/api/v1", tags=["Onboarding"])
app.include_router(negotiate.router, prefix="/api/v1", tags=["Negotiation"])
app.include_router(attestation.router, prefix="/api/v1", tags=["Attestation"])
app.include_router(audit.router, prefix="/api/v1", tags=["Audit"])


@app.get("/health")
async def health_check():
    """Health check endpoint for ALB."""
    return {"status": "healthy", "service": "accord-parent"}


@app.websocket("/ws/negotiations/{session_id}")
async def negotiation_websocket(websocket, session_id: str):
    """WebSocket endpoint for real-time negotiation updates."""
    await ws_manager.connect(websocket, session_id)
    try:
        while True:
            data = await websocket.receive_text()
            # Client can send commands like "subscribe" or "unsubscribe"
    except Exception:
        ws_manager.disconnect(websocket, session_id)
