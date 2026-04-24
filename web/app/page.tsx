import Link from "next/link";
import { supabaseAdmin } from "@/lib/supabase-admin";
import { SpecForm } from "@/components/spec-form";

export const dynamic = "force-dynamic";

export default async function Home() {
  const sb = supabaseAdmin();
  const { data: runs } = await sb
    .from("runs")
    .select("id, created_at, status, client_name, spec, tier_1_count, tier_2_count, tier_3_count, scored_count")
    .order("created_at", { ascending: false })
    .limit(15);

  return (
    <main className="space-y-10">
      <section>
        <h1 className="mb-1 text-2xl font-semibold">New discovery run</h1>
        <p className="mb-6 text-sm text-zinc-500">
          Fill in the client brief — the worker fans out to 10times, Sessionize, Cvent, and Google, then scores with Claude.
        </p>
        <SpecForm />
      </section>

      <section>
        <h2 className="mb-4 text-lg font-semibold">Recent runs</h2>
        <div className="overflow-hidden rounded-xl border border-zinc-200 bg-white shadow-sm dark:border-zinc-800 dark:bg-zinc-900">
          <table className="w-full text-left text-sm">
            <thead className="bg-zinc-50 text-xs uppercase tracking-wide text-zinc-500 dark:bg-zinc-950">
              <tr>
                <th className="px-4 py-3">Client</th>
                <th className="px-4 py-3">Location</th>
                <th className="px-4 py-3">Status</th>
                <th className="px-4 py-3">Tiers (1/2/3)</th>
                <th className="px-4 py-3">Started</th>
                <th className="px-4 py-3"></th>
              </tr>
            </thead>
            <tbody>
              {!runs?.length && (
                <tr>
                  <td colSpan={6} className="px-4 py-6 text-center text-zinc-500">
                    No runs yet.
                  </td>
                </tr>
              )}
              {runs?.map((r) => (
                <tr key={r.id} className="border-t border-zinc-100 dark:border-zinc-800">
                  <td className="px-4 py-3 font-medium">{r.client_name ?? "—"}</td>
                  <td className="px-4 py-3 text-zinc-600 dark:text-zinc-400">{(r.spec as { location?: string })?.location ?? "—"}</td>
                  <td className="px-4 py-3">
                    <StatusBadge status={r.status} />
                  </td>
                  <td className="px-4 py-3 tabular-nums text-zinc-700 dark:text-zinc-300">
                    {r.scored_count ? `${r.tier_1_count ?? 0} / ${r.tier_2_count ?? 0} / ${r.tier_3_count ?? 0}` : "—"}
                  </td>
                  <td className="px-4 py-3 text-zinc-500">{new Date(r.created_at).toLocaleString()}</td>
                  <td className="px-4 py-3 text-right">
                    <Link href={`/runs/${r.id}`} className="text-zinc-900 underline dark:text-zinc-100">
                      Open →
                    </Link>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
    </main>
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
