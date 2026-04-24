from __future__ import annotations

from datetime import datetime, timezone
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Query
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
)
from app.models.tf_anomaly import TensorFlowAnomalyDetector
from app.models.pytorch_risk import PyTorchRiskModel
from app.services.event_bus import hub
from app.agents.langgraph_flow import graph
from app.config import settings


app = FastAPI(title="Realtime Agentic Ops")
anomaly_model = TensorFlowAnomalyDetector(window_size=8)
risk_model = PyTorchRiskModel()
app_started_at = datetime.now(timezone.utc)


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


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/system/status", response_model=SystemStatus)
def system_status():
    uptime_seconds = int((datetime.now(timezone.utc) - app_started_at).total_seconds())
    return SystemStatus(
        status="ok",
        uptime_seconds=uptime_seconds,
        connected_clients=len(hub.clients),
        total_events=hub.total_events,
    )


@app.get("/alerts/recent", response_model=list[EventRecord])
def recent_alerts(
    limit: int = Query(default=20, ge=1, le=200),
    service: str | None = Query(default=None),
    emitted: bool | None = Query(default=None),
):
    events = list(hub.recent_events)
    if service:
        events = [entry for entry in events if entry["service"] == service]
    if emitted is not None:
        events = [entry for entry in events if bool(entry["emitted"]) == emitted]
    return events[:limit]


@app.get("/analytics/summary", response_model=AnalyticsSummary)
def analytics_summary():
    total = max(hub.total_events, 1)
    services = {entry["service"] for entry in hub.recent_events}
    return AnalyticsSummary(
        total_events=hub.total_events,
        emitted_events=hub.emitted_events,
        suppressed_events=hub.suppressed_events,
        suppression_rate=round(hub.suppressed_events / total, 4),
        active_services=len(services),
    )


@app.get("/analytics/service/{service}", response_model=ServiceAnalytics)
def analytics_for_service(service: str):
    entries = [entry for entry in hub.recent_events if entry["service"] == service]
    if not entries:
        return ServiceAnalytics(
            service=service,
            events=0,
            emitted=0,
            suppressed=0,
            suppression_rate=0.0,
            average_risk_score=0.0,
            average_anomaly_score=0.0,
        )

    emitted = sum(1 for entry in entries if entry["emitted"])
    suppressed = len(entries) - emitted
    return ServiceAnalytics(
        service=service,
        events=len(entries),
        emitted=emitted,
        suppressed=suppressed,
        suppression_rate=round(suppressed / len(entries), 4),
        average_risk_score=round(sum(float(e["risk_score"]) for e in entries) / len(entries), 4),
        average_anomaly_score=round(sum(float(e["anomaly_score"]) for e in entries) / len(entries), 4),
    )


@app.get("/analytics/severity/{severity}", response_model=SeverityAnalytics)
def analytics_for_severity(severity: str):
    normalized = severity.lower()
    entries = [
        entry
        for entry in hub.recent_events
        if str(entry.get("severity", "unknown")).lower() == normalized
    ]
    emitted = sum(1 for entry in entries if entry["emitted"])
    return SeverityAnalytics(
        severity=normalized,
        events=len(entries),
        emitted=emitted,
        suppressed=len(entries) - emitted,
    )


@app.post("/ingest", response_model=InferenceResponse)
async def ingest_event(event: TelemetryEvent):
    window = hub.get_window(event.service, size=8)
    window.append(event.metric_value)
    padded = list(window)
    if len(padded) < 8:
        padded = [padded[0]] * (8 - len(padded)) + padded

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

    decision = AgentDecision(**state["decision"])
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
    hub.record_event(payload, emitted=emitted, suppression_reason=suppression_reason)
    if emitted:
        await hub.broadcast(payload)
    return response


@app.websocket("/ws/decisions")
async def ws_decisions(websocket: WebSocket):
    await websocket.accept()
    await hub.register(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        await hub.unregister(websocket)
    except Exception:
        await hub.unregister(websocket)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app.main:app", host=settings.host, port=settings.port, reload=True)
