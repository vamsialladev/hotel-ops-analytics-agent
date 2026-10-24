"""Daily anomaly check: five rules, each one SQL query plus a threshold, compared with the previous 28 days.

    findings = detect(con, date(2026, 6, 10))        # what the daily job runs for one day
    alerts = backfill(con, start, end)                # every day in a range, one alert per episode

No model is involved: the rules are deterministic, so a false alarm can be explained line by line. Thresholds were
set on the main database (seed 42) and checked, unchanged, on a held-out database with other anomaly dates (seed 7).
"""

import sqlite3
import statistics
from dataclasses import dataclass, field
from datetime import date, timedelta

BASELINE_DAYS = 28
EPISODE_DAYS = 7  # a second alert for the same rule and entity within this many days is the same episode

OCCUPANCY_SQL = """SELECT b.property_id, COUNT(*) * 1.0 / p.rooms_count AS occupancy
FROM bookings b JOIN properties p ON p.id = b.property_id
WHERE b.status != 'cancelled' AND b.check_in <= :day AND b.check_out > :day
GROUP BY b.property_id"""
CANCELLATIONS_SQL = """SELECT property_id, COUNT(*) AS cancellations
FROM bookings WHERE cancelled_at = :day GROUP BY property_id"""
REFUNDS_SQL = """SELECT b.property_id, COUNT(*) AS refunds, ROUND(SUM(r.amount_usd), 2) AS amount_usd
FROM refunds r JOIN bookings b ON b.id = r.booking_id WHERE r.date = :day GROUP BY b.property_id"""
NO_SHOWS_SQL = """SELECT a.property_id, a.name, SUM(ab.status = 'no_show') AS no_shows,
  SUM(ab.status IN ('attended', 'no_show')) AS expected
FROM activity_bookings ab JOIN activities a ON a.id = ab.activity_id
WHERE ab.date BETWEEN :start AND :day GROUP BY a.id"""
RATES_SQL = """SELECT property_id, room_type, rate_usd FROM rates WHERE date = :day"""


@dataclass
class Finding:
    kind: str
    property: str
    entity: str  # property, activity name or room type
    day: str
    value: float
    baseline: float
    message: str
    sql: str
    series: list = field(default_factory=list)  # recent values, for the chart


def _rows(con, sql, **params):
    return con.execute(sql, params).fetchall()


def _series(con, sql, day: date, n: int, key_cols: int = 1, value_col: int = 1) -> dict:
    """{key: [value for each of the n days ending at `day`]} (0 when a day has no row)."""
    out = {}
    for i in range(n):
        d = (day - timedelta(days=n - 1 - i)).isoformat()
        for row in _rows(con, sql, day=d):
            key = row[0] if key_cols == 1 else tuple(row[:key_cols])
            out.setdefault(key, [0.0] * n)[i] = float(row[value_col] or 0)
    return out


def occupancy(con, day: date) -> list[Finding]:
    found = []
    for prop, values in _series(con, OCCUPANCY_SQL, day, BASELINE_DAYS + 3).items():
        base, recent = statistics.median(values[:BASELINE_DAYS]), sum(values[-3:]) / 3
        if base > 0.2 and recent < 0.6 * base:
            msg = f"Occupancy at {prop} averaged {recent:.0%} over 3 days vs a 28-day median of {base:.0%}."
            found.append(
                Finding("occupancy_drop", prop, prop, day.isoformat(), recent, base, msg, OCCUPANCY_SQL, values[-14:])
            )
    return found


def cancellations(con, day: date) -> list[Finding]:
    found = []
    for prop, values in _series(con, CANCELLATIONS_SQL, day, BASELINE_DAYS + 1).items():
        base, today = values[:BASELINE_DAYS], values[-1]
        mean = statistics.mean(base)
        if today >= 6 and today > mean + 5 * max(statistics.pstdev(base), 1.0):
            msg = f"{today:.0f} cancellations at {prop} today vs a 28-day average of {mean:.1f} a day."
            found.append(
                Finding(
                    "cancellation_spike", prop, prop, day.isoformat(), today, mean, msg, CANCELLATIONS_SQL, values[-14:]
                )
            )
    return found


def refunds(con, day: date) -> list[Finding]:
    found = []
    for prop, values in _series(con, REFUNDS_SQL, day, BASELINE_DAYS + 1).items():
        base, today = values[:BASELINE_DAYS], values[-1]
        mean = statistics.mean(base)
        if today >= 5 and today > mean + 5 * max(statistics.pstdev(base), 1.0):
            msg = f"{today:.0f} refunds at {prop} today vs a 28-day average of {mean:.1f} a day."
            found.append(
                Finding("refund_spike", prop, prop, day.isoformat(), today, mean, msg, REFUNDS_SQL, values[-14:])
            )
    return found


def no_shows(con, day: date) -> list[Finding]:
    found = []
    start = (day - timedelta(days=2)).isoformat()
    for prop, name, ns, expected in _rows(con, NO_SHOWS_SQL, start=start, day=day.isoformat()):
        if expected and expected >= 10 and ns / expected > 0.4:
            share = ns / expected
            msg = f"{name} at {prop}: {ns} of {expected} expected guests didn't show in the last 3 days ({share:.0%})."
            found.append(
                Finding("activity_no_shows", prop, name, day.isoformat(), ns / expected, 0.07, msg, NO_SHOWS_SQL)
            )
    return found


def rates(con, day: date) -> list[Finding]:
    found = []
    history = _series(con, RATES_SQL, day, BASELINE_DAYS + 1, key_cols=2, value_col=2)
    for (prop, room_type), values in history.items():
        base, today = statistics.median(values[:BASELINE_DAYS]), values[-1]
        if base > 0 and today < 0.5 * base:
            msg = f"{room_type} at {prop} is priced ${today:.0f} today vs a 28-day median of ${base:.0f}."
            found.append(
                Finding("rate_error", prop, room_type, day.isoformat(), today, base, msg, RATES_SQL, values[-14:])
            )
    return found


RULES = (occupancy, cancellations, refunds, no_shows, rates)


def detect(con: sqlite3.Connection, day: date) -> list[Finding]:
    return [f for rule in RULES for f in rule(con, day)]


def backfill(con: sqlite3.Connection, start: date, end: date) -> list[Finding]:
    """Run every day; keep the first alert of each episode (same rule and entity within EPISODE_DAYS)."""
    alerts, last = [], {}
    d = start
    while d <= end:
        for f in detect(con, d):
            key = (f.kind, f.property, f.entity)
            if key not in last or (d - last[key]).days > EPISODE_DAYS:
                alerts.append(f)
            last[key] = d
        d += timedelta(days=1)
    return alerts


def score(alerts: list[Finding], planted: list[dict], grace_days: int = 3) -> dict:
    """Which planted anomalies were caught (an alert of the same kind and property inside the window, up to
    `grace_days` after it), and which alerts are false alarms."""
    caught, false = set(), []
    for a in alerts:
        d = date.fromisoformat(a.day)
        match = next(
            (
                p
                for p in planted
                if p["kind"] == a.kind
                and p["property"] == a.property
                and date.fromisoformat(p["start"]) <= d <= date.fromisoformat(p["end"]) + timedelta(days=grace_days)
            ),
            None,
        )
        if match:
            caught.add(match["kind"])
        else:
            false.append(a)
    per_month = {}
    for a in false:
        per_month[a.day[:7]] = per_month.get(a.day[:7], 0) + 1
    return {
        "caught": sorted(caught),
        "missed": sorted({p["kind"] for p in planted} - caught),
        "false_alarms": len(false),
        "max_false_per_month": max(per_month.values(), default=0),
        "false": false,
    }
