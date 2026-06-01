"""WebSocket manager for real-time updates.

Provides a broadcast mechanism for notifying connected clients
when the entity state changes (e.g., from MCP operations).
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, Self

from fastapi import WebSocket

logger = logging.getLogger(__name__)


class ConnectionManager:
    """Manages WebSocket connections and broadcasts."""

    def __init__(self) -> None:
        self.active_connections: list[WebSocket] = []
        self._lock = asyncio.Lock()
        self._pending_tasks: set[asyncio.Task[None]] = set()

    async def connect(self: Self, websocket: WebSocket) -> None:
        """Accept and register a new WebSocket connection."""
        await websocket.accept()
        async with self._lock:
            self.active_connections.append(websocket)
        logger.info("WebSocket client connected (%d total)", len(self.active_connections))

    async def disconnect(self: Self, websocket: WebSocket) -> None:
        """Remove a WebSocket connection."""
        async with self._lock:
            if websocket in self.active_connections:
                self.active_connections.remove(websocket)
        logger.info("WebSocket client disconnected (%d remaining)", len(self.active_connections))

    async def broadcast(self: Self, message: dict[str, Any]) -> None:
        """Broadcast a message to all connected clients."""
        if not self.active_connections:
            return

        data = json.dumps(message)
        disconnected = []

        async with self._lock:
            for connection in self.active_connections:
                try:
                    await connection.send_text(data)
                except Exception:
                    disconnected.append(connection)

        # Clean up disconnected clients
        for conn in disconnected:
            await self.disconnect(conn)

    def broadcast_sync(self: Self, message: dict[str, Any]) -> None:
        """Broadcast from synchronous code (creates event loop if needed)."""
        if not self.active_connections:
            return

        try:
            loop = asyncio.get_running_loop()
            task = loop.create_task(self.broadcast(message))
            self._pending_tasks.add(task)
            task.add_done_callback(self._pending_tasks.discard)
        except RuntimeError:
            # No running loop - create one
            asyncio.run(self.broadcast(message))


# Global manager instance
manager = ConnectionManager()


def notify_state_changed(event: str = "state_changed", **data: Any) -> None:
    """Notify all connected clients that state has changed.

    Args:
        event: Event type (e.g., "state_changed", "entity_created").
        **data: Additional data to include in the message.
    """
    manager.broadcast_sync({"event": event, **data})
