"""
Accord Negotiation Engine — Unified FastAPI Server.

Runs inside a GCP Confidential VM (AMD SEV-SNP) with GPU acceleration.
The entire VM's memory is hardware-encrypted, providing TEE guarantees.
Combines the API server and negotiation engine in a single process —
no vsock relay needed since the whole VM is the trusted execution
environment.

SECURITY: All confidential negotiation data exists only in encrypted
VM memory. Cloud KMS decryption is restricted to this VM's service
account via attestation-conditioned IAM policy.
"""
import uuid
import logging
import sys
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware

from routes import sessions, onboard, negotiate, attestation, audit
from middleware.auth import FirebaseAuthMiddleware
from middleware.audit import AuditLogMiddleware
from middleware.rate_limit import RateLimitMiddleware
from websocket_manager import WebSocketManager
from config import ENVIRONMENT, LOG_LEVEL

logging.basicConfig(
    level=getattr(logging, LOG_LEVEL, logging.INFO),
    format='%(asctime)s [%(name)s] %(levelname)s: %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("accord")

ws_manager = WebSocketManager()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler."""
    logger.info("Accord Negotiation Engine starting (GCP Confidential VM)...")
    yield
    logger.info("Accord Negotiation Engine shutting down...")
    # Terminate all active sessions (provable deletion)
    active_sessions = sessions.get_sessions()
    for sid in list(active_sessions.keys()):
        active_sessions[sid].terminate("vm_shutdown")
        del active_sessions[sid]
    await ws_manager.shutdown()


app = FastAPI(
    title="Accord Negotiation Engine",
    description="TEE-based AI negotiation engine API (GCP Confidential VM)",
    version="2.0.0",
    lifespan=lifespan,
)

# CORS — configure per environment in production
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Restrict to Firebase Hosting domain in production
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
app.add_middleware(FirebaseAuthMiddleware)
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
    """Health check endpoint for GCP Load Balancer."""
    return {"status": "healthy", "service": "accord", "platform": "gcp-confidential-vm"}


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
