"""
Accord Enclave Application -- Entry Point.

Main entry point for the negotiation engine running inside the
AWS Nitro Enclave. Listens on vsock for commands from the parent
EC2 instance and orchestrates the negotiation protocol.
"""
from __future__ import annotations

import json
import logging
import sys
import time
from typing import Optional

from vsock_server import VsockServer
from session import NegotiationSession
from attestation import get_attestation_document
from kms_client import EnclaveKMSClient
from agent.seller_agent import SellerAgent
from agent.buyer_agent import BuyerAgent
from agent.llm_engine import LLMEngine
from protocol.sao import SAOProtocol
from protocol.zopa import compute_zopa
from protocol.schemas import (
    PartyConfig, NegotiationRole, SessionStatus, VsockMessage
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(name)s] %(levelname)s: %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("accord.enclave")

# Global state
sessions: dict[str, NegotiationSession] = {}
kms_client = EnclaveKMSClient()
llm_engine: Optional[LLMEngine] = None


def initialize() -> None:
    """Initialize the enclave application."""
    global llm_engine
    logger.info("Accord Enclave starting...")

    try:
        llm_engine = LLMEngine()
        logger.info("LLM engine initialized")
    except Exception as e:
        logger.warning(f"LLM engine init failed (will use fallback): {e}")
        llm_engine = LLMEngine.__new__(LLMEngine)
        llm_engine._model = None
        llm_engine.model_path = ""
        llm_engine.temperature = 0.3


def handle_message(msg: dict) -> dict:
    """
    Route incoming vsock messages to appropriate handlers.

    Message format: {"action": "...", "session_id": "...", "payload": {...}}
    """
    action = msg.get("action", "")
    session_id = msg.get("session_id", "")
    payload = msg.get("payload", {})
    request_id = msg.get("request_id", "")

    try:
        if action == "get_attestation":
            return _handle_attestation(payload)
        elif action == "create_session":
            return _handle_create_session(payload)
        elif action == "onboard":
            return _handle_onboard(session_id, payload)
        elif action == "start_negotiation":
            return _handle_start_negotiation(session_id)
        elif action == "get_status":
            return _handle_get_status(session_id)
        elif action == "terminate":
            return _handle_terminate(session_id, payload)
        elif action == "health":
            return {"status": "healthy", "sessions_active": len(sessions)}
        else:
            return {"error": f"Unknown action: {action}"}
    except Exception as e:
        logger.error(f"Error handling {action}: {e}", exc_info=True)
        return {"error": str(e), "action": action, "request_id": request_id}


def _handle_attestation(payload: dict) -> dict:
    """Return enclave attestation document."""
    nonce = payload.get("nonce")
    doc = get_attestation_document(nonce=nonce)
    return doc.model_dump()


def _handle_create_session(payload: dict) -> dict:
    """Create a new negotiation session."""
    session_id = payload.get("session_id")
    max_duration = payload.get("max_duration_sec", 3600)

    if not session_id:
        import uuid
        session_id = str(uuid.uuid4())

    if session_id in sessions:
        return {"error": f"Session {session_id} already exists"}

    session = NegotiationSession(
        session_id=session_id,
        max_duration_sec=max_duration,
    )
    sessions[session_id] = session

    logger.info(f"Session created: {session_id}")
    return {
        "session_id": session_id,
        "status": session.status.value,
        "created_at": session.created_at,
    }


def _handle_onboard(session_id: str, payload: dict) -> dict:
    """Onboard a party to a session."""
    session = sessions.get(session_id)
    if not session:
        return {"error": f"Session {session_id} not found"}

    # In production, decrypt config using KMS
    encrypted_config = payload.get("encrypted_config")
    if encrypted_config:
        try:
            decrypted = kms_client.decrypt(encrypted_config)
            config_data = json.loads(decrypted)
        except Exception as e:
            logger.warning(f"KMS decrypt failed, using plaintext: {e}")
            config_data = payload.get("config", {})
    else:
        config_data = payload.get("config", {})

    config = PartyConfig(**config_data)
    return session.onboard_party(config)


def _handle_start_negotiation(session_id: str) -> dict:
    """Start the negotiation for a session."""
    session = sessions.get(session_id)
    if not session:
        return {"error": f"Session {session_id} not found"}

    if not session.is_ready():
        return {"error": "Both parties must be onboarded before starting"}

    if session.status != SessionStatus.ZOPA_CHECK:
        return {"error": f"Cannot start negotiation in status {session.status.value}"}

    # Phase 3: ZOPA Check
    zopa_result = compute_zopa(session.seller_config, session.buyer_config)

    if not zopa_result["zopa_exists"]:
        logger.info(f"No ZOPA for session {session_id}")
        outcome = session.terminate("no_zopa")
        return outcome.model_dump()

    # Phase 4: Run negotiation
    seller_agent = SellerAgent(session.seller_config, llm_engine)
    buyer_agent = BuyerAgent(session.buyer_config, llm_engine)

    protocol = SAOProtocol(
        seller_agent=seller_agent,
        buyer_agent=buyer_agent,
        session=session,
    )

    outcome = protocol.run()

    # Clean up session
    if session_id in sessions:
        del sessions[session_id]

    return outcome.model_dump()


def _handle_get_status(session_id: str) -> dict:
    """Get current status of a session."""
    session = sessions.get(session_id)
    if not session:
        return {"error": f"Session {session_id} not found", "status": "not_found"}

    return {
        "session_id": session_id,
        "status": session.status.value,
        "current_round": session.current_round,
        "is_expired": session.is_expired(),
        "seller_onboarded": session.seller_config is not None,
        "buyer_onboarded": session.buyer_config is not None,
        "log": session.get_redacted_log(),
    }


def _handle_terminate(session_id: str, payload: dict) -> dict:
    """Manually terminate a session."""
    session = sessions.get(session_id)
    if not session:
        return {"error": f"Session {session_id} not found"}

    reason = payload.get("reason", "manual_termination")
    outcome = session.terminate(reason)

    if session_id in sessions:
        del sessions[session_id]

    return outcome.model_dump()


def main() -> None:
    """Main loop: listen for vsock connections and handle messages."""
    initialize()

    server = VsockServer()
    server.start()

    logger.info("Accord Enclave ready — waiting for connections")

    try:
        while True:
            conn = server.accept()
            try:
                while True:
                    msg = server.recv_message(conn)
                    if msg is None:
                        break

                    response = handle_message(msg)
                    server.send_message(conn, response)
            except Exception as e:
                logger.error(f"Connection error: {e}")
            finally:
                conn.close()
    except KeyboardInterrupt:
        logger.info("Shutting down...")
    finally:
        # Terminate all active sessions
        for sid in list(sessions.keys()):
            sessions[sid].terminate("enclave_shutdown")
            del sessions[sid]
        server.shutdown()


if __name__ == "__main__":
    main()
