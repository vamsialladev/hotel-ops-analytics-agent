"""Text-to-SQL eval: execution accuracy on labelled questions, clarifying questions, and unsafe requests that must be
refused (writes, schema changes, personal data for a non-manager, injection in the question).

python -m eval.run_eval --runs 3 --price-in 0.1 --price-out 0.5            # dev set, saves a report
python -m eval.run_eval --split heldout --runs 3 --price-in 0.1 --price-out 0.5
python -m eval.run_eval --guard-only                                      # free: every reference SQL passes the guard

Every run calls the model (Claude Haiku 5.5) for each question; prices are flags, never hard-coded.
"""

import argparse
import json
import sys
from datetime import date
from pathlib import Path

from src import agent, db, sqlguard
from src.compare import matches
from src.config import LLM_MODEL

HERE = Path(__file__).resolve().parent
REPORTS = HERE / "reports"


def load(split: str) -> list[dict]:
    rows = [json.loads(line) for line in (HERE / "questions.jsonl").read_text(encoding="utf-8").splitlines() if line]
    return [r for r in rows if split == "all" or r["split"] == split]


def grade(case: dict, res, con) -> bool:
    if case["expect"] != "sql":
        return res.action == case["expect"]
    if res.action != "sql":
        return False
    _, expected = db.run(con, case["sql"])
    return matches([list(r) for r in expected], res.rows, case.get("ordered", False), case["sql"])


def percentile(values, q):
    if not values:
        return None
    values = sorted(values)
    k = (len(values) - 1) * q
    lo, hi = int(k), min(int(k) + 1, len(values) - 1)
    return values[lo] + (values[hi] - values[lo]) * (k - lo)


def summarize(runs: list[list[dict]], price_in, price_out) -> dict:
    flat = [r for run in runs for r in run]
    by_cat = {}
    for r in flat:
        by_cat.setdefault(r["category"], []).append(r["pass"])
    sql_cases = [r for r in flat if r["expect"] == "sql"]
    unsafe = [r for r in flat if r["expect"] == "refuse"]
    tokens_in = sum(r["tokens_in"] for r in flat)
    tokens_out = sum(r["tokens_out"] for r in flat)
    cost = None if price_in is None else (tokens_in * price_in + tokens_out * price_out) / 1e6 / len(flat) * 1000
    verdicts = {}
    for r in flat:
        verdicts.setdefault(r["id"], set()).add(r["pass"])
    return {
        "overall": (sum(r["pass"] for r in flat), len(flat)),
        "execution": (sum(r["pass"] for r in sql_cases), len(sql_cases)),
        "refused": (sum(r["pass"] for r in unsafe), len(unsafe)),
        "per_run": [(sum(r["pass"] for r in run), len(run)) for run in runs],
        "by_category": {k: (sum(v), len(v)) for k, v in sorted(by_cat.items())},
        "p50": percentile([r["seconds"] for r in flat], 0.5),
        "p95": percentile([r["seconds"] for r in flat], 0.95),
        "cost_per_1000": cost,
        "consistent": sum(len(v) == 1 for v in verdicts.values()),
        "cases": len(verdicts),
        "failing": sorted({r["id"] for r in flat if not r["pass"]}),
        "guard_rejections": sum(len(r["rejected"]) for r in flat),
        "ungrounded_answers": sum(bool(r["ungrounded"]) for r in flat),
    }


def pct(pair) -> str:
    ok, n = pair
    return f"{ok / n:.0%} ({ok}/{n})" if n else "n/a"


def report(split, s, args) -> str:
    cost = "not configured" if s["cost_per_1000"] is None else f"${s['cost_per_1000']:.2f}"
    lines = [
        f"# Text-to-SQL eval: {split} ({date.today().isoformat()})",
        "",
        f"- Model {LLM_MODEL}, effort low · {s['cases']} questions × {args.runs} runs · prices ${args.price_in} / "
        f"${args.price_out} per million tokens (in / out)",
        "",
        "| Metric | Result |",
        "|---|---|",
        f"| Execution accuracy (answerable questions) | **{pct(s['execution'])}** |",
        f"| Unsafe requests refused | **{pct(s['refused'])}** |",
        f"| All checks | {pct(s['overall'])} (runs: {', '.join(pct(r) for r in s['per_run'])}) |",
        f"| Same verdict in every run | {s['consistent']}/{s['cases']} questions |",
        f"| Latency per question (plan + query + answer) | p50 {s['p50']:.2f} s, p95 {s['p95']:.2f} s |",
        f"| Cost per 1,000 questions | {cost} |",
        f"| Queries the guard rejected (then retried or refused) | {s['guard_rejections']} |",
        f"| Answers with a number not in the result | {s['ungrounded_answers']} |",
        "",
        "| Category | Pass |",
        "|---|---|",
    ]
    lines += [f"| {k} | {pct(v)} |" for k, v in s["by_category"].items()]
    lines += ["", "Failing: " + (", ".join(s["failing"]) or "none")]
    return "\n".join(lines) + "\n"


def rescore(path: Path) -> int:
    """Re-grade a saved run with the current grader, re-running each saved query (no model calls)."""
    con, cases = db.connect(), {c["id"]: c for c in load("all")}
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]
    changed = 0
    for r in rows:
        case = cases[r["id"]]
        if case["expect"] == "sql" and r["action"] == "sql" and r["sql"]:
            _, got = db.run(con, r["sql"])
            _, exp = db.run(con, case["sql"])
            ok = matches([list(x) for x in exp], [list(x) for x in got], case.get("ordered", False), case["sql"])
        else:
            ok = r["action"] == case["expect"]
        changed += ok != r["pass"]
        r["pass"] = ok
    per_id = {}
    for r in rows:
        per_id.setdefault(r["id"], []).append(r["pass"])
    sql_rows = [r for r in rows if cases[r["id"]]["expect"] == "sql"]
    print(f"re-scored {len(rows)} answers, {changed} verdicts changed")
    print(
        f"execution accuracy {sum(r['pass'] for r in sql_rows)}/{len(sql_rows)}; "
        f"all {sum(r['pass'] for r in rows)}/{len(rows)}"
    )
    print("still failing:", ", ".join(sorted(k for k, v in per_id.items() if not all(v))))
    return 1 if changed else 0  # CI: the grader and the saved run must agree


def guard_only() -> int:
    bad = []
    for case in load("all"):
        if case["expect"] == "sql":
            try:
                sqlguard.check(case["sql"], case.get("role", "analyst"))
            except sqlguard.Rejected as exc:
                bad.append(f"{case['id']}: {exc}")
    print("\n".join(bad) or "every reference query passes the guard")
    return 1 if bad else 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--split", default="dev", choices=["dev", "heldout", "all"])
    parser.add_argument("--runs", type=int, default=1)
    parser.add_argument("--price-in", type=float, default=None)
    parser.add_argument("--price-out", type=float, default=None)
    parser.add_argument("--guard-only", action="store_true")
    parser.add_argument("--rescore", type=Path, help="re-grade a saved .jsonl run (no model calls)")
    parser.add_argument("--no-report", action="store_true")
    args = parser.parse_args(argv)
    if args.guard_only:
        return guard_only()
    if args.rescore:
        return rescore(args.rescore)
    con, client = db.connect(), agent.make_client()
    runs, raw = [], []
    for run in range(args.runs):
        out = []
        for case in load(args.split):
            res = agent.ask(case["question"], case.get("role", "analyst"), con=con, client=client)
            ok = grade(case, res, con)
            out.append(
                {
                    "id": case["id"],
                    "category": case["category"],
                    "expect": case["expect"],
                    "pass": ok,
                    "action": res.action,
                    "sql": res.sql,
                    "answer": res.answer,
                    "message": res.message,
                    "rejected": res.rejected,
                    "ungrounded": res.ungrounded,
                    "seconds": round(res.seconds, 3),
                    "tokens_in": res.usage["input_tokens"],
                    "tokens_out": res.usage["output_tokens"],
                    "run": run + 1,
                }
            )
            print(f"run {run + 1} {case['id']} {'pass' if ok else 'FAIL'} {res.action}", flush=True)
        runs.append(out)
        raw += out
    s = summarize(runs, args.price_in, args.price_out)
    text = report(args.split, s, args)
    print(text)
    if not args.no_report:
        REPORTS.mkdir(exist_ok=True)
        stem = REPORTS / f"sql-{date.today().isoformat()}-{args.split}"
        stem.with_suffix(".md").write_text(text, encoding="utf-8")
        stem.with_suffix(".jsonl").write_text("\n".join(json.dumps(r) for r in raw) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
