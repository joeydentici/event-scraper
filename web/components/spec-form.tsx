"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import type { RunSpec } from "@/lib/types";

export function SpecForm() {
  const router = useRouter();
  const [submitting, setSubmitting] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  async function onSubmit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setErr(null);
    setSubmitting(true);

    const form = e.currentTarget;
    const fd = new FormData(form);
    const startDate = String(fd.get("start_date") ?? "").trim();
    const derivedYear = startDate ? Number(startDate.slice(0, 4)) : new Date().getFullYear() + 1;
    const spec: RunSpec = {
      client_context: String(fd.get("client_context") ?? "").trim(),
      industries: String(fd.get("industries") ?? "").split(",").map((s) => s.trim()).filter(Boolean),
      sub_topics: String(fd.get("sub_topics") ?? "").split(",").map((s) => s.trim()).filter(Boolean),
      event_types: String(fd.get("event_types") ?? "conferences").split(",").map((s) => s.trim()).filter(Boolean),
      location: String(fd.get("location") ?? "").trim(),
      start_date: startDate || undefined,
      year: derivedYear,
      target_count: Number(fd.get("target_count") || 100),
      exclusions: String(fd.get("exclusions") ?? "").split(",").map((s) => s.trim()).filter(Boolean),
    };
    const client_name = String(fd.get("client_name") ?? "").trim() || undefined;

    try {
      const res = await fetch("/api/run", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ spec, client_name }),
      });
      const json = await res.json();
      if (!res.ok) throw new Error(json.error ?? "failed");
      router.push(`/runs/${json.run_id}`);
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
      setSubmitting(false);
    }
  }

  return (
    <form onSubmit={onSubmit} className="space-y-4 rounded-xl border border-zinc-200 bg-white p-6 shadow-sm dark:border-zinc-800 dark:bg-zinc-900">
      <div className="grid gap-4 md:grid-cols-2">
        <Field label="Client name" name="client_name" placeholder="Lance" />
        <Field label="Location" name="location" placeholder="Texas, Austin, Southwest, Nationwide…" required />
      </div>
      <Field
        label="Client context"
        name="client_context"
        as="textarea"
        rows={3}
        placeholder="K-12 education leadership speaker focused on athletic directors and superintendents…"
        required
      />
      <div className="grid gap-4 md:grid-cols-2">
        <Field label="Industries (comma-sep)" name="industries" placeholder="Education, Business Services" required />
        <Field label="Sub-topics (comma-sep)" name="sub_topics" placeholder="K-12, athletic directors" />
      </div>
      <div className="grid gap-4 md:grid-cols-4">
        <Field label="Event types" name="event_types" defaultValue="conferences" />
        <Field
          label="Earliest event date"
          name="start_date"
          type="date"
          defaultValue={new Date().toISOString().slice(0, 10)}
        />
        <Field label="Target count" name="target_count" type="number" defaultValue={100} />
        <Field label="Exclusions" name="exclusions" placeholder="no virtual" />
      </div>

      {err && <p className="text-sm text-red-600">{err}</p>}

      <button
        type="submit"
        disabled={submitting}
        className="rounded-md bg-zinc-900 px-4 py-2 text-sm font-medium text-white transition hover:bg-zinc-700 disabled:opacity-50 dark:bg-zinc-100 dark:text-zinc-900 dark:hover:bg-white"
      >
        {submitting ? "Starting…" : "Start discovery"}
      </button>
    </form>
  );
}

function Field(props: {
  label: string;
  name: string;
  placeholder?: string;
  defaultValue?: string | number;
  required?: boolean;
  type?: string;
  as?: "textarea";
  rows?: number;
}) {
  const { label, as, ...rest } = props;
  return (
    <label className="block">
      <span className="mb-1 block text-xs font-medium uppercase tracking-wide text-zinc-500">{label}</span>
      {as === "textarea" ? (
        <textarea
          {...rest}
          className="w-full rounded-md border border-zinc-200 bg-white px-3 py-2 text-sm shadow-sm focus:border-zinc-400 focus:outline-none dark:border-zinc-700 dark:bg-zinc-950"
        />
      ) : (
        <input
          {...rest}
          className="w-full rounded-md border border-zinc-200 bg-white px-3 py-2 text-sm shadow-sm focus:border-zinc-400 focus:outline-none dark:border-zinc-700 dark:bg-zinc-950"
        />
      )}
    </label>
  );
}
