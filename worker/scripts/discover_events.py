#!/usr/bin/env python3
"""
Event Discovery orchestrator.

Reads a structured input spec (JSON), runs all 4 sources in parallel,
dedupes, and writes a JSON file of unique events ready for scoring.

Usage:
    python scripts/discover_events.py --input spec.json --output events.json

Input spec format (spec.json):
{
    "client_context": "Speaker is a former D1 athlete, books K-12 athletic directors...",
    "industries": ["Education", "Business Services"],
    "sub_topics": ["K-12", "athletic directors"],
    "event_types": ["conferences", "tradeshows"],
    "location": "Texas",
    "year": 2026,
    "target_count": 100,
    "exclusions": ["no virtual"],
    "skip_sources": []                  # optional: ["10times"] to skip specific sources
}

Output (events.json):
[
    {
        "event_name": "...",
        "event_url": "...",
        "event_date": "...",
        "location": "...",
        "industry": "...",
        "description": "...",
        "source": "...",
        "sources": ["10times", "google"],
        "dup_count": 2
    },
    ...
]

Performance:
    All 4 sources fire in parallel as separate threads.
    Total time = max(slowest source). Typical: 5-10 minutes.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

from utils import normalize_industry, normalize_location, load_industries
from sources import fetch_tentimes, fetch_sessionize, fetch_cvent, fetch_general_google
from dedup import dedupe_events, filter_obvious_garbage, filter_by_exclusions


def parse_input_spec(spec: dict) -> dict:
    """Validate and normalize the input spec."""
    industries_raw = spec.get("industries", [])
    industries_data = load_industries()

    # Map free-text industries to verified slugs
    industry_slugs = []
    industry_displays = []
    unknown = []
    for ind in industries_raw:
        slug = normalize_industry(ind, industries_data)
        if slug:
            if slug not in industry_slugs:  # dedupe
                industry_slugs.append(slug)
                # Look up display name
                for entry in industries_data["industries"]:
                    if entry["slug"] == slug:
                        industry_displays.append(entry["display"])
                        break
        else:
            unknown.append(ind)

    if unknown:
        print(f"WARNING: unknown industries (will be used in Serper but not 10times): {unknown}", file=sys.stderr)

    location = normalize_location(spec.get("location", "nationwide"))

    parsed = {
        "client_context": spec.get("client_context", "").strip(),
        "industries_raw": industries_raw,
        "industry_slugs": industry_slugs,
        "industry_displays": industry_displays,
        "industries_unknown": unknown,
        "sub_topics": spec.get("sub_topics", []),
        "event_types": spec.get("event_types", ["conferences"]),
        "location": location,
        "year": spec.get("year", 2026),
        "target_count": spec.get("target_count", 100),
        "exclusions": spec.get("exclusions", []),
        "skip_sources": [s.lower() for s in spec.get("skip_sources", [])],
    }
    return parsed


def print_run_plan(spec: dict) -> None:
    """Print a clear summary of what's about to run."""
    loc = spec["location"]
    print("=" * 60, file=sys.stderr)
    print("EVENT DISCOVERY — RUN PLAN", file=sys.stderr)
    print("=" * 60, file=sys.stderr)
    print(f"Client context: {spec['client_context'][:80]}{'...' if len(spec['client_context']) > 80 else ''}", file=sys.stderr)
    print(f"Industries: {', '.join(spec['industry_displays']) or '(none mapped to 10times)'}", file=sys.stderr)
    if spec["industries_unknown"]:
        print(f"  Unknown (Serper-only): {', '.join(spec['industries_unknown'])}", file=sys.stderr)
    if spec["sub_topics"]:
        print(f"Sub-topics: {', '.join(spec['sub_topics'])}", file=sys.stderr)
    print(f"Event types: {', '.join(spec['event_types'])}", file=sys.stderr)
    print(f"Location: {loc['display']} (type={loc['type']}, cities={len(loc['city_slugs'])})", file=sys.stderr)
    print(f"Year: {spec['year']}", file=sys.stderr)
    print(f"Target events: {spec['target_count']}", file=sys.stderr)
    print(f"Skip sources: {spec['skip_sources'] or '(none)'}", file=sys.stderr)
    print("=" * 60, file=sys.stderr)


def run_discovery(spec: dict) -> list[dict]:
    """Fire all 4 sources in parallel and return merged, deduped event list."""
    # Build serper-friendly industry list (combine displays + unknowns)
    serper_industries = spec["industry_displays"] + spec["industries_unknown"]
    if not serper_industries:
        serper_industries = [""]  # so Serper still fires generic queries

    # Build serper location string
    loc = spec["location"]
    if loc["type"] == "nationwide":
        loc_text = "USA"
    elif loc["type"] == "state":
        loc_text = loc["display"]
    elif loc["type"] == "city":
        loc_text = loc["display"]
    elif loc["type"] == "region":
        loc_text = loc["display"]
    else:
        loc_text = None

    # Define source jobs
    skip = set(spec["skip_sources"])
    jobs: dict[str, callable] = {}

    if "10times" not in skip:
        jobs["10times"] = lambda: fetch_tentimes(
            spec["industry_slugs"],
            spec["location"],
            spec["event_types"],
        )
    if "sessionize" not in skip:
        jobs["sessionize"] = lambda: fetch_sessionize(
            serper_industries,
            spec["event_types"],
            spec["year"],
            loc_text,
        )
    if "cvent" not in skip:
        jobs["cvent"] = lambda: fetch_cvent(
            serper_industries,
            spec["event_types"],
            spec["year"],
            loc_text,
        )
    if "google" not in skip:
        jobs["google"] = lambda: fetch_general_google(
            serper_industries,
            spec["event_types"],
            spec["year"],
            loc_text,
            spec["sub_topics"],
        )

    print(f"\nLaunching {len(jobs)} sources in parallel: {list(jobs.keys())}\n", file=sys.stderr)

    all_events = []
    start_time = time.time()
    with ThreadPoolExecutor(max_workers=len(jobs)) as executor:
        futures = {executor.submit(fn): name for name, fn in jobs.items()}
        for future in as_completed(futures):
            name = futures[future]
            try:
                events = future.result()
                all_events.extend(events)
                elapsed = time.time() - start_time
                print(f"[{elapsed:.0f}s] {name} done: {len(events)} events", file=sys.stderr)
            except Exception as e:
                print(f"ERROR in source {name}: {e}", file=sys.stderr)

    elapsed_total = time.time() - start_time
    print(f"\nAll sources complete in {elapsed_total:.0f}s. Raw total: {len(all_events)}", file=sys.stderr)

    # Filter + dedupe
    print("Filtering obvious garbage...", file=sys.stderr)
    filtered = filter_obvious_garbage(all_events)
    print(f"  Kept {len(filtered)} of {len(all_events)}", file=sys.stderr)

    print("Deduping...", file=sys.stderr)
    deduped = dedupe_events(filtered)
    print(f"  {len(deduped)} unique events after dedup", file=sys.stderr)

    if spec.get("exclusions"):
        print(f"Applying exclusions: {spec['exclusions']}...", file=sys.stderr)
        before = len(deduped)
        deduped = filter_by_exclusions(deduped, spec["exclusions"])
        print(f"  Kept {len(deduped)} of {before} after exclusions", file=sys.stderr)

    return deduped


def main():
    parser = argparse.ArgumentParser(description="Event Discovery orchestrator")
    parser.add_argument("--input", required=True, help="Path to input spec JSON file")
    parser.add_argument("--output", required=True, help="Path to write deduped events JSON file")
    parser.add_argument("--dry-run", action="store_true", help="Print run plan but don't actually scrape")
    args = parser.parse_args()

    with open(args.input) as f:
        raw_spec = json.load(f)

    spec = parse_input_spec(raw_spec)
    print_run_plan(spec)

    if args.dry_run:
        print("\nDRY RUN — exiting before scrape.", file=sys.stderr)
        return

    events = run_discovery(spec)

    with open(args.output, "w") as f:
        json.dump(events, f, indent=2, default=str)

    print(f"\nWrote {len(events)} events to {args.output}", file=sys.stderr)


if __name__ == "__main__":
    main()
