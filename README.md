# Sharan G S

# SentinelFlow-AIOps

Realtime agentic incident triage platform for distributed systems using **LangGraph + LangChain + FastAPI + WebSockets + PyTorch + TensorFlow**.

## Problem it solves

In production systems, infrastructure metrics spike fast and teams need immediate:
- anomaly detection,
- risk prediction,
- root-cause style triage,
- action recommendations.

This project provides a complete system workflow to ingest telemetry, score anomalies (TensorFlow), estimate escalation risk (PyTorch), and orchestrate an LLM-based response path with LangGraph/LangChain in real time.

## Architecture

1. **Ingestion API** (`/ingest`) receives telemetry events.
2. **TensorFlow model** computes anomaly score from recent metric window.
3. **PyTorch model** predicts escalation risk.
4. **LangGraph state machine** routes events and calls a LangChain LLM triage step.
5. **WebSocket stream** (`/ws/decisions`) broadcasts live decisions.
6. **Dashboard + simulator** show end-to-end real-time behavior.

## Repo structure

```
app/
  agents/langgraph_flow.py
  models/pytorch_risk.py
  models/tf_anomaly.py
  services/event_bus.py
  config.py
  main.py
  schemas.py
dashboard.py
simulator.py
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

## API sample

POST `http://127.0.0.1:8000/ingest`

```json
{
  "service": "payments",
  "metric_name": "cpu_percent",
  "metric_value": 82.4,
  "metadata": { "error_rate": 0.18 }
}
```

## Additional APIs

- `GET /system/status` -> uptime, client connections, total processed events.
- `GET /alerts/recent?limit=20&service=payments&emitted=true` -> filtered timeline.
- `GET /analytics/summary` -> global suppression and throughput metrics.
- `GET /analytics/service/{service}` -> service-specific averages and suppression.
- `GET /analytics/severity/{severity}` -> severity-level delivery metrics.
- `POST /analytics/reset` -> clears rolling analytics history/counters.

All sensitive endpoints require header `x-api-key` when `API_KEY_ENABLED=true`.

## Extra environment controls

- `RISK_HIGH_THRESHOLD`, `RISK_MEDIUM_THRESHOLD`
- `DEDUP_HIGH_COOLDOWN_SEC`, `DEDUP_MEDIUM_COOLDOWN_SEC`, `DEDUP_LOW_COOLDOWN_SEC`
- `EVENT_HISTORY_SIZE`
- `SIM_SERVICES`, `SIM_INTERVAL_SECONDS`
- `API_KEY_ENABLED`, `API_KEY`

# Sharan G S
