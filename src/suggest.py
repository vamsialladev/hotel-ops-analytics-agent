"""Suggested next questions after an answer: picked from the tables the SQL read, no model call.

Each suggestion is a full standalone question that the eval set or the examples show the agent answers, so a
click never lands on a dead end.
"""

BY_TABLE = {
    "bookings": [
        "Split that by booking channel.",
        "What was the cancellation rate at each property in 2026?",
        "What was the average daily rate at Beach Resort in 2026?",
    ],
    "refunds": [
        "Which refund reason cost the most at Mountain Lodge in 2026?",
        "What was the total amount refunded at Beach Resort in 2026?",
    ],
    "feedback": [
        "What was the average feedback score at each property in 2026?",
        "How many feedback entries got each score at Mountain Lodge?",
    ],
    "activity_bookings": [
        "What was the no-show rate for each activity at Beach Resort?",
        "Which activity had the most attended bookings in 2026?",
    ],
    "rates": ["What was the average loaded Suite rate at Beach Resort in September 2026?"],
    "guests": ["How many guests are there in each loyalty tier?"],
    "rooms": ["Which room type at Mountain Lodge earned the most revenue in 2026?"],
}
DEFAULT = [
    "What was total revenue at Beach Resort in October 2026?",
    "What was the occupancy at Mountain Lodge on 2026-03-12?",
    "Which refund reason cost the most at Mountain Lodge in 2026?",
]


def after(tables: list[str], asked: set[str], n: int = 3) -> list[str]:
    """Up to n suggestions for the tables just used, never one already asked in this conversation."""
    pool = [q for t in tables for q in BY_TABLE.get(t, [])] + DEFAULT
    out = []
    for q in pool:
        if q not in asked and q not in out:
            out.append(q)
    return out[:n]
