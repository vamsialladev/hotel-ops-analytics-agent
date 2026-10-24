"""Build the synthetic hotel database (SQLite): 12 months of bookings with seasonality and five planted anomalies.

    python scripts/make_db.py                 # data/hotel.db (seed 42): what the app, the SQL eval and CI use
    python scripts/make_db.py --heldout       # data/hotel_heldout.db (seed 7): other anomaly dates, for the detector

Everything is fake: names come from short lists, emails end in @mail.test, phones are 555 numbers. The planted
anomalies are listed in ANOMALIES (and written to the `planted_anomalies` table only in the held-out file's
companion JSON, never read by the detector).
"""

import argparse
import json
import random
import sqlite3
import sys
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
START, END = date(2025, 11, 1), date(2026, 10, 31)  # inclusive; "today" in the app is 2026-10-31

PROPERTIES = {
    "beach-resort": {
        "name": "Beach Resort",
        "location": "Florida",
        "rooms": {"Ocean King": 15, "Garden Queen": 20, "Suite": 5},
    },
    "mountain-lodge": {
        "name": "Mountain Lodge",
        "location": "North Carolina",
        "rooms": {"Cabin": 10, "Lodge Queen": 12, "Lodge King": 8},
    },
}
BASE_RATE = {"Ocean King": 290, "Garden Queen": 210, "Suite": 520, "Cabin": 260, "Lodge Queen": 180, "Lodge King": 210}
ACTIVITIES = {
    "beach-resort": [
        ("Sunrise yoga", "wellness", 0, 15),
        ("Kids club", "family", 25, 12),
        ("Sunset cruise", "outdoor", 65, 20),
        ("Cooking class", "food", 45, 10),
    ],
    "mountain-lodge": [
        ("Guided morning trek", "outdoor", 30, 10),
        ("Fire pit evening", "family", 0, 30),
        ("Mountain breakfast class", "food", 45, 8),
        ("Stargazing", "outdoor", 20, 15),
    ],
}
FIRST = "Ana Ben Chloe Dev Elena Farid Grace Hiro Ivy Jon Kai Lena Marco Nia Omar Priya Quinn Rosa Sam Tara Uma Vik Wen Yara Zane".split()
LAST = "Adams Berg Chen Diaz Evans Fox Garcia Hughes Ito Jones Khan Lopez Moreau Nair Okafor Patel Quist Ruiz Singh Torres".split()
COUNTRIES = ["US"] * 8 + ["CA", "MX", "UK", "DE"]
TIERS = ["None"] * 6 + ["Silver", "Silver", "Gold", "Platinum"]
CHANNELS = ["direct", "direct", "ota", "ota", "phone", "travel_agent"]
REFUND_REASONS = ["noise", "room not ready", "maintenance", "billing error", "service"]

ANOMALIES = {
    42: {
        "occupancy_drop": ("mountain-lodge", date(2026, 3, 9), date(2026, 3, 15)),
        "cancellation_spike": ("beach-resort", date(2026, 6, 8), date(2026, 6, 14)),
        "refund_spike": ("mountain-lodge", date(2026, 8, 17), date(2026, 8, 20)),
        "activity_no_shows": ("beach-resort", date(2026, 1, 19), date(2026, 1, 25)),
        "rate_error": ("beach-resort", date(2026, 9, 14), date(2026, 9, 18)),
    },
    7: {
        "occupancy_drop": ("beach-resort", date(2026, 5, 4), date(2026, 5, 10)),
        "cancellation_spike": ("mountain-lodge", date(2026, 2, 9), date(2026, 2, 15)),
        "refund_spike": ("beach-resort", date(2025, 12, 15), date(2025, 12, 18)),
        "activity_no_shows": ("mountain-lodge", date(2026, 7, 13), date(2026, 7, 19)),
        "rate_error": ("mountain-lodge", date(2026, 4, 20), date(2026, 4, 24)),
    },
}
NO_SHOW_ACTIVITY = {"beach-resort": "Sunset cruise", "mountain-lodge": "Guided morning trek"}
RATE_ERROR_ROOM = {"beach-resort": "Suite", "mountain-lodge": "Cabin"}

SCHEMA = """
CREATE TABLE properties (id TEXT PRIMARY KEY, name TEXT, location TEXT, rooms_count INTEGER);
CREATE TABLE rooms (id INTEGER PRIMARY KEY, property_id TEXT, number TEXT, room_type TEXT);
CREATE TABLE guests (id INTEGER PRIMARY KEY, full_name TEXT, email TEXT, phone TEXT, loyalty_tier TEXT, country TEXT);
CREATE TABLE rates (property_id TEXT, room_type TEXT, date TEXT, rate_usd REAL, PRIMARY KEY (property_id, room_type, date));
CREATE TABLE bookings (id INTEGER PRIMARY KEY, property_id TEXT, room_id INTEGER, guest_id INTEGER, check_in TEXT,
  check_out TEXT, nights INTEGER, status TEXT, channel TEXT, booked_at TEXT, cancelled_at TEXT, total_usd REAL);
CREATE TABLE activities (id INTEGER PRIMARY KEY, property_id TEXT, name TEXT, category TEXT, price_usd REAL, capacity INTEGER);
CREATE TABLE activity_bookings (id INTEGER PRIMARY KEY, activity_id INTEGER, booking_id INTEGER, date TEXT,
  party_size INTEGER, status TEXT);
CREATE TABLE refunds (id INTEGER PRIMARY KEY, booking_id INTEGER, date TEXT, amount_usd REAL, reason TEXT);
CREATE TABLE feedback (id INTEGER PRIMARY KEY, booking_id INTEGER, date TEXT, score INTEGER, comment TEXT);
CREATE INDEX bookings_dates ON bookings (property_id, check_in, check_out);
CREATE INDEX bookings_cancelled ON bookings (cancelled_at);
CREATE INDEX refunds_date ON refunds (date);
CREATE INDEX activity_bookings_date ON activity_bookings (date);
CREATE INDEX rates_date ON rates (date);
"""


def days(a: date, b: date):
    d = a
    while d <= b:
        yield d
        d += timedelta(days=1)


def in_window(anoms: dict, kind: str, prop: str, d: date) -> bool:
    p, a, b = anoms[kind]
    return p == prop and a <= d <= b


def occupancy_target(prop: str, d: date) -> float:
    m = d.month
    if prop == "beach-resort":  # busy in winter and spring, quieter late summer
        season = {
            12: 0.85,
            1: 0.88,
            2: 0.9,
            3: 0.92,
            4: 0.85,
            5: 0.75,
            6: 0.7,
            7: 0.72,
            8: 0.6,
            9: 0.55,
            10: 0.65,
            11: 0.75,
        }[m]
    else:  # busy in summer and October leaves, quiet in spring mud season
        season = {
            12: 0.7,
            1: 0.6,
            2: 0.6,
            3: 0.5,
            4: 0.5,
            5: 0.65,
            6: 0.8,
            7: 0.88,
            8: 0.85,
            9: 0.8,
            10: 0.92,
            11: 0.65,
        }[m]
    if d.weekday() in (4, 5):
        season += 0.08
    return min(season, 0.97)


def build(path: Path, seed: int) -> dict:
    rng = random.Random(seed)
    anoms = ANOMALIES[seed]
    path.unlink(missing_ok=True)
    con = sqlite3.connect(path)
    con.executescript(SCHEMA)
    room_id, rooms = 0, []
    for prop, info in PROPERTIES.items():
        con.execute(
            "INSERT INTO properties VALUES (?,?,?,?)",
            (prop, info["name"], info["location"], sum(info["rooms"].values())),
        )
        n = 100
        for rtype, count in info["rooms"].items():
            for _ in range(count):
                room_id += 1
                n += 1
                rooms.append((room_id, prop, rtype))
                con.execute("INSERT INTO rooms VALUES (?,?,?,?)", (room_id, prop, str(n), rtype))
    # rates: seasonal, weekend uplift, the planted rate error
    rate = {}
    for prop, info in PROPERTIES.items():
        for rtype in info["rooms"]:
            for d in days(START - timedelta(days=60), END + timedelta(days=30)):
                r = (
                    BASE_RATE[rtype]
                    * (0.75 + 0.4 * occupancy_target(prop, d))
                    * (1.1 if d.weekday() in (4, 5) else 1.0)
                )
                r = round(r)
                if rtype == RATE_ERROR_ROOM[prop] and in_window(anoms, "rate_error", prop, d):
                    r = round(r / 10)  # a missing zero, loaded for five days
                rate[(prop, rtype, d)] = r
                con.execute("INSERT INTO rates VALUES (?,?,?,?)", (prop, rtype, d.isoformat(), r))
    guests = []
    for gid in range(1, 2201):
        first, last = rng.choice(FIRST), rng.choice(LAST)
        email = f"{first.lower()}.{last.lower()}{gid}@mail.test"
        phone = f"+1 555 {rng.randint(100, 999)} {rng.randint(1000, 9999)}"
        guests.append(gid)
        con.execute(
            "INSERT INTO guests VALUES (?,?,?,?,?,?)",
            (gid, f"{first} {last}", email, phone, rng.choice(TIERS), rng.choice(COUNTRIES)),
        )
    # bookings: walk each room's calendar
    bid, bookings = 0, []
    for rid, prop, rtype in rooms:
        d = START
        while d <= END:
            target = occupancy_target(prop, d)
            if in_window(anoms, "occupancy_drop", prop, d):
                target *= 0.2
            nights = rng.choice([1, 2, 2, 3, 3, 4, 5, 7])
            if rng.random() < target / (0.55 + 0.45 * target):
                check_out = d + timedelta(days=nights)
                if in_window(anoms, "occupancy_drop", prop, check_out - timedelta(days=1)) and not in_window(
                    anoms, "occupancy_drop", prop, d
                ):
                    check_out = anoms["occupancy_drop"][1]  # guests leave before the drop
                    nights = max((check_out - d).days, 1)
                    check_out = d + timedelta(days=nights)
                bid += 1
                booked_at = d - timedelta(days=rng.randint(1, 90))
                total = sum(rate[(prop, rtype, d + timedelta(days=i))] for i in range(nights))
                status = "completed" if check_out <= END else "confirmed"
                cancelled = None
                if rng.random() < 0.07:
                    status, cancelled = (
                        "cancelled",
                        booked_at + timedelta(days=rng.randint(0, max((d - booked_at).days - 1, 0))),
                    )
                bookings.append(
                    [
                        bid,
                        prop,
                        rid,
                        rng.choice(guests),
                        d,
                        check_out,
                        nights,
                        status,
                        rng.choice(CHANNELS),
                        booked_at,
                        cancelled,
                        total,
                    ]
                )
                d = check_out if status != "cancelled" else d + timedelta(days=1)
            else:
                d += timedelta(days=1)
    # planted cancellation spike: many future bookings cancelled during one week
    cprop, ca, cb = anoms["cancellation_spike"]
    candidates = [
        b for b in bookings if b[1] == cprop and b[7] != "cancelled" and b[4] > cb + timedelta(days=7) and b[9] < ca
    ]
    for b in rng.sample(candidates, min(70, len(candidates))):
        b[7], b[10] = "cancelled", ca + timedelta(days=rng.randint(0, (cb - ca).days))
    for b in bookings:
        con.execute(
            "INSERT INTO bookings VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                b[0],
                b[1],
                b[2],
                b[3],
                b[4].isoformat(),
                b[5].isoformat(),
                b[6],
                b[7],
                b[8],
                b[9].isoformat(),
                b[10].isoformat() if b[10] else None,
                b[11],
            ),
        )
    # activities and attendance
    aid, act_ids = 0, {}
    for prop, acts in ACTIVITIES.items():
        for name, cat, price, cap in acts:
            aid += 1
            act_ids[(prop, name)] = (aid, cap)
            con.execute("INSERT INTO activities VALUES (?,?,?,?,?,?)", (aid, prop, name, cat, price, cap))
    staying = {}
    for b in bookings:
        if b[7] != "cancelled":
            for i in range(b[6]):
                staying.setdefault((b[1], b[4] + timedelta(days=i)), []).append(b[0])
    abid = 0
    for (prop, d), guests_in in sorted(staying.items()):
        if d > END:
            continue
        for name, *_ in ACTIVITIES[prop]:
            act, cap = act_ids[(prop, name)]
            for _ in range(min(rng.randint(2, cap), len(guests_in))):
                abid += 1
                no_show_p = (
                    0.75 if name == NO_SHOW_ACTIVITY[prop] and in_window(anoms, "activity_no_shows", prop, d) else 0.07
                )
                status = "no_show" if rng.random() < no_show_p else ("cancelled" if rng.random() < 0.05 else "attended")
                con.execute(
                    "INSERT INTO activity_bookings VALUES (?,?,?,?,?,?)",
                    (abid, act, rng.choice(guests_in), d.isoformat(), rng.randint(1, 4), status),
                )
    # refunds: a few a week, plus the planted spike
    rid_ = 0
    by_prop = {p: [b for b in bookings if b[1] == p and b[7] == "completed"] for p in PROPERTIES}
    for d in days(START, END):
        for prop in PROPERTIES:
            n = 1 if rng.random() < 0.35 else 0
            if in_window(anoms, "refund_spike", prop, d):
                n = rng.randint(9, 13)
            for _ in range(n):
                rid_ += 1
                b = rng.choice(by_prop[prop])
                amount = round(rng.uniform(25, 120) if n < 5 else rng.uniform(150, 400), 2)
                con.execute(
                    "INSERT INTO refunds VALUES (?,?,?,?,?)",
                    (rid_, b[0], d.isoformat(), amount, rng.choice(REFUND_REASONS)),
                )
    # feedback on completed stays
    fid = 0
    for b in bookings:
        if b[7] == "completed" and rng.random() < 0.3:
            fid += 1
            score = rng.choices([1, 2, 3, 4, 5], [2, 4, 12, 40, 42])[0]
            comment = {
                1: "Very disappointed.",
                2: "Room was noisy.",
                3: "Fine.",
                4: "Great stay.",
                5: "Perfect, will return.",
            }[score]
            con.execute("INSERT INTO feedback VALUES (?,?,?,?,?)", (fid, b[0], b[5].isoformat(), score, comment))
    con.commit()
    counts = {
        t: con.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
        for t in ("bookings", "guests", "refunds", "activity_bookings", "feedback")
    }
    con.close()
    return counts


def planted(seed: int) -> list[dict]:
    return [
        {"kind": k, "property": p, "start": a.isoformat(), "end": b.isoformat()}
        for k, (p, a, b) in ANOMALIES[seed].items()
    ]


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--heldout", action="store_true")
    args = parser.parse_args(argv)
    seed, name = (7, "hotel_heldout") if args.heldout else (42, "hotel")
    counts = build(ROOT / "data" / f"{name}.db", seed)
    (ROOT / "data" / f"{name}.planted.json").write_text(json.dumps(planted(seed), indent=2) + "\n", encoding="utf-8")
    print(f"data/{name}.db (seed {seed}): {counts}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
