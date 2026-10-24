"""The agent loop with the model replaced: SQL path, guard retry, clarify, refuse, grounding (no API calls)."""

import json
from types import SimpleNamespace

from src import agent, db


class FakeClient:
    """Returns the queued JSON replies in order and records the requests."""

    def __init__(self, *replies):
        self.replies, self.requests = list(replies), []
        self.messages = self

    def create(self, **request):
        self.requests.append(request)
        text = json.dumps(self.replies.pop(0))
        usage = SimpleNamespace(input_tokens=100, output_tokens=20)
        return SimpleNamespace(content=[SimpleNamespace(type="text", text=text)], usage=usage)


def plan(action="sql", sql="", message="m", chart="none", x="", y=""):
    return {"action": action, "message": message, "sql": sql, "chart": chart, "x": x, "y": y}


def test_sql_path_runs_the_guarded_query_and_answers_from_the_rows():
    client = FakeClient(
        plan(
            sql="SELECT property_id, COUNT(*) AS n FROM bookings GROUP BY property_id",
            chart="bar",
            x="property_id",
            y="n",
        ),
        {"answer": "Beach Resort had 4,347 bookings and Mountain Lodge 3,182."},
    )
    res = agent.ask("Bookings per property?", "analyst", con=db.connect(), client=client)
    assert res.action == "sql" and res.sql.endswith("LIMIT 500")
    assert res.rows == [["beach-resort", 4347], ["mountain-lodge", 3182]] and res.ungrounded == []
    assert res.usage == {"input_tokens": 200, "output_tokens": 40, "calls": 2}
    assert (
        "role: analyst" in client.requests[0]["system"]
        and "refuse any request for full_name" in client.requests[0]["system"]
    )
    assert client.requests[0]["output_config"]["format"]["type"] == "json_schema"


def test_a_rejected_query_is_sent_back_once_then_refused():
    client = FakeClient(plan(sql="DELETE FROM bookings"), plan(sql="SELECT email FROM guests"))
    res = agent.ask("Wipe it", "analyst", con=db.connect(), client=client)
    assert res.action == "refuse" and res.attempts == 2 and len(res.rejected) == 2
    assert "was rejected" in client.requests[1]["messages"][0]["content"]


def test_clarify_and_refuse_make_one_call_and_run_nothing():
    for action in ("clarify", "refuse"):
        client = FakeClient(plan(action=action, message="Which property?"))
        res = agent.ask("What was our occupancy?", "analyst", con=db.connect(), client=client)
        assert res.action == action and res.rows == [] and res.usage["calls"] == 1


def test_clarification_answer_is_combined_with_the_first_question():
    client = FakeClient(plan(action="clarify", message="ok"))
    agent.ask(
        "Beach Resort", "analyst", context="How much revenue did the hotel make?", con=db.connect(), client=client
    )
    content = client.requests[0]["messages"][0]["content"]
    assert "How much revenue did the hotel make?" in content and "Beach Resort" in content


def test_manager_prompt_allows_personal_data():
    client = FakeClient(plan(action="refuse"))
    agent.ask("Name of guest 42?", "manager", con=db.connect(), client=client)
    assert "full_name, email and phone are allowed" in client.requests[0]["system"]


def test_ungrounded_numbers_are_flagged():
    assert agent.ungrounded("Revenue was $1,200 and 34.2% direct.", [[1200.0, 0.342]], "q") == []
    assert agent.ungrounded("Revenue was $9,999.", [[1200.0]], "q") == ["9999.0"]


def test_unknown_role():
    import pytest

    with pytest.raises(ValueError):
        agent.ask("x", "owner", con=db.connect(), client=FakeClient())
