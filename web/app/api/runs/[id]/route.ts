import { NextRequest, NextResponse } from "next/server";
import { supabaseAdmin } from "@/lib/supabase-admin";

export async function GET(_req: NextRequest, ctx: { params: Promise<{ id: string }> }) {
  const { id } = await ctx.params;
  const sb = supabaseAdmin();
  const { data: run, error: runErr } = await sb.from("runs").select("*").eq("id", id).maybeSingle();
  if (runErr) return NextResponse.json({ error: runErr.message }, { status: 500 });
  if (!run) return NextResponse.json({ error: "not found" }, { status: 404 });

  const { data: events, error: evErr } = await sb
    .from("events")
    .select("*")
    .eq("run_id", id)
    .order("score", { ascending: true, nullsFirst: false })
    .order("event_name", { ascending: true });

  if (evErr) return NextResponse.json({ error: evErr.message }, { status: 500 });

  return NextResponse.json({ run, events: events ?? [] });
}
