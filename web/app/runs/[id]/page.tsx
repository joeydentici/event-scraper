import { notFound } from "next/navigation";
import { supabaseAdmin } from "@/lib/supabase-admin";
import { RunDetail } from "@/components/run-detail";
import type { EventRow, Run } from "@/lib/types";

export const dynamic = "force-dynamic";

export default async function RunPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const sb = supabaseAdmin();
  const { data: run } = await sb.from("runs").select("*").eq("id", id).maybeSingle();
  if (!run) notFound();

  const { data: events } = await sb
    .from("events")
    .select("*")
    .eq("run_id", id)
    .order("score", { ascending: true, nullsFirst: false })
    .order("event_name", { ascending: true });

  return <RunDetail runId={id} initialRun={run as Run} initialEvents={(events ?? []) as EventRow[]} />;
}
