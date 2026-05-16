from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from fastapi import Depends, FastAPI, Request, WebSocket, WebSocketDisconnect, Query, status
from app.schemas import (
    TelemetryEvent,
    InferenceResponse,
    AgentDecision,
    Explainability,
    EventRecord,
    AnalyticsSummary,
    ServiceAnalytics,
    SystemStatus,
    SeverityAnalytics,
    ResetResponse,
    BatchIngestRequest,
    BatchIngestResponse,
    ServiceHealthScore,
    ServiceHealthList,
    AuditTailResponse,
    CircuitBreakerStatus,
    VersionInfo,
)
from app.models.tf_anomaly import TensorFlowAnomalyDetector
from app.models.pytorch_risk import PyTorchRiskModel
from app.services.event_bus import hub
from app.services.storage import storage
from app.services.notifier import notifier
from app.services.metrics import metrics
from app.services.audit import audit
from app.agents.langgraph_flow import graph
from app.agents.circuit_breaker import llm_circuit
from app.config import settings
from app.security import require_api_key
from app.middleware.rate_limiter import SlidingWindowRateLimiter
from app.middleware.correlation import CorrelationIDMiddleware
from app.middleware.timing import RequestTimingMiddleware


app = FastAPI(title="SentinelFlow-AIOps", version=settings.app_version)
app.add_middleware(RequestTimingMiddleware)
app.add_middleware(CorrelationIDMiddleware)
app.add_middleware(
    SlidingWindowRateLimiter,
    max_requests=settings.rate_limit_max_requests,
    window_seconds=settings.rate_limit_window_sec,
)
anomaly_model = TensorFlowAnomalyDetector(window_size=8)
risk_model = PyTorchRiskModel()
app_started_at = datetime.now(timezone.utc)
logger = logging.getLogger(__name__)


def build_explainability(
    metric_value: float, anomaly_score: float, risk_score: float, error_rate: float, window: list[float]
) -> Explainability:
    if risk_score >= settings.risk_high_threshold:
        risk_band = "high"
    elif risk_score >= settings.risk_medium_threshold:
        risk_band = "medium"
    else:
        risk_band = "low"

    if len(window) >= 2:
        delta = window[-1] - window[0]
    else:
        delta = 0.0
    if delta > 5:
        trend = "rapidly rising"
    elif delta > 1:
        trend = "rising"
    elif delta < -5:
        trend = "rapidly falling"
    elif delta < -1:
        trend = "falling"
    else:
        trend = "stable"

    weighted_factors = {
        "metric_value": round((metric_value / 100.0) * 0.45, 4),
        "anomaly_score": round(anomaly_score * 0.4, 4),
        "error_rate": round(error_rate * 0.15, 4),
    }
    top_signals = [k for k, _ in sorted(weighted_factors.items(), key=lambda item: item[1], reverse=True)[:2]]

    return Explainability(
        risk_band=risk_band,
        trend=trend,
        top_signals=top_signals,
        contributing_factors=weighted_factors,
    )


def _pad_metric_window(window: list[float], metric_value: float, size: int = 8) -> list[float]:
    padded = list(window)
    if len(padded) < size:
        fill = padded[0] if padded else metric_value
        padded = [fill] * (size - len(padded)) + padded
    return padded


def _risk_to_severity(risk_score: float) -> str:
    if risk_score >= settings.risk_high_threshold:
        return "high"
    if risk_score >= settings.risk_medium_threshold:
        return "medium"
    return "low"


def _severity_badge(severity: str) -> str:
    return {
        "critical": "\U0001f534",
        "high": "\U0001f7e0",
        "medium": "\U0001f7e1",
        "low": "\U0001f7e2",
    }.get(severity.lower(), "\u26aa")

@app.get("/health")
def health():
    return {
        "status": "ok",
        "service": "sentinelflow-aiops",
        "utc_time": datetime.now(timezone.utc).isoformat(),
    }


@app.get("/version", response_model=VersionInfo)
def version_info():
    import sys

    return VersionInfo(
        name="SentinelFlow-AIOps",
        version=settings.app_version,
        python=f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
    )


@app.get("/metrics", include_in_schema=False)
def prometheus_metrics():
    """Prometheus metrics exposition endpoint."""
    from fastapi.responses import PlainTextResponse
    metrics.set_gauge("sentinelflow_connected_clients", len(hub.clients))
    metrics.set_gauge("sentinelflow_total_events", hub.total_events)
    metrics.set_gauge("sentinelflow_emitted_events", hub.emitted_events)
    metrics.set_gauge("sentinelflow_suppressed_events", hub.suppressed_events)
    return PlainTextResponse(metrics.exposition(), media_type="text/plain; version=0.0.4")


@app.get("/system/status", response_model=SystemStatus)
def system_status(_: None = Depends(require_api_key)):
    uptime_seconds = int((datetime.now(timezone.utc) - app_started_at).total_seconds())
    return SystemStatus(
        status="ok",
        uptime_seconds=uptime_seconds,
        connected_clients=len(hub.clients),
        total_events=hub.total_events,
    )


@app.get("/alerts/export", include_in_schema=True)
def export_alerts(
    limit: int = Query(default=500, ge=1, le=5000),
    _: None = Depends(require_api_key),
):
    """Download recent alert records as CSV for offline analysis."""
    from fastapi.responses import PlainTextResponse

    csv_body = storage.export_events_csv(limit=limit)
    return PlainTextResponse(
        csv_body,
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="alerts_export.csv"'},
    )


@app.get("/alerts/recent", response_model=list[EventRecord])
def recent_alerts(
    limit: int = Query(default=20, ge=1, le=200),
    service: str | None = Query(default=None),
    emitted: bool | None = Query(default=None),
    severity: str | None = Query(default=None),
    _: None = Depends(require_api_key),
):
    return storage.list_recent_events(
        limit=limit, service=service, emitted=emitted, severity=severity
    )


@app.get("/analytics/summary", response_model=AnalyticsSummary)
def analytics_summary(_: None = Depends(require_api_key)):
    return AnalyticsSummary(**storage.get_summary())


@app.get("/analytics/service/{service}", response_model=ServiceAnalytics)
def analytics_for_service(service: str, _: None = Depends(require_api_key)):
    return ServiceAnalytics(**storage.get_service_analytics(service))


@app.get("/analytics/severity/{severity}", response_model=SeverityAnalytics)
def analytics_for_severity(severity: str, _: None = Depends(require_api_key)):
    return SeverityAnalytics(**storage.get_severity_analytics(severity))


@app.post("/analytics/reset", response_model=ResetResponse)
def reset_analytics(request: Request, _: None = Depends(require_api_key)):
    correlation_id = getattr(request.state, "correlation_id", "n/a")
    hub.reset_analytics()
    storage.reset()
    audit.log_analytics_reset(correlation_id)
    return ResetResponse(ok=True, message="analytics counters and history reset")


# ---------------------------------------------------------------------------
# Service health scoring
# ---------------------------------------------------------------------------
def _compute_service_health(service: str) -> ServiceHealthScore:
    sa = storage.get_service_analytics(service)
    avg_risk: float = sa.get("average_risk_score", 0.0)
    suppression_rate: float = sa.get("suppression_rate", 0.0)
    events: int = sa.get("events", 0)

    health_score = round(max(0.0, 1.0 - avg_risk * 0.7 - (1 - suppression_rate) * 0.3), 4)

    if avg_risk >= settings.risk_high_threshold:
        risk_trend = "critical"
        recommendation = "Escalate immediately – engage on-call SRE."
    elif avg_risk >= settings.risk_medium_threshold:
        risk_trend = "elevated"
        recommendation = "Increase monitoring cadence; review recent deployments."
    else:
        risk_trend = "normal"
        recommendation = "No action required."

    return ServiceHealthScore(
        service=service,
        health_score=health_score,
        risk_trend=risk_trend,
        events_last_5min=events,
        suppression_rate=suppression_rate,
        recommendation=recommendation,
    )


@app.get("/health/service/{service}", response_model=ServiceHealthScore)
def service_health(service: str, _: None = Depends(require_api_key)):
    """Compute a composite 0–1 health score for a named service."""
    return _compute_service_health(service)


@app.get("/health/services", response_model=ServiceHealthList)
def all_services_health(_: None = Depends(require_api_key)):
    """Return composite health scores for every service seen in storage."""
    scores = [_compute_service_health(s) for s in storage.list_distinct_services()]
    return ServiceHealthList(services=scores, total=len(scores))


# ---------------------------------------------------------------------------
# Circuit-breaker status
# ---------------------------------------------------------------------------
@app.get("/system/circuit-breaker", response_model=CircuitBreakerStatus)
def circuit_breaker_status(_: None = Depends(require_api_key)):
    """Return the current state of the LLM circuit breaker."""
    return CircuitBreakerStatus(**llm_circuit.status())


# ---------------------------------------------------------------------------
# Audit tail
# ---------------------------------------------------------------------------
@app.get("/audit/tail", response_model=AuditTailResponse)
def audit_tail(n: int = Query(default=50, ge=1, le=500), _: None = Depends(require_api_key)):
    """Return the last n audit log entries."""
    entries = audit.tail(n=n)
    return AuditTailResponse(entries=entries, total_returned=len(entries))


@app.post("/ingest", response_model=InferenceResponse)
async def ingest_event(request: Request, event: TelemetryEvent, _: None = Depends(require_api_key)):
    correlation_id = getattr(request.state, "correlation_id", "n/a")
    import time as _time
    t0 = _time.monotonic()

    window = hub.get_window(event.service, size=8)
    window.append(event.metric_value)
    padded = _pad_metric_window(list(window), event.metric_value)

    anomaly_score = anomaly_model.score(padded)
    error_rate = float(event.metadata.get("error_rate", 0.02))
    risk_score = risk_model.predict_risk(event.metric_value, anomaly_score, error_rate)
    explainability = build_explainability(
        metric_value=event.metric_value,
        anomaly_score=anomaly_score,
        risk_score=risk_score,
        error_rate=error_rate,
        window=padded,
    )

    state = graph.invoke(
        {
            "service": event.service,
            "metric_name": event.metric_name,
            "metric_value": event.metric_value,
            "anomaly_score": anomaly_score,
            "risk_score": risk_score,
            "route": [],
            "decision": {},
        }
    )

    raw_decision = state["decision"]
    raw_decision["severity_badge"] = _severity_badge(raw_decision.get("severity", "low"))
    decision = AgentDecision(**raw_decision)
    response = InferenceResponse(
        event=event,
        anomaly_score=anomaly_score,
        risk_score=risk_score,
        decision=decision,
        explainability=explainability,
        route=state["route"],
    )
    payload = response.model_dump(mode="json")
    emitted, suppression_reason = hub.should_emit(payload)
    response.emitted = emitted
    response.suppression_reason = suppression_reason
    event_record = hub.record_event(payload, emitted=emitted, suppression_reason=suppression_reason)
    storage.insert_event(event_record)

    audit.log_ingest(
        correlation_id=correlation_id,
        service=event.service,
        metric_name=event.metric_name,
        metric_value=event.metric_value,
        risk_score=risk_score,
        severity=decision.severity,
        emitted=emitted,
    )

    elapsed = _time.monotonic() - t0
    metrics.observe("sentinelflow_ingest_latency", elapsed)
    metrics.inc("sentinelflow_ingest_total", labels=f'service="{event.service}"')
    if emitted:
        metrics.inc("sentinelflow_emitted_total")
        await hub.broadcast(payload)
        try:
            await notifier.notify(payload)
            audit.log_alert_dispatch(correlation_id, "webhook", event.service, decision.severity)
        except Exception as exc:
            logger.warning("failed to dispatch incident notification: %s", exc)
    else:
        metrics.inc("sentinelflow_suppressed_total")
    return response


# ---------------------------------------------------------------------------
# Batch ingest
# ---------------------------------------------------------------------------
@app.post("/ingest/batch", response_model=BatchIngestResponse)
async def ingest_batch(request: Request, body: BatchIngestRequest, _: None = Depends(require_api_key)):
    """Accept up to 100 telemetry events in a single HTTP call."""
    correlation_id = getattr(request.state, "correlation_id", "n/a")
    results = []
    for event in body.events:
        window = hub.get_window(event.service, size=8)
        window.append(event.metric_value)
        padded = _pad_metric_window(list(window), event.metric_value)

        anomaly_score = anomaly_model.score(padded)
        error_rate = float(event.metadata.get("error_rate", 0.02))
        risk_score = risk_model.predict_risk(event.metric_value, anomaly_score, error_rate)
        severity = _risk_to_severity(risk_score)
        results.append(
            {
                "service": event.service,
                "metric_name": event.metric_name,
                "anomaly_score": round(anomaly_score, 4),
                "risk_score": round(risk_score, 4),
            }
        )
        storage.insert_event(
            {
                "recorded_at": datetime.now(timezone.utc).isoformat(),
                "service": event.service,
                "metric_name": event.metric_name,
                "metric_value": event.metric_value,
                "risk_score": risk_score,
                "anomaly_score": anomaly_score,
                "severity": severity,
                "emitted": True,
                "suppression_reason": None,
            }
        )
        metrics.inc("sentinelflow_batch_ingest_events_total")

    audit.log_batch_ingest(
        correlation_id=correlation_id,
        count=len(body.events),
        services=list({e.service for e in body.events}),
    )
    return BatchIngestResponse(accepted=len(body.events), results=results)


@app.websocket("/ws/decisions")
async def ws_decisions(websocket: WebSocket):
    if settings.api_key_enabled:
        if not settings.api_key:
            await websocket.close(code=status.WS_1011_INTERNAL_ERROR)
            return
        if websocket.headers.get("x-api-key") != settings.api_key:
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
            return

    await websocket.accept()
    audit.log_websocket("connect", websocket.client.host if websocket.client else None)
    await hub.register(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        audit.log_websocket("disconnect", websocket.client.host if websocket.client else None)
        await hub.unregister(websocket)
    except Exception:
        await hub.unregister(websocket)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app.main:app", host=settings.host, port=settings.port, reload=True)
