"""Red-team suite for the analytics agent: the shared corpus (hotel-ai-platform) plus this app's own cases
(redteam/cases.jsonl), through the real defences. No API calls; runs in CI.

    python scripts/run_redteam.py                 print the summary, exit 1 on any new miss
    python scripts/run_redteam.py --report        also rewrite docs/redteam-report.md

Layers:
    input      a question -> the shared input check (src/ops.py)
    output     an answer -> the shared output check, grounded on the query's rows
    retrieved  schema docs and metric definitions are the app's own files: the shared quarantine is applied as a check
    tool       SQL the model might write -> the SQL guard for the role (src/sqlguard.py), then the read-only
               connection (src/db.py); "bypass_guard" sends it straight to the connection
"""

import argparse
import io
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from hotelplatform import guardrails, injection, jsonlog, redteam  # noqa: E402

from src import db, ops, sqlguard  # noqa: E402

CASES = ROOT / "redteam" / "cases.jsonl"
OVERRIDES = ROOT / "redteam" / "overrides.json"
REPORT = ROOT / "docs" / "redteam-report.md"


def input_layer(case):
    v = ops.check_question(case.text)
    if not v.allowed:
        return redteam.Outcome("block", v.reason, ", ".join(v.reasons))
    if any(f.startswith("injection_removed") for f in v.flags):
        return redteam.Outcome("quarantine", None, v.text[:100])
    if any(f.startswith("pii_redacted") for f in v.flags):
        return redteam.Outcome("redact")
    return redteam.Outcome("allow")


def output_layer(case):
    # The app grounds on the query's rows (ops.check_answer turns them into one text); here the case's sources are
    # that text already.
    v = guardrails.check_output(case.text, ops.OUTPUT_POLICY, sources=case.context.get("sources", []),
                                input_text=case.context.get("input", ""))  # fmt: skip
    if not v.allowed:
        return redteam.Outcome("block", v.reason)
    return redteam.Outcome("redact" if v.text != case.text else "allow", None, ", ".join(v.flags))


def retrieved_layer(case):
    _, removed = injection.quarantine(case.text)
    return redteam.Outcome("quarantine" if removed else "allow")


def tool_layer(case):
    spec = json.loads(case.text)
    sql = spec["sql"]
    if not spec.get("bypass_guard"):
        try:
            sql = sqlguard.check(sql, spec["role"])
        except sqlguard.Rejected as exc:
            return redteam.Outcome("block", "sql_guard", str(exc)[:100])
    try:
        db.run(db.connect(), sql)
    except Exception as exc:  # noqa: BLE001 - a refused query is the outcome being tested
        return redteam.Outcome("block", "read_only", f"{type(exc).__name__}: {str(exc)[:80]}")
    return redteam.Outcome("allow", None, sql[:100])


HANDLERS = {"input": input_layer, "output": output_layer, "retrieved": retrieved_layer, "tool": tool_layer}


def shared_cases_for_this_app() -> list:
    overrides = json.loads(OVERRIDES.read_text(encoding="utf-8"))["expect"] if OVERRIDES.exists() else {}
    cases = redteam.shared_cases()
    for c in cases:
        if c.id in overrides:
            c.expect, c.reason = overrides[c.id], None
    return cases


def run():
    jsonlog.configure("redteam", "ci", stream=io.StringIO())
    return redteam.run(shared_cases_for_this_app(), HANDLERS), redteam.run(redteam.load_cases(CASES), HANDLERS)


def known_gaps() -> set[str]:
    lines = (ROOT / "redteam" / "known_gaps.txt").read_text(encoding="utf-8").splitlines()
    return {ln.split()[0] for ln in lines if ln.strip() and not ln.startswith("#")}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--report", action="store_true")
    args = ap.parse_args(argv)
    shared, own = run()
    for name, results in (("shared corpus", shared), ("this app's cases", own)):
        s = redteam.score(results)
        print(f"{name}: {s['passed']}/{s['cases']} passed; attacks stopped {s['attacks_stopped']}/{s['attacks']}; "
              f"false alarms {s['false_alarms']}/{s['controls']}")  # fmt: skip
        for r in results:
            if not r.passed:
                print(f"  FAIL {r.case.id} [{r.case.category}] expected {r.case.expect}, got {r.outcome.verdict}"
                      f"  ({r.outcome.detail[:80]})")  # fmt: skip
    if args.report:
        REPORT.write_text(
            redteam.report_markdown(shared, "Red-team report: shared corpus through the analytics agent")
            + "\n"
            + redteam.report_markdown(own, "Red-team report: this app's own cases (held out)"),
            encoding="utf-8",
            newline="\n",
        )
    new_failures = [r.case.id for r in shared + own if not r.passed and r.case.id not in known_gaps()]
    if new_failures:
        print("GATE FAILED: new red-team failures:", ", ".join(new_failures))
    return 1 if new_failures else 0


if __name__ == "__main__":
    sys.exit(main())
