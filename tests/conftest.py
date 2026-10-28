import pytest


@pytest.fixture(autouse=True)
def fresh_gate_counters():
    """The Admin lockout counts per process (hotel-ai-platform admin_gate): reset it between tests."""
    from hotelplatform import admin_gate

    admin_gate.reset_process_counters()
    yield
    admin_gate.reset_process_counters()


@pytest.fixture(autouse=True)
def ops_log_in_tmp(tmp_path, monkeypatch):
    """The ops store writes JSONL files without DATABASE_URL; tests write to a temp folder and never use a live URL."""
    from hotelplatform import oplog

    from src import ops

    monkeypatch.delenv("DATABASE_URL", raising=False)
    store = oplog.OpsStore("hotel-ops-analytics-agent", url="", log_dir=tmp_path / "ops")
    monkeypatch.setattr(ops, "store", lambda: store)
    yield store
