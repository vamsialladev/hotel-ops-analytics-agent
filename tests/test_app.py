"""The Streamlit app runs for real (AppTest), with the agent replaced so no model is called."""

import pytest
from streamlit.testing.v1 import AppTest

from src import agent, config, limits, share
from src.config import ROOT


def fake_plan(question, role, context="", history=None, con=None, client=None):
    if "occupancy" in question.lower() and not context:
        return agent.Result("clarify", "Which property, and which date?", question)
    if "email" in question.lower():
        return agent.Result("refuse", "Personal data is for managers only.", question)
    res = agent.Result(
        "sql",
        "Counts bookings per property.",
        question,
        sql="SELECT property_id, COUNT(*) AS n FROM bookings GROUP BY 1 LIMIT 500",
        columns=["property_id", "n"],
        rows=[["beach-resort", 4347], ["mountain-lodge", 3182]],
        chart={"type": "bar", "x": "property_id", "y": "n"},
        usage={"input_tokens": 1, "output_tokens": 1, "calls": 2},
        seconds=1.0,
        tables=["bookings"],
        docs=["def:bookings", "table:bookings"],
        steps=[agent.Step("Plan (Claude Haiku 5.5)", {"attempt": 1}, {"action": "sql"}, 0.5)],
    )
    if history and question.lower().startswith("and"):
        res.original, res.question = question, "Bookings per property at Mountain Lodge?"
    return res


def fake_stream(res, client=None):
    res.answer = "Beach Resort had 4,347 bookings."
    yield res.answer


@pytest.fixture
def at(monkeypatch, tmp_path):
    monkeypatch.setattr(agent, "plan_and_run", fake_plan)
    monkeypatch.setattr(agent, "stream_answer", fake_stream)
    monkeypatch.setattr(config, "LOG_DIR", tmp_path)
    return AppTest.from_file(str(ROOT / "app.py"), default_timeout=120)


def test_app_renders_all_tabs_and_links(at):
    at.run()
    assert not at.exception
    assert [t.label for t in at.tabs] == ["Ask", "Daily anomalies", "How it works"]
    assert any("rate error" in w.value for w in at.warning)  # the default day shows the planted rate error
    assert any("synthetic" in c.value.lower() for c in at.sidebar.caption)


def test_a_question_shows_answer_sources_steps_and_suggestions(at):
    at.run()
    at.chat_input[0].set_value("Bookings per property?").run()
    assert not at.exception
    assert any("4,347" in m.value for m in at.markdown)
    assert any("SELECT property_id" in c.value for c in at.code)
    assert any("Sources: tables `bookings`" in c.value for c in at.caption)
    assert any(e.label.startswith("Steps (1)") for e in at.expander)
    assert any(b.label == "Split that by booking channel." for b in at.button)
    assert len(at.session_state["conversations"]) == 1


def test_follow_up_shows_how_it_was_understood_and_stays_in_one_conversation(at):
    at.run()
    at.chat_input[0].set_value("Bookings per property?").run()
    at.chat_input[0].set_value("And at Mountain Lodge?").run()
    assert any("Understood as: Bookings per property at Mountain Lodge?" in c.value for c in at.caption)
    (conv,) = at.session_state["conversations"].values()
    assert len(conv["turns"]) == 2


def test_new_conversation_and_reopen(at):
    at.run()
    at.chat_input[0].set_value("Bookings per property?").run()
    next(b for b in at.sidebar.button if b.label == "New conversation").click().run()
    assert at.session_state["current"] is None
    next(b for b in at.sidebar.button if "Bookings per property?" in b.label).click().run()
    assert at.session_state["current"] is not None
    assert any("4,347" in m.value for m in at.markdown)


def test_share_link_round_trip(at):
    at.run()
    at.chat_input[0].set_value("Bookings per property?").run()
    next(b for b in at.button if b.label == "Share this conversation").click().run()
    url = next(c.value for c in at.code if "?share=" in c.value)
    token = url.split("?share=", 1)[1]
    assert share.decode(token)[0]["q"] == "Bookings per property?"
    shared = AppTest.from_file(str(ROOT / "app.py"), default_timeout=120)
    shared.query_params["share"] = token
    shared.run()
    assert not shared.exception and "shared conversation" in shared.title[0].value
    assert not shared.chat_input  # read-only


def test_clarify_then_answer(at):
    at.run()
    at.chat_input[0].set_value("What was our occupancy?").run()
    assert any("Which property" in i.value for i in at.info)
    assert at.session_state["clarify_for"] == "What was our occupancy?"
    at.chat_input[0].set_value("Mountain Lodge, 2026-03-12").run()
    assert "clarify_for" not in at.session_state and any("SELECT" in c.value for c in at.code)


def test_refusal_is_shown(at):
    at.run()
    at.chat_input[0].set_value("List guest emails").run()
    assert any("managers only" in w.value for w in at.warning)


def test_daily_cap_stops_before_any_model_call(at, monkeypatch, tmp_path):
    monkeypatch.setattr(config, "DAILY_QUESTION_CAP", 1)
    limits.record({"input_tokens": 1, "output_tokens": 1}, log_dir=tmp_path)
    calls = []
    monkeypatch.setattr(agent, "plan_and_run", lambda *a, **k: calls.append(1))
    at.run()
    at.chat_input[0].set_value("Bookings per property?").run()
    assert not calls and any("today's limit" in i.value for i in at.info)


def test_damaged_share_link_is_explained(at):
    at.query_params["share"] = "not-a-real-link"
    at.run()
    assert any("damaged" in w.value for w in at.warning)


# ---------- shared guardrails, tracing and the Admin page (hotel-ai-platform) ----------
def ops_rows(store):
    store.flush()
    return store.requests(since="0")


def test_question_gets_a_trace_with_every_step(at, ops_log_in_tmp, monkeypatch):
    from hotelplatform import tracing

    def traced_plan(question, role, **kw):
        res = fake_plan(question, role, **kw)
        tracing.current().record("SQL guard", 2.0, verdict="passed")  # what agent._step does for each real step
        return res

    monkeypatch.setattr(agent, "plan_and_run", traced_plan)
    at.run()
    at.chat_input[0].set_value("Bookings per property?").run()
    row = ops_rows(ops_log_in_tmp)[0]
    assert row["status"] == "ok" and row["request_type"] == "question:analyst" and "table:bookings" in row["sources"]
    assert [s["name"] for s in ops_log_in_tmp.spans(row["trace_id"])] == ["guardrails.input", "SQL guard",
                                                                          "guardrails.output"]  # fmt: skip


def test_drop_table_is_blocked_before_any_model_call(at, ops_log_in_tmp, monkeypatch):
    called = []
    monkeypatch.setattr(agent, "plan_and_run", lambda *a, **k: called.append(1))
    at.run()
    at.chat_input[0].set_value("DROP TABLE guests;").run()
    assert not called and any("can't run that" in m.value for m in at.markdown)
    assert ops_rows(ops_log_in_tmp)[0]["error_type"] == "tool_misuse"


def test_error_shows_a_reference(at, ops_log_in_tmp, monkeypatch):
    def broken(*a, **k):
        raise RuntimeError("boom")

    monkeypatch.setattr(agent, "plan_and_run", broken)
    at.run()
    at.chat_input[0].set_value("Bookings per property?").run()
    row = ops_rows(ops_log_in_tmp)[0]
    assert row["status"] == "error" and any(f"Reference: {row['trace_id'][:8]}" in e.value for e in at.error)


def test_keep_awake_visit_runs_nothing(at, ops_log_in_tmp):
    at.query_params["source"] = "keepawake"
    at.run()
    assert any(c.value == "Awake." for c in at.caption) and ops_rows(ops_log_in_tmp) == []


def test_no_admin_page_without_a_password(at, monkeypatch):
    monkeypatch.delenv("ADMIN_PASSWORD", raising=False)
    at.run()
    with pytest.raises(ValueError):
        at.switch_page("views/admin.py")


def test_admin_page_locks_after_five_tries(at, monkeypatch):
    monkeypatch.setenv("ADMIN_PASSWORD", "test-only-password")
    at.run()
    at.switch_page("views/admin.py").run()
    for _ in range(5):
        at.text_input[0].input("wrong")
        at.button[0].click().run()
    assert any("Too many attempts" in e.value for e in at.error)


def test_policy_passages_from_mcp_are_shown_as_written(at, monkeypatch):
    def with_policy(question, role, context="", history=None, con=None, client=None):
        res = fake_plan(question, role, context, history, con, client)
        res.policy = [{"cite_as": "Hotel policy: Beach Resort - Property Policies > Pets", "property": "beach-resort",
                       "text": "Dogs are welcome up to 40 lbs. Pet fee is $75 per stay."}]  # fmt: skip
        return res

    monkeypatch.setattr(agent, "plan_and_run", with_policy)
    at.run()
    at.chat_input[0].set_value("Bookings at Beach Resort, and what is the pet policy?").run()
    assert not at.exception
    assert any(e.label == "Hotel policy (1 passage, via MCP)" for e in at.expander)
    assert any("Pet fee is $75 per stay." in t.value for t in at.text)
