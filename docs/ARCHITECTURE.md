# Architecture

## A question, start to finish

```mermaid
sequenceDiagram
    actor M as Manager
    participant UI as Streamlit (app.py)
    participant A as agent.ask
    participant L as Claude Haiku 5.5
    participant G as sqlguard.check
    participant D as SQLite (read-only)
    M->>UI: "Which room type earned the most at Mountain Lodge in 2026?"
    UI->>A: question, role
    A->>L: rules + schema + definitions + question (structured JSON)
    L-->>A: action=sql, SQL, chart
    A->>G: SQL, role
    alt rejected
        G-->>A: reason
        A->>L: question + "your SQL was rejected: reason" (once)
    end
    G-->>A: SQL with LIMIT
    A->>D: run (3 s limit)
    D-->>A: columns, rows
    A->>L: question + first 20 rows
    L-->>A: 1-3 sentence answer
    A-->>UI: answer, rows, chart, SQL, flagged numbers
```

## Components

| Module | Job |
|---|---|
| `src/schema.py` | Tables, columns, personal-data columns, metric definitions; what the model is told |
| `src/agent.py` | Plan → guard → run → answer; one retry after a rejection |
| `src/sqlguard.py` | Parses with sqlglot and enforces the rules; returns the SQL to run |
| `src/db.py` | Read-only connection and query time limit |
| `src/compare.py` | Execution accuracy for the eval |
| `src/anomaly.py` | Five SQL rules, backfill, scoring against planted anomalies |
| `scripts/daily_check.py` | The daily job: detect, format, post to Slack or print |
| `scripts/make_db.py` | The synthetic databases (seeds 42 and 7) |
| `app.py` | Ask, Daily anomalies, How it works |

## Data

`data/hotel.db` (seed 42) is what the app, the eval and CI use; `data/hotel_heldout.db` (seed 7) only tests the
detector. `*.planted.json` lists each year's planted anomalies; the detector never reads them.

Tables: properties, rooms, guests (full_name, email, phone are personal data), rates, bookings, activities,
activity_bookings, refunds, feedback.
