#!/usr/bin/env python3
"""
Build a CSV from scored events, ready for Google Drive upload.

Input: scored_events.json — array of events, each with score + score_rationale added
Output: events.csv — column order optimized for Sheets viewing

Usage:
    python scripts/build_csv.py --input scored_events.json --output events.csv
"""

from __future__ import annotations

import argparse
import csv
import json
import sys


COLUMN_ORDER = [
    "score",
    "score_rationale",
    "event_name",
    "event_date",
    "location",
    "event_type",         # Conference | Workshop | Tradeshow (10times only)
    "is_virtual",         # bool — useful for "no virtual" filtering
    "estimated_size",     # 10times's estimated attendance band
    "industry",
    "organizer_name",     # 10times only — pre-extracted, used in Step 2
    "organizer_website",  # 10times only — pre-extracted, used in Step 2
    "event_url",
    "source",
    "sources",            # all sources event appeared in
    "dup_count",
    "opportunity_score",  # 10times's own quality score
    "description",
]


def build_csv(events: list[dict], out_path: str) -> None:
    # Sort by score (1 first, then 2, then 3), then by name
    events_sorted = sorted(events, key=lambda e: (e.get("score", 9), (e.get("event_name") or "").lower()))

    with open(out_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=COLUMN_ORDER, extrasaction="ignore")
        writer.writeheader()
        for ev in events_sorted:
            row = {col: ev.get(col, "") for col in COLUMN_ORDER}
            # Flatten list fields
            if isinstance(row["sources"], list):
                row["sources"] = ", ".join(row["sources"])
            writer.writerow(row)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True, help="Scored events JSON")
    parser.add_argument("--output", required=True, help="Output CSV path")
    args = parser.parse_args()

    with open(args.input) as f:
        events = json.load(f)

    build_csv(events, args.output)
    print(f"Wrote {len(events)} rows to {args.output}", file=sys.stderr)

    # Print score distribution
    score_counts = {1: 0, 2: 0, 3: 0, "unscored": 0}
    for ev in events:
        s = ev.get("score")
        if s in (1, 2, 3):
            score_counts[s] += 1
        else:
            score_counts["unscored"] += 1
    print(f"Score distribution: 1={score_counts[1]}, 2={score_counts[2]}, 3={score_counts[3]}, unscored={score_counts['unscored']}", file=sys.stderr)


if __name__ == "__main__":
    main()
