"""
Prometheus-compatible metrics collector for SentinelFlow-AIOps.

Exposes a /metrics endpoint that returns plain-text exposition format
consumable by any Prometheus scraper or compatible tool (Grafana Agent,
VictoriaMetrics, etc.).
"""
from __future__ import annotations

import time
from threading import Lock
from typing import Dict


class MetricsRegistry:
    """Thread-safe in-process metrics registry."""

    def __init__(self) -> None:
        self._lock = Lock()
        self._counters: Dict[str, float] = {}
        self._gauges: Dict[str, float] = {}
        self._histograms: Dict[str, list[float]] = {}
        self._start_time: float = time.time()

    # ------------------------------------------------------------------
    # Counter helpers
    # ------------------------------------------------------------------
    def inc(self, name: str, value: float = 1.0, labels: str = "") -> None:
        key = f"{name}{{{labels}}}" if labels else name
        with self._lock:
            self._counters[key] = self._counters.get(key, 0.0) + value

    # ------------------------------------------------------------------
    # Gauge helpers
    # ------------------------------------------------------------------
    def set_gauge(self, name: str, value: float, labels: str = "") -> None:
        key = f"{name}{{{labels}}}" if labels else name
        with self._lock:
            self._gauges[key] = value

    # ------------------------------------------------------------------
    # Histogram helpers
    # ------------------------------------------------------------------
    def observe(self, name: str, value: float) -> None:
        with self._lock:
            self._histograms.setdefault(name, []).append(value)

    # ------------------------------------------------------------------
    # Exposition format
    # ------------------------------------------------------------------
    def exposition(self) -> str:
        lines: list[str] = []
        uptime = time.time() - self._start_time

        lines.append("# HELP sentinelflow_uptime_seconds Seconds since process start")
        lines.append("# TYPE sentinelflow_uptime_seconds gauge")
        lines.append(f"sentinelflow_uptime_seconds {uptime:.2f}")

        with self._lock:
            for key, value in self._counters.items():
                metric = key.split("{")[0]
                lines.append(f"# HELP {metric} Counter metric")
                lines.append(f"# TYPE {metric} counter")
                lines.append(f"{key} {value}")

            for key, value in self._gauges.items():
                metric = key.split("{")[0]
                lines.append(f"# HELP {metric} Gauge metric")
                lines.append(f"# TYPE {metric} gauge")
                lines.append(f"{key} {value}")

            for name, observations in self._histograms.items():
                if not observations:
                    continue
                count = len(observations)
                total = sum(observations)
                avg = total / count
                lines.append(f"# HELP {name}_seconds Histogram metric")
                lines.append(f"# TYPE {name}_seconds summary")
                lines.append(f'{name}_seconds{{quantile="0.5"}} {sorted(observations)[count // 2]:.6f}')
                lines.append(f'{name}_seconds{{quantile="0.95"}} {sorted(observations)[int(count * 0.95)]:.6f}')
                lines.append(f"{name}_seconds_sum {total:.6f}")
                lines.append(f"{name}_seconds_count {count}")

        return "\n".join(lines) + "\n"


# Module-level singleton
metrics = MetricsRegistry()
