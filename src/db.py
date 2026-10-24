"""Read-only access to the SQLite database, with a time limit per query."""

import sqlite3
import time
from pathlib import Path

from src.config import DB_PATH, QUERY_TIMEOUT_S


class QueryTimeout(RuntimeError):
    pass


def connect(path: Path = DB_PATH) -> sqlite3.Connection:
    """Opened read-only at the file level (mode=ro) and at the connection level (query_only)."""
    con = sqlite3.connect(f"file:{Path(path).as_posix()}?mode=ro", uri=True, check_same_thread=False)
    con.execute("PRAGMA query_only = ON")
    return con


def run(con: sqlite3.Connection, sql: str, timeout_s: float = QUERY_TIMEOUT_S) -> tuple[list[str], list[tuple]]:
    deadline = time.monotonic() + timeout_s
    con.set_progress_handler(lambda: 1 if time.monotonic() > deadline else 0, 10_000)
    try:
        cur = con.execute(sql)
        rows = cur.fetchall()
    except sqlite3.OperationalError as exc:
        if "interrupted" in str(exc):
            raise QueryTimeout(f"query took longer than {timeout_s:.0f} s") from exc
        raise
    finally:
        con.set_progress_handler(None, 0)
    return [d[0] for d in cur.description or []], rows
