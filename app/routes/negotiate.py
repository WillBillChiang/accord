"""
Negotiation control API routes.

Start, monitor, and manage active negotiations.
"""
import logging

from fastapi import APIRouter, Request, HTTPException

from models.firestore import FirestoreClient
from engine.agent.seller_agent import SellerAgent
from engine.agent.buyer_agent import BuyerAgent
from engine.agent.llm_engine import LLMEngine
from engine.protocol.sao import SAOProtocol
from engine.protocol.zopa import compute_zopa
from engine.protocol.schemas import SessionStatus
from routes.sessions import get_sessions

logger = logging.getLogger("accord.negotiate")
router = APIRouter()
db = FirestoreClient()

# LLM engine singleton (initialized once at startup)
_llm_engine = None


def get_llm_engine() -> LLMEngine:
    """Get or create the LLM engine singleton."""
    global _llm_engine
    if _llm_engine is None:
        try:
            _llm_engine = LLMEngine()
            logger.info("LLM engine initialized")
        except Exception as e:
            logger.warning(f"LLM engine init failed (will use fallback): {e}")
            _llm_engine = LLMEngine.__new__(LLMEngine)
            _llm_engine._model = None
            _llm_engine.model_path = ""
            _llm_engine.temperature = 0.3
    return _llm_engine


@router.post("/sessions/{session_id}/start")
async def start_negotiation(session_id: str, request: Request):
    """
    Start the negotiation for a session.

    Both parties must be onboarded. The engine will:
    1. Check ZOPA existence
    2. If ZOPA exists, run SAO protocol
    3. Return deal terms or no-deal outcome
    """
    session_meta = db.get_session(session_id)
    if not session_meta:
        raise HTTPException(status_code=404, detail="Session not found")

    if not session_meta.get("sellerOnboarded") or not session_meta.get("buyerOnboarded"):
        raise HTTPException(
            status_code=400,
            detail="Both parties must be onboarded before starting",
        )

    sessions = get_sessions()
    engine_session = sessions.get(session_id)
    if not engine_session:
        raise HTTPException(status_code=404, detail="Session not active in engine")

    if engine_session.status != SessionStatus.ZOPA_CHECK:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot start negotiation in status {engine_session.status.value}",
        )

    db.update_session_status(session_id, "negotiating")

    try:
        # Phase 3: ZOPA Check
        zopa_result = compute_zopa(engine_session.seller_config, engine_session.buyer_config)

        if not zopa_result["zopa_exists"]:
            logger.info(f"No ZOPA for session {session_id}")
            outcome = engine_session.terminate("no_zopa")
            result = outcome.model_dump()
            if session_id in sessions:
                del sessions[session_id]
            db.update_session_status(session_id, "no_zopa")
            return result

        # Phase 4: Run negotiation
        llm = get_llm_engine()
        seller_agent = SellerAgent(engine_session.seller_config, llm)
        buyer_agent = BuyerAgent(engine_session.buyer_config, llm)

        protocol = SAOProtocol(
            seller_agent=seller_agent,
            buyer_agent=buyer_agent,
            session=engine_session,
        )

        outcome = protocol.run()
        result = outcome.model_dump()
    except Exception as e:
        db.update_session_status(session_id, "error")
        logger.error(f"Negotiation error for session {session_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))

    # Clean up session from memory
    if session_id in sessions:
        del sessions[session_id]

    # Update Firestore with outcome
    outcome_status = result.get("outcome", "error")
    db.update_session_status(session_id, outcome_status)

    if outcome_status == "deal_reached":
        db.update_session_field(session_id, "finalTerms", result.get("final_terms"))
        db.update_session_field(session_id, "finalPrice", result.get("final_price"))

    db.update_session_field(session_id, "roundsCompleted", result.get("rounds_completed", 0))

    # Log audit entry
    user_id = getattr(request.state, 'user_id', 'anonymous')
    db.put_audit_log({
        "sessionId": session_id,
        "action": "negotiation_completed",
        "userId": user_id,
        "outcome": outcome_status,
        "roundsCompleted": result.get("rounds_completed", 0),
    })

    return result


@router.get("/sessions/{session_id}/status")
async def get_negotiation_status(session_id: str):
    """Get real-time negotiation status from engine."""
    sessions = get_sessions()
    engine_session = sessions.get(session_id)

    if engine_session:
        return {
            "session_id": session_id,
            "status": engine_session.status.value,
            "current_round": engine_session.current_round,
            "is_expired": engine_session.is_expired(),
            "seller_onboarded": engine_session.seller_config is not None,
            "buyer_onboarded": engine_session.buyer_config is not None,
            "log": engine_session.get_redacted_log(),
        }

    # Fall back to Firestore metadata
    session_meta = db.get_session(session_id)
    if not session_meta:
        raise HTTPException(status_code=404, detail="Session not found")
    return {
        "session_id": session_id,
        "status": session_meta.get("status", "unknown"),
        "note": "Session not active in engine, showing stored status",
    }
