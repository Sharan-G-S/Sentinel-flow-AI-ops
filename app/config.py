from pydantic import BaseModel
from dotenv import load_dotenv
import os

load_dotenv()


class Settings(BaseModel):
    openai_api_key: str = os.getenv("OPENAI_API_KEY", "")
    model_name: str = os.getenv("MODEL_NAME", "gpt-4.1-mini")
    host: str = os.getenv("HOST", "0.0.0.0")
    port: int = int(os.getenv("PORT", "8000"))
    risk_high_threshold: float = float(os.getenv("RISK_HIGH_THRESHOLD", "0.8"))
    risk_medium_threshold: float = float(os.getenv("RISK_MEDIUM_THRESHOLD", "0.5"))
    dedup_high_cooldown_sec: int = int(os.getenv("DEDUP_HIGH_COOLDOWN_SEC", "12"))
    dedup_medium_cooldown_sec: int = int(os.getenv("DEDUP_MEDIUM_COOLDOWN_SEC", "25"))
    dedup_low_cooldown_sec: int = int(os.getenv("DEDUP_LOW_COOLDOWN_SEC", "45"))
    event_history_size: int = int(os.getenv("EVENT_HISTORY_SIZE", "500"))
    api_key_enabled: bool = os.getenv("API_KEY_ENABLED", "true").lower() == "true"
    api_key: str = os.getenv("API_KEY", "")
    sqlite_db_path: str = os.getenv("SQLITE_DB_PATH", "sentinelflow.db")
    slack_webhook_url: str = os.getenv("SLACK_WEBHOOK_URL", "")
    alert_webhook_url: str = os.getenv("ALERT_WEBHOOK_URL", "")
    notify_high_severity_only: bool = os.getenv("NOTIFY_HIGH_SEVERITY_ONLY", "true").lower() == "true"


settings = Settings()
