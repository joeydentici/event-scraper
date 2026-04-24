# Event Scraper

SpeakHyve event-discovery dashboard. Vercel (Next.js) → Railway (FastAPI worker) → Supabase (Postgres + Realtime).

## Architecture

```
[Browser] ─→ Vercel (Next.js dashboard)
                │
                ├── reads/writes ── Supabase (runs, events tables)
                │
                └── POST /runs ──→ Railway (FastAPI worker)
                                      │
                                      ├── 10times via Apify
                                      ├── Sessionize/Cvent/Google via Serper
                                      ├── Claude scoring (Anthropic API)
                                      └── writes events back to Supabase
```

## Repo layout

```
event-scraper/
├── web/                    # Next.js 15 (App Router) — deploy to Vercel
├── worker/                 # FastAPI + Python pipeline — deploy to Railway
│   ├── main.py             # FastAPI entry
│   ├── pipeline.py         # orchestrator: discover → score → write
│   ├── scoring.py          # Claude-based 1/2/3 scoring
│   ├── scripts/            # source-specific scrapers (10times, Sessionize, Cvent, Google)
│   └── references/         # industry slugs, state→cities, etc.
└── supabase/migrations/    # initial schema
```

## Setup

### 1. Supabase

Create a new project at https://supabase.com/dashboard and apply the migration:

```bash
# Either via SQL editor (paste supabase/migrations/0001_init.sql)
# or via CLI:
supabase link --project-ref <ref>
supabase db push
```

Capture: `SUPABASE_URL` (Project URL), `SUPABASE_SERVICE_ROLE_KEY`, `NEXT_PUBLIC_SUPABASE_ANON_KEY`.

### 2. Railway worker

```bash
cd worker
railway login
railway init    # creates a new project
railway up      # builds Dockerfile, deploys
```

Set env vars in Railway dashboard or via CLI:

```bash
railway variables set \
  SERPER_API_KEY=... \
  APIFY_TOKEN=... \
  TENTIMES_ACTOR_ID=zen-studio/10times-events-scraper \
  ANTHROPIC_API_KEY=... \
  SUPABASE_URL=... \
  SUPABASE_SERVICE_ROLE_KEY=... \
  WORKER_SHARED_SECRET="$(openssl rand -hex 32)"
```

After deploy, copy the Railway public domain (e.g. `https://event-scraper-worker.up.railway.app`).

### 3. Vercel web

```bash
cd web
npm install
vercel link
vercel env add NEXT_PUBLIC_SUPABASE_URL
vercel env add NEXT_PUBLIC_SUPABASE_ANON_KEY
vercel env add SUPABASE_SERVICE_ROLE_KEY
vercel env add WORKER_URL          # the Railway URL from step 2
vercel env add WORKER_SHARED_SECRET # same value as worker
vercel deploy --prod
```

### 4. Smoke test

Open the Vercel URL → fill the form → submit. Run detail page should show live progress, then tier 1/2/3 results.

## Local dev

```bash
# Terminal 1: worker
cd worker
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp ../.env.example .env  # fill in worker vars
export $(grep -v '^#' .env | xargs)
uvicorn main:app --reload --port 8080

# Terminal 2: web
cd web
npm install
cp ../.env.example .env.local  # fill in web vars (point WORKER_URL to http://localhost:8080)
npm run dev
```

## Notes

- **Auth**: not wired yet — dashboard is open. Lock it down with Supabase magic-link before sharing the URL externally. Add policies on `runs` / `events` gated on `auth.jwt() ->> 'email' = 'joey@speakhyve.io'`.
- **RLS**: enabled with no policies, so only `service_role` reads/writes. Browser realtime subscribes via anon key but won't get rows back unless policies are added.
- **Long runs**: the worker is a stateful service (always-on container) so 25-min runs aren't a problem. The API route returns immediately after kicking off the background thread.
- **Cost**: ~$1–4 per run (Serper + Apify + Claude scoring). Railway worker idle cost is minimal.
