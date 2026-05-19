from __future__ import annotations

import asyncio
from collections import deque
from datetime import datetime, timezone
from typing import Any, Deque, Dict, Set

from app.config import settings


class RealtimeHub:
    def __init__(self):
        self.clients: Set = set()
        self.metric_windows: Dict[str, Deque[float]] = {}
        self.last_emitted_by_signature: Dict[str, datetime] = {}
        self.recent_events: Deque[Dict[str, Any]] = deque(maxlen=settings.event_history_size)
        self.total_events: int = 0
        self.emitted_events: int = 0
        self.suppressed_events: int = 0
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

        if risk_score >= settings.risk_high_threshold:
            cooldown_seconds = settings.dedup_high_cooldown_sec
        elif risk_score >= settings.risk_medium_threshold:
            cooldown_seconds = settings.dedup_medium_cooldown_sec
        else:
            cooldown_seconds = settings.dedup_low_cooldown_sec

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

    def record_event(self, payload: dict, emitted: bool, suppression_reason: str | None) -> dict[str, Any]:
        self.total_events += 1
        if emitted:
            self.emitted_events += 1
        else:
            self.suppressed_events += 1

        entry = {
            "recorded_at": datetime.now(timezone.utc).isoformat(),
            "service": payload.get("event", {}).get("service", "unknown"),
            "metric_name": payload.get("event", {}).get("metric_name", "unknown"),
            "metric_value": payload.get("event", {}).get("metric_value", 0.0),
            "risk_score": payload.get("risk_score", 0.0),
            "anomaly_score": payload.get("anomaly_score", 0.0),
            "severity": payload.get("decision", {}).get("severity", "unknown"),
            "emitted": emitted,
            "suppression_reason": suppression_reason,
        }
        self.recent_events.appendleft(entry)
        return entry

    def reset_analytics(self) -> None:
        self.recent_events.clear()
        self.metric_windows.clear()
        self.total_events = 0
        self.emitted_events = 0
        self.suppressed_events = 0
        self.last_emitted_by_signature.clear()


hub = RealtimeHub()
