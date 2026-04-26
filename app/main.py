from __future__ import annotations

import logging
from datetime import datetime, timezone
from fastapi import Depends, FastAPI, WebSocket, WebSocketDisconnect, Query, status
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
)
from app.models.tf_anomaly import TensorFlowAnomalyDetector
from app.models.pytorch_risk import PyTorchRiskModel
from app.services.event_bus import hub
from app.services.storage import storage
from app.services.notifier import notifier
from app.agents.langgraph_flow import graph
from app.config import settings
from app.security import require_api_key


app = FastAPI(title="Realtime Agentic Ops")
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


@app.get("/health")
def health():
    return {
        "status": "ok",
        "service": "sentinelflow-aiops",
        "utc_time": datetime.now(timezone.utc).isoformat(),
    }


@app.get("/system/status", response_model=SystemStatus)
def system_status(_: None = Depends(require_api_key)):
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
    _: None = Depends(require_api_key),
):
    return storage.list_recent_events(limit=limit, service=service, emitted=emitted)


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
def reset_analytics(_: None = Depends(require_api_key)):
    hub.reset_analytics()
    storage.reset()
    return ResetResponse(ok=True, message="analytics counters and history reset")


@app.post("/ingest", response_model=InferenceResponse)
async def ingest_event(event: TelemetryEvent, _: None = Depends(require_api_key)):
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
    event_record = hub.record_event(payload, emitted=emitted, suppression_reason=suppression_reason)
    storage.insert_event(event_record)
    if emitted:
        await hub.broadcast(payload)
        try:
            await notifier.notify(payload)
        except Exception as exc:
            logger.warning("failed to dispatch incident notification: %s", exc)
    return response


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
