from pydantic import BaseModel, Field
from typing import Dict, Any, List
from datetime import datetime


class TelemetryEvent(BaseModel):
    service: str = Field(..., description="Microservice name")
    metric_name: str
    metric_value: float
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class AgentDecision(BaseModel):
    severity: str
    probable_cause: str
    action: str
    confidence: float


class Explainability(BaseModel):
    risk_band: str
    trend: str
    top_signals: List[str]
    contributing_factors: Dict[str, float]


class InferenceResponse(BaseModel):
    event: TelemetryEvent
    anomaly_score: float
    risk_score: float
    decision: AgentDecision
    explainability: Explainability
    route: List[str]
    emitted: bool = True
    suppression_reason: str | None = None


class EventRecord(BaseModel):
    recorded_at: str
    service: str
    metric_name: str
    metric_value: float
    risk_score: float
    anomaly_score: float
    severity: str
    emitted: bool
    suppression_reason: str | None = None


class AnalyticsSummary(BaseModel):
    total_events: int
    emitted_events: int
    suppressed_events: int
    suppression_rate: float
    active_services: int
