"""Claude-based event scoring.

Scores each event 1/2/3 against the client context, in parallel batches of 50.
Extracts missing date/location from title+snippet when it can.
"""

from __future__ import annotations

import json
import os
import re
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed

from anthropic import Anthropic

MODEL = "claude-sonnet-4-6"
BATCH_SIZE = 50
MAX_WORKERS = 6

_client: Anthropic | None = None


def _get_client() -> Anthropic:
    global _client
    if _client is None:
        api_key = os.environ.get("ANTHROPIC_API_KEY")
        if not api_key:
            raise RuntimeError("ANTHROPIC_API_KEY not set")
        _client = Anthropic(api_key=api_key)
    return _client


SYSTEM_PROMPT = """You score events for a speaker-booking agency.

For each event, return a score and a one-line rationale:
- 1 (Hot fit) — strong match on industry, audience, format. Speaker's target attendees would attend.
- 2 (Workable) — adjacent fit. Right industry OR right audience, but not both tightly.
- 3 (Unqualified) — wrong audience, wrong format, virtual-only when in-person wanted, listing pages, etc.

Also extract missing data when available:
- event_date from title/description (e.g. "SXSW EDU 2026" → "2026"; "March 9-12, 2026" → "March 9-12, 2026")
- location from title/description (e.g. "Austin, TX" or "Orlando")
- Leave null if genuinely not present.

Apply user exclusions strictly. If exclusions say "no virtual", anything with virtual/online/remote/webinar in the name gets a 3 with rationale "excluded: virtual".

Be honest. Typical split: 10-20% tier 1, 30-40% tier 2, 40-50% tier 3. Don't inflate scores."""


def _build_user_message(batch: list[dict], client_context: str, exclusions: list[str]) -> str:
    lines = [
        f"Client context: {client_context}",
        f"Exclusions: {exclusions if exclusions else 'none'}",
        "",
        "Score these events. Reply with ONLY a JSON array, one object per event in the same order, with these fields:",
        '  {"score": 1|2|3, "score_rationale": "one line", "event_date": "extracted or null", "location": "extracted or null"}',
        "",
        "Events:",
    ]
    for i, ev in enumerate(batch):
        name = ev.get("event_name") or ""
        desc = ev.get("description") or ""
        url = ev.get("event_url") or ""
        cur_date = ev.get("event_date") or ""
        cur_loc = ev.get("location") or ""
        lines.append(
            f"[{i}] name: {name}\n    date: {cur_date}\n    location: {cur_loc}\n    url: {url}\n    desc: {desc[:300]}"
        )
    return "\n".join(lines)


def _score_batch(batch: list[dict], client_context: str, exclusions: list[str]) -> list[dict]:
    """Score one batch. Returns list of {score, rationale, event_date, location} in same order."""
    user_msg = _build_user_message(batch, client_context, exclusions)
    client = _get_client()

    try:
        resp = client.messages.create(
            model=MODEL,
            max_tokens=8192,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_msg}],
        )
        text = resp.content[0].text  # type: ignore
    except Exception as e:
        print(f"Scoring batch failed: {e}", file=sys.stderr)
        return [{"score": None, "score_rationale": f"scoring error: {e}"} for _ in batch]

    # Strip any markdown fences
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip(), flags=re.MULTILINE).strip()

    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        # Try to pull the first JSON array out of the text
        m = re.search(r"\[.*\]", text, re.DOTALL)
        if not m:
            print(f"Could not parse JSON from response: {text[:500]}", file=sys.stderr)
            return [{"score": None, "score_rationale": "unparseable scoring response"} for _ in batch]
        try:
            parsed = json.loads(m.group(0))
        except json.JSONDecodeError:
            return [{"score": None, "score_rationale": "unparseable scoring response"} for _ in batch]

    # Pad if model returned fewer items
    while len(parsed) < len(batch):
        parsed.append({"score": None, "score_rationale": "missing from response"})
    return parsed[:len(batch)]


def score_events(events: list[dict], client_context: str, exclusions: list[str]) -> list[dict]:
    """Score all events in parallel batches. Returns events with score/rationale merged in."""
    if not events:
        return []

    batches = [events[i:i+BATCH_SIZE] for i in range(0, len(events), BATCH_SIZE)]
    results: list[list[dict]] = [[] for _ in batches]

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = {executor.submit(_score_batch, batch, client_context, exclusions): i for i, batch in enumerate(batches)}
        for future in as_completed(futures):
            i = futures[future]
            results[i] = future.result()

    # Merge scores back onto events
    merged = []
    for batch, scores in zip(batches, results):
        for ev, sc in zip(batch, scores):
            out = dict(ev)
            if sc.get("score") in (1, 2, 3):
                out["score"] = sc["score"]
            out["score_rationale"] = sc.get("score_rationale")
            # Fill in missing date/location if model extracted them
            if not out.get("event_date") and sc.get("event_date"):
                out["event_date"] = sc["event_date"]
            if not out.get("location") and sc.get("location"):
                out["location"] = sc["location"]
            merged.append(out)

    return merged
