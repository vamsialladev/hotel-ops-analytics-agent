"""The SQL guard, the read-only connection and the execution-accuracy comparison (no model calls)."""

import sqlite3

import pytest

from src import db, sqlguard
from src.compare import matches


@pytest.mark.parametrize(
    "sql,reason",
    [
        ("DELETE FROM bookings", "only SELECT"),
        ("UPDATE rates SET rate_usd = 0", "only SELECT"),
        ("DROP TABLE guests", "only SELECT"),
        ("SELECT 1; DROP TABLE guests", "exactly one statement"),
        ("PRAGMA writable_schema = 1", "only SELECT"),
        ("SELECT * FROM sqlite_master", "table not allowed"),
        ("SELECT email FROM guests", "manager role only"),
        ("SELECT g.phone FROM bookings b JOIN guests g ON g.id = b.guest_id", "manager role only"),
        ("SELECT * FROM guests", "over guests would include"),
        ("SELECT g.* FROM guests g", "over guests would include"),
        ("SELEC count(*) FROM bookings", "not valid SQL"),
        ("", "empty"),
    ],
)
def test_guard_rejects(sql, reason):
    with pytest.raises(sqlguard.Rejected, match=reason):
        sqlguard.check(sql, "analyst")


def test_guard_allows_reads_and_forces_a_limit():
    assert sqlguard.check("SELECT COUNT(*) FROM guests", "analyst").endswith("LIMIT 500")
    assert sqlguard.check("SELECT id FROM bookings LIMIT 10", "analyst").endswith("LIMIT 10")
    assert sqlguard.check("SELECT id FROM bookings LIMIT 100000", "analyst").endswith("LIMIT 500")
    cte = "WITH x AS (SELECT property_id FROM bookings) SELECT COUNT(*) FROM x"
    assert "LIMIT 500" in sqlguard.check(cte, "analyst")
    assert "email" in sqlguard.check("SELECT email FROM guests WHERE id = 1", "manager")


def test_connection_is_read_only_even_if_the_guard_were_bypassed():
    con = db.connect()
    with pytest.raises(sqlite3.OperationalError):
        con.execute("DELETE FROM bookings")
    cols, rows = db.run(con, "SELECT COUNT(*) AS n FROM properties")
    assert cols == ["n"] and rows == [(2,)]


def test_slow_query_times_out():
    con = db.connect()
    slow = "WITH RECURSIVE n(i) AS (SELECT 1 UNION ALL SELECT i + 1 FROM n) SELECT COUNT(*) FROM n"
    with pytest.raises(db.QueryTimeout):
        db.run(con, slow, timeout_s=0.2)


def test_compare_rules():
    assert matches([["beach-resort", 10.0]], [[10, "Beach Resort"]])  # columns in any order, name = id
    assert matches([[3.3694]], [[3.37]])  # 2-decimal rounding
    assert not matches([[45.92]], [[45.5]])
    assert matches([["Cabin"]], [["Cabin", 9], ["Lodge Queen", 7]], reference_sql="... LIMIT 1")
    assert not matches([["Cabin"]], [["Lodge Queen", 9], ["Cabin", 7]], reference_sql="... LIMIT 1")
    assert matches([[0.3421]], [[34.21]])  # a share as a percentage
    assert not matches([["a"], ["b"]], [["b"], ["a"]], ordered=True)
    assert matches([["a"], ["b"]], [["b"], ["a"]])
    assert not matches([["a"]], [["a"], ["b"]])
