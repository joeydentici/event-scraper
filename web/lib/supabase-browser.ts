"use client";

import { createClient } from "@supabase/supabase-js";

// Anon-key client for realtime subscriptions from the browser.
// Since RLS is currently locked down, this won't return rows — we use it only for realtime channel events.
// TODO: once magic-link auth is wired, add RLS policies gated on email and this client can also read rows.
export function supabaseBrowser() {
  return createClient(
    process.env.NEXT_PUBLIC_SUPABASE_URL!,
    process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!,
    { auth: { persistSession: false } },
  );
}
