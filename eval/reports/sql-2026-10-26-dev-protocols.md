# Text-to-SQL eval: dev (2026-10-26)

- Model claude-haiku-5-5, effort low · 68 questions × 3 runs · prices $0.1 / $0.5 per million tokens (in / out)

| Metric | Result |
|---|---|
| Execution accuracy (answerable questions) | **99% (167/168)** |
| Unsafe requests refused | **100% (27/27)** |
| All checks | 100% (203/204) (runs: 99% (67/68), 100% (68/68), 100% (68/68)) |
| Same verdict in every run | 67/68 questions |
| Latency per question (plan + query + answer) | p50 2.45 s, p95 4.31 s |
| Cost per 1,000 questions | $0.28 |
| Queries the guard rejected (then retried or refused) | 0 |
| Answers with a number not in the result | 3 |

| Category | Pass |
|---|---|
| anomaly | 100% (18/18) |
| average | 92% (11/12) |
| clarify | 100% (9/9) |
| count | 100% (33/33) |
| followup | 100% (24/24) |
| group | 100% (12/12) |
| join | 100% (24/24) |
| pii_manager | 100% (3/3) |
| ranking | 100% (15/15) |
| rate | 100% (9/9) |
| revenue | 100% (15/15) |
| time | 100% (6/6) |
| unsafe | 100% (24/24) |

Failing: q38
