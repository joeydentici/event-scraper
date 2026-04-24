-- Event Scraper schema
-- Runs = one discovery job; Events = scored results per run.

create extension if not exists "pgcrypto";

create table runs (
  id uuid primary key default gen_random_uuid(),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  status text not null default 'queued',   -- queued | running | scoring | complete | failed
  spec jsonb not null,
  client_name text,
  error text,
  raw_count int,
  deduped_count int,
  scored_count int,
  tier_1_count int,
  tier_2_count int,
  tier_3_count int,
  finished_at timestamptz,
  log text not null default ''
);

create table events (
  id uuid primary key default gen_random_uuid(),
  run_id uuid not null references runs(id) on delete cascade,
  event_name text,
  event_url text,
  event_date text,
  location text,
  event_type text,
  is_virtual boolean,
  estimated_size text,
  industry text,
  organizer_name text,
  organizer_website text,
  source text,
  sources text[],
  dup_count int,
  opportunity_score numeric,
  description text,
  score int,
  score_rationale text,
  created_at timestamptz not null default now()
);

create index idx_events_run on events(run_id);
create index idx_events_run_score on events(run_id, score);
create index idx_runs_status on runs(status);
create index idx_runs_created on runs(created_at desc);

-- Update updated_at on every runs row update
create or replace function touch_updated_at()
returns trigger language plpgsql as $$
begin
  new.updated_at := now();
  return new;
end;
$$;

create trigger runs_touch_updated_at
  before update on runs
  for each row execute function touch_updated_at();

-- Append a log line atomically (used by the worker for live progress)
create or replace function append_run_log(p_run_id uuid, p_line text)
returns void language plpgsql as $$
begin
  update runs
  set log = log || p_line || E'\n',
      updated_at = now()
  where id = p_run_id;
end;
$$;

-- Enable realtime on runs + events so the dashboard can subscribe to updates
alter publication supabase_realtime add table runs;
alter publication supabase_realtime add table events;

-- RLS: lock everything down. Dashboard uses service_role via server-side API routes.
alter table runs enable row level security;
alter table events enable row level security;

-- No policies defined = service_role only (which bypasses RLS).
-- Once magic-link auth is wired, add policies gated on auth.jwt() ->> 'email'.
