"""Settings from environment variables (README configuration table). Secrets come from .env or the host's secrets."""

import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

DB_PATH = Path(os.getenv("DB_PATH", ROOT / "data" / "hotel.db"))
LLM_MODEL = os.getenv("LLM_MODEL", "claude-haiku-5-5")
LLM_EFFORT = os.getenv("LLM_EFFORT", "low")
LLM_MAX_TOKENS = int(os.getenv("LLM_MAX_TOKENS", "2000"))
LLM_TIMEOUT_S = float(os.getenv("LLM_TIMEOUT_S", "30"))
QUERY_TIMEOUT_S = float(os.getenv("QUERY_TIMEOUT_S", "3"))
MAX_QUESTIONS_PER_SESSION = int(os.getenv("MAX_QUESTIONS_PER_SESSION", "20"))
PRICE_IN_PER_M = float(os.getenv("PRICE_IN_PER_M")) if os.getenv("PRICE_IN_PER_M") else None
PRICE_OUT_PER_M = float(os.getenv("PRICE_OUT_PER_M")) if os.getenv("PRICE_OUT_PER_M") else None
SLACK_WEBHOOK_URL_ENV = "SLACK_WEBHOOK_URL"  # read at call time; never logged
