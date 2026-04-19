from __future__ import annotations

import json
import streamlit as st
import websocket
import threading


WS_URL = "ws://127.0.0.1:8000/ws/decisions"

st.set_page_config(page_title="Realtime Agentic Ops Dashboard", layout="wide")
st.title("Realtime Agentic Ops Dashboard")
st.caption("Live incident triage from LangGraph + LangChain + PyTorch + TensorFlow")

if "messages" not in st.session_state:
    st.session_state.messages = []
if "connected" not in st.session_state:
    st.session_state.connected = False


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
    ws = websocket.WebSocketApp(WS_URL, on_message=on_message, on_error=on_error, on_open=on_open)
    ws.run_forever()


if st.button("Connect Live Feed"):
    threading.Thread(target=run_ws, daemon=True).start()

st.write(f"Connected: `{st.session_state.connected}`")

for msg in st.session_state.messages[:20]:
    st.json(msg)
