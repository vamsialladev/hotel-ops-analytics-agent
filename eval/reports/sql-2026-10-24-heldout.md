# Text-to-SQL eval: heldout (2026-10-24)

- Model claude-haiku-5-5, effort low · 10 questions × 3 runs · prices $0.1 / $0.5 per million tokens (in / out)

| Metric | Result |
|---|---|
| Execution accuracy (answerable questions) | **95% (20/21)** |
| Unsafe requests refused | **100% (6/6)** |
| All checks | 97% (29/30) (runs: 90% (9/10), 100% (10/10), 100% (10/10)) |
| Same verdict in every run | 9/10 questions |
| Latency per question (plan + query + answer) | p50 2.51 s, p95 4.86 s |
| Cost per 1,000 questions | $0.31 |
| Queries the guard rejected (then retried or refused) | 0 |
| Answers with a number not in the result | 0 |

| Category | Pass |
|---|---|
| anomaly | 67% (2/3) |
| clarify | 100% (3/3) |
| count | 100% (3/3) |
| join | 100% (3/3) |
| ranking | 100% (3/3) |
| revenue | 100% (6/6) |
| time | 100% (3/3) |
| unsafe | 100% (6/6) |

Failing: h03
