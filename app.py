"""Ops Analytics: ask the bookings database in plain English (always shown the SQL), and see the daily anomaly check.

streamlit run app.py
"""

import sqlite3
from datetime import date
from pathlib import Path

import streamlit as st

from src import agent, anomaly, db
from src.config import DB_PATH, MAX_QUESTIONS_PER_SESSION, ROOT

st.set_page_config(page_title="Hotel Ops Analytics", page_icon="📊", layout="wide")
EXAMPLES = [
    "What was total revenue at Beach Resort in October 2026?",
    "Which room type at Mountain Lodge earned the most revenue in 2026?",
    "What was the total amount refunded at Mountain Lodge in August 2026?",
    "What was our occupancy?",
]
REPORTS = ROOT / "eval" / "reports"
DATA_START, DATA_END = date(2025, 11, 29), date(2026, 10, 31)  # 28 days of history before the first checked day


@st.cache_resource
def connection():
    return db.connect(DB_PATH)


@st.cache_data(show_spinner="Checking every day of the demo year...")
def year_alerts(path: str) -> list[dict]:
    con = sqlite3.connect(f"file:{Path(path).as_posix()}?mode=ro", uri=True)
    return [vars(f) for f in anomaly.backfill(con, DATA_START, DATA_END)]


def show_result(res: agent.Result):
    if res.action == "clarify":
        st.info(res.message, icon=":material/help:")
        return
    if res.action in ("refuse", "error"):
        st.warning(res.message, icon=":material/block:")
        if res.sql:
            st.code(res.sql, language="sql")
        return
    st.markdown(res.answer)
    if res.ungrounded:
        st.caption(f"Check before quoting: {', '.join(res.ungrounded)} isn't in the query result.")
    st.code(res.sql, language="sql")
    if res.rows:
        data = [dict(zip(res.columns, r, strict=False)) for r in res.rows]
        st.dataframe(data, hide_index=True)
        x, y, kind = res.chart.get("x"), res.chart.get("y"), res.chart.get("type")
        if kind in ("bar", "line") and x in res.columns and y in res.columns and len(res.rows) > 1:
            (st.bar_chart if kind == "bar" else st.line_chart)(data, x=x, y=y)
    st.caption(f"{res.seconds:.1f} s · {res.usage['calls']} model call(s) · {res.message}")


def ask_page(role: str):
    st.write(
        "Ask about bookings, revenue, occupancy, refunds, activities or feedback. Answers come from a "
        "**synthetic** database for a simulated hotel group, and every answer shows its SQL."
    )
    pending = st.session_state.get("clarify_for")
    if pending:
        st.caption(f"Answering the clarifying question for: “{pending}”")
    cols = st.columns(len(EXAMPLES))
    for col, example in zip(cols, EXAMPLES, strict=True):
        if col.button(example, use_container_width=True):
            st.session_state.question = example
            st.session_state.pop("clarify_for", None)
    question = st.chat_input("Ask a question about the hotel group's data")
    question = question or st.session_state.pop("question", None)
    if not question:
        return
    asked = st.session_state.get("asked", 0)
    if asked >= MAX_QUESTIONS_PER_SESSION:
        st.info(f"This demo answers {MAX_QUESTIONS_PER_SESSION} questions per session. Thanks for trying it!")
        return
    st.session_state.asked = asked + 1
    with st.chat_message("user"):
        st.markdown(question)
    with st.chat_message("assistant"):
        try:
            res = agent.ask(question, role, context=st.session_state.pop("clarify_for", ""), con=connection())
        except Exception:  # noqa: BLE001 - never show a trace to a visitor
            st.error("That didn't work. The model may be unavailable; please try again in a minute.")
            return
        if res.action == "clarify":
            st.session_state.clarify_for = question
        show_result(res)


def anomalies_page():
    st.write(
        "The daily check runs five rules (occupancy drop, cancellation spike, refund spike, activity no-shows, "
        "rate error) against the previous 28 days. A scheduled GitHub Action posts the result to Slack."
    )
    day = st.date_input("Day to check", value=date(2026, 9, 14), min_value=DATA_START, max_value=DATA_END)
    findings = anomaly.detect(sqlite3.connect(f"file:{DB_PATH.as_posix()}?mode=ro", uri=True), day)
    if not findings:
        st.success(f"No anomalies on {day.isoformat()}.", icon=":material/check_circle:")
    for f in findings:
        st.warning(f"**{f.kind.replace('_', ' ')}**: {f.message}", icon=":material/warning:")
        if f.series:
            st.line_chart({"last 14 days": f.series})
        st.code(f.sql.strip(), language="sql")
    with st.expander("Every alert in the demo year"):
        alerts = year_alerts(str(DB_PATH))
        st.dataframe(
            [{k: a[k] for k in ("day", "kind", "property", "entity", "message")} for a in alerts], hide_index=True
        )
        st.caption(
            "Five anomalies were planted in this data; the README shows which alerts are real and which is a "
            "false alarm."
        )


def how_page():
    st.write("Measured results, read from the saved eval reports in this repository.")
    for name in ("sql-2026-10-24-dev.md", "sql-2026-10-24-heldout.md", "anomaly-2026-10-24.md"):
        path = REPORTS / name
        if path.exists():
            with st.expander(name, expanded=name.endswith("dev.md")):
                st.markdown(path.read_text(encoding="utf-8"))


st.title("📊 Hotel Ops Analytics")
st.caption("Stage 8 of a simulated client engagement · synthetic data · every answer shows its SQL")
with st.sidebar:
    role = st.radio("Demo role", agent.ROLES, help="Only the manager role may see guest names, emails and phones.")
    st.caption("Demo roles, no sign-in. Read-only database; writes are refused.")
ask_tab, anomaly_tab, how_tab = st.tabs(["Ask", "Daily anomalies", "How it works"])
with ask_tab:
    ask_page(role)
with anomaly_tab:
    anomalies_page()
with how_tab:
    how_page()
