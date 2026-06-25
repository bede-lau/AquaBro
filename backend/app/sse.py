"""In-process SSE pub/sub bus.

Producers (the engine) publish event dicts; the SSE endpoint subscribes a
bounded queue per client and drains it as ``text/event-stream``. Backpressure
is handled by dropping on a full queue rather than blocking the engine loop.
"""
from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator

log = logging.getLogger("aquabro.sse")


class SSEBus:
    def __init__(self, maxqueue: int = 200) -> None:
        self._queues: set[asyncio.Queue[dict]] = set()
        self._maxqueue = maxqueue

    def subscribe(self) -> asyncio.Queue[dict]:
        q: asyncio.Queue[dict] = asyncio.Queue(maxsize=self._maxqueue)
        self._queues.add(q)
        return q

    def unsubscribe(self, q: asyncio.Queue[dict]) -> None:
        self._queues.discard(q)

    async def publish(self, event: dict) -> None:
        for q in list(self._queues):
            try:
                q.put_nowait(event)
            except asyncio.QueueFull:
                # Drop oldest to make room — freshest state matters most.
                try:
                    q.get_nowait()
                    q.put_nowait(event)
                except Exception:
                    pass

    async def stream(self, q: asyncio.Queue[dict]) -> AsyncIterator[bytes]:
        """Yield SSE-formatted frames for a subscriber queue."""
        import json

        while True:
            event = await q.get()
            payload = json.dumps(event, default=str)
            yield f"data: {payload}\n\n".encode()
