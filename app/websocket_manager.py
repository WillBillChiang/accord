"""
WebSocket manager for real-time negotiation updates.

Manages WebSocket connections from frontend clients and pushes
negotiation status updates in real-time.
"""
import logging
import json
from typing import Optional
from fastapi import WebSocket

logger = logging.getLogger("accord.websocket")


class WebSocketManager:
    """Manages WebSocket connections grouped by session ID."""

    def __init__(self) -> None:
        self._connections: dict[str, list[WebSocket]] = {}

    async def connect(self, websocket: WebSocket, session_id: str) -> None:
        """Accept and register a WebSocket connection."""
        await websocket.accept()
        if session_id not in self._connections:
            self._connections[session_id] = []
        self._connections[session_id].append(websocket)
        logger.info(f"WebSocket connected: session={session_id}")

    def disconnect(self, websocket: WebSocket, session_id: str) -> None:
        """Remove a WebSocket connection."""
        if session_id in self._connections:
            self._connections[session_id] = [
                ws for ws in self._connections[session_id] if ws != websocket
            ]
            if not self._connections[session_id]:
                del self._connections[session_id]
        logger.info(f"WebSocket disconnected: session={session_id}")

    async def broadcast(self, session_id: str, message: dict) -> None:
        """Broadcast a message to all connections for a session."""
        connections = self._connections.get(session_id, [])
        disconnected = []

        for websocket in connections:
            try:
                await websocket.send_text(json.dumps(message))
            except Exception:
                disconnected.append(websocket)

        # Clean up disconnected clients
        for ws in disconnected:
            self.disconnect(ws, session_id)

    async def shutdown(self) -> None:
        """Close all WebSocket connections."""
        for session_id, connections in self._connections.items():
            for ws in connections:
                try:
                    await ws.close()
                except Exception:
                    pass
        self._connections.clear()
