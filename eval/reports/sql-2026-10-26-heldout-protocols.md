# Text-to-SQL eval: heldout (2026-10-26)

- Model claude-haiku-5-5, effort low · 13 questions × 3 runs · prices $0.1 / $0.5 per million tokens (in / out)

| Metric | Result |
|---|---|
| Execution accuracy (answerable questions) | **100% (27/27)** |
| Unsafe requests refused | **100% (9/9)** |
| All checks | 100% (39/39) (runs: 100% (13/13), 100% (13/13), 100% (13/13)) |
| Same verdict in every run | 13/13 questions |
| Latency per question (plan + query + answer) | p50 2.59 s, p95 4.53 s |
| Cost per 1,000 questions | $0.29 |
| Queries the guard rejected (then retried or refused) | 0 |
| Answers with a number not in the result | 0 |

| Category | Pass |
|---|---|
| anomaly | 100% (3/3) |
| clarify | 100% (3/3) |
| count | 100% (3/3) |
| followup | 100% (9/9) |
| join | 100% (3/3) |
| ranking | 100% (3/3) |
| revenue | 100% (6/6) |
| time | 100% (3/3) |
| unsafe | 100% (6/6) |

Failing: none
