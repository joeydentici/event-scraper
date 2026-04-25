import { NextRequest, NextResponse } from "next/server";
import { supabaseAdmin } from "@/lib/supabase-admin";

const COLUMNS = [
  "score",
  "score_rationale",
  "event_name",
  "event_date",
  "location",
  "event_type",
  "is_virtual",
  "estimated_size",
  "industry",
  "organizer_name",
  "organizer_website",
  "event_url",
  "source",
  "sources",
  "dup_count",
  "opportunity_score",
  "description",
] as const;

function csvEscape(v: unknown): string {
  if (v == null) return "";
  if (Array.isArray(v)) v = v.join(", ");
  const s = String(v);
  if (/[",\n\r]/.test(s)) return `"${s.replace(/"/g, '""')}"`;
  return s;
}

export async function GET(req: NextRequest, ctx: { params: Promise<{ id: string }> }) {
  const { id } = await ctx.params;
  const tiersParam = req.nextUrl.searchParams.get("tiers");
  const tiers = tiersParam
    ? tiersParam.split(",").map((s) => Number(s.trim())).filter((n) => [1, 2, 3].includes(n))
    : [1, 2, 3];

  const sb = supabaseAdmin();
  const { data: run, error: runErr } = await sb
    .from("runs")
    .select("client_name, created_at")
    .eq("id", id)
    .maybeSingle();
  if (runErr || !run) return NextResponse.json({ error: "not found" }, { status: 404 });

  const { data: events, error: evErr } = await sb
    .from("events")
    .select("*")
    .eq("run_id", id)
    .in("score", tiers)
    .order("score", { ascending: true })
    .order("event_name", { ascending: true });
  if (evErr) return NextResponse.json({ error: evErr.message }, { status: 500 });

  const lines = [COLUMNS.join(",")];
  for (const ev of events ?? []) {
    lines.push(COLUMNS.map((c) => csvEscape((ev as Record<string, unknown>)[c])).join(","));
  }
  const body = lines.join("\n") + "\n";

  const slug = (run.client_name ?? "events").replace(/[^a-z0-9]+/gi, "-").replace(/^-+|-+$/g, "").toLowerCase() || "events";
  const tierLabel = tiers.length === 3 ? "all" : `tier-${tiers.join("-")}`;
  const filename = `${slug}-${tierLabel}-${id.slice(0, 8)}.csv`;

  return new NextResponse(body, {
    status: 200,
    headers: {
      "content-type": "text/csv; charset=utf-8",
      "content-disposition": `attachment; filename="${filename}"`,
      "cache-control": "no-store",
    },
  });
}
