import { NextRequest, NextResponse } from "next/server";
import { supabaseAdmin } from "@/lib/supabase-admin";
import type { RunSpec } from "@/lib/types";

export async function POST(req: NextRequest) {
  const body = (await req.json()) as { spec: RunSpec; client_name?: string };

  if (!body?.spec?.client_context || !body?.spec?.industries?.length || !body?.spec?.location) {
    return NextResponse.json(
      { error: "spec must include client_context, industries, and location" },
      { status: 400 },
    );
  }

  const sb = supabaseAdmin();
  const { data: run, error } = await sb
    .from("runs")
    .insert({
      spec: body.spec,
      client_name: body.client_name ?? null,
      status: "queued",
    })
    .select()
    .single();

  if (error || !run) {
    return NextResponse.json({ error: error?.message ?? "insert failed" }, { status: 500 });
  }

  const workerUrl = process.env.WORKER_URL;
  const workerSecret = process.env.WORKER_SHARED_SECRET;
  if (!workerUrl || !workerSecret) {
    await sb.from("runs").update({ status: "failed", error: "WORKER_URL or WORKER_SHARED_SECRET not configured" }).eq("id", run.id);
    return NextResponse.json({ error: "worker not configured" }, { status: 500 });
  }

  try {
    const res = await fetch(`${workerUrl}/runs`, {
      method: "POST",
      headers: {
        "content-type": "application/json",
        authorization: `Bearer ${workerSecret}`,
      },
      body: JSON.stringify({ run_id: run.id }),
    });
    if (!res.ok) {
      const text = await res.text();
      await sb.from("runs").update({ status: "failed", error: `worker ${res.status}: ${text.slice(0, 500)}` }).eq("id", run.id);
      return NextResponse.json({ error: `worker responded ${res.status}` }, { status: 502 });
    }
  } catch (e) {
    const msg = e instanceof Error ? e.message : String(e);
    await sb.from("runs").update({ status: "failed", error: `worker unreachable: ${msg}` }).eq("id", run.id);
    return NextResponse.json({ error: `worker unreachable: ${msg}` }, { status: 502 });
  }

  return NextResponse.json({ run_id: run.id });
}
