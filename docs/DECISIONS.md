# Decisions

Each: context, decision, tradeoff, result.

## 1. A guard decides, not the prompt

- **Context:** a prompt that says "only SELECT" is a request, not a control.
- **Decision:** `src/sqlguard.py` parses every query with sqlglot: one statement, a SELECT, allowlisted tables, no
  personal-data columns or `SELECT *` over guests unless the role is manager, LIMIT forced to ≤ 500. The connection
  is read-only too (`mode=ro` and `query_only`), with a 3 s limit.
- **Tradeoff:** a valid query that uses an unusual construct can be rejected; the model gets one retry.
- **Result:** 100% of unsafe requests refused (24/24 dev, 6/6 held-out); the guard rejected 0 generated queries in
  the final runs because the model refused first, and the tests prove the guard holds when the model doesn't.

## 2. Clarify only in two named cases

- **Context:** a clarifying question costs the manager a round trip. My first prompt said to clarify for any
  time-dependent figure without a time frame, with "cancellations" as the example.
- **Decision:** clarify only for "our hotel" / "the hotel" without a name, or occupancy without a date. No time
  frame means all data; no property means both.
- **Tradeoff:** "How many cancelled bookings at Mountain Lodge?" gets an all-time answer even if the asker meant
  this month; the SQL on screen makes that visible.
- **Result:** clarify cases 100% (9/9 dev, 3/3 held-out), and the five over-clarified dev questions now answer.

## 3. Two model calls: plan, then answer from the rows

- **Context:** the model can't write a correct answer before seeing the result.
- **Decision:** call 1 plans (clarify / refuse / SQL + chart) with structured JSON output; call 2 writes 1–3
  sentences from the first 20 rows. Numbers in the answer that are in neither the rows nor the question are flagged.
- **Tradeoff:** two calls: $0.30 per 1,000 questions, p95 4.0 s.
- **Result:** 0 answers with an ungrounded number in the final dev and held-out runs.

## 4. Fix the grader with the saved answers, not new model calls

- **Context:** the first recorded dev run scored 84%. Reading every failure showed the grader marking right answers
  wrong: a property name instead of its id, a full ranking for a "which … most?" question with the answer first,
  and a share as a percentage.
- **Decision:** fix `src/compare.py` for those three cases (with tests), and add `--rescore`, which re-runs the
  saved queries and re-grades them without calling the model.
- **Tradeoff:** a more lenient grader could pass a wrong answer; each rule is narrow and tested both ways.
- **Result:** the same answers went from 84% to 92%. The remaining failures were real model choices, fixed in the
  prompt and definitions (decision 5) before the final runs.

## 5. Define "bookings", "check-ins", and the manager's access

- **Context:** the model excluded cancelled bookings when a question said "bookings" (q30, q37), counted cancelled
  bookings as check-ins in my own reference (my label was wrong for q24/q25/h07), and refused a manager a guest's
  name even though the prompt allowed it.
- **Decision:** two definitions in the schema text ("bookings" include cancelled ones; check-ins don't) and a
  role-specific personal-data rule (the manager's prompt says the columns are allowed; the analyst's says refuse).
  The held-out set had not been run yet when the labels were fixed.
- **Tradeoff:** definitions are conventions this client would have to confirm.
- **Result:** final dev 98% (144/147), held-out 95% (20/21). Remaining misses q38 (rounding) and h03 (counted
  people, not bookings), reported and not tuned.

## 6. Deterministic anomaly rules, checked on a second year

- **Context:** the revenue manager accepts "one false alarm a month, more and I'll mute it".
- **Decision:** five SQL rules against the previous 28 days, no model. Thresholds set once on the main synthetic
  year (seed 42); a second year (seed 7) with different anomaly dates is the held-out test.
- **Tradeoff:** fixed rules won't catch a new kind of anomaly; a model could, at the cost of explainability.
- **Result:** the first thresholds caught 5/5 on both years: 1 false alarm in 11 months on the main year (a quiet
  Mountain Lodge day with 7 cancellations), 0 on the held-out year. No threshold was changed after.

## 7. The daily job replays the calendar into the demo year

- **Context:** the demo data ends on 2026-10-31; a job that checks "today" would never see an anomaly.
- **Decision:** the scheduled job checks today's month and day inside the demo year and posts only when the
  `SLACK_WEBHOOK_URL` secret is set; otherwise it prints (dry run).
- **Tradeoff:** it's a replay, labelled as such in the message.
- **Result:** on 2026-09-14 replayed, the message names the Suite rate error with a 14-day chart and the SQL.
