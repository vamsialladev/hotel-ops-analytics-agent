"""Every SQL statement is checked here before it runs, whatever the model said or the question asked.

Rules: one statement; a SELECT (WITH and UNION allowed); no write, schema, PRAGMA or ATTACH anywhere; only allowlisted
tables; no personal-data column (and no `*` over guests) unless the role is manager; a LIMIT of at most MAX_ROWS is
forced. The connection is also read-only (db.py), so a mistake here still can't change data.
"""

import sqlglot
from sqlglot import exp

from src.schema import PII_COLUMNS, TABLES

MAX_ROWS = 500
FORBIDDEN = (
    exp.Insert,
    exp.Update,
    exp.Delete,
    exp.Drop,
    exp.Create,
    exp.Alter,
    exp.Command,
    exp.Pragma,
    exp.Attach,
    exp.Detach,
    exp.TruncateTable,
)


class Rejected(ValueError):
    """The SQL breaks a rule. The message is safe to show and to send back to the model."""


def projects_star(select: exp.Select) -> bool:
    """`SELECT *` or `SELECT g.*`, but not COUNT(*) (found by the eval's free guard check: q10, q11, q35, q36)."""
    return any(
        isinstance(e, exp.Star) or (isinstance(e, exp.Column) and isinstance(e.this, exp.Star))
        for e in select.expressions
    )


def check(sql: str, role: str) -> str:
    """Returns the SQL to run (with the LIMIT forced), or raises Rejected."""
    if not sql or not sql.strip():
        raise Rejected("empty query")
    try:
        statements = [s for s in sqlglot.parse(sql, read="sqlite") if s is not None]
    except sqlglot.errors.ParseError as exc:
        raise Rejected(f"not valid SQL: {str(exc).splitlines()[0][:120]}") from exc
    if len(statements) != 1:
        raise Rejected("exactly one statement is allowed")
    tree = statements[0]
    if not isinstance(tree, (exp.Select, exp.Union)):  # WITH ... SELECT parses as a Select
        raise Rejected("only SELECT queries are allowed")
    for node in tree.walk():
        if isinstance(node, FORBIDDEN):
            raise Rejected(f"{node.key.upper()} is not allowed: this connection is read-only")
    ctes = {c.alias_or_name.lower() for c in tree.find_all(exp.CTE)}
    tables = {t.name.lower() for t in tree.find_all(exp.Table)} - ctes
    unknown = tables - set(TABLES)
    if unknown:
        raise Rejected(f"table not allowed: {', '.join(sorted(unknown))}")
    if role != "manager":
        used = {c.name.lower() for c in tree.find_all(exp.Column)} & PII_COLUMNS
        if used:
            raise Rejected(f"personal data ({', '.join(sorted(used))}) is for the manager role only")
        if "guests" in tables and any(projects_star(s) for s in tree.find_all(exp.Select)):
            raise Rejected("SELECT * over guests would include personal data; name the columns")
    limit = tree.args.get("limit")
    current = None
    if limit is not None:
        try:
            current = int(limit.expression.name)
        except (AttributeError, ValueError, TypeError):
            current = None
    if current is None or current > MAX_ROWS:
        tree = tree.limit(MAX_ROWS)
    return tree.sql(dialect="sqlite")
