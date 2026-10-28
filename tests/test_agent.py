"""The agent loop with the model replaced: SQL path, guard retry, clarify, refuse, grounding, steps, follow-ups,
streaming (no API calls)."""

import pytest

from src import agent, db
from tests.fakes import FakeClient, plan

BOOKINGS_SQL = "SELECT property_id, COUNT(*) AS n FROM bookings GROUP BY property_id"


def test_sql_path_runs_the_guarded_query_and_answers_from_the_rows():
    client = FakeClient(plan(sql=BOOKINGS_SQL, chart="bar", x="property_id", y="n"))
    res = agent.ask("Bookings per property?", "analyst", con=db.connect(), client=client)
    assert res.action == "sql" and res.sql.endswith("LIMIT 500")
    assert res.rows == [["beach-resort", 4347], ["mountain-lodge", 3182]] and res.ungrounded == []
    assert res.answer.startswith("Beach Resort had 4,347")
    assert res.usage == {"input_tokens": 200, "output_tokens": 40, "calls": 2}
    system = client.requests[0]["system"]
    assert "role: analyst" in system and "refuse any request for full_name" in system
    assert client.requests[0]["output_config"]["format"]["type"] == "json_schema"
    assert res.tables == ["bookings"] and "table:bookings" in res.docs


def test_the_plan_prompt_holds_only_the_retrieved_docs():
    client = FakeClient(plan(action="refuse"))
    agent.ask("What was the no-show rate for the spa?", "analyst", con=db.connect(), client=client)
    system = client.requests[0]["system"]
    assert "[def:no_show_rate]" in system and "[table:activity_bookings]" in system
    assert "[def:occupancy]" not in system


def test_every_step_is_recorded_with_input_and_result():
    client = FakeClient(plan(sql=BOOKINGS_SQL))
    res = agent.ask("Bookings per property?", "analyst", con=db.connect(), client=client)
    names = [s.name for s in res.steps]
    assert names == [
        "Retrieve schema docs",
        "Plan (Claude Haiku 5.5)",
        "SQL guard",
        "Run query (read-only)",
        "Answer (streamed)",
    ]
    guard = res.steps[2]
    assert guard.input["sql"] == BOOKINGS_SQL and guard.result == {"verdict": "passed", "tables": ["bookings"]}
    assert res.steps[3].result["rows"] == 2


def test_the_answer_streams_in_chunks():
    client = FakeClient(plan(sql=BOOKINGS_SQL))
    res = agent.plan_and_run("Bookings per property?", "analyst", con=db.connect(), client=client)
    chunks = list(agent.stream_answer(res, client))
    assert len(chunks) == 2 and res.answer == "".join(chunks).strip()


def test_a_rejected_query_is_sent_back_once_then_refused():
    client = FakeClient(plan(sql="DELETE FROM bookings"), plan(sql="SELECT email FROM guests"))
    res = agent.ask("Wipe it", "analyst", con=db.connect(), client=client)
    assert res.action == "refuse" and res.attempts == 2 and len(res.rejected) == 2
    assert "was rejected" in client.requests[1]["messages"][0]["content"]
    assert [s.result.get("verdict") for s in res.steps if s.name == "SQL guard"] == ["rejected", "rejected"]


def test_clarify_and_refuse_make_one_call_and_run_nothing():
    for action in ("clarify", "refuse"):
        client = FakeClient(plan(action=action, message="Which property?"))
        res = agent.ask("What was our occupancy?", "analyst", con=db.connect(), client=client)
        assert res.action == action and res.rows == [] and res.usage["calls"] == 1 and res.answer == ""


def test_clarification_answer_is_combined_with_the_first_question():
    client = FakeClient(plan(action="clarify", message="ok"))
    agent.ask(
        "Beach Resort", "analyst", context="How much revenue did the hotel make?", con=db.connect(), client=client
    )
    content = client.requests[0]["messages"][0]["content"]
    assert "How much revenue did the hotel make?" in content and "Beach Resort" in content


def test_a_follow_up_is_rewritten_before_retrieval():
    history = [{"question": "What was total revenue at Beach Resort in October 2026?", "answer": "$412,000."}]
    client = FakeClient(
        "What was total revenue at Mountain Lodge in October 2026?", plan(action="refuse", message="no")
    )
    res = agent.ask("And at Mountain Lodge?", "analyst", history=history, con=db.connect(), client=client)
    assert res.original == "And at Mountain Lodge?"
    assert res.question == "What was total revenue at Mountain Lodge in October 2026?"
    assert res.steps[0].name == "Rewrite follow-up" and res.usage["calls"] == 2
    assert "Mountain Lodge in October 2026" in client.requests[1]["messages"][0]["content"]


def test_a_standalone_question_in_a_conversation_costs_no_rewrite_call():
    history = [{"question": "What was total revenue at Beach Resort in October 2026?", "answer": "$412,000."}]
    client = FakeClient(plan(action="refuse"))
    res = agent.ask(
        "How many rooms does Mountain Lodge have in total today?", history=[], con=db.connect(), client=client
    )
    assert res.usage["calls"] == 1
    client = FakeClient(plan(action="refuse"))
    res = agent.ask("Which refund reason cost the most in 2026, by amount?", history=history, client=client)
    assert res.usage["calls"] == 1 and res.original == ""


def test_manager_prompt_allows_personal_data():
    client = FakeClient(plan(action="refuse"))
    agent.ask("Name of guest 42?", "manager", con=db.connect(), client=client)
    assert "full_name, email and phone are allowed" in client.requests[0]["system"]


def test_ungrounded_numbers_are_flagged():
    assert agent.ungrounded("Revenue was $1,200 and 34.2% direct.", [[1200.0, 0.342]], "q") == []
    assert agent.ungrounded("Revenue was $9,999.", [[1200.0]], "q") == ["9999.0"]


def test_source_tables_ignore_ctes_and_bad_sql():
    sql = "WITH m AS (SELECT * FROM bookings) SELECT r.room_type FROM m JOIN rooms r ON r.id = m.room_id"
    assert agent.source_tables(sql) == ["bookings", "rooms"]
    assert agent.source_tables("SELECT FROM WHERE (") == []


def test_unknown_role():
    with pytest.raises(ValueError):
        agent.ask("x", "owner", con=db.connect(), client=FakeClient())
