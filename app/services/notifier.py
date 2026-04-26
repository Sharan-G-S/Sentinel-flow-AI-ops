from __future__ import annotations

from typing import Any

import httpx

from app.config import settings


class IncidentNotifier:
    async def notify(self, payload: dict[str, Any]) -> None:
        if not self._should_notify(payload):
            return

        tasks: list[httpx.Response] = []
        async with httpx.AsyncClient(timeout=5.0) as client:
            if settings.slack_webhook_url:
                tasks.append(
                    await client.post(
                        settings.slack_webhook_url,
                        json={"text": self._build_slack_message(payload)},
                    )
                )
            if settings.alert_webhook_url:
                tasks.append(await client.post(settings.alert_webhook_url, json=payload))

        for response in tasks:
            response.raise_for_status()

    def _should_notify(self, payload: dict[str, Any]) -> bool:
        severity = str(payload.get("decision", {}).get("severity", "unknown")).lower()
        if settings.notify_high_severity_only:
            return severity == "high"
        return severity in {"high", "medium", "low"}

    @staticmethod
    def _build_slack_message(payload: dict[str, Any]) -> str:
        event = payload.get("event", {})
        decision = payload.get("decision", {})
        return (
            f":rotating_light: *SentinelFlow Incident* "
            f"service={event.get('service', 'unknown')} "
            f"metric={event.get('metric_name', 'unknown')} "
            f"value={event.get('metric_value', 0)} "
            f"severity={decision.get('severity', 'unknown')} "
            f"action={decision.get('action', 'monitor')}"
        )


notifier = IncidentNotifier()
