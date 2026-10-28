"""Ops Analytics: ask the bookings database in plain English (always shown the SQL and its sources), and see the
daily anomaly check.

streamlit run app.py
"""

import sqlite3
import time
import uuid
from datetime import date
from pathlib import Path

import anthropic
import streamlit as st

from src import agent, anomaly, db, limits, requestlog, share, suggest
from src.config import DB_PATH, DEMO_VIDEO_URL, PORTFOLIO_URL, REPO_URL, ROOT

st.set_page_config(page_title="Hotel Ops Analytics", page_icon="📊", layout="wide")
EXAMPLES = [
    "What was total revenue at Beach Resort in October 2026?",
    "Which room type at Mountain Lodge earned the most revenue in 2026?",
    "What was the total amount refunded at Mountain Lodge in August 2026?",
    "What was our occupancy?",
]
REPORTS = ROOT / "eval" / "reports"
DATA_START, DATA_END = date(2025, 11, 29), date(2026, 10, 31)  # 28 days of history before the first checked day
FRIENDLY_ERROR = "That didn't work: the model didn't answer in time. Please try again in a minute."


@st.cache_resource(show_spinner="Opening the database...")
def connection():
    return db.connect(DB_PATH)


@st.cache_data(show_spinner="Checking every day of the demo year...")
def year_alerts(path: str) -> list[dict]:
    con = sqlite3.connect(f"file:{Path(path).as_posix()}?mode=ro", uri=True)
    return [vars(f) for f in anomaly.backfill(con, DATA_START, DATA_END)]


def state():
    s = st.session_state
    s.setdefault("session_id", uuid.uuid4().hex[:12])
    s.setdefault("conversations", {})  # id -> {"title", "turns"}
    s.setdefault("current", None)
    s.setdefault("asked", 0)
    s.setdefault("times", [])
    return s


def current_turns() -> list[dict]:
    s = state()
    return s.conversations.get(s.current, {}).get("turns", [])


def new_conversation():
    s = state()
    s.current = None
    s.pop("clarify_for", None)
    s.pop("share_link", None)


def show_steps(steps: list):
    for i, step in enumerate(steps, 1):
        st.markdown(f"**{i}. {step['name']}** · {step['seconds']:.2f} s")
        st.json({"input": step["input"], "result": step["result"]}, expanded=False)


def show_turn(turn: dict, live: bool = False):
    with st.chat_message("user"):
        st.markdown(turn["question"])
        if turn.get("understood_as") and turn["understood_as"] != turn["question"]:
            st.caption(f"Understood as: {turn['understood_as']}")
    with st.chat_message("assistant"):
        action = turn["action"]
        if action == "clarify":
            st.info(turn["message"], icon=":material/help:")
        elif action in ("refuse", "error"):
            st.warning(turn["message"], icon=":material/block:")
        elif not live:
            st.markdown(turn["answer"])
        if action == "sql":
            if turn.get("ungrounded"):
                st.caption(f"Check before quoting: {', '.join(turn['ungrounded'])} isn't in the query result.")
            st.caption(
                "Sources: tables "
                + ", ".join(f"`{t}`" for t in turn["tables"])
                + " · written from "
                + ", ".join(f"`{d}`" for d in turn["docs"] if d.startswith("def:"))
            )
            with st.expander("SQL and result", expanded=False):
                st.code(turn["sql"], language="sql")
                if turn["rows"]:
                    data = [dict(zip(turn["columns"], r, strict=False)) for r in turn["rows"]]
                    st.dataframe(data, hide_index=True)
                    x, y, kind = turn["chart"].get("x"), turn["chart"].get("y"), turn["chart"].get("type")
                    if kind in ("bar", "line") and x in turn["columns"] and y in turn["columns"] and len(data) > 1:
                        (st.bar_chart if kind == "bar" else st.line_chart)(data, x=x, y=y)
        if turn.get("steps"):
            with st.expander(f"Steps ({len(turn['steps'])}) · {turn['seconds']:.1f} s · {turn['calls']} model call(s)"):
                show_steps(turn["steps"])


def turn_from(res: agent.Result) -> dict:
    return {
        "question": res.original or res.question,
        "understood_as": res.question if res.original else "",
        "action": res.action,
        "message": res.message,
        "answer": res.answer,
        "sql": res.sql,
        "columns": res.columns,
        "rows": res.rows,
        "chart": res.chart,
        "tables": res.tables,
        "docs": res.docs,
        "ungrounded": res.ungrounded,
        "steps": [vars(s) for s in res.steps],
        "seconds": res.seconds,
        "calls": res.usage["calls"],
        "names": list(requestlog.names_in(res)),
    }


def answer(question: str, role: str):
    s = state()
    reason = limits.blocked(s.times, s.asked, time.time())
    if reason:
        st.info(reason, icon=":material/hourglass:")
        return
    s.asked += 1
    s.times = [t for t in s.times if time.time() - t < 60] + [time.time()]
    history = [
        {"question": t["understood_as"] or t["question"], "answer": t["answer"] or t["message"]}
        for t in current_turns()
    ]
    with st.chat_message("user"):
        st.markdown(question)
    with st.chat_message("assistant"):
        try:
            with st.status("Working on it...", expanded=False) as status:
                res = agent.plan_and_run(
                    question, role, context=s.pop("clarify_for", ""), history=history, con=connection()
                )
                for step in res.steps:
                    status.write(f"✓ {step.name}")
                status.update(label=f"Done: {len(res.steps)} steps", state="complete")
            if res.action == "sql":
                st.write_stream(agent.stream_answer(res))
        except (anthropic.APIConnectionError, anthropic.APITimeoutError, anthropic.APIStatusError):
            st.error(FRIENDLY_ERROR, icon=":material/cloud_off:")
            return
        except Exception:  # noqa: BLE001 - never show a trace to a visitor
            st.error("Something went wrong on my side. Please try a different question.", icon=":material/error:")
            return
    if res.action == "clarify":
        s.clarify_for = res.question
    limits.record(res.usage)
    try:
        requestlog.write(res, s.session_id, role)
    except OSError:
        pass  # a full or read-only disk never breaks an answer
    if s.current is None:
        s.current = uuid.uuid4().hex[:8]
        s.conversations[s.current] = {"title": (res.original or question)[:48], "turns": []}
    s.conversations[s.current]["turns"].append(turn_from(res))
    s.pop("share_link", None)
    st.rerun()


def share_box():
    turns = current_turns()
    if not turns:
        return
    if st.button("Share this conversation", icon=":material/link:"):
        names = tuple(n for t in turns for n in t.get("names", []))
        token, found = share.make_token(turns, names)
        state().share_link = {"token": token, "found": found}
    link = state().get("share_link")
    if link:
        if not link["token"]:
            st.caption("This conversation is too long to share as a link.")
            return
        st.caption("Read-only link (the conversation is inside the link; nothing is stored):")
        st.code(share.share_url(st.context.url, link["token"]), language=None, wrap_lines=True)
        if link["found"]:
            st.caption("Replaced before sharing: " + ", ".join(link["found"]) + ".")


def ask_page(role: str):
    s = state()
    st.write(
        "Ask about bookings, revenue, occupancy, refunds, activities or feedback. Answers come from a "
        "**synthetic** database for a simulated hotel group. Every answer shows its SQL, the tables it read and the "
        "definitions it was written from. Follow-ups work: try “and at Mountain Lodge?”"
    )
    turns = current_turns()
    for turn in turns:
        show_turn(turn)
    if s.get("clarify_for"):
        st.caption(f"Answering the clarifying question for: “{s.clarify_for}”")
    picked = None
    options = (
        EXAMPLES
        if not turns
        else suggest.after(turns[-1]["tables"], {t["question"] for t in turns})
        if turns[-1]["action"] == "sql"
        else []
    )
    if options:
        st.caption("Try:" if not turns else "Next questions:")
        cols = st.columns(len(options))
        for i, (col, q) in enumerate(zip(cols, options, strict=True)):
            if col.button(q, key=f"suggest-{len(turns)}-{i}", use_container_width=True):
                picked = q
    share_box()
    question = st.chat_input("Ask a question about the hotel group's data") or picked
    if question:
        answer(question, role)


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
    if st.toggle("Show every alert in the demo year", help="Checks all 337 days; takes a little while the first time."):
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
    reports = sorted(REPORTS.glob("*.md"), reverse=True)
    for i, path in enumerate(reports):
        with st.expander(path.name, expanded=i == 0):
            st.markdown(path.read_text(encoding="utf-8"))


def shared_page(token: str):
    st.title("📊 Hotel Ops Analytics · shared conversation")
    st.caption("Read-only copy. Personal data was checked and replaced before the link was made. Synthetic data.")
    turns = share.decode(token)
    if not turns:
        st.warning("This link is damaged or from a different version of the app.", icon=":material/link_off:")
    for t in turns or []:
        with st.chat_message("user"):
            st.text(t["q"])
            if t["u"] and t["u"] != t["q"]:
                st.caption(f"Understood as: {t['u']}")
        with st.chat_message("assistant"):
            st.text(t["a"])
            if t["sql"]:
                st.caption("Sources: tables " + ", ".join(t["t"]))
                st.code(t["sql"], language="sql")
    st.link_button("Ask your own question", "?", icon=":material/chat:")


def sidebar() -> str:
    s = state()
    with st.sidebar:
        role = st.radio("Demo role", agent.ROLES, help="Only the manager role may see guest names, emails and phones.")
        st.caption("Demo roles, no sign-in. Read-only database; writes are refused.")
        st.divider()
        st.button("New conversation", icon=":material/add:", on_click=new_conversation, use_container_width=True)
        if s.conversations:
            st.caption("Conversations (this browser tab)")
        for cid, conv in reversed(list(s.conversations.items())):
            label = ("▸ " if cid == s.current else "") + conv["title"]
            if st.button(label, key=f"conv-{cid}", use_container_width=True):
                s.current = cid
                s.pop("share_link", None)
                st.rerun()
        st.divider()
        if DEMO_VIDEO_URL:
            st.link_button("Watch the 90-second demo", DEMO_VIDEO_URL, icon=":material/play_circle:")
        st.link_button("About this project (GitHub)", REPO_URL, icon=":material/code:")
        st.link_button("Portfolio", PORTFOLIO_URL, icon=":material/person:")
        st.caption("Stage 8 of a simulated client engagement. Synthetic data, no real guests.")
    return role


token = st.query_params.get("share")
if token:
    shared_page(token)
    st.stop()
st.title("📊 Hotel Ops Analytics")
st.caption("Stage 8 of a simulated client engagement · synthetic data · every answer shows its SQL")
demo_role = sidebar()
ask_tab, anomaly_tab, how_tab = st.tabs(["Ask", "Daily anomalies", "How it works"])
with ask_tab:
    ask_page(demo_role)
with anomaly_tab:
    anomalies_page()
with how_tab:
    how_page()
