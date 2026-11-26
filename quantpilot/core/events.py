"""Thread-safe WebSocket event hub. Agents (running in worker threads) call ``emit``."""
from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import Any, Optional

from fastapi import WebSocket

log = logging.getLogger("quantpilot.events")


class EventHub:
    """Fan-out of JSON events to all connected WebSocket clients."""

    def __init__(self) -> None:
        self.clients: set[WebSocket] = set()
        self.loop: Optional[asyncio.AbstractEventLoop] = None
        self.queue: Optional[asyncio.Queue] = None
        self.sent = 0

    def bind(self, loop: asyncio.AbstractEventLoop) -> None:
        self.loop = loop
        self.queue = asyncio.Queue(maxsize=5000)

    def emit(self, type_: str, data: Any) -> None:
        """Schedule an event from any thread."""
        if self.loop is None or self.queue is None:
            return
        msg = {"type": type_, "ts": time.time(), "data": data}
        try:
            self.loop.call_soon_threadsafe(self._put, msg)
        except RuntimeError:
            pass  # loop closed during shutdown

    def _put(self, msg: dict) -> None:
        assert self.queue is not None
        if self.queue.full():
            self.queue.get_nowait()
        self.queue.put_nowait(msg)

    async def pump(self) -> None:
        """Forward queued events to every client forever."""
        assert self.queue is not None
        while True:
            msg = await self.queue.get()
            if not self.clients:
                continue
            payload = json.dumps(msg, default=str)
            dead = []
            for ws in list(self.clients):
                try:
                    await ws.send_text(payload)
                    self.sent += 1
                except Exception:  # noqa: BLE001 - drop broken sockets
                    dead.append(ws)
            for ws in dead:
                self.clients.discard(ws)
