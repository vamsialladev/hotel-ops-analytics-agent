# Architecture

## System

```mermaid
flowchart LR
    U[Manager] --> UI[Streamlit app.py<br/>chat, history, share link, steps]
    UI --> LIM[limits.py]
    LIM --> RW[rewrite.py<br/>Claude Haiku 5.5]
    RW --> RET[retrieval.py<br/>BM25, 19 docs]
    RET --> PLAN[agent.plan_and_run<br/>Claude Haiku 5.5, JSON]
    PLAN --> G[sqlguard.py]
    G --> DB[(SQLite read-only)]
    DB --> ANS[agent.stream_answer<br/>Claude Haiku 5.5, streamed]
    ANS --> UI
    ANS --> LOG[requestlog.py<br/>redacted JSONL]
    CRON[GitHub Actions daily] --> AN[anomaly.py] --> DB
    AN --> SL[Slack]
```

## A question, start to finish

```mermaid
sequenceDiagram
    actor M as Manager
    participant UI as Streamlit (app.py)
    participant A as agent
    participant L as Claude Haiku 5.5
    participant G as sqlguard.check
    participant D as SQLite (read-only)
    M->>UI: "Which room type earned the most at Mountain Lodge in 2026?"
    UI->>UI: limits.blocked() (session, minute, day)
    UI->>A: plan_and_run(question, role, history)
    opt the message leans on an earlier turn
        A->>L: last 3 turns + message
        L-->>A: standalone question
    end
    A->>A: retrieval.search(question) -> table docs + definitions
    A->>L: rules + retrieved docs + question (structured JSON)
    L-->>A: action=sql, SQL, chart
    A->>G: SQL, role
    alt rejected
        G-->>A: reason
        A->>L: question + "your SQL was rejected: reason" (once)
    end
    G-->>A: SQL with LIMIT, tables read
    A->>D: run (3 s limit)
    D-->>A: columns, rows
    A-->>UI: Result with steps (shown as a status)
    UI->>A: stream_answer(result)
    A->>L: question + first 20 rows (stream)
    L-->>UI: answer text
    UI->>UI: limits.record(), requestlog.write() (redacted, no rows)
```

## Components

| Module | Job |
|---|---|
| `src/schema.py` | Tables, join partners, personal-data columns, metric definitions as retrievable docs |
| `src/retrieval.py` | BM25 over the schema docs; the docs the plan prompt is built from |
| `src/rewrite.py` | Follow-up → standalone question (one short model call, only when it looks like a follow-up) |
| `src/agent.py` | Plan → guard → run (with steps), then the streamed answer and the grounding check |
| `src/sqlguard.py` | Parses with sqlglot and enforces the rules; returns the SQL to run |
| `src/db.py` | Read-only connection and query time limit |
| `src/limits.py` | Per-session, per-minute and daily (questions and cost) limits, checked before any model call |
| `src/requestlog.py` / `src/pii.py` | One redacted JSON line per question; stage 1's redaction |
| `src/share.py` | Read-only share links (conversation inside the URL, personal data removed) |
| `src/suggest.py` | Suggested next questions from the tables the SQL read (no model call) |
| `src/compare.py` | Execution accuracy for the eval |
| `src/anomaly.py` | Five SQL rules, backfill, scoring against planted anomalies |
| `scripts/daily_check.py` | The daily job: detect, format, post to Slack or print |
| `scripts/make_db.py` | The synthetic databases (seeds 42 and 7) |
| `app.py` | Ask (chat), Daily anomalies, How it works, the shared-conversation view |

## Data

`data/hotel.db` (seed 42) is what the app, the eval and CI use; `data/hotel_heldout.db` (seed 7) only tests the
detector. `*.planted.json` lists each year's planted anomalies; the detector never reads them.

Tables: properties, rooms, guests (full_name, email, phone are personal data), rates, bookings, activities,
activity_bookings, refunds, feedback.

## Scaling path

1. Postgres (Neon) via `DATABASE_URL`, a read-only role, and the same guard (sqlglot transpiles to Postgres).
2. A daily-metrics table written once a day, so the anomaly check reads 28 rows instead of scanning bookings.
3. Limits and the request log in a shared store (Postgres) instead of files, so they survive restarts and
   several app replicas.
4. For a schema with hundreds of tables: embeddings next to BM25 for the schema docs, and a larger model for the
   plan step if the eval says so.
