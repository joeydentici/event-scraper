# API Configuration — Event Discovery (Step 1)

## Required Environment Variables

```bash
export SERPER_API_KEY="your-serper-api-key"
export APIFY_TOKEN="your-apify-token"
export TENTIMES_ACTOR_ID="zen-studio/10times-events-scraper"  # Verified working
```

**10times actor:** `zen-studio/10times-events-scraper` is verified working as of build date. Cost is roughly $0.003 per event scraped (~$0.16 for a 50-event run, ~$1 for a 6-city Texas Education run). It returns structured data with `name`, `url`, `description`, `startDate`/`endDate`, nested `location` (cityName, state, venueName, venueAddress, coordinates), `categories` array, `organizer` object (name + website — useful for Step 2!), `type` (Conference/Workshop/Tradeshow), `hybrid`, `onlineEvent`, `eventEstimatedSize`, and `stats.opportunityScore`.

**No contact APIs in Step 1.** The waterfall (a-leads, Findymail, scraping) lives in the separate Step 2 enrichment skill. Step 1 outputs event data only.

## Sources & Their Roles

| Source | Tool | Strength | Speed | Output |
|---|---|---|---|---|
| 10times | Apify actor | Structured event database, broad inventory | 2-5 min per run, parallel | ~50 events per run |
| Sessionize | Serper search | CFP/speaker-seeking events | <2s per query | ~5-10 events per query |
| Cvent | Serper search | Large professional conferences | <2s per query | ~5-10 events per query |
| General Google | Serper search | Niche industry events, fills gaps | <2s per query | ~5-10 events per query |

## 10times URL Patterns (verified against live site)

**Country + industry (broad, recommended for nationwide):**
```
https://10times.com/usa/{industry_slug}/{event_type}
https://10times.com/usa/technology/conferences
https://10times.com/usa/education/conferences
```

**City + industry (focused, recommended for regional):**
```
https://10times.com/{city_slug}-us/{industry_slug}
https://10times.com/austin-us/technology
https://10times.com/chicago-us/wellness-healthcare
```

**City only (broad regional):**
```
https://10times.com/{city_slug}-us/{event_type}
https://10times.com/orlando-us/conferences
```

**Event type slugs:** `conferences`, `tradeshows`, `expos`

**Industry slugs:** See `industries.json` for the full verified list (22 slugs).

**City slugs:** Single token, no hyphens. See `state_cities.json`.

## Serper Query Patterns by Source

### Sessionize
```
site:sessionize.com {industry} {event_type} {year} {location}
site:sessionize.com {industry} call for speakers {year}
```

### Cvent
```
site:cvent.com {industry} {event_type} {year} {location}
site:cvent.com/d {industry} conference {year}
```

### General Google
```
{industry} {event_type} {year} {location}
{industry} {event_type} call for speakers {year}
{industry} summit {year} {location}
```

Use `tbs=qdr:y` to filter to results from the past year (avoids stale events).

## API Quick Reference

| API | Base URL | Auth | Key Endpoints |
|---|---|---|---|
| Serper.dev | https://google.serper.dev | X-API-KEY header | POST /search |
| Apify | https://api.apify.com/v2 | ?token= query param | POST /acts/{id}/runs |

## Google Drive Output

Target folder: `Speakhyve → Lead Scraper (Claude)`
Folder ID: `1jxOmQtTDnuCWAhQ6MLZ1rwasiQPP0Y78`

**Method (preferred):**
1. Build CSV locally with score column (instant)
2. `Google Drive:google_drive_upload_file` with `convert=true` (auto-converts to Sheet)
3. `Google Drive:google_drive_move_file` to target folder

The CSV has these columns:
- `score` (1, 2, 3)
- `score_rationale`
- `event_name`
- `event_date`
- `location`
- `industry`
- `event_type`
- `event_url`
- `source` (10times | sessionize | cvent | google)
- `description` (1-2 sentences if available)

Conditional formatting on the score column should be applied client-side after upload (the user can do this in Sheets, or we can apply via Apps Script — but for v1, plain CSV with a score column is enough).

## Performance Targets

| Stage | Target Time |
|---|---|
| Input parsing & confirmation | <30 seconds |
| All 4 sources running in parallel | 5-8 minutes |
| Dedup | <10 seconds |
| Scoring (batches of 50) | 30-60 seconds per batch, parallel |
| Sheet upload | <30 seconds |
| **Total end-to-end** | **8-15 minutes** for typical run |

Tight runs (1 industry, 1 location, 100 events): 5-8 minutes.
Heavy runs (5 industries × 5 locations, 500 events): 15-25 minutes.

## Cost Estimate Per Run

| Tool | Usage | Est. Cost |
|---|---|---|
| Serper.dev | ~30-60 queries | ~$0.06-0.12 |
| Apify (10times) | ~5-15 parallel actor runs | ~$1-3 |
| Claude (scoring) | 5-15 batched calls | Included in subscription |
| **Total per run** | | **~$1-4** |
