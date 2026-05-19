from __future__ import annotations

import csv
import io
import sqlite3
from threading import Lock
from typing import Any

from app.config import settings


class SQLiteStorage:
    def __init__(self, db_path: str):
        self.db_path = db_path
        self._lock = Lock()
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._init_schema()

    def _init_schema(self) -> None:
        with self._lock:
            self._conn.execute(
                """
                CREATE TABLE IF NOT EXISTS events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    recorded_at TEXT NOT NULL,
                    service TEXT NOT NULL,
                    metric_name TEXT NOT NULL,
                    metric_value REAL NOT NULL,
                    risk_score REAL NOT NULL,
                    anomaly_score REAL NOT NULL,
                    severity TEXT NOT NULL,
                    emitted INTEGER NOT NULL,
                    suppression_reason TEXT
                )
                """
            )
            self._conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_events_service ON events (service)"
            )
            self._conn.commit()

    def insert_event(self, entry: dict[str, Any]) -> None:
        with self._lock:
            self._conn.execute(
                """
                INSERT INTO events (
                    recorded_at, service, metric_name, metric_value,
                    risk_score, anomaly_score, severity, emitted, suppression_reason
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    entry["recorded_at"],
                    entry["service"],
                    entry["metric_name"],
                    float(entry["metric_value"]),
                    float(entry["risk_score"]),
                    float(entry["anomaly_score"]),
                    entry["severity"],
                    1 if entry["emitted"] else 0,
                    entry.get("suppression_reason"),
                ),
            )
            self._conn.commit()

    def list_recent_events(
        self,
        limit: int,
        service: str | None = None,
        emitted: bool | None = None,
        severity: str | None = None,
    ) -> list[dict[str, Any]]:
        clauses: list[str] = []
        params: list[Any] = []
        if service:
            clauses.append("service = ?")
            params.append(service)
        if emitted is not None:
            clauses.append("emitted = ?")
            params.append(1 if emitted else 0)
        if severity:
            clauses.append("LOWER(severity) = LOWER(?)")
            params.append(severity)

        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        query = (
            "SELECT recorded_at, service, metric_name, metric_value, risk_score, "
            "anomaly_score, severity, emitted, suppression_reason "
            f"FROM events {where} ORDER BY id DESC LIMIT ?"
        )
        params.append(limit)

        with self._lock:
            rows = self._conn.execute(query, tuple(params)).fetchall()

        return [self._to_event_dict(row) for row in rows]

    def get_summary(self) -> dict[str, Any]:
        with self._lock:
            totals = self._conn.execute(
                """
                SELECT
                    COUNT(*) AS total_events,
                    COALESCE(SUM(emitted), 0) AS emitted_events
                FROM events
                """
            ).fetchone()
            active_services = self._conn.execute(
                "SELECT COUNT(DISTINCT service) AS active_services FROM events"
            ).fetchone()

        total_events = int(totals["total_events"])
        emitted_events = int(totals["emitted_events"])
        suppressed_events = total_events - emitted_events
        suppression_rate = round((suppressed_events / total_events), 4) if total_events else 0.0
        return {
            "total_events": total_events,
            "emitted_events": emitted_events,
            "suppressed_events": suppressed_events,
            "suppression_rate": suppression_rate,
            "active_services": int(active_services["active_services"]),
        }

    def get_service_analytics(self, service: str) -> dict[str, Any]:
        with self._lock:
            row = self._conn.execute(
                """
                SELECT
                    COUNT(*) AS events,
                    COALESCE(SUM(emitted), 0) AS emitted,
                    COALESCE(AVG(risk_score), 0) AS average_risk_score,
                    COALESCE(AVG(anomaly_score), 0) AS average_anomaly_score
                FROM events
                WHERE service = ?
                """,
                (service,),
            ).fetchone()

        events = int(row["events"])
        emitted_count = int(row["emitted"])
        suppressed = events - emitted_count
        return {
            "service": service,
            "events": events,
            "emitted": emitted_count,
            "suppressed": suppressed,
            "suppression_rate": round((suppressed / events), 4) if events else 0.0,
            "average_risk_score": round(float(row["average_risk_score"]), 4),
            "average_anomaly_score": round(float(row["average_anomaly_score"]), 4),
        }

    def get_severity_analytics(self, severity: str) -> dict[str, Any]:
        with self._lock:
            row = self._conn.execute(
                """
                SELECT COUNT(*) AS events, COALESCE(SUM(emitted), 0) AS emitted
                FROM events
                WHERE LOWER(severity) = LOWER(?)
                """,
                (severity,),
            ).fetchone()

        events = int(row["events"])
        emitted_count = int(row["emitted"])
        return {
            "severity": severity.lower(),
            "events": events,
            "emitted": emitted_count,
            "suppressed": events - emitted_count,
        }

    def export_events_csv(self, limit: int = 500) -> str:
        events = self.list_recent_events(limit=limit)
        buffer = io.StringIO()
        writer = csv.DictWriter(
            buffer,
            fieldnames=[
                "recorded_at",
                "service",
                "metric_name",
                "metric_value",
                "risk_score",
                "anomaly_score",
                "severity",
                "emitted",
                "suppression_reason",
            ],
        )
        writer.writeheader()
        for row in events:
            writer.writerow({**row, "emitted": int(row["emitted"])})
        return buffer.getvalue()

    def ping(self) -> bool:
        try:
            with self._lock:
                self._conn.execute("SELECT 1").fetchone()
            return True
        except sqlite3.Error:
            return False

    def count_events(
        self,
        service: str | None = None,
        severity: str | None = None,
    ) -> int:
        clauses: list[str] = []
        params: list[Any] = []
        if service:
            clauses.append("service = ?")
            params.append(service)
        if severity:
            clauses.append("LOWER(severity) = LOWER(?)")
            params.append(severity)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        with self._lock:
            row = self._conn.execute(
                f"SELECT COUNT(*) AS total FROM events {where}", tuple(params)
            ).fetchone()
        return int(row["total"])

    def list_distinct_services(self) -> list[str]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT DISTINCT service FROM events ORDER BY service ASC"
            ).fetchall()
        return [str(row["service"]) for row in rows]

    def reset(self) -> None:
        with self._lock:
            self._conn.execute("DELETE FROM events")
            self._conn.commit()

    @staticmethod
    def _to_event_dict(row: sqlite3.Row) -> dict[str, Any]:
        return {
            "recorded_at": row["recorded_at"],
            "service": row["service"],
            "metric_name": row["metric_name"],
            "metric_value": float(row["metric_value"]),
            "risk_score": float(row["risk_score"]),
            "anomaly_score": float(row["anomaly_score"]),
            "severity": row["severity"],
            "emitted": bool(row["emitted"]),
            "suppression_reason": row["suppression_reason"],
        }


storage = SQLiteStorage(settings.sqlite_db_path)
