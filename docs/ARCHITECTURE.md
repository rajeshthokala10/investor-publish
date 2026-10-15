# Architecture

Bengaluru Property Review is one application with three layers:

```
                    ┌───────────────────────────── batch (06:00 IST, launchd) ─────────────────────────────┐
 public web  ──►    │ daily pipeline  →  magazine (monthly)  →  weekly  →  metrics builder  →  site builder │
 (RSS, agency,      │ harness/pipeline   harness/magazine*     weekly.py   metrics_build.py   app/site_data   │
  news, research)   └─────────────┬───────────────────┬────────────────────────┬─────────────────┬──────────┘
                                  ▼                   ▼                        ▼                 ▼
                     reports/daily/*.{md,html,     reports/magazine/*     data/app/metrics.json  data/app/site.json
                     pdf,json}                     .{pdf,html}                                  data/app/downloads/
                                                                                                │
                                         web app (FastAPI, launchd service, :8787) ◄────────────┘
                                         app/server.py  +  app/static/{index.html,styles.css,app.js}
                                         SQLite data/app/app.db (subscribers, job_runs)
```

## Components

| Layer | Code | Responsibility |
|---|---|---|
| Collection | `harness/collect_rss.py`, `harness/agent.py` | Public RSS + headless research agents (WebSearch/WebFetch only, no MCP connectors) returning schema-validated JSON |
| Evidence pipeline | `harness/pipeline.py` | Discover → Collect → Extract → Normalise → Deduplicate → Verify → Analyse → Recheck → Publish → Archive, with checkpoints |
| Trust rules | `validation/`, `recheck/`, `noise_removal/` | Source tiers, independence groups, citation checks, stage evidence, contradictions, gates |
| Analysis | `analysis/` | Price normalisation (same basis only), corridor scores, scenarios, trackers |
| Daily report | `harness/report.py`, `harness/infographic.py`, `harness/pdf_edition.py` | MD/HTML/JSON + 5-page PDF with infographic cover |
| Magazine | `harness/magazine.py`, `magazine_write.py`, `magazine_render.py` | 10-page monthly issue; writer has no tools; numbers checked against cited claims |
| Dashboard data | `harness/metrics_build.py` | KPIs, single-producer growth series, area prices, builders (validated) |
| Batch | `harness/batch.py` | One job running all steps; records each run in `job_runs` |
| Web | `app/` | FastAPI API + static landing page (Chart.js), subscriptions in SQLite |
| Ops | `harness/scheduler.py`, `Makefile` | launchd jobs for the batch (06:00 IST) and the web service (KeepAlive) |

## Trust model (unchanged across layers)

* Statuses are set only by code; LLM outputs never carry a status field.
* Usable evidence = verified_primary / corroborated / single_source. Interested parties (developers, brokers,
  portals, consultancies, influencers) are only printed as their own attributed announcements.
* Corroboration counts independent ORIGINAL producers (two papers quoting ANAROCK = one source).
* Any LLM-written text or chart value must contain only numbers present in the claims it cites.
* Charts never stitch different producers into one series.

## Data locations

| Path | Content |
|---|---|
| `data/raw/` | RSS captures, agent outputs (per edition/issue) |
| `data/processed/` | `claims_ledger.json`, `projects.json`, `infrastructure.json`, `magazine/<YYYY-MM>*.json` |
| `data/history/` | Edition snapshots, seen-story registry |
| `data/runs/<date>/` | Stage checkpoints + manifest |
| `data/app/` | `site.json`, `metrics.json`, `downloads/`, `app.db` |
