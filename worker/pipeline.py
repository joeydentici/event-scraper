"""End-to-end pipeline for a single run.

Loads the run row, discovers events, scores with Claude, writes results back.
Updates run status/counts at each phase.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path
from typing import Any

# Make scripts/ importable
SCRIPTS_DIR = Path(__file__).parent / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

from discover_events import parse_input_spec, run_discovery  # type: ignore
from scoring import score_events
from supabase_client import get_supabase


def _log(run_id: str, line: str) -> None:
    """Append a line to the run's log column and print to stderr."""
    print(line, file=sys.stderr, flush=True)
    sb = get_supabase()
    sb.rpc("append_run_log", {"p_run_id": run_id, "p_line": line}).execute()


def _set_status(run_id: str, status: str, **fields: Any) -> None:
    sb = get_supabase()
    payload = {"status": status, **fields}
    sb.table("runs").update(payload).eq("id", run_id).execute()


def run_pipeline(run_id: str) -> None:
    """Run the full pipeline for one run_id."""
    sb = get_supabase()

    # Load run + spec
    row = sb.table("runs").select("*").eq("id", run_id).single().execute()
    run = row.data
    spec_raw = run["spec"]

    _log(run_id, f"=== Run {run_id} starting ===")
    _set_status(run_id, "running")

    # Phase 1: parse spec
    spec = parse_input_spec(spec_raw)
    _log(run_id, f"Industries: {spec['industry_displays']} | Location: {spec['location']['display']} | Year: {spec['year']}")

    # Phase 2: discover (parallel sources)
    _log(run_id, "Launching all sources in parallel...")
    t0 = time.time()
    events = run_discovery(spec)
    elapsed = time.time() - t0
    _log(run_id, f"Discovery complete in {elapsed:.0f}s — {len(events)} unique events")

    _set_status(run_id, "scoring", raw_count=len(events), deduped_count=len(events))

    if not events:
        _set_status(run_id, "complete", finished_at="now()", tier_1_count=0, tier_2_count=0, tier_3_count=0, scored_count=0)
        _log(run_id, "No events found — finishing.")
        return

    # Phase 3: score (Claude)
    _log(run_id, f"Scoring {len(events)} events with Claude...")
    t1 = time.time()
    scored = score_events(events, spec["client_context"], spec.get("exclusions", []))
    elapsed = time.time() - t1
    _log(run_id, f"Scoring complete in {elapsed:.0f}s")

    # Phase 4: write events to Supabase
    tier_counts = {1: 0, 2: 0, 3: 0}
    rows = []
    for ev in scored:
        score = ev.get("score") if ev.get("score") in (1, 2, 3) else None
        if score:
            tier_counts[score] += 1
        rows.append({
            "run_id": run_id,
            "event_name": ev.get("event_name"),
            "event_url": ev.get("event_url"),
            "event_date": ev.get("event_date"),
            "location": ev.get("location"),
            "event_type": ev.get("event_type"),
            "is_virtual": bool(ev.get("is_virtual")) if ev.get("is_virtual") is not None else None,
            "estimated_size": ev.get("estimated_size"),
            "industry": ev.get("industry"),
            "organizer_name": ev.get("organizer_name"),
            "organizer_website": ev.get("organizer_website"),
            "source": ev.get("source"),
            "sources": ev.get("sources") or [],
            "dup_count": ev.get("dup_count"),
            "opportunity_score": ev.get("opportunity_score"),
            "description": ev.get("description"),
            "score": score,
            "score_rationale": ev.get("score_rationale"),
        })

    # Batch insert in chunks of 500
    for i in range(0, len(rows), 500):
        sb.table("events").insert(rows[i:i+500]).execute()

    _set_status(
        run_id,
        "complete",
        finished_at="now()",
        scored_count=len(scored),
        tier_1_count=tier_counts[1],
        tier_2_count=tier_counts[2],
        tier_3_count=tier_counts[3],
    )
    _log(run_id, f"=== Run complete: tier 1={tier_counts[1]}, tier 2={tier_counts[2]}, tier 3={tier_counts[3]} ===")
