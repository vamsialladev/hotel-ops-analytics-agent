"""Settings from environment variables (README configuration table). Secrets come from .env or the host's secrets."""

import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")


def _float(name: str, default: str) -> float:
    return float(os.getenv(name) or default)


DB_PATH = Path(os.getenv("DB_PATH", ROOT / "data" / "hotel.db"))
LOG_DIR = Path(os.getenv("LOG_DIR", ROOT / "logs"))
LLM_MODEL = os.getenv("LLM_MODEL", "claude-haiku-5-5")
LLM_EFFORT = os.getenv("LLM_EFFORT", "low")
LLM_MAX_TOKENS = int(os.getenv("LLM_MAX_TOKENS", "2000"))
LLM_TIMEOUT_S = float(os.getenv("LLM_TIMEOUT_S", "30"))
QUERY_TIMEOUT_S = float(os.getenv("QUERY_TIMEOUT_S", "3"))
MAX_QUESTIONS_PER_SESSION = int(os.getenv("MAX_QUESTIONS_PER_SESSION", "20"))
RATE_LIMIT_PER_MINUTE = int(os.getenv("RATE_LIMIT_PER_MINUTE", "6"))
DAILY_QUESTION_CAP = int(os.getenv("DAILY_QUESTION_CAP", "300"))
DAILY_COST_CAP_USD = _float("DAILY_COST_CAP_USD", "1.00")
# Used for the app's daily cost cap. Defaults are Claude Haiku 5.5's list price (USD per million tokens, 2026-10);
# the eval takes prices as flags instead and never reads these.
PRICE_IN_PER_M = _float("PRICE_IN_PER_M", "0.10")
PRICE_OUT_PER_M = _float("PRICE_OUT_PER_M", "0.50")
DEMO_VIDEO_URL = os.getenv("DEMO_VIDEO_URL", "")
REPO_URL = "https://github.com/vamsialladev/hotel-ops-analytics-agent"
PORTFOLIO_URL = "https://vamsialla.com"
SLACK_WEBHOOK_URL_ENV = "SLACK_WEBHOOK_URL"  # read at call time; never logged
