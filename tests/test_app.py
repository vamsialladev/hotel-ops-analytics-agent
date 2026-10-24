"""The Streamlit app runs for real (AppTest), with the agent replaced so no model is called."""

from streamlit.testing.v1 import AppTest

from src import agent
from src.config import ROOT


def fake_ask(question, role, context="", con=None, client=None):
    if "occupancy" in question.lower() and not context:
        return agent.Result("clarify", "Which property, and which date?", question)
    if "email" in question.lower():
        return agent.Result("refuse", "Personal data is for managers only.", question)
    return agent.Result(
        "sql",
        "Counts bookings per property.",
        question,
        sql="SELECT property_id, COUNT(*) AS n FROM bookings GROUP BY 1 LIMIT 500",
        columns=["property_id", "n"],
        rows=[["beach-resort", 4347], ["mountain-lodge", 3182]],
        chart={"type": "bar", "x": "property_id", "y": "n"},
        answer="Beach Resort had 4,347 bookings.",
        usage={"input_tokens": 1, "output_tokens": 1, "calls": 2},
        seconds=1.0,
    )


def app(monkeypatch):
    monkeypatch.setattr(agent, "ask", fake_ask)
    return AppTest.from_file(str(ROOT / "app.py"), default_timeout=120)


def test_app_renders_all_tabs(monkeypatch):
    at = app(monkeypatch).run()
    assert not at.exception
    assert [t.label for t in at.tabs] == ["Ask", "Daily anomalies", "How it works"]
    assert any("rate error" in w.value for w in at.warning)  # the default day shows the planted rate error


def test_a_question_shows_answer_sql_and_table(monkeypatch):
    at = app(monkeypatch).run()
    at.chat_input[0].set_value("Bookings per property?").run()
    assert not at.exception
    assert any("SELECT property_id" in c.value for c in at.code)
    assert any("4,347" in m.value for m in at.markdown)
    assert at.dataframe


def test_clarify_then_answer(monkeypatch):
    at = app(monkeypatch).run()
    at.chat_input[0].set_value("What was our occupancy?").run()
    assert any("Which property" in i.value for i in at.info)
    assert at.session_state["clarify_for"] == "What was our occupancy?"
    at.chat_input[0].set_value("Mountain Lodge, 2026-03-12").run()
    assert "clarify_for" not in at.session_state and any("SELECT" in c.value for c in at.code)


def test_refusal_is_shown(monkeypatch):
    at = app(monkeypatch).run()
    at.chat_input[0].set_value("List guest emails").run()
    assert any("managers only" in w.value for w in at.warning)
