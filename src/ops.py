"""Shared guardrails, request tracing and the cross-app ops log (hotel-ai-platform), wired for the analytics agent.

    with ops.start(session_id) as trace:             one trace per question; the reference shows on errors
        v = ops.check_question(text)                 before the rewrite and the plan
        ...agent.plan_and_run(): every step (rewrite, schema retrieval, plan, SQL guard, query, answer) is a span...
        o = ops.check_answer(answer, result)         after the model, against the query's rows
        ops.finish(trace, result, status)            one ops_request_log row + the spans, PII removed first

The SQL guard (sqlglot allowlist, one SELECT, no PII columns unless manager) and the read-only connection stay the
real defence for the database; the guardrails stop obvious attacks before a model call is spent on them.
"""

import json
import os
from functools import lru_cache

from hotelplatform import guardrails, jsonlog, oplog, tracing, version

from src import limits
from src.config import DAILY_COST_CAP_USD, LLM_MODEL, LOG_DIR, ROOT

APP = "hotel-ops-analytics-agent"
APP_VERSION = "1.2.0"
MONTHLY_COST_CAP_USD = float(os.getenv("MONTHLY_COST_CAP_USD", "10.00"))

INPUT_POLICY = guardrails.InputPolicy(max_chars=1000, languages=("en", "es"))
# Numbers have this app's own check (every number in an answer must come from the rows) and there are no promises
# to make: the agent only reads. Contact details are checked against the rows, so a manager's own query that returns
# a phone number isn't a leak.
OUTPUT_POLICY = guardrails.OutputPolicy(require_citation=False, numbers="off", promises="off", pii_leak="redact")


@lru_cache(maxsize=1)
def store() -> oplog.OpsStore:
    """One per process; nothing connects until the first row (the keep-awake visit never gets that far)."""
    url = os.getenv("DATABASE_URL", "").strip().replace("postgres://", "postgresql://", 1)
    return oplog.OpsStore(APP, url=url, log_dir=LOG_DIR / "ops", retention_days=30)


@lru_cache(maxsize=1)
def running_version() -> str:
    return version.version_string(APP_VERSION, ROOT)


def configure_logs() -> None:
    jsonlog.configure(APP, running_version())


def start(session_id: str | None):
    return tracing.new_trace(APP, session_id=session_id)


def check_question(text: str) -> guardrails.Verdict:
    return guardrails.check_input(text, INPUT_POLICY)


def check_answer(answer: str, rows: list, question: str) -> guardrails.Verdict:
    sources = [json.dumps(rows, default=str)[:20000]] if rows else []
    return guardrails.check_output(answer, OUTPUT_POLICY, sources=sources, input_text=question)


def safety_flags(trace) -> list[str]:
    flags = set()
    for span in trace.spans if trace is not None else []:
        if span.name.startswith("guardrails."):
            stage = span.name.split(".", 1)[1]
            flags.update(span.attributes.get("flags") or [])
            flags.update(f"{stage}:{r}" for r in span.attributes.get("reasons") or [])
        if span.name == "SQL guard" and span.status == "blocked":
            flags.add("sql_guard:rejected")
    return sorted(flags)


def status_of(result) -> str:
    """ok | refused | error, from the agent's result (blocked and capped are decided by the page)."""
    action = getattr(result, "action", "error")
    return {"sql": "ok", "clarify": "ok", "refuse": "refused"}.get(action, "error")


def finish(trace, result=None, role: str = "analyst", status: str | None = None, error_type: str | None = None):
    """Write the ops row for one question. Never raises, never blocks."""
    if trace is None:
        return False
    try:
        usage = getattr(result, "usage", None) or {"input_tokens": 0, "output_tokens": 0}
        status = status or status_of(result)
        row = oplog.request_row(
            trace,
            request_type=f"question:{role}",
            status=status,
            latency_ms=round(getattr(result, "seconds", 0.0) * 1000, 1) or trace.elapsed_ms(),
            error_type=error_type or (getattr(result, "message", None) if status == "error" else None),
            tokens_in=usage.get("input_tokens", 0),
            tokens_out=usage.get("output_tokens", 0),
            cost_usd=limits.cost_usd(usage),
            model=LLM_MODEL if usage.get("calls") else None,
            tool_calls=[{"sql": getattr(result, "sql", "")}] if getattr(result, "sql", "") else [],
            sources=list(getattr(result, "docs", [])) + [f"table:{t}" for t in getattr(result, "tables", [])],
            safety_flags=safety_flags(trace),
            version=running_version(),
            data={
                "role": role,
                "question": getattr(result, "question", None),
                "answer": getattr(result, "answer", None) or getattr(result, "message", None),
                "rows": len(getattr(result, "rows", []) or []),
            },  # fmt: skip
        )
        if status == "capped":
            jsonlog.cap_hit(error_type or "cap", trace_id=trace.trace_id)
        return store().submit(trace, row)
    except Exception:
        return False


def dependencies() -> dict[str, str]:
    return {
        "anthropic": "configured" if os.getenv("ANTHROPIC_API_KEY") else "missing key",
        "database": "SQLite, read-only (synthetic hotel data)",
        "ops log": store().health()["status"],
        "model": LLM_MODEL,
    }


def caps() -> dict[str, float]:
    return {"cost_cap_day": DAILY_COST_CAP_USD, "cost_cap_month": MONTHLY_COST_CAP_USD}
