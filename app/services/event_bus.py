from __future__ import annotations

import asyncio
from collections import deque
from datetime import datetime, timezone
from typing import Deque, Dict, Set


class RealtimeHub:
    def __init__(self):
        self.clients: Set = set()
        self.metric_windows: Dict[str, Deque[float]] = {}
        self.last_emitted_by_signature: Dict[str, datetime] = {}
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

    def should_emit(self, payload: dict) -> tuple[bool, str | None]:
        service = payload.get("event", {}).get("service", "unknown")
        metric_name = payload.get("event", {}).get("metric_name", "unknown")
        severity = payload.get("decision", {}).get("severity", "unknown")
        action = payload.get("decision", {}).get("action", "monitor")
        risk_score = float(payload.get("risk_score", 0.0))

        if risk_score >= 0.9:
            return True, None

        if risk_score >= 0.7:
            cooldown_seconds = 12
        elif risk_score >= 0.4:
            cooldown_seconds = 25
        else:
            cooldown_seconds = 45

        signature = f"{service}:{metric_name}:{severity}:{action}".lower()
        now = datetime.now(timezone.utc)
        last_emitted = self.last_emitted_by_signature.get(signature)
        if last_emitted is None:
            self.last_emitted_by_signature[signature] = now
            return True, None

        age_seconds = (now - last_emitted).total_seconds()
        if age_seconds < cooldown_seconds:
            reason = (
                f"suppressed duplicate incident for signature '{signature}' "
                f"within {cooldown_seconds}s cooldown window"
            )
            return False, reason

        self.last_emitted_by_signature[signature] = now
        return True, None


hub = RealtimeHub()
