from __future__ import annotations

import asyncio
import random
from datetime import datetime, timezone
import httpx


API_URL = "http://127.0.0.1:8000/ingest"
SERVICES = ["checkout", "payments", "inventory", "auth"]


async def push_event(client: httpx.AsyncClient, service: str):
    base = {
        "checkout": 55,
        "payments": 63,
        "inventory": 48,
        "auth": 42,
    }[service]

    spike = random.choice([0, 0, 0, 15, 25])
    value = float(base + random.uniform(-7, 7) + spike)
    error_rate = max(0.0, min(0.4, (value - base) / 100 + random.uniform(0, 0.05)))

    payload = {
        "service": service,
        "metric_name": "cpu_percent",
        "metric_value": value,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "metadata": {"error_rate": round(error_rate, 4)},
    }
    r = await client.post(API_URL, json=payload, timeout=20)
    print(service, r.status_code, r.json().get("risk_score"))


async def run():
    async with httpx.AsyncClient() as client:
        while True:
            await asyncio.gather(*(push_event(client, s) for s in SERVICES))
            await asyncio.sleep(2)


if __name__ == "__main__":
    asyncio.run(run())
