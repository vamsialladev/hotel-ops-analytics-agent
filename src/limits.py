"""Spending and abuse limits for the public demo. Checked before any model call; nothing is sent when one is hit.

- per session: MAX_QUESTIONS_PER_SESSION questions, and RATE_LIMIT_PER_MINUTE in any 60 seconds
- per day, across every visitor: DAILY_QUESTION_CAP questions and DAILY_COST_CAP_USD of model spend

The daily counters live in one small JSON file per day under LOG_DIR (git-ignored), written atomically. On
Streamlit Cloud the disk resets when the app restarts, so the daily counters reset too: the Anthropic Console's
monthly spend limit stays the backstop (README, Deploy).
"""

import json
import os
import threading
from datetime import date
from pathlib import Path

from src import config

_LOCK = threading.Lock()


def cost_usd(usage: dict, price_in: float | None = None, price_out: float | None = None) -> float:
    price_in = config.PRICE_IN_PER_M if price_in is None else price_in
    price_out = config.PRICE_OUT_PER_M if price_out is None else price_out
    return (usage.get("input_tokens", 0) * price_in + usage.get("output_tokens", 0) * price_out) / 1e6


def _path(day: date, log_dir: Path | None = None) -> Path:
    return Path(log_dir or config.LOG_DIR) / f"usage-{day.isoformat()}.json"


def today_totals(day: date | None = None, log_dir: Path | None = None) -> dict:
    path = _path(day or date.today(), log_dir)
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"questions": 0, "cost_usd": 0.0}


def blocked(session_times: list[float], asked: int, now: float, day: date | None = None, log_dir=None) -> str | None:
    """A friendly reason the question can't be answered right now, or None."""
    if asked >= config.MAX_QUESTIONS_PER_SESSION:
        return f"This demo answers {config.MAX_QUESTIONS_PER_SESSION} questions per visit. Thanks for trying it!"
    if sum(1 for t in session_times if now - t < 60) >= config.RATE_LIMIT_PER_MINUTE:
        return "That's a lot of questions in a minute. Give it a few seconds and try again."
    totals = today_totals(day, log_dir)
    if totals["questions"] >= config.DAILY_QUESTION_CAP or totals["cost_usd"] >= config.DAILY_COST_CAP_USD:
        return "The demo has reached today's limit for questions. It resets tomorrow; the README shows how to run it."
    return None


def record(usage: dict, day: date | None = None, log_dir: Path | None = None) -> dict:
    """Add one question and its cost to today's totals."""
    path = _path(day or date.today(), log_dir)
    with _LOCK:
        totals = today_totals(day, log_dir)
        totals["questions"] += 1
        totals["cost_usd"] = round(totals["cost_usd"] + cost_usd(usage), 6)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(totals), encoding="utf-8")
        os.replace(tmp, path)
    return totals
