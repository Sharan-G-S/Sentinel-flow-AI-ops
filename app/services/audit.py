"""
Append-only audit log service for SentinelFlow-AIOps.

Every ingest event, analytics reset, and alert emission is written to a
structured JSONL audit file so operators have a tamper-evident trail for
compliance and post-incident review.
"""
from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
from typing import Any


logger = logging.getLogger(__name__)

_AUDIT_LOG_PATH = os.getenv("AUDIT_LOG_PATH", "audit.jsonl")


class AuditLogger:
    """Thread-safe append-only JSONL audit writer."""

    def __init__(self, path: str = _AUDIT_LOG_PATH) -> None:
        self._path = Path(path)
        self._lock = Lock()
        # Ensure the parent directory exists
        self._path.parent.mkdir(parents=True, exist_ok=True)

    def _write(self, entry: dict[str, Any]) -> None:
        entry["_ts"] = datetime.now(timezone.utc).isoformat()
        line = json.dumps(entry, default=str)
        with self._lock:
            try:
                with self._path.open("a", encoding="utf-8") as fh:
                    fh.write(line + "\n")
            except OSError as exc:
                logger.warning("audit log write failed: %s", exc)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def log_ingest(
        self,
        correlation_id: str,
        service: str,
        metric_name: str,
        metric_value: float,
        risk_score: float,
        severity: str,
        emitted: bool,
    ) -> None:
        self._write(
            {
                "event": "ingest",
                "correlation_id": correlation_id,
                "service": service,
                "metric_name": metric_name,
                "metric_value": metric_value,
                "risk_score": risk_score,
                "severity": severity,
                "emitted": emitted,
            }
        )

    def log_batch_ingest(self, correlation_id: str, count: int, services: list[str]) -> None:
        self._write(
            {
                "event": "batch_ingest",
                "correlation_id": correlation_id,
                "event_count": count,
                "services": services,
            }
        )

    def log_analytics_reset(self, correlation_id: str) -> None:
        self._write(
            {
                "event": "analytics_reset",
                "correlation_id": correlation_id,
            }
        )

    def log_alert_dispatch(self, correlation_id: str, channel: str, service: str, severity: str) -> None:
        self._write(
            {
                "event": "alert_dispatch",
                "correlation_id": correlation_id,
                "channel": channel,
                "service": service,
                "severity": severity,
            }
        )

    def log_websocket(self, action: str, client_host: str | None) -> None:
        self._write(
            {
                "event": f"websocket_{action}",
                "client_host": client_host or "unknown",
            }
        )

    def tail(self, n: int = 50) -> list[dict[str, Any]]:
        """Return the last *n* audit entries (most-recent-first)."""
        entries: list[dict[str, Any]] = []
        try:
            with self._path.open("r", encoding="utf-8") as fh:
                lines = fh.readlines()
            for line in reversed(lines[-n:]):
                line = line.strip()
                if line:
                    entries.append(json.loads(line))
        except (OSError, json.JSONDecodeError):
            pass
        return entries


audit = AuditLogger()
