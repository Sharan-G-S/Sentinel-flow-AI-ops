from __future__ import annotations

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from app.schemas import TelemetryEvent, InferenceResponse, AgentDecision
from app.models.tf_anomaly import TensorFlowAnomalyDetector
from app.models.pytorch_risk import PyTorchRiskModel
from app.services.event_bus import hub
from app.agents.langgraph_flow import graph
from app.config import settings


app = FastAPI(title="Realtime Agentic Ops")
anomaly_model = TensorFlowAnomalyDetector(window_size=8)
risk_model = PyTorchRiskModel()


@app.get("/health")
def health():
    return {"status": "ok"}


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
        route=state["route"],
    )
    payload = response.model_dump(mode="json")
    emitted, suppression_reason = hub.should_emit(payload)
    response.emitted = emitted
    response.suppression_reason = suppression_reason
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
