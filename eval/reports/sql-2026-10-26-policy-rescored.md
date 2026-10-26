# Policy split, re-scored without the model (2026-10-26)

Saved run: [sql-2026-10-26-policy-protocols.jsonl](sql-2026-10-26-policy-protocols.jsonl) (as measured: [sql-2026-10-26-policy-asmeasured.md](sql-2026-10-26-policy-asmeasured.md), 73%, 11/15).

Grader change: a data answer must cite one of the passages it was given, with or without the "Hotel policy: " prefix the agent adds to labels. On the first run, 4 correct answers (p01 runs 1-2, p04 runs 1 and 3) cited `[Hotel Group Brand Standards > Cancellation]` / `[... > Refunds and Escalation]` without the prefix.

`python -m eval.run_eval --rescore eval/reports/sql-2026-10-26-policy-protocols.jsonl`:

```
re-scored 15 answers, 4 verdicts changed
execution accuracy 12/12; all 15/15
still failing: 
```
