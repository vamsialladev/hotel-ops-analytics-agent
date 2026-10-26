# Text-to-SQL eval: policy (2026-10-26)

- Model claude-haiku-5-5, effort low · 5 questions × 3 runs · prices $0.1 / $0.5 per million tokens (in / out)

| Metric | Result |
|---|---|
| Execution accuracy (answerable questions) | **67% (8/12)** |
| Unsafe requests refused | **100% (3/3)** |
| All checks | 73% (11/15) (runs: 60% (3/5), 80% (4/5), 80% (4/5)) |
| Same verdict in every run | 3/5 questions |
| Latency per question (plan + query + answer) | p50 5.40 s, p95 6.98 s |
| Cost per 1,000 questions | $0.53 |
| Queries the guard rejected (then retried or refused) | 0 |
| Answers with a number not in the result | 0 |

| Category | Pass |
|---|---|
| policy | 67% (8/12) |
| policy_only | 100% (3/3) |

Failing: p01, p04
