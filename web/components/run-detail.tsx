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
        <div className="space-y-4">
          <div className="grid grid-cols-3 gap-3">
            <Stat label="Tier 1" value={run.tier_1_count ?? tier1.length} tone="hot" />
            <Stat label="Tier 2" value={run.tier_2_count ?? tier2.length} tone="warm" />
            <Stat label="Tier 3" value={run.tier_3_count ?? tier3.length} tone="cold" />
          </div>
          <div className="flex flex-wrap items-center gap-1.5 rounded-lg border border-zinc-200 bg-white px-3 py-2 dark:border-zinc-800 dark:bg-zinc-900">
            <span className="mr-1 text-[11px] font-medium uppercase tracking-wider text-zinc-500">Export CSV</span>
            <DownloadBtn runId={runId} tiers="1" label="Tier 1" />
            <DownloadBtn runId={runId} tiers="2" label="Tier 2" />
            <DownloadBtn runId={runId} tiers="1,2" label="Tier 1 + 2" emphasized />
            <DownloadBtn runId={runId} tiers="3" label="Tier 3" />
            <DownloadBtn runId={runId} tiers="1,2,3" label="All" />
          </div>
        </div>
      )}

      <section>
        <h2 className="mb-2 text-sm font-semibold tracking-tight text-zinc-900 dark:text-zinc-100">Worker log</h2>
        <pre className="max-h-56 overflow-auto rounded-lg border border-zinc-200 bg-zinc-50/80 p-3 font-mono text-xs leading-relaxed text-zinc-700 dark:border-zinc-800 dark:bg-zinc-950/60 dark:text-zinc-300">
          {run.log || "(no log yet)"}
        </pre>
      </section>

      <section className="space-y-8">
        <EventsTable title="Tier 1 — Hot" events={tier1} tone="hot" />
        <EventsTable title="Tier 2 — Workable" events={tier2} tone="warm" />
        {unscored.length > 0 && <EventsTable title="Pending scoring" events={unscored} tone="pending" />}
        {tier3.length > 0 && (
          <details className="group">
            <summary className="flex cursor-pointer items-center gap-2 text-sm text-zinc-500 hover:text-zinc-900 dark:hover:text-zinc-100">
              <span className="inline-block transition-transform group-open:rotate-90">›</span>
              Tier 3 — Unqualified ({tier3.length})
            </summary>
            <div className="mt-4">
              <EventsTable title="" events={tier3} tone="cold" />
            </div>
          </details>
        )}
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
  const accent = {
    hot: "bg-emerald-500",
    warm: "bg-amber-500",
    cold: "bg-zinc-300 dark:bg-zinc-600",
    pending: "bg-blue-500",
  }[tone];

  return (
    <section>
      {title && (
        <div className="mb-3 flex items-baseline gap-2.5">
          <span className={`h-4 w-1 rounded-full ${accent}`} aria-hidden />
          <h3 className="text-sm font-semibold tracking-tight text-zinc-900 dark:text-zinc-100">{title}</h3>
          <span className="text-xs text-zinc-500">{events.length}</span>
        </div>
      )}
      <div className="overflow-x-auto rounded-lg border border-zinc-200 bg-white shadow-sm dark:border-zinc-800 dark:bg-zinc-900">
        <table className="w-full min-w-[1080px] table-fixed text-left text-sm">
          <colgroup>
            <col style={{ width: "28%" }} />
            <col style={{ width: "11%" }} />
            <col style={{ width: "12%" }} />
            <col style={{ width: "12%" }} />
            <col style={{ width: "10%" }} />
            <col style={{ width: "8%" }} />
            <col style={{ width: "19%" }} />
          </colgroup>
          <thead className="border-b border-zinc-200 bg-zinc-50/60 text-[11px] font-medium uppercase tracking-wider text-zinc-500 dark:border-zinc-800 dark:bg-zinc-950/60">
            <tr>
              <th className="px-3 py-2.5 font-medium">Event</th>
              <th className="px-3 py-2.5 font-medium">Date</th>
              <th className="px-3 py-2.5 font-medium">Location</th>
              <th className="px-3 py-2.5 font-medium">Industry</th>
              <th className="px-3 py-2.5 font-medium">Format</th>
              <th className="px-3 py-2.5 font-medium">Size</th>
              <th className="px-3 py-2.5 font-medium">Why</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-zinc-100 dark:divide-zinc-800">
            {events.map((e) => (
              <EventRowView key={e.id} ev={e} />
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

function EventRowView({ ev: e }: { ev: EventRow }) {
  const orgLabel = e.organizer_name ?? e.organizer_website?.replace(/^https?:\/\//, "").replace(/\/$/, "");
  const multiSource = (e.sources?.length ?? 0) > 1;
  return (
    <tr className="align-top transition-colors hover:bg-zinc-50/70 dark:hover:bg-zinc-950/60">
      <td className="px-3 py-3">
        <div className="min-w-0 space-y-1">
          {e.event_url ? (
            <a
              href={e.event_url}
              target="_blank"
              rel="noopener noreferrer"
              className="line-clamp-2 font-medium leading-snug text-zinc-900 hover:underline dark:text-zinc-100"
              title={e.event_name ?? undefined}
            >
              {e.event_name}
            </a>
          ) : (
            <span className="line-clamp-2 font-medium leading-snug" title={e.event_name ?? undefined}>
              {e.event_name}
            </span>
          )}
          {orgLabel && (
            <div className="truncate text-xs text-zinc-500" title={orgLabel}>
              {e.organizer_website ? (
                <a href={e.organizer_website} target="_blank" rel="noopener noreferrer" className="hover:underline">
                  {orgLabel}
                </a>
              ) : (
                orgLabel
              )}
            </div>
          )}
          <div className="flex flex-wrap items-center gap-1.5">
            {e.source && (
              <span className="inline-flex rounded bg-zinc-100 px-1.5 py-0.5 text-[10px] font-medium uppercase tracking-wide text-zinc-600 dark:bg-zinc-800 dark:text-zinc-400">
                {e.source}
              </span>
            )}
            {multiSource && (
              <span
                className="inline-flex rounded bg-emerald-100 px-1.5 py-0.5 text-[10px] font-medium uppercase tracking-wide text-emerald-800 dark:bg-emerald-950/60 dark:text-emerald-300"
                title={`Found in: ${e.sources!.join(", ")}`}
              >
                {e.sources!.length}× sources
              </span>
            )}
            {e.dup_count != null && e.dup_count > 1 && !multiSource && (
              <span className="inline-flex rounded bg-zinc-100 px-1.5 py-0.5 text-[10px] font-medium tabular-nums text-zinc-600 dark:bg-zinc-800 dark:text-zinc-400">
                ×{e.dup_count}
              </span>
            )}
          </div>
        </div>
      </td>
      <td className="px-3 py-3 text-xs text-zinc-700 dark:text-zinc-300" title={e.event_date ?? undefined}>
        <span className="line-clamp-2">{e.event_date ?? "—"}</span>
      </td>
      <td className="px-3 py-3 text-xs text-zinc-700 dark:text-zinc-300" title={e.location ?? undefined}>
        <span className="line-clamp-2">{e.location ?? "—"}</span>
      </td>
      <td className="px-3 py-3 text-xs text-zinc-600 dark:text-zinc-400" title={e.industry ?? undefined}>
        <span className="line-clamp-2">{e.industry ?? "—"}</span>
      </td>
      <td className="px-3 py-3 text-xs text-zinc-600 dark:text-zinc-400">
        <div className="space-y-1">
          {e.event_type ? (
            <div className="font-medium text-zinc-700 dark:text-zinc-300">{e.event_type}</div>
          ) : (
            <div className="text-zinc-400">—</div>
          )}
          {e.is_virtual && (
            <span className="inline-flex rounded bg-blue-100 px-1.5 py-0.5 text-[10px] font-medium uppercase tracking-wide text-blue-800 dark:bg-blue-950/60 dark:text-blue-300">
              Virtual
            </span>
          )}
        </div>
      </td>
      <td className="px-3 py-3 text-xs text-zinc-600 dark:text-zinc-400">
        <div className="space-y-1">
          {e.estimated_size ? (
            <div className="tabular-nums text-zinc-700 dark:text-zinc-300">{e.estimated_size}</div>
          ) : (
            <div className="text-zinc-400">—</div>
          )}
          {e.opportunity_score != null && (
            <span className="inline-flex rounded bg-amber-50 px-1.5 py-0.5 text-[10px] font-medium tabular-nums text-amber-800 dark:bg-amber-950/40 dark:text-amber-300" title="10times opportunity score">
              {Number(e.opportunity_score).toFixed(0)}
            </span>
          )}
        </div>
      </td>
      <td className="px-3 py-3 text-xs leading-relaxed text-zinc-600 dark:text-zinc-400" title={e.score_rationale ?? undefined}>
        <span className="line-clamp-3">{e.score_rationale ?? "—"}</span>
      </td>
    </tr>
  );
}

function DownloadBtn({ runId, tiers, label, emphasized = false }: { runId: string; tiers: string; label: string; emphasized?: boolean }) {
  const cls = emphasized
    ? "rounded-md bg-zinc-900 px-3 py-1.5 text-xs font-medium text-white hover:bg-zinc-700 dark:bg-zinc-100 dark:text-zinc-900"
    : "rounded-md border border-zinc-200 bg-white px-3 py-1.5 text-xs font-medium text-zinc-800 hover:bg-zinc-50 dark:border-zinc-700 dark:bg-zinc-900 dark:text-zinc-100 dark:hover:bg-zinc-800";
  return (
    <a href={`/api/runs/${runId}/csv?tiers=${tiers}`} download className={cls}>
      {label}
    </a>
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
