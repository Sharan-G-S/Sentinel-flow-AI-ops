from __future__ import annotations

import asyncio
from collections import deque
from typing import Deque, Dict, Set


class RealtimeHub:
    def __init__(self):
        self.clients: Set = set()
        self.metric_windows: Dict[str, Deque[float]] = {}
        self.lock = asyncio.Lock()

    def get_window(self, service: str, size: int = 8) -> Deque[float]:
        if service not in self.metric_windows:
            self.metric_windows[service] = deque(maxlen=size)
        return self.metric_windows[service]

    async def register(self, ws):
        async with self.lock:
            self.clients.add(ws)

    async def unregister(self, ws):
        async with self.lock:
            if ws in self.clients:
                self.clients.remove(ws)

    async def broadcast(self, payload: dict):
        stale = []
        async with self.lock:
            for ws in self.clients:
                try:
                    await ws.send_json(payload)
                except Exception:
                    stale.append(ws)
            for ws in stale:
                self.clients.remove(ws)


hub = RealtimeHub()
