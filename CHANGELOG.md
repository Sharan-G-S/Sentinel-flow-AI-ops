# Changelog

All notable changes to **SentinelFlow-AIOps** are documented here.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

---

## [Unreleased]

## [2.0.0] – 2026-04-27

### Added
- **Prometheus metrics endpoint** (`GET /metrics`) — exposes counters and latency
  histograms in Prometheus text exposition format for scraping by Grafana Agent,
  VictoriaMetrics, or any compatible collector.
- **Sliding-window rate limiter** (`app/middleware/rate_limiter.py`) — protects
  `/ingest` and `/ingest/batch` from telemetry floods; configurable via
  `RATE_LIMIT_MAX_REQUESTS` and `RATE_LIMIT_WINDOW_SEC` env vars.
- **Correlation ID tracing** (`app/middleware/correlation.py`) — reads or generates
  an `X-Correlation-ID` header on every request and propagates it through the
  response, WebSocket events, and audit entries for end-to-end trace stitching.
- **Severity badge** field (`AgentDecision.severity_badge`) — emoji shorthand
  (🔴 critical / 🟠 high / 🟡 medium / 🟢 low) appended to every triage decision.
- **Batch ingest endpoint** (`POST /ingest/batch`) — accepts up to 100 telemetry
  events per call, runs anomaly + risk scoring for each, and returns aggregated
  results without LLM overhead.
- **Service health scoring** (`GET /health/service/{service}`) — computes a
  composite 0–1 health score derived from average risk, suppression rate, and
  event volume with a plain-language recommendation.
- **Circuit breaker** (`app/agents/circuit_breaker.py`) — wraps all LangChain/
  OpenAI calls; opens after 3 consecutive failures and probes again after a 30 s
  cooldown.  Status visible at `GET /system/circuit-breaker`.
- **Audit log service** (`app/services/audit.py`) — append-only JSONL file
  records every ingest, batch, analytics reset, alert dispatch, and WebSocket
  connect/disconnect.  Tail available at `GET /audit/tail`.
- **Docker Compose + Dockerfile** — full-stack `docker-compose.yml` orchestrates
  API, simulator, and Streamlit dashboard containers with health-check gating.

### Changed
- `app/main.py` — registered `CorrelationIDMiddleware` and `SlidingWindowRateLimiter`;
  rewired `/ingest` to emit Prometheus metrics and audit entries.
- `app/schemas.py` — added `BatchIngestRequest`, `BatchIngestResponse`,
  `ServiceHealthScore`, `AuditTailResponse`, `CircuitBreakerStatus`.
- FastAPI app title updated to `SentinelFlow-AIOps` and bumped version to `2.0.0`.
- `GET /analytics/reset` now records an audit entry.

---

## [1.0.0] – 2026-04-01

### Added
- Initial release: TensorFlow anomaly detection, PyTorch risk model, LangGraph
  triage agent, WebSocket broadcast, SQLite persistence, Slack/webhook notifier,
  Streamlit dashboard, and telemetry simulator.
