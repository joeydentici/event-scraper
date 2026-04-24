#!/usr/bin/env python3
"""
Source modules for event discovery.

Each function returns list of normalized event dicts:
    {
        "event_name": str,
        "event_url": str,
        "event_date": str | None,        # raw date string if available
        "location": str | None,          # raw location if available
        "industry": str | None,          # source-reported industry
        "description": str | None,
        "source": str,                   # "10times" | "sessionize" | "cvent" | "google"
        "raw": dict                      # original record for debugging
    }
"""

from __future__ import annotations

import os
import sys
from utils import serper_search_batch, apify_run_batch, load_industries


# ============================================================
# 10times via Apify
# ============================================================

def build_tentimes_urls(industry_slugs: list[str], location: dict, event_types: list[str]) -> list[dict]:
    """
    Build the list of 10times scrape URLs based on industries, location, event types.
    Returns list of {"url": str, "label": str} dicts.

    Strategy:
        - nationwide: /usa/{industry}/{event_type} for each industry × event_type
        - state: /{city}-us/{industry} for each city × industry (state URLs are weaker)
                 PLUS /{state}state-us as backup if no industries given
        - city: /{city}-us/{industry} for the city × industries
        - region: /{city}-us/{industry} for each city in region × industries
    """
    urls = []
    loc_type = location["type"]

    if loc_type == "nationwide":
        # /usa/{industry}/{event_type} — broadest, one URL per industry × event_type
        for ind in industry_slugs:
            for et in event_types:
                urls.append({
                    "url": f"https://10times.com/usa/{ind}/{et}",
                    "label": f"usa-{ind}-{et}",
                })
        # If no industries, fall back to broad nationwide event lists
        if not industry_slugs:
            for et in event_types:
                urls.append({
                    "url": f"https://10times.com/usa/{et}",
                    "label": f"usa-{et}",
                })

    elif loc_type in ("state", "city", "region"):
        cities = location["city_slugs"]
        if industry_slugs:
            for city in cities:
                for ind in industry_slugs:
                    urls.append({
                        "url": f"https://10times.com/{city}-us/{ind}",
                        "label": f"{city}-{ind}",
                    })
        else:
            # No industry filter — use city + event type
            for city in cities:
                for et in event_types:
                    urls.append({
                        "url": f"https://10times.com/{city}-us/{et}",
                        "label": f"{city}-{et}",
                    })

    return urls


def fetch_tentimes(industry_slugs: list[str], location: dict, event_types: list[str], max_per_url: int = 50, max_concurrent: int = 25) -> list[dict]:
    """
    Run 10times scrapes in parallel via Apify.
    Returns normalized event list.
    """
    actor_id = os.environ.get("TENTIMES_ACTOR_ID")
    apify_token = os.environ.get("APIFY_TOKEN")

    if not actor_id or not apify_token:
        print("SKIPPING 10times: TENTIMES_ACTOR_ID or APIFY_TOKEN not set", file=sys.stderr)
        return []

    urls = build_tentimes_urls(industry_slugs, location, event_types)

    if not urls:
        print("SKIPPING 10times: no URLs to scrape (empty input)", file=sys.stderr)
        return []

    if len(urls) > max_concurrent:
        print(f"NOTE: 10times fan-out has {len(urls)} URLs, capping at {max_concurrent}", file=sys.stderr)
        urls = urls[:max_concurrent]

    print(f"10times: launching {len(urls)} parallel scrapes...", file=sys.stderr)

    runs = [
        {
            "actor_id": actor_id,
            "input": {"searchUrl": u["url"], "maxItems": max_per_url},
            "label": u["label"],
        }
        for u in urls
    ]

    all_results = apify_run_batch(runs, apify_token)

    events = []
    for url_meta, results in zip(urls, all_results):
        for item in results or []:
            events.append(_normalize_tentimes_event(item, url_meta))

    print(f"10times: collected {len(events)} raw events from {len(urls)} URLs", file=sys.stderr)
    return events


def _normalize_tentimes_event(item: dict, url_meta: dict) -> dict:
    """
    Map a 10times Apify result (zen-studio/10times-events-scraper schema) to our standard event shape.

    Real schema includes:
        - name, url, description (top-level strings)
        - startDate, endDate (ISO YYYY-MM-DD)
        - type ("Conference", "Workshop", "Tradeshow")
        - location (nested: cityName, state, countryName, venueName, venueAddress)
        - categories (list of {id, name, ...})
        - organizer (nested: name, website, address)
        - hybrid, onlineEvent (bools/ints — 1 means yes)
        - eventEstimatedSize ("300-500", "500-1000", etc.)
        - stats (nested: opportunityScore, etc.)
    """
    # Build a readable location string from the nested location object
    loc = item.get("location") or {}
    if isinstance(loc, dict):
        loc_parts = [loc.get("venueName"), loc.get("cityName"), loc.get("state"), loc.get("countryName")]
        location_str = ", ".join([p for p in loc_parts if p])
    elif isinstance(loc, str):
        location_str = loc
    else:
        location_str = None

    # Build a readable date range
    start = item.get("startDate")
    end = item.get("endDate")
    if start and end and start != end:
        date_str = f"{start} → {end}"
    else:
        date_str = start or item.get("date") or item.get("dates")

    # Build industry string from categories list
    cats = item.get("categories") or []
    if isinstance(cats, list) and cats:
        industry_str = ", ".join([c.get("name", "") for c in cats if isinstance(c, dict) and c.get("name")])
    else:
        industry_str = item.get("industry") or item.get("category") or None

    # Pull organizer info — useful for Step 2 enrichment, store now even though Step 1 doesn't use it
    org = item.get("organizer") or {}
    organizer_name = org.get("name") if isinstance(org, dict) else None
    organizer_website = org.get("website") if isinstance(org, dict) else None

    return {
        "event_name": item.get("name") or item.get("title") or item.get("shortName") or "",
        "event_url": item.get("url") or item.get("link") or item.get("eventUrl") or "",
        "event_date": date_str,
        "location": location_str,
        "industry": industry_str,
        "description": item.get("description") or item.get("punchLine") or None,
        "event_type": item.get("type"),                          # "Conference" | "Workshop" | "Tradeshow"
        "is_virtual": bool(item.get("onlineEvent")) or bool(item.get("hybrid")),
        "estimated_size": item.get("eventEstimatedSize"),
        "opportunity_score": (item.get("stats") or {}).get("opportunityScore") if isinstance(item.get("stats"), dict) else None,
        "organizer_name": organizer_name,
        "organizer_website": organizer_website,
        "source": "10times",
        "raw": item,
    }


# ============================================================
# Sessionize via Serper
# ============================================================

def fetch_sessionize(industries: list[str], event_types: list[str], year: int, location_text: str | None) -> list[dict]:
    """
    Search Sessionize via Serper.
    Sessionize is a CFP and speaker management platform — strong for tech/leadership/CFP-focused events.
    """
    queries = []
    loc_part = f" {location_text}" if location_text else ""

    for ind in industries:
        for et in event_types:
            queries.append(f"site:sessionize.com {ind} {et} {year}{loc_part}")
        # CFP-specific query (Sessionize's bread and butter)
        queries.append(f"site:sessionize.com {ind} call for speakers {year}{loc_part}")

    print(f"Sessionize: firing {len(queries)} parallel Serper queries...", file=sys.stderr)
    raw = serper_search_batch(queries, num=15)

    events = [_normalize_serper_result(r, "sessionize") for r in raw if _is_event_url(r.get("link", ""), "sessionize.com")]
    print(f"Sessionize: collected {len(events)} raw events from {len(queries)} queries", file=sys.stderr)
    return events


# ============================================================
# Cvent via Serper
# ============================================================

def fetch_cvent(industries: list[str], event_types: list[str], year: int, location_text: str | None) -> list[dict]:
    """Search Cvent (cvent.com/d/...) via Serper. Strong for large professional conferences."""
    queries = []
    loc_part = f" {location_text}" if location_text else ""

    for ind in industries:
        for et in event_types:
            # /d/ is Cvent's event landing page path
            queries.append(f"site:cvent.com/d {ind} {et} {year}{loc_part}")
        queries.append(f"site:cvent.com/d {ind} conference {year}{loc_part}")

    print(f"Cvent: firing {len(queries)} parallel Serper queries...", file=sys.stderr)
    raw = serper_search_batch(queries, num=15)

    events = [_normalize_serper_result(r, "cvent") for r in raw if _is_event_url(r.get("link", ""), "cvent.com")]
    print(f"Cvent: collected {len(events)} raw events from {len(queries)} queries", file=sys.stderr)
    return events


# ============================================================
# General Google via Serper
# ============================================================

def fetch_general_google(industries: list[str], event_types: list[str], year: int, location_text: str | None, sub_topics: list[str] | None = None) -> list[dict]:
    """
    Free-form Google search. Picks up niche industry sites that Sessionize/Cvent miss.
    Uses sub-topics to add precision (e.g., "K-12", "superintendents", "athletic directors").
    """
    queries = []
    loc_part = f" {location_text}" if location_text else ""
    sub_part_list = sub_topics or [""]

    for ind in industries:
        for sub in sub_part_list:
            sub_str = f" {sub}" if sub else ""
            for et in event_types:
                queries.append(f"{ind}{sub_str} {et} {year}{loc_part}")
            # CFP-style query
            queries.append(f"{ind}{sub_str} conference call for speakers {year}{loc_part}")

    print(f"General: firing {len(queries)} parallel Serper queries...", file=sys.stderr)
    raw = serper_search_batch(queries, num=15)

    # Looser filter for general — exclude listing aggregators, but allow any individual event site
    blocklist = {"facebook.com", "linkedin.com", "youtube.com", "twitter.com", "x.com", "reddit.com", "wikipedia.org", "amazon.com", "ebay.com"}
    events = [_normalize_serper_result(r, "google") for r in raw if r.get("link") and not any(b in r["link"] for b in blocklist)]
    print(f"General: collected {len(events)} raw events from {len(queries)} queries", file=sys.stderr)
    return events


# ============================================================
# Helpers
# ============================================================

def _is_event_url(url: str, expected_domain: str) -> bool:
    """Sanity check that a Serper result is from the expected domain (filters off-domain spam)."""
    return expected_domain in (url or "").lower()


def _normalize_serper_result(item: dict, source: str) -> dict:
    """Map a Serper organic result to our standard event shape."""
    return {
        "event_name": item.get("title", "").strip(),
        "event_url": item.get("link", ""),
        "event_date": None,           # Serper doesn't reliably give us dates — extracted later if needed
        "location": None,             # same — extracted from snippet/title later if needed
        "industry": None,
        "description": item.get("snippet", ""),
        "source": source,
        "raw": item,
    }
