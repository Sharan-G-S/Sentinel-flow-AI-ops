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


class InferenceResponse(BaseModel):
    event: TelemetryEvent
    anomaly_score: float
    risk_score: float
    decision: AgentDecision
    route: List[str]
    emitted: bool = True
    suppression_reason: str | None = None
