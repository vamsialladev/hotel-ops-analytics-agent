"""Anomaly detector eval: run the daily check for every day of both synthetic years and compare with the planted
anomalies (the detector never reads the planted list).

python -m eval.run_anomaly_eval                 # saves eval/reports/anomaly-<date>.md
python -m eval.run_anomaly_eval --gate          # CI: fail unless all 5 are caught with at most 1 false alarm a month
"""

import argparse
import json
import sqlite3
import sys
from datetime import date

from src import anomaly
from src.config import ROOT

DATABASES = {"main (seed 42, thresholds set here)": "hotel", "held-out (seed 7, other dates)": "hotel_heldout"}
START, END = date(2025, 11, 29), date(2026, 10, 31)


def evaluate(name: str) -> dict:
    con = sqlite3.connect(f"file:{(ROOT / 'data' / f'{name}.db').as_posix()}?mode=ro", uri=True)
    planted = json.loads((ROOT / "data" / f"{name}.planted.json").read_text(encoding="utf-8"))
    alerts = anomaly.backfill(con, START, END)
    return {"alerts": alerts, **anomaly.score(alerts, planted)}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--gate", action="store_true")
    args = parser.parse_args(argv)
    lines = [
        f"# Anomaly detector eval ({date.today().isoformat()})",
        "",
        f"Every day from {START} to {END} (11 months, after 28 days of history). 5 planted anomalies per database.",
        "",
        "| Database | Caught | Missed | False alarms | Most false alarms in one month |",
        "|---|---|---|---|---|",
    ]
    ok = True
    details = []
    for label, name in DATABASES.items():
        r = evaluate(name)
        lines.append(
            f"| {label} | {len(r['caught'])}/5 | {', '.join(r['missed']) or 'none'} | {r['false_alarms']} | "
            f"{r['max_false_per_month']} |"
        )
        ok &= not r["missed"] and r["max_false_per_month"] <= 1
        details += [f"- {label}: {a.day} {a.kind} ({a.entity}): {a.message}" for a in r["false"]]
    lines += ["", "False alarms:", *(details or ["- none"])]
    text = "\n".join(lines) + "\n"
    print(text)
    if not args.gate:
        (ROOT / "eval" / "reports").mkdir(exist_ok=True)
        (ROOT / "eval" / "reports" / f"anomaly-{date.today().isoformat()}.md").write_text(text, encoding="utf-8")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
