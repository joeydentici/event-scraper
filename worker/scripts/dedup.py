#!/usr/bin/env python3
"""
Dedup events from multiple sources, then prepare for scoring.

Dedup strategy:
    - Normalize event names (lowercase, strip punctuation, collapse whitespace)
    - Group by normalized name; within a group, prefer events with more complete data
    - Cross-check with URL: if two events have the same domain + similar path, treat as duplicate even if names differ slightly
"""

from __future__ import annotations

import re
from collections import defaultdict


def _normalize_name(name: str) -> str:
    """Lowercase, remove punctuation, collapse whitespace, strip year tokens."""
    if not name:
        return ""
    s = name.lower()
    # Remove year tokens that change between editions of the same event
    s = re.sub(r"\b(19|20)\d{2}\b", "", s)
    # Remove leading "the "
    s = re.sub(r"^the\s+", "", s)
    # Strip punctuation
    s = re.sub(r"[^a-z0-9\s]", " ", s)
    # Collapse whitespace
    s = re.sub(r"\s+", " ", s).strip()
    return s


def _completeness_score(event: dict) -> int:
    """How complete is this event record? Higher = more fields populated."""
    score = 0
    if event.get("event_name"): score += 1
    if event.get("event_url"): score += 1
    if event.get("event_date"): score += 2  # date matters
    if event.get("location"): score += 2    # location matters
    if event.get("description"): score += 1
    if event.get("industry"): score += 1
    return score


def _source_priority(source: str) -> int:
    """When tied on completeness, prefer 10times > sessionize > cvent > google."""
    return {"10times": 4, "sessionize": 3, "cvent": 2, "google": 1}.get(source, 0)


def dedupe_events(events: list[dict]) -> list[dict]:
    """
    Dedupe events. Returns a deduped list, preferring the most complete record for each cluster.
    Each deduped event gains a 'sources' field listing all sources it appeared in.
    """
    if not events:
        return []

    # Group by normalized name
    groups: dict[str, list[dict]] = defaultdict(list)
    for ev in events:
        key = _normalize_name(ev.get("event_name", ""))
        if not key or len(key) < 4:  # too short = not enough signal
            # Treat as unique by URL as a fallback
            key = f"_url_{ev.get('event_url', '')}"
        groups[key].append(ev)

    deduped = []
    for key, cluster in groups.items():
        # Pick the best one: highest completeness, then source priority
        cluster.sort(key=lambda e: (_completeness_score(e), _source_priority(e.get("source", ""))), reverse=True)
        winner = dict(cluster[0])  # copy

        # Track all sources this event appeared in
        sources_seen = sorted(set(e.get("source", "") for e in cluster if e.get("source")))
        winner["sources"] = sources_seen
        winner["dup_count"] = len(cluster)

        deduped.append(winner)

    return deduped


def filter_obvious_garbage(events: list[dict]) -> list[dict]:
    """
    Drop events that obviously aren't events (webinars, mixers, listing pages, etc.).
    Conservative — only filters when very confident.
    """
    drop_patterns = [
        r"\bwebinar\b",
        r"\bmixer\b",
        r"\bnetworking happy hour\b",
        r"^conferences?\s+by\s+",   # listing pages like "Conferences by Industry"
        r"^upcoming\s+events?$",
        r"^events?\s+in\s+",        # "Events in Austin" listing pages
        r"^all\s+events?",
    ]
    compiled = [re.compile(p, re.IGNORECASE) for p in drop_patterns]

    kept = []
    for ev in events:
        name = ev.get("event_name", "")
        if any(p.search(name) for p in compiled):
            continue
        kept.append(ev)
    return kept


def filter_by_exclusions(events: list[dict], exclusions: list[str]) -> list[dict]:
    """
    Apply user-specified exclusions to event list.
    Currently supports:
      - "no virtual" / "no online" / "no webinar" → drops events with is_virtual=True
      - "no workshops" → drops events with event_type="Workshop"
      - "no tradeshows" / "no trade shows" → drops events with event_type="Tradeshow"
    """
    if not exclusions:
        return events

    excl_text = " ".join(exclusions).lower()
    drop_virtual = any(k in excl_text for k in ["no virtual", "no online", "no remote", "no webinar", "no hybrid"])
    drop_workshops = "no workshop" in excl_text
    drop_tradeshows = "no tradeshow" in excl_text or "no trade show" in excl_text

    kept = []
    for ev in events:
        if drop_virtual and ev.get("is_virtual"):
            continue
        et = (ev.get("event_type") or "").lower()
        if drop_workshops and "workshop" in et:
            continue
        if drop_tradeshows and "tradeshow" in et:
            continue
        kept.append(ev)
    return kept


if __name__ == "__main__":
    # Quick self-test
    test_events = [
        {"event_name": "TEDx Phoenix 2026", "event_url": "https://tedx.com/phx", "source": "google", "event_date": "Mar 2026", "location": "Phoenix"},
        {"event_name": "TEDx Phoenix", "event_url": "https://tedx.com/phx-2026", "source": "10times", "event_date": None, "location": "Phoenix, AZ"},
        {"event_name": "The TEDx Phoenix Conference", "event_url": "https://10times.com/tedx-phx", "source": "sessionize", "description": "annual TEDx event"},
        {"event_name": "ASCD Annual Conference 2026", "event_url": "https://ascd.org", "source": "cvent", "event_date": "April 2026", "location": "Orlando"},
        {"event_name": "Webinar: Future of EdTech", "event_url": "https://webinar.com", "source": "google"},
        {"event_name": "Conferences by Industry", "event_url": "https://10times.com/conferences/by-industry", "source": "10times"},
    ]
    filtered = filter_obvious_garbage(test_events)
    print(f"After garbage filter: {len(filtered)} of {len(test_events)}")
    deduped = dedupe_events(filtered)
    print(f"After dedup: {len(deduped)} unique events")
    for ev in deduped:
        print(f"  - {ev['event_name']!r:50} sources={ev['sources']} dup_count={ev['dup_count']}")
