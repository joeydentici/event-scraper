"use client";

import { useEffect, useState } from "react";
import { supabaseBrowser } from "@/lib/supabase-browser";
import type { EventRow, Run } from "@/lib/types";

type Props = { runId: string; initialRun: Run; initialEvents: EventRow[] };

export function RunDetail({ runId, initialRun, initialEvents }: Props) {
  const [run, setRun] = useState<Run>(initialRun);
  const [events, setEvents] = useState<EventRow[]>(initialEvents);

  // Poll the API route every 3s while running; switch to pure-realtime once complete.
  // Using a polling fallback since RLS locks the anon key out of reads (realtime INSERTs still fire, though).
  useEffect(() => {
    if (run.status === "complete" || run.status === "failed") return;
    const interval = setInterval(async () => {
      const res = await fetch(`/api/runs/${runId}`, { cache: "no-store" });
      if (!res.ok) return;
      const json = (await res.json()) as { run: Run; events: EventRow[] };
      setRun(json.run);
      setEvents(json.events);
    }, 3000);
    return () => clearInterval(interval);
  }, [run.status, runId]);

  // Subscribe to realtime changes on this run's row + events — fallback for speedy updates if RLS allows.
  useEffect(() => {
    const sb = supabaseBrowser();
    const channel = sb
      .channel(`run-${runId}`)
      .on(
        "postgres_changes",
        { event: "UPDATE", schema: "public", table: "runs", filter: `id=eq.${runId}` },
        (payload) => setRun(payload.new as Run),
      )
      .on(
        "postgres_changes",
        { event: "INSERT", schema: "public", table: "events", filter: `run_id=eq.${runId}` },
        (payload) => setEvents((prev) => [...prev, payload.new as EventRow]),
      )
      .subscribe();
    return () => {
      sb.removeChannel(channel);
    };
  }, [runId]);

  const tier1 = events.filter((e) => e.score === 1);
  const tier2 = events.filter((e) => e.score === 2);
  const tier3 = events.filter((e) => e.score === 3);
  const unscored = events.filter((e) => e.score == null);

  return (
    <div className="space-y-8">
      <header className="space-y-2">
        <div className="flex items-center gap-3">
          <h1 className="text-2xl font-semibold">{run.client_name ?? "Untitled"} — Discovery</h1>
          <StatusBadge status={run.status} />
        </div>
        <p className="text-sm text-zinc-500">
          Started {new Date(run.created_at).toLocaleString()} · Location:{" "}
          <code className="text-xs">{run.spec?.location}</code> · Industries:{" "}
          <code className="text-xs">{run.spec?.industries?.join(", ")}</code>
        </p>
      </header>

      {run.status !== "complete" && run.status !== "failed" && (
        <div className="rounded-lg border border-blue-200 bg-blue-50 p-4 text-sm text-blue-900 dark:border-blue-900 dark:bg-blue-950 dark:text-blue-100">
          Running — this typically takes 3–10 min. Events appear below as they're scored.
        </div>
      )}

      {run.status === "failed" && (
        <div className="rounded-lg border border-red-200 bg-red-50 p-4 text-sm dark:border-red-900 dark:bg-red-950">
          <p className="font-medium text-red-900 dark:text-red-100">Run failed</p>
          <pre className="mt-2 whitespace-pre-wrap text-xs text-red-800 dark:text-red-200">{run.error}</pre>
        </div>
      )}

      {run.status === "complete" && (
        <div className="grid grid-cols-3 gap-3">
          <Stat label="Tier 1" value={run.tier_1_count ?? tier1.length} tone="hot" />
          <Stat label="Tier 2" value={run.tier_2_count ?? tier2.length} tone="warm" />
          <Stat label="Tier 3" value={run.tier_3_count ?? tier3.length} tone="cold" />
        </div>
      )}

      <section>
        <h2 className="mb-2 text-lg font-semibold">Worker log</h2>
        <pre className="max-h-64 overflow-auto rounded-lg border border-zinc-200 bg-zinc-50 p-3 font-mono text-xs leading-relaxed text-zinc-700 dark:border-zinc-800 dark:bg-zinc-950 dark:text-zinc-300">
          {run.log || "(no log yet)"}
        </pre>
      </section>

      <section className="space-y-6">
        <EventsTable title="Tier 1 — Hot" events={tier1} tone="hot" />
        <EventsTable title="Tier 2 — Workable" events={tier2} tone="warm" />
        {unscored.length > 0 && <EventsTable title="Pending scoring" events={unscored} tone="pending" />}
        <details>
          <summary className="cursor-pointer text-sm text-zinc-500">
            Show tier 3 ({tier3.length})
          </summary>
          <div className="mt-3">
            <EventsTable title="" events={tier3} tone="cold" />
          </div>
        </details>
      </section>
    </div>
  );
}

function Stat({ label, value, tone }: { label: string; value: number; tone: "hot" | "warm" | "cold" }) {
  const colors = {
    hot: "bg-emerald-100 text-emerald-900 dark:bg-emerald-950 dark:text-emerald-200",
    warm: "bg-amber-100 text-amber-900 dark:bg-amber-950 dark:text-amber-200",
    cold: "bg-zinc-100 text-zinc-600 dark:bg-zinc-900 dark:text-zinc-400",
  };
  return (
    <div className={`rounded-xl p-4 ${colors[tone]}`}>
      <div className="text-xs uppercase tracking-wide">{label}</div>
      <div className="mt-1 text-2xl font-semibold tabular-nums">{value}</div>
    </div>
  );
}

function EventsTable({ title, events, tone }: { title: string; events: EventRow[]; tone: "hot" | "warm" | "cold" | "pending" }) {
  if (!events.length) return null;
  const borderColor = {
    hot: "border-emerald-300",
    warm: "border-amber-300",
    cold: "border-zinc-200",
    pending: "border-blue-300",
  }[tone];
  return (
    <div>
      {title && <h3 className="mb-2 text-base font-semibold">{title}</h3>}
      <div className={`overflow-hidden rounded-xl border ${borderColor} bg-white shadow-sm dark:bg-zinc-900`}>
        <table className="w-full text-left text-sm">
          <thead className="bg-zinc-50 text-xs uppercase tracking-wide text-zinc-500 dark:bg-zinc-950">
            <tr>
              <th className="px-4 py-2">Event</th>
              <th className="px-4 py-2">Date</th>
              <th className="px-4 py-2">Location</th>
              <th className="px-4 py-2">Why</th>
              <th className="px-4 py-2">Source</th>
            </tr>
          </thead>
          <tbody>
            {events.map((e) => (
              <tr key={e.id} className="border-t border-zinc-100 dark:border-zinc-800">
                <td className="px-4 py-2">
                  {e.event_url ? (
                    <a href={e.event_url} target="_blank" rel="noopener noreferrer" className="font-medium text-zinc-900 underline dark:text-zinc-100">
                      {e.event_name}
                    </a>
                  ) : (
                    <span className="font-medium">{e.event_name}</span>
                  )}
                </td>
                <td className="px-4 py-2 text-zinc-600 dark:text-zinc-400">{e.event_date ?? "—"}</td>
                <td className="px-4 py-2 text-zinc-600 dark:text-zinc-400">{e.location ?? "—"}</td>
                <td className="px-4 py-2 text-xs text-zinc-500">{e.score_rationale ?? "—"}</td>
                <td className="px-4 py-2 text-xs text-zinc-500">{e.source ?? "—"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function StatusBadge({ status }: { status: string }) {
  const styles: Record<string, string> = {
    queued: "bg-zinc-200 text-zinc-800",
    running: "bg-blue-100 text-blue-800",
    scoring: "bg-amber-100 text-amber-800",
    complete: "bg-emerald-100 text-emerald-800",
    failed: "bg-red-100 text-red-800",
  };
  return (
    <span className={`inline-flex rounded-md px-2 py-0.5 text-xs font-medium ${styles[status] ?? "bg-zinc-200"}`}>
      {status}
    </span>
  );
}
