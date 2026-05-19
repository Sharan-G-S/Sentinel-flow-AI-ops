# Sharan G S

# SentinelFlow-AIOps v2.2.0

Realtime agentic incident triage platform for distributed systems using **LangGraph + LangChain + FastAPI + WebSockets + PyTorch + TensorFlow**.

## Problem it solves

In production systems, infrastructure metrics spike fast and teams need immediate:
- anomaly detection,
- risk prediction,
- root-cause style triage,
- action recommendations.

This project provides a complete system workflow to ingest telemetry, score anomalies (TensorFlow), estimate escalation risk (PyTorch), and orchestrate an LLM-based response path with LangGraph/LangChain in real time.

## Architecture

1. **Ingestion API** (`/ingest`, `/ingest/batch`) receives telemetry events.
2. **TensorFlow model** computes anomaly score from recent metric window.
3. **PyTorch model** predicts escalation risk.
4. **LangGraph state machine** routes events and calls a LangChain LLM triage step.
5. **Circuit Breaker** protects LLM calls; falls back gracefully when OpenAI is unavailable.
6. **WebSocket stream** (`/ws/decisions`) broadcasts live decisions.
7. **Dashboard + simulator** show end-to-end real-time behavior.
8. **SQLite persistence** stores alert records and analytics source data across restarts.
9. **Notification integrations** send high-severity incidents to Slack/webhooks.
10. **Prometheus metrics** (`/metrics`) expose counters and latency histograms for scraping.
11. **Rate limiter** protects ingest endpoints from telemetry floods.
12. **Correlation ID tracing** propagates `X-Correlation-ID` headers end-to-end.
13. **Audit log** records every ingest, batch, reset, and alert dispatch to a JSONL file.
14. **Service health scoring** computes a 0-1 composite score per microservice.

## Repo structure

```
app/
  agents/
    langgraph_flow.py       # LangGraph state machine + LLM triage
    circuit_breaker.py      # Circuit breaker for LLM/OpenAI calls
  middleware/
    correlation.py          # X-Correlation-ID propagation middleware
    rate_limiter.py         # Sliding-window rate limiter middleware
  models/
    pytorch_risk.py         # PyTorch escalation risk model
    tf_anomaly.py           # TensorFlow anomaly detection model
  services/
    audit.py                # Append-only JSONL audit log
    event_bus.py            # WebSocket hub + dedup logic
    metrics.py              # Prometheus-compatible metrics registry
    notifier.py             # Slack / webhook notification dispatcher
    storage.py              # SQLite persistence layer
  config.py
  main.py
  schemas.py
  security.py
dashboard.py
simulator.py
Dockerfile
docker-compose.yml
CHANGELOG.md
requirements.txt
```

## Run locally

1. Create venv and install dependencies:
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   pip install -r requirements.txt
   ```

2. Setup env:
   ```bash
   cp .env.example .env
   ```
   Put your `OPENAI_API_KEY` in `.env` (optional; fallback logic works without it).

3. Start backend:
   ```bash
   uvicorn app.main:app --reload
   ```

4. Start simulator (new terminal):
   ```bash
   python simulator.py
   ```

5. Start dashboard (new terminal):
   ```bash
   streamlit run dashboard.py
   ```

## Run with Docker

```bash
docker compose up --build
```

Services exposed:

| Container | Port | Purpose |
|---|---|---|
| `sentinelflow_api` | 8000 | FastAPI backend |
| `sentinelflow_dashboard` | 8501 | Streamlit dashboard |

## API reference

### Core ingest

| Method | Path | Description |
|---|---|---|
| `POST` | `/ingest` | Ingest a single telemetry event |
| `POST` | `/ingest/batch` | Ingest up to 100 events in one call |

**Single ingest sample:**
```json
POST http://127.0.0.1:8000/ingest
{
  "service": "payments",
  "metric_name": "cpu_percent",
  "metric_value": 82.4,
  "metadata": { "error_rate": 0.18 }
}
```

**Batch ingest sample:**
```json
POST http://127.0.0.1:8000/ingest/batch
{
  "events": [
    { "service": "payments", "metric_name": "cpu_percent", "metric_value": 82.4, "metadata": {} },
    { "service": "auth",     "metric_name": "latency_ms",  "metric_value": 310.0, "metadata": {} }
  ]
}
```

### System and observability

| Method | Path | Description |
|---|---|---|
| `GET` | `/health` | Liveness probe |
| `GET` | `/health/ready` | Readiness probe (SQLite connectivity) |
| `GET` | `/version` | App name, semver, Python runtime |
| `GET` | `/metrics` | Prometheus text exposition |
| `GET` | `/system/status` | Uptime, clients, total events |
| `GET` | `/system/circuit-breaker` | LLM circuit-breaker state |

### Alerts and analytics

| Method | Path | Description |
|---|---|---|
| `GET` | `/alerts/recent` | Filtered event timeline (`limit`, `service`, `emitted`, `severity`) |
| `GET` | `/alerts/count` | Total alert count with optional filters |
| `GET` | `/alerts/export` | Download alerts as CSV |
| `GET` | `/analytics/summary` | Global suppression and throughput metrics |
| `GET` | `/analytics/service/{service}` | Per-service averages and suppression |
| `GET` | `/analytics/severity/{severity}` | Severity-level delivery metrics |
| `POST` | `/analytics/reset` | Clears rolling analytics history |

### Health scoring and audit

| Method | Path | Description |
|---|---|---|
| `GET` | `/health/service/{service}` | Composite 0-1 health score |
| `GET` | `/health/services` | Fleet-wide health scores for all services |
| `GET` | `/audit/tail` | Last N audit log entries (`n` query param) |

All sensitive endpoints require header `x-api-key` when `API_KEY_ENABLED=true`.

## Environment variables

| Variable | Default | Description |
|---|---|---|
| `OPENAI_API_KEY` | _(empty)_ | LLM key; fallback used if absent |
| `MODEL_NAME` | `gpt-4.1-mini` | OpenAI chat model |
| `API_KEY_ENABLED` | `true` | Enable API-key auth |
| `API_KEY` | _(empty)_ | Shared API key value |
| `RISK_HIGH_THRESHOLD` | `0.8` | Risk score threshold for high severity |
| `RISK_MEDIUM_THRESHOLD` | `0.5` | Risk score threshold for medium severity |
| `DEDUP_HIGH_COOLDOWN_SEC` | `12` | Suppression window for high-risk duplicates |
| `DEDUP_MEDIUM_COOLDOWN_SEC` | `25` | Suppression window for medium-risk duplicates |
| `DEDUP_LOW_COOLDOWN_SEC` | `45` | Suppression window for low-risk duplicates |
| `EVENT_HISTORY_SIZE` | `500` | In-memory rolling event buffer size |
| `SQLITE_DB_PATH` | `sentinelflow.db` | SQLite database file path |
| `SLACK_WEBHOOK_URL` | _(empty)_ | Slack incoming webhook URL |
| `ALERT_WEBHOOK_URL` | _(empty)_ | Generic alert webhook URL |
| `NOTIFY_HIGH_SEVERITY_ONLY` | `true` | Only notify on high/critical alerts |
| `AUDIT_LOG_PATH` | `audit.jsonl` | Audit log file path |
| `RATE_LIMIT_MAX_REQUESTS` | `120` | Max requests per window per client IP |
| `RATE_LIMIT_WINDOW_SEC` | `60` | Rate-limit rolling window in seconds |
| `CORS_ORIGINS` | _(empty)_ | Comma-separated browser origins |
| `APP_VERSION` | `2.2.0` | API semver exposed at `/version` |

## Sharan G S
