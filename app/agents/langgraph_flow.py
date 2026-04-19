from __future__ import annotations

from typing import TypedDict, List
from langgraph.graph import StateGraph, END
from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI
from app.config import settings


class AgentState(TypedDict):
    service: str
    metric_name: str
    metric_value: float
    anomaly_score: float
    risk_score: float
    route: List[str]
    decision: dict


def enrich_routing(state: AgentState) -> AgentState:
    route = ["ingest", "anomaly_detection", "risk_prediction"]
    if state["risk_score"] > 0.8:
        route.append("critical_path")
    elif state["risk_score"] > 0.5:
        route.append("warning_path")
    else:
        route.append("normal_path")
    state["route"] = route
    return state


def llm_decision(state: AgentState) -> AgentState:
    prompt = ChatPromptTemplate.from_messages(
        [
            (
                "system",
                "You are an SRE copilot. Return concise incident triage as: "
                "severity|probable_cause|action|confidence (0-1).",
            ),
            (
                "human",
                "Service={service}, metric={metric_name}, value={metric_value}, "
                "anomaly={anomaly_score}, risk={risk_score}",
            ),
        ]
    )

    default_decision = {
        "severity": "low",
        "probable_cause": "normal variability",
        "action": "continue monitoring",
        "confidence": 0.55,
    }

    if not settings.openai_api_key:
        state["decision"] = default_decision
        return state

    llm = ChatOpenAI(api_key=settings.openai_api_key, model=settings.model_name, temperature=0.1)
    chain = prompt | llm
    raw = chain.invoke(
        {
            "service": state["service"],
            "metric_name": state["metric_name"],
            "metric_value": state["metric_value"],
            "anomaly_score": round(state["anomaly_score"], 4),
            "risk_score": round(state["risk_score"], 4),
        }
    ).content

    try:
        severity, cause, action, confidence = [s.strip() for s in raw.split("|", 3)]
        state["decision"] = {
            "severity": severity.lower(),
            "probable_cause": cause,
            "action": action,
            "confidence": float(confidence),
        }
    except Exception:
        state["decision"] = default_decision
    return state


def build_graph():
    builder = StateGraph(AgentState)
    builder.add_node("enrich_routing", enrich_routing)
    builder.add_node("llm_decision", llm_decision)
    builder.set_entry_point("enrich_routing")
    builder.add_edge("enrich_routing", "llm_decision")
    builder.add_edge("llm_decision", END)
    return builder.compile()


graph = build_graph()
