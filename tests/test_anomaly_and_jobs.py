"""The anomaly rules, the daily Slack job (no network), the data generator and the eval plumbing (no model)."""

import json
import sqlite3
import sys
from datetime import date

import pytest

from eval import run_eval
from src import anomaly
from src.config import ROOT

sys.path.insert(0, str(ROOT / "scripts"))
import daily_check  # noqa: E402
import make_db  # noqa: E402


@pytest.fixture(scope="module")
def con():
    return sqlite3.connect(f"file:{(ROOT / 'data' / 'hotel.db').as_posix()}?mode=ro", uri=True)


@pytest.mark.parametrize(
    "day,kind",
    [
        ("2026-03-10", "occupancy_drop"),
        ("2026-06-08", "cancellation_spike"),
        ("2026-08-17", "refund_spike"),
        ("2026-01-20", "activity_no_shows"),
        ("2026-09-14", "rate_error"),
    ],
)
def test_each_planted_anomaly_is_found_on_its_first_day(con, day, kind):
    assert kind in {f.kind for f in anomaly.detect(con, date.fromisoformat(day))}


def test_a_quiet_day_has_no_findings(con):
    assert anomaly.detect(con, date(2026, 10, 20)) == []


def test_score_counts_caught_missed_and_false_alarms():
    f = anomaly.Finding("rate_error", "beach-resort", "Suite", "2026-09-15", 50, 500, "m", "sql")
    g = anomaly.Finding("refund_spike", "beach-resort", "beach-resort", "2026-02-01", 9, 1, "m", "sql")
    planted = [
        {"kind": "rate_error", "property": "beach-resort", "start": "2026-09-14", "end": "2026-09-18"},
        {"kind": "occupancy_drop", "property": "mountain-lodge", "start": "2026-03-09", "end": "2026-03-15"},
    ]
    s = anomaly.score([f, g], planted)
    assert s["caught"] == ["rate_error"] and s["missed"] == ["occupancy_drop"] and s["false_alarms"] == 1


def test_daily_message_has_summary_chart_and_sql(con):
    payload = daily_check.message(date(2026, 9, 14), anomaly.detect(con, date(2026, 9, 14)))
    text = payload["text"]
    assert "rate error" in text and "last 14 days" in text and "SELECT" in text and "synthetic" in text
    assert daily_check.message(date(2026, 10, 20), [])["text"].startswith("Daily check 2026-10-20: no anomalies")


def test_replay_and_sparkline():
    assert daily_check.replay(date(2027, 3, 10)) == date(2026, 3, 10)
    assert daily_check.replay(date(2026, 11, 5)) == date(2025, 11, 5)
    assert daily_check.replay(date(2028, 2, 29)) == date(2026, 2, 28)
    assert daily_check.sparkline([0, 5, 10]) == "▁▄█" and daily_check.sparkline([]) == ""


def test_daily_job_dry_run_and_post_without_a_webhook(monkeypatch, capsys):
    monkeypatch.delenv("SLACK_WEBHOOK_URL", raising=False)
    assert daily_check.main(["--day", "2026-09-14", "--post"]) == 0
    assert "SLACK_WEBHOOK_URL is not set" in capsys.readouterr().out
    assert daily_check.main(["--day", "2024-01-01"]) == 2


def test_daily_job_posts_to_the_webhook(monkeypatch, capsys):
    sent = {}
    monkeypatch.setenv("SLACK_WEBHOOK_URL", "https://hooks.slack.test/T/B/X")
    monkeypatch.setattr(daily_check, "post", lambda payload, url: sent.update(payload=payload, url=url) or 200)
    assert daily_check.main(["--day", "2026-09-14", "--post"]) == 0
    out = capsys.readouterr().out
    assert sent["url"].startswith("https://hooks.slack.test") and "hooks.slack.test" not in out


def test_generator_is_deterministic(tmp_path):
    a, b = tmp_path / "a.db", tmp_path / "b.db"
    assert make_db.build(a, 7) == make_db.build(b, 7)
    q = "SELECT COUNT(*), SUM(total_usd) FROM bookings"
    assert sqlite3.connect(a).execute(q).fetchone() == sqlite3.connect(b).execute(q).fetchone()
    assert make_db.planted(42)[0]["kind"] == "occupancy_drop"


def test_committed_database_matches_the_generator(tmp_path):
    fresh = tmp_path / "hotel.db"
    make_db.build(fresh, 42)
    q = "SELECT COUNT(*), SUM(total_usd), SUM(cancelled_at IS NOT NULL) FROM bookings"
    committed = sqlite3.connect(ROOT / "data" / "hotel.db").execute(q).fetchone()
    assert sqlite3.connect(fresh).execute(q).fetchone() == committed


def test_eval_cases_and_summary():
    cases = run_eval.load("all")
    assert sum(c["split"] == "dev" and c["expect"] == "sql" for c in cases) >= 45
    assert sum(c["expect"] == "refuse" for c in cases) >= 10 and any(c["split"] == "heldout" for c in cases)
    assert run_eval.guard_only() == 0
    runs = [
        [
            {
                "id": "a",
                "category": "x",
                "expect": "sql",
                "pass": True,
                "seconds": 1.0,
                "tokens_in": 1000,
                "tokens_out": 100,
                "rejected": [],
                "ungrounded": [],
            }
        ]
    ]
    s = run_eval.summarize(runs, 0.1, 0.5)
    assert s["execution"] == (1, 1) and round(s["cost_per_1000"], 4) == round((1000 * 0.1 + 100 * 0.5) / 1e6 * 1000, 4)


def test_rescore_reproduces_a_saved_run(capsys):
    path = ROOT / "eval" / "reports" / "sql-2026-10-24-dev.jsonl"
    assert run_eval.rescore(path) == 0
    assert "0 verdicts changed" in capsys.readouterr().out
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]
    assert len(rows) == 180
