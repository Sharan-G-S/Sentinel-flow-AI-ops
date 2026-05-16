from __future__ import annotations

import json
import os
import httpx
import streamlit as st
import websocket
import threading


WS_URL = "ws://127.0.0.1:8000/ws/decisions"
API_URL = "http://127.0.0.1:8000"
API_KEY = os.getenv("API_KEY", "")

st.set_page_config(page_title="Realtime Agentic Ops Dashboard", layout="wide")
st.title("Realtime Agentic Ops Dashboard")
st.caption("Live incident triage from LangGraph + LangChain + PyTorch + TensorFlow")

if "messages" not in st.session_state:
    st.session_state.messages = []
if "connected" not in st.session_state:
    st.session_state.connected = False


def fetch_json(path: str) -> dict:
    try:
        headers = {"x-api-key": API_KEY} if API_KEY else {}
        response = httpx.get(f"{API_URL}{path}", headers=headers, timeout=5)
        response.raise_for_status()
        return response.json()
    except Exception:
        return {}


def on_message(_, message):
    try:
        payload = json.loads(message)
        st.session_state.messages = [payload] + st.session_state.messages[:99]
    except Exception:
        pass


def on_error(_, error):
    st.session_state.connected = False
    st.error(f"WebSocket error: {error}")


def on_open(ws):
    st.session_state.connected = True
    ws.send("subscribe")


def run_ws():
    headers = [f"x-api-key: {API_KEY}"] if API_KEY else None
    ws = websocket.WebSocketApp(WS_URL, header=headers, on_message=on_message, on_error=on_error, on_open=on_open)
    ws.run_forever()


if st.button("Connect Live Feed"):
    threading.Thread(target=run_ws, daemon=True).start()

st.write(f"Connected: `{st.session_state.connected}`")

summary = fetch_json("/analytics/summary")
c1, c2, c3 = st.columns(3)
c1.metric("Total Events", summary.get("total_events", 0))
c2.metric("Suppression Rate", f"{summary.get('suppression_rate', 0.0) * 100:.1f}%")
c3.metric("Active Services", summary.get("active_services", 0))

system_status = fetch_json("/system/status")
if system_status:
    st.caption(
        f"Uptime: {system_status.get('uptime_seconds', 0)}s | "
        f"Connected clients: {system_status.get('connected_clients', 0)}"
    )

cb_status = fetch_json("/system/circuit-breaker")
if cb_status:
    cb_col1, cb_col2 = st.columns(2)
    cb_col1.metric("Circuit Breaker", cb_status.get("state", "unknown").upper())
    cb_col2.metric("LLM Failures", cb_status.get("failure_count", 0))

service_input = st.text_input("Service drilldown", value="payments")
health_data = fetch_json(f"/health/service/{service_input}")
if health_data:
    h1, h2, h3 = st.columns(3)
    h1.metric("Health Score", f"{health_data.get('health_score', 0):.2f}")
    h2.metric("Risk Trend", health_data.get("risk_trend", "n/a"))
    h3.caption(health_data.get("recommendation", ""))
service_analytics = fetch_json(f"/analytics/service/{service_input}")
if service_analytics:
    st.caption(
        f"Service `{service_input}` -> events={service_analytics.get('events', 0)}, "
        f"avg_risk={service_analytics.get('average_risk_score', 0.0):.3f}, "
        f"avg_anomaly={service_analytics.get('average_anomaly_score', 0.0):.3f}"
    )

severity_filter = st.selectbox("Severity filter", options=["all", "critical", "high", "medium", "low"])
if st.button("Refresh Dashboard"):
    st.rerun()
for msg in st.session_state.messages[:30]:
    current_severity = str(msg.get("decision", {}).get("severity", "unknown")).lower()
    if severity_filter != "all" and current_severity != severity_filter:
        continue

    explainability = msg.get("explainability", {})
    if explainability:
        st.markdown(
            f"**{msg['event']['service']}** | severity=`{current_severity}` | risk=`{msg.get('risk_score', 0):.3f}` | "
            f"band=`{explainability.get('risk_band', 'n/a')}` | trend=`{explainability.get('trend', 'n/a')}`"
        )
        st.caption(f"Top signals: {', '.join(explainability.get('top_signals', []))}")
    st.json(msg)
