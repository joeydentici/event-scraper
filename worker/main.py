"""FastAPI entry point — accepts run requests, kicks off background pipeline."""

from __future__ import annotations

import os
import threading
import traceback
from typing import Any

from fastapi import FastAPI, HTTPException, Header
from pydantic import BaseModel, Field

from pipeline import run_pipeline
from supabase_client import get_supabase

app = FastAPI(title="Event Scraper Worker")

WORKER_SHARED_SECRET = os.environ.get("WORKER_SHARED_SECRET", "")


class RunRequest(BaseModel):
    run_id: str = Field(..., description="Supabase runs.id UUID — must already exist")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/runs")
def start_run(req: RunRequest, authorization: str | None = Header(default=None)) -> dict[str, Any]:
    if not WORKER_SHARED_SECRET:
        raise HTTPException(status_code=500, detail="Worker not configured: WORKER_SHARED_SECRET missing")
    if authorization != f"Bearer {WORKER_SHARED_SECRET}":
        raise HTTPException(status_code=401, detail="Invalid authorization")

    sb = get_supabase()
    row = sb.table("runs").select("*").eq("id", req.run_id).maybe_single().execute()
    if not row.data:
        raise HTTPException(status_code=404, detail=f"Run {req.run_id} not found")

    thread = threading.Thread(target=_run_with_error_handling, args=(req.run_id,), daemon=True)
    thread.start()

    return {"run_id": req.run_id, "status": "started"}


def _run_with_error_handling(run_id: str) -> None:
    try:
        run_pipeline(run_id)
    except Exception as e:
        tb = traceback.format_exc()
        sb = get_supabase()
        sb.table("runs").update({
            "status": "failed",
            "error": f"{e}\n\n{tb}",
        }).eq("id", run_id).execute()


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))
