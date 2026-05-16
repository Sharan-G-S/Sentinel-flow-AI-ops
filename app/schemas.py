from pydantic import BaseModel, Field
from typing import Dict, Any, List, Optional
from datetime import datetime, timezone


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class TelemetryEvent(BaseModel):
    service: str = Field(..., description="Microservice name")
    metric_name: str
    metric_value: float
    timestamp: datetime = Field(default_factory=_utc_now)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class AgentDecision(BaseModel):
    severity: str
    probable_cause: str
    action: str
    confidence: float
    severity_badge: str = Field(
        default="",
        description="Emoji badge derived from severity level (🔴 critical, 🟠 high, 🟡 medium, 🟢 low)",
    )


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


class ServiceAnalytics(BaseModel):
    service: str
    events: int
    emitted: int
    suppressed: int
    suppression_rate: float
    average_risk_score: float
    average_anomaly_score: float


class SystemStatus(BaseModel):
    status: str
    uptime_seconds: int
    connected_clients: int
    total_events: int


class SeverityAnalytics(BaseModel):
    severity: str
    events: int
    emitted: int
    suppressed: int


class ResetResponse(BaseModel):
    ok: bool
    message: str


# ---------------------------------------------------------------------------
# Batch ingest
# ---------------------------------------------------------------------------
class BatchIngestRequest(BaseModel):
    events: List["TelemetryEvent"] = Field(..., min_length=1, max_length=100)


class BatchIngestResponse(BaseModel):
    accepted: int
    results: List[Dict[str, Any]]


# ---------------------------------------------------------------------------
# Service health scoring
# ---------------------------------------------------------------------------
class ServiceHealthScore(BaseModel):
    service: str
    health_score: float = Field(..., ge=0.0, le=1.0, description="1.0 = fully healthy")
    risk_trend: str
    events_last_5min: int
    suppression_rate: float
    recommendation: str


class ServiceHealthList(BaseModel):
    services: List[ServiceHealthScore]
    total: int


# ---------------------------------------------------------------------------
# Audit
# ---------------------------------------------------------------------------
class AuditEntry(BaseModel):
    _ts: Optional[str] = None
    event: str
    correlation_id: Optional[str] = None
    service: Optional[str] = None


class AuditTailResponse(BaseModel):
    entries: List[Dict[str, Any]]
    total_returned: int


# ---------------------------------------------------------------------------
# Circuit breaker
# ---------------------------------------------------------------------------
class CircuitBreakerStatus(BaseModel):
    name: str
    state: str
    failure_count: int
    failure_threshold: int
    recovery_timeout_seconds: float


class VersionInfo(BaseModel):
    name: str
    version: str
    python: str
