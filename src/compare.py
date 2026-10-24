"""Execution accuracy: does the generated query return the same answer as the reference query?

Column names and column order don't matter. Rows are compared as a multiset (in order when the question asks for a
ranking). A generated row may carry extra columns, as long as it contains every value of its expected row. Numbers
are compared to about 2 decimal places; text case-insensitively, with a property's id and name treated as the same
('beach-resort' = 'Beach Resort'). Three fixes came from reading failed cases in the first recorded run, where the
model was right and the grader wasn't (docs/DECISIONS.md, decision 4):
- a property name instead of its id;
- for a "which ... most?" question (reference ends in LIMIT 1), a full ranking whose first row is the answer;
- a share as a percentage (34.21) instead of a fraction (0.3421).
"""

import re

TOP1 = re.compile(r"\blimit\s+1\s*$", re.IGNORECASE)


def norm(value):
    if isinstance(value, bool):
        return float(value)
    if isinstance(value, (int, float)):
        return float(value)
    if value is None:
        return None
    return str(value).strip().lower().replace("-", " ")


def same(a, b) -> bool:
    if isinstance(a, float) and isinstance(b, float):
        return abs(a - b) <= max(0.006, abs(b) * 0.0001)
    return a == b


def contains(row: list, expected: list) -> bool:
    """Every expected value appears in the row (each used once)."""
    pool = list(row)
    for v in expected:
        i = next((k for k, p in enumerate(pool) if same(p, v)), None)
        if i is None:
            return False
        pool.pop(i)
    return True


def matches(expected_rows: list, actual_rows: list, ordered: bool = False, reference_sql: str = "") -> bool:
    exp = [[norm(v) for v in r] for r in expected_rows]
    act = [[norm(v) for v in r] for r in actual_rows]
    if len(exp) == 1 and len(act) > 1 and TOP1.search(reference_sql.strip()):
        return contains(act[0], exp[0])
    if len(exp) == 1 and len(act) == 1 and len(exp[0]) == 1 and isinstance(exp[0][0], float):
        if any(isinstance(v, float) and same(v, exp[0][0] * 100) for v in act[0]):
            return True
    if len(exp) != len(act):
        return False
    if ordered:
        return all(contains(a, e) for a, e in zip(act, exp, strict=True))
    remaining = list(act)
    for e in exp:
        i = next((k for k, a in enumerate(remaining) if contains(a, e)), None)
        if i is None:
            return False
        remaining.pop(i)
    return True
