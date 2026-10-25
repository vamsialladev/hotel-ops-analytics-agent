"""One JSON line per question, with personal data removed BEFORE it is written (src/pii.py).

Recorded: time, anonymous session ID, role, the question as typed and as understood, action, SQL, source tables,
retrieved docs, row count, flagged numbers, timing, tokens and cost. Never recorded: the result rows. Guest names
returned to a manager are also masked wherever they appear in the answer. Files live under LOG_DIR (git-ignored).
"""

import json
import threading
from datetime import UTC, date, datetime
from pathlib import Path

from src import config, limits
from src.pii import scrub

_LOCK = threading.Lock()


def names_in(result) -> tuple[str, ...]:
    if "full_name" not in result.columns:
        return ()
    i = result.columns.index("full_name")
    return tuple(str(r[i]) for r in result.rows[:500] if r[i])


def record(result, session_id: str, role: str) -> dict:
    return {
        "ts": datetime.now(UTC).isoformat(timespec="seconds"),
        "session_id": session_id,
        "role": role,
        "question": result.original or result.question,
        "understood_as": result.question,
        "action": result.action,
        "message": result.message,
        "sql": result.sql,
        "tables": result.tables,
        "docs": result.docs,
        "rows_returned": len(result.rows),
        "answer": result.answer,
        "ungrounded": result.ungrounded,
        "rejected": result.rejected,
        "seconds": round(result.seconds, 3),
        "tokens_in": result.usage["input_tokens"],
        "tokens_out": result.usage["output_tokens"],
        "cost_usd": round(limits.cost_usd(result.usage), 6),
    }


def write(result, session_id: str, role: str, log_dir: Path | None = None) -> dict:
    rec = record(result, session_id, role)
    clean = scrub(rec, names_in(result))
    path = Path(log_dir or config.LOG_DIR) / f"requests-{date.today().isoformat()}.jsonl"
    with _LOCK:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(clean, ensure_ascii=False) + "\n")
    return clean
