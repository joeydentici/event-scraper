#!/usr/bin/env python3
"""
Shared utilities for event discovery.

Functions:
    - serper_search(query, num=20): single Serper call
    - serper_search_batch(queries, num=20): parallel Serper calls
    - apify_run(actor_id, input_data, token): start + poll one Apify run
    - apify_run_batch(runs): start many Apify runs in parallel, return all results
    - normalize_industry(text): map free-text industry to verified 10times slug
    - normalize_location(text): parse location into structured form
    - load_industries(), load_state_cities(): load reference JSON
"""

from __future__ import annotations

import json
import os
import sys
import time
import urllib.request
import urllib.error
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path


# ---------------- Paths ----------------

REFERENCES_DIR = Path(__file__).parent.parent / "references"


def load_industries() -> dict:
    with open(REFERENCES_DIR / "industries.json") as f:
        return json.load(f)


def load_state_cities() -> dict:
    with open(REFERENCES_DIR / "state_cities.json") as f:
        return json.load(f)


# ---------------- Serper ----------------

SERPER_BASE = "https://google.serper.dev"


def serper_search(query: str, num: int = 20, tbs: str | None = "qdr:y") -> list[dict]:
    """One Serper search. Returns list of organic results."""
    api_key = os.environ.get("SERPER_API_KEY")
    if not api_key:
        raise RuntimeError("SERPER_API_KEY not set")

    body = {"q": query, "num": num}
    if tbs:
        body["tbs"] = tbs

    payload = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        f"{SERPER_BASE}/search",
        data=payload,
        headers={"X-API-KEY": api_key, "Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body_text = e.read().decode("utf-8", errors="replace")
        print(f"Serper error {e.code} for '{query}': {body_text}", file=sys.stderr)
        return []
    except Exception as e:
        print(f"Serper exception for '{query}': {e}", file=sys.stderr)
        return []

    return [
        {
            "title": item.get("title", ""),
            "link": item.get("link", ""),
            "snippet": item.get("snippet", ""),
            "query": query,
        }
        for item in data.get("organic", [])
    ]


def serper_search_batch(queries: list[str], num: int = 20, max_workers: int = 20) -> list[dict]:
    """Run many Serper queries in parallel. Returns flat list of results across all queries."""
    all_results = []
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(serper_search, q, num): q for q in queries}
        for future in as_completed(futures):
            try:
                all_results.extend(future.result())
            except Exception as e:
                print(f"Serper batch error: {e}", file=sys.stderr)
    return all_results


# ---------------- Apify ----------------

APIFY_BASE = "https://api.apify.com/v2"


def apify_start_run(actor_id: str, input_data: dict, token: str) -> tuple[str, str] | None:
    """Start an Apify run. Returns (run_id, dataset_id) or None on failure."""
    actor_path = actor_id.replace("/", "~")
    url = f"{APIFY_BASE}/acts/{actor_path}/runs?token={token}"
    payload = json.dumps(input_data).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        print(f"Apify run start failed ({e.code}): {body}", file=sys.stderr)
        return None
    except Exception as e:
        print(f"Apify start exception: {e}", file=sys.stderr)
        return None

    return data["data"]["id"], data["data"].get("defaultDatasetId")


def apify_poll_run(run_id: str, token: str, timeout: int = 360, poll_interval: int = 5) -> dict | None:
    """Poll a single run until it completes or times out. Returns final status data or None."""
    status_url = f"{APIFY_BASE}/actor-runs/{run_id}?token={token}"
    elapsed = 0
    while elapsed < timeout:
        time.sleep(poll_interval)
        elapsed += poll_interval
        try:
            req = urllib.request.Request(status_url)
            with urllib.request.urlopen(req, timeout=30) as resp:
                status_data = json.loads(resp.read().decode("utf-8"))
        except Exception as e:
            print(f"Poll exception for {run_id}: {e}", file=sys.stderr)
            continue

        status = status_data["data"]["status"]
        if status == "SUCCEEDED":
            return status_data["data"]
        if status in ("FAILED", "ABORTED", "TIMED-OUT"):
            print(f"Apify run {run_id} ended: {status}", file=sys.stderr)
            return None

    print(f"Apify run {run_id} timed out after {timeout}s", file=sys.stderr)
    return None


def apify_fetch_dataset(dataset_id: str, token: str) -> list[dict]:
    """Fetch results from an Apify dataset."""
    url = f"{APIFY_BASE}/datasets/{dataset_id}/items?token={token}&format=json"
    try:
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=60) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        print(f"Dataset fetch error: {e}", file=sys.stderr)
        return []


def apify_run_batch(runs: list[dict], token: str, timeout: int = 360, max_concurrent: int = 30) -> list[list[dict]]:
    """
    Run multiple Apify actor runs in parallel.

    Each run dict: {"actor_id": str, "input": dict, "label": str (optional)}
    Returns list of result lists, one per input run, in same order.
    """
    if len(runs) > max_concurrent:
        print(f"WARNING: {len(runs)} runs requested, capping at {max_concurrent}", file=sys.stderr)
        runs = runs[:max_concurrent]

    # Phase 1: start all runs in parallel
    print(f"Starting {len(runs)} Apify runs in parallel...", file=sys.stderr)
    started = []
    with ThreadPoolExecutor(max_workers=min(len(runs), 10)) as executor:
        futures = {
            executor.submit(apify_start_run, r["actor_id"], r["input"], token): (i, r)
            for i, r in enumerate(runs)
        }
        for future in as_completed(futures):
            i, r = futures[future]
            result = future.result()
            if result:
                run_id, dataset_id = result
                started.append((i, r, run_id, dataset_id))
                label = r.get("label", f"run_{i}")
                print(f"  Started [{label}]: {run_id}", file=sys.stderr)

    # Phase 2: poll all in parallel
    print(f"Polling {len(started)} runs...", file=sys.stderr)
    final_data = {}
    with ThreadPoolExecutor(max_workers=len(started) or 1) as executor:
        futures = {
            executor.submit(apify_poll_run, run_id, token, timeout): (i, dataset_id)
            for i, r, run_id, dataset_id in started
        }
        for future in as_completed(futures):
            i, dataset_id = futures[future]
            status_data = future.result()
            if status_data:
                # use latest dataset_id from status (may differ from start response in rare cases)
                ds = status_data.get("defaultDatasetId") or dataset_id
                final_data[i] = ds

    # Phase 3: fetch all datasets in parallel
    print(f"Fetching {len(final_data)} datasets...", file=sys.stderr)
    results: list[list[dict]] = [[] for _ in runs]
    with ThreadPoolExecutor(max_workers=len(final_data) or 1) as executor:
        futures = {
            executor.submit(apify_fetch_dataset, ds, token): i
            for i, ds in final_data.items()
        }
        for future in as_completed(futures):
            i = futures[future]
            results[i] = future.result()

    return results


# ---------------- Normalization ----------------

def normalize_industry(text: str, industries_data: dict | None = None) -> str | None:
    """Map free-text industry to verified 10times slug. Returns slug or None if no match."""
    if industries_data is None:
        industries_data = load_industries()

    text_lower = text.strip().lower()

    # Direct slug match
    for ind in industries_data["industries"]:
        if ind["slug"] == text_lower:
            return ind["slug"]

    # Display name match (case-insensitive, partial)
    for ind in industries_data["industries"]:
        display_lower = ind["display"].lower()
        if text_lower == display_lower or text_lower in display_lower:
            return ind["slug"]

    # Alias match
    aliases = industries_data.get("common_input_aliases", {})
    if text_lower in aliases:
        return aliases[text_lower]

    # Substring alias match
    for alias, slug in aliases.items():
        if alias in text_lower or text_lower in alias:
            return slug

    return None


def normalize_location(text: str, state_cities_data: dict | None = None) -> dict:
    """
    Parse location text into structured form.

    Returns:
        {
            "type": "nationwide" | "state" | "city" | "region",
            "state_slug": str | None,
            "city_slugs": list[str],
            "display": str
        }
    """
    if state_cities_data is None:
        state_cities_data = load_state_cities()

    text_lower = text.strip().lower()

    # Nationwide
    if text_lower in ("nationwide", "national", "us", "usa", "united states", "all", ""):
        return {
            "type": "nationwide",
            "state_slug": None,
            "city_slugs": [],
            "display": "Nationwide (US)",
        }

    # Region
    regions = state_cities_data.get("regions", {})
    region_key = text_lower.replace(" ", "").replace("-", "")
    if region_key in regions:
        state_slugs = regions[region_key]
        all_cities = []
        for s in state_slugs:
            if s in state_cities_data["states"]:
                all_cities.extend(state_cities_data["states"][s]["cities"][:3])  # top 3 per state
        return {
            "type": "region",
            "state_slug": None,
            "city_slugs": all_cities,
            "display": text.title(),
        }

    # State alias resolution
    state_aliases = state_cities_data.get("state_aliases", {})
    if text_lower in state_aliases:
        text_lower = state_aliases[text_lower]

    # State match
    if text_lower in state_cities_data["states"]:
        state_data = state_cities_data["states"][text_lower]
        return {
            "type": "state",
            "state_slug": state_data["slug"],
            "city_slugs": state_data["cities"],
            "display": text.title(),
        }

    # City match — search across all states
    text_city = text_lower.replace(" ", "").replace("-", "")
    for state_name, state_data in state_cities_data["states"].items():
        for city in state_data["cities"]:
            if city == text_city:
                return {
                    "type": "city",
                    "state_slug": state_data["slug"],
                    "city_slugs": [city],
                    "display": text.title(),
                }

    # No match — assume nationwide and warn
    print(f"WARNING: location '{text}' did not match any known state/city/region. Defaulting to nationwide.", file=sys.stderr)
    return {
        "type": "nationwide",
        "state_slug": None,
        "city_slugs": [],
        "display": f"{text} (no slug match, using nationwide)",
    }


# ---------------- Self-test ----------------

if __name__ == "__main__":
    print("Testing normalization functions...")
    print()
    print("Industries:")
    for test in ["Education", "k-12", "tech", "leadership", "Manufacturing", "Made-up"]:
        result = normalize_industry(test)
        print(f"  {test!r:20} → {result}")

    print()
    print("Locations:")
    for test in ["Texas", "TX", "California", "Austin", "Nationwide", "Southwest", "fake place"]:
        result = normalize_location(test)
        print(f"  {test!r:20} → type={result['type']}, cities={result['city_slugs'][:3]}{'...' if len(result['city_slugs']) > 3 else ''}")
