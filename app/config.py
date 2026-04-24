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


settings = Settings()
