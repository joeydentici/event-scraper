export type RunStatus = "queued" | "running" | "scoring" | "complete" | "failed";

export type RunSpec = {
  client_context: string;
  industries: string[];
  sub_topics?: string[];
  event_types?: string[];
  location: string;
  year?: number;
  target_count?: number;
  exclusions?: string[];
  skip_sources?: string[];
};

export type Run = {
  id: string;
  created_at: string;
  updated_at: string;
  status: RunStatus;
  spec: RunSpec;
  client_name: string | null;
  error: string | null;
  raw_count: number | null;
  deduped_count: number | null;
  scored_count: number | null;
  tier_1_count: number | null;
  tier_2_count: number | null;
  tier_3_count: number | null;
  finished_at: string | null;
  log: string;
};

export type EventRow = {
  id: string;
  run_id: string;
  event_name: string | null;
  event_url: string | null;
  event_date: string | null;
  location: string | null;
  event_type: string | null;
  is_virtual: boolean | null;
  estimated_size: string | null;
  industry: string | null;
  organizer_name: string | null;
  organizer_website: string | null;
  source: string | null;
  sources: string[] | null;
  dup_count: number | null;
  opportunity_score: number | null;
  description: string | null;
  score: 1 | 2 | 3 | null;
  score_rationale: string | null;
};
