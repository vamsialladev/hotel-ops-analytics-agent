"""Daily anomaly check: run the five rules for one day and post a short summary, a text chart and the SQL to Slack.

    python scripts/daily_check.py                      # dry run for today's date replayed into the demo year
    python scripts/daily_check.py --day 2026-06-10     # a specific day of the demo data
    python scripts/daily_check.py --post               # post to SLACK_WEBHOOK_URL (prints instead if it isn't set)

The demo database covers 2025-11-01 to 2026-10-31. A scheduled run "replays" the real calendar into that year
(today's month and day), so the job finds the planted anomalies on their dates. The webhook URL is a secret: it
comes only from the environment and is never printed.
"""

import argparse
import json
import os
import sqlite3
import sys
import urllib.request
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src import anomaly  # noqa: E402
from src.config import DB_PATH, SLACK_WEBHOOK_URL_ENV  # noqa: E402

BARS = "▁▂▃▄▅▆▇█"
DATA_START, DATA_END = date(2025, 11, 1), date(2026, 10, 31)


def replay(today: date) -> date:
    """Today's month and day inside the demo year (Feb 29 becomes Feb 28)."""
    year = 2025 if (today.month, today.day) >= (11, 1) else 2026
    day = min(today.day, 28) if today.month == 2 else today.day
    return date(year, today.month, day)


def sparkline(values: list) -> str:
    if not values:
        return ""
    lo, hi = min(values), max(values)
    span = (hi - lo) or 1
    return "".join(BARS[int((v - lo) / span * (len(BARS) - 1))] for v in values)


def message(day: date, findings: list) -> dict:
    """A Slack incoming-webhook payload (plain text with mrkdwn)."""
    if not findings:
        return {"text": f"Daily check {day.isoformat()}: no anomalies in the five rules. (Simulated hotel group.)"}
    lines = [f"*Daily check {day.isoformat()}: {len(findings)} anomaly(ies)* (simulated hotel group, synthetic data)"]
    for f in findings:
        chart = f"  last 14 days: `{sparkline(f.series)}`" if f.series else ""
        lines.append(f"• *{f.kind.replace('_', ' ')}* · {f.message}{chart}")
        lines.append(f"```{f.sql.strip()}```")
    lines.append("Rules and thresholds: src/anomaly.py. Nothing changes automatically; a person decides what to do.")
    return {"text": "\n".join(lines)}


def post(payload: dict, url: str) -> int:
    request = urllib.request.Request(
        url, data=json.dumps(payload).encode("utf-8"), headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(request, timeout=15) as response:  # noqa: S310 - https webhook from a secret
        return response.status


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--day", type=date.fromisoformat, help="a day in the demo data (default: today, replayed)")
    parser.add_argument("--post", action="store_true", help="post to Slack (needs SLACK_WEBHOOK_URL)")
    parser.add_argument("--db", type=Path, default=DB_PATH)
    args = parser.parse_args(argv)
    day = args.day or replay(date.today())
    if not DATA_START <= day <= DATA_END:
        print(f"{day} is outside the demo data ({DATA_START} to {DATA_END}).")
        return 2
    con = sqlite3.connect(f"file:{args.db.as_posix()}?mode=ro", uri=True)
    findings = anomaly.detect(con, day)
    payload = message(day, findings)
    url = os.getenv(SLACK_WEBHOOK_URL_ENV, "").strip()
    if args.post and url:
        status = post(payload, url)
        print(f"posted {len(findings)} finding(s) for {day} to Slack (HTTP {status})")
    else:
        reason = "dry run" if not args.post else f"{SLACK_WEBHOOK_URL_ENV} is not set, printing instead"
        print(f"[{reason}]\n{payload['text']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
