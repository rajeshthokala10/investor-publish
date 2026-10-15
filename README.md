# Bengaluru Real Estate Intelligence · Bengaluru Property Review

**Quick start**
```bash
make web-install   # website at http://127.0.0.1:8787 (runs in the background)
make schedule      # 06:00 IST batch: daily research → magazine (monthly) → weekly → metrics → website
make batch         # run the whole application now
make help          # all commands
```
Email: `make email-preview` (dry run) · `make email` (sends "Bangalore RealEstate Delta" from info@raditsoftware.com;
needs SMTP settings in `.env`, see [Operations](docs/OPERATIONS.md#bangalore-realestate-delta-email))

Docs: [Architecture](docs/ARCHITECTURE.md) · [Operations](docs/OPERATIONS.md) · [API](docs/API.md) · [Roadmap](docs/ROADMAP.md)

## Web application
A FastAPI back end (`app/server.py`) and a static front end (`app/static/`). The site includes:
- a landing page with the latest headline and rotating quotes;
- KPI cards;
- today's Bengaluru real-estate news, filterable by zone;
- growth charts, each from a single research firm;
- price levels by area;
- top builders;
- the government's plans;
- growth towns and zone summaries;
- magazine and daily-brief downloads;
- a subscribe form (stored in SQLite).

Data comes from `data/app/site.json`, which the batch job rebuilds every morning.

A daily, evidence-first research system for Bengaluru property. East Bengaluru gets the most
attention, followed by North, South, West and the peripheral corridors. It compares **villa
plots, villas and high-rise apartments**, tracks projects and government and infrastructure
moves, and publishes a sourced report every morning at **06:00 IST** covering the preceding
**72 hours**.

> Research tool, not investment advice. Forecasts are scenarios under stated assumptions.
> Anything not verified is labelled as such.

## What a run does

```
Discover → Collect → Extract → Normalise → Deduplicate → Verify → Analyse → Recheck → Publish → Archive
```

| Stage | What happens | Code |
|---|---|---|
| Discover | Plans feeds, Google News queries and research tasks (baseline task weekly) | `harness/pipeline.py::discover` |
| Collect | Public RSS feeds + Google News RSS (rate-limited); headless research agents (`claude -p`, **WebSearch/WebFetch only**) return schema-validated JSON | `harness/collect_rss.py`, `harness/agent.py` |
| Extract | Claims and projects → canonical records; source tier/group; corridor via gazetteer; marketing and staleness flags | `pipeline.py::extract` |
| Normalise | Prices → ₹/sq ft on the *same basis*; comparability classes | `analysis/prices.py` |
| Deduplicate | URL canonicalisation, story clustering, syndication clusters, new/update/repeat vs history | `noise_removal/` |
| Verify | Citation check (excerpt must be on the page), evidenced infra stage, status ladder, contradictions | `recheck/citations.py`, `validation/verification.py` |
| Analyse | Claims ledger, project + infrastructure trackers, corridor × type scores, scenarios, illustrations | `analysis/` |
| Recheck | Independent reviewer agent re-reads consequential claims; link checks; calculations recomputed | `recheck/recheck.py` |
| Publish | Gates, then Markdown + HTML + PDF (infographic cover) + JSON from one dataset | `validation/gates.py`, `harness/report.py`, `harness/infographic.py` |
| Archive | Edition snapshot, seen-story registry, change tracking | `harness/report.py::archive_edition` |

Outputs: `reports/daily/<date>.{md,html,pdf,json}`; weekly: `reports/weekly/<date>.{md,html,json}`.

## Magazine edition: *Bengaluru Property Review*

A 10-page, magazine-style guide to the whole city:
- cover;
- editor's note and city at a glance;
- the government's plan (metro, rail, roads, townships, water, governance);
- growth map;
- East, North, and South & West features;
- beyond-the-city growth towns (Hoskote, Devanahalli, Doddaballapur, Nelamangala, Bidadi, Kanakapura/Harohalli, Anekal/Attibele, Sarjapur, Hosur);
- plots vs villas vs apartments with a price guide;
- outlook, projects and sources.

```bash
python -m harness.cli magazine                         # research → verify → write → render (current month)
python -m harness.cli magazine --from-step write       # re-write and re-render from the verified data
python -m harness.cli magazine --from-step render      # re-render only
```

- **Research:** ten deep-research tasks (`config/magazine.yaml`) with a 24-month lookback. They use the same extraction, citation checks and verification as the daily report.
- **What gets printed:** only publishable evidence. That means verified, corroborated or single-source facts, plus a developer's or agency's own attributed announcements. Unverified material is left out rather than printed.
- **Writer guardrail:** the writer is an LLM with no tools. Any text block whose numbers are not in the claims it cites is removed before printing (`harness/magazine_write.py`).
- **Output:** `reports/magazine/bengaluru-property-review-<YYYY-MM>.{pdf,html}`, plus the dataset in `data/processed/magazine/`.
- **Cost:** about $8–10 per issue (research plus writer), capped by `agent.max_budget_usd_per_run` in `config/magazine.yaml`.

## Setup

Requirements: macOS (launchd) or Linux (cron), Python 3.11+ with `pyyaml requests jsonschema markdown pytest`,
Google Chrome or Edge (for PDF), and the Claude Code CLI (`claude`) logged in, for the research agents.

```bash
pip install pyyaml requests jsonschema markdown pytest
claude --version          # research agent CLI; auth is in your keychain, not in this repo
```

No API keys or secrets are stored in the repository. An optional `.env` is git-ignored.

## Commands

```bash
python -m harness.cli run                          # run today's edition (resumes from checkpoints)
python -m harness.cli run --edition 2026-10-15     # (re)build a specific edition, e.g. after a missed run
python -m harness.cli run --from-stage verify      # redo from a stage onward
python -m harness.cli run --force                  # redo everything for the edition
python -m harness.cli run --no-agent               # RSS-only run (no LLM research, no spend)
python -m harness.cli run --offline tests/fixtures/findings_sample.json --edition 2026-10-15   # replay, no network

python -m harness.cli schedule install             # install/refresh the launchd job (06:00 Asia/Kolkata)
python -m harness.cli schedule status              # loaded?, calendar slot, next run, last exit code
python -m harness.cli schedule uninstall
python -m harness.cli pause                        # scheduled runs exit (code 5) without researching
python -m harness.cli resume
python -m harness.cli status                       # lock holder, pause flag, last manifest, scheduler
python -m harness.cli weekly                       # weekly summary (also automatic on Mondays)

python -m pytest -q tests                          # data-quality and workflow tests
```

Exit codes: `0` ok / no new updates / partial · `2` research failed · `3` publication blocked by a gate ·
`4` another run holds the lock · `5` paused · `1` unexpected error.

## Scheduling

- launchd agent `~/Library/LaunchAgents/com.bengaluru-rei.daily.plist`, `StartCalendarInterval` 06:00.
  The installer converts 06:00 **Asia/Kolkata** into the Mac's local zone and warns if that zone observes DST.
- Asleep at 06:00 → launchd runs once on wake. Powered off → the run is missed; recover with
  `python -m harness.cli run --edition <date>`. The window is anchored to that date's 06:00 slot.
- Retries: `config/schedule.yaml` (3 attempts, 10/30-minute backoff) for failures only, not for gate blocks.
- Overlap: an `fcntl` lock (`logs/.run.lock`) prevents concurrent runs.
- Logs: `logs/run-<date>.jsonl`, `logs/source_failures.jsonl`, `logs/launchd.{out,err}.log`.
- Linux: `python -c "from harness.scheduler import linux_hint; print(linux_hint())"` prints a `CRON_TZ=Asia/Kolkata` crontab line.

## Configuration (`config/`)

| File | Controls |
|---|---|
| `corridors.yaml` | Regions, corridors, unique aliases, centroids, straddling notes, infrastructure → corridor links |
| `sources.yaml` | Domain tiers and independence groups, RSS feeds, Google News queries, known-unavailable sources |
| `research_tasks.yaml` | Research agent tasks and focus (daily vs weekly baseline) |
| `schedule.yaml` | Time zone, run time, window, weekly day, retries |
| `scoring.yaml` | Factor weights/bands, ranking threshold, confidence rules, scenario parameters, illustrative cost assumptions |
| `harness.yaml` | Runtime/HTTP/citation budgets, rate limits, agent tools/model/spend caps, recheck settings |

**Spend.** Each run makes about 6–7 headless Claude calls, capped by `agent.max_budget_usd_per_task` and
`max_budget_usd_per_run` (default caps $2/task, $12/run; typical runs cost much less).
Lower the caps, or set `agent.enabled: false` for RSS-only runs.

## How trust is enforced

- Verification statuses are set **only by code** (`validation/verification.py`). The agent's output schema has no status field.
- Official source → *verified_primary*; ≥2 independent non-interested publisher groups (syndicated copies count once) → *corroborated*;
  developers, brokers, portals, consultancies and influencers → *interested_party_claim* however many repeat it.
- Guarantee language, failed citation checks, failed independent rechecks and infra stages the quoted text does not support all force *unverified*.
- Hard publication gates (G1–G6) block a report whose usable claims lack evidence, whose calculations do not recompute,
  or whose rankings or stage changes rest on weak claims.
- Prices are compared only within the same basis and price kind; land rates are never ranked against saleable rates.
- Scenarios need appreciation evidence from ≥2 independent groups; otherwise *Insufficient evidence to estimate*. Cells with <3 evidenced factors are *Unranked*.

## Troubleshooting

| Symptom | Check / fix |
|---|---|
| Report says "Research failed" | `logs/source_failures.jsonl`; network down or every source blocked. Rerun `run --edition <date>`. |
| Agent tasks fail instantly | `claude --version`; `claude -p "hi"` to confirm login; see `stderr` in `source_failures.jsonl`. |
| Scheduled run did not happen | `schedule status` (loaded? last exit code); `logs/launchd.err.log`; was the Mac off? Run the edition manually. |
| "Another run is in progress" | `status` shows the PID holding the lock; the lock is released automatically when that process exits. |
| Report in `reports/daily/_blocked/` | A hard gate failed; the reasons are in the red banner and in `meta.gates.hard_failures` of the JSON. Fix data/config, then `run --from-stage publish`. |
| PDF missing | Chrome/Edge not found or headless print failed (`pdf_failed` in the run log); MD/HTML/JSON are still produced. |
| Wrong corridor for a locality | Add or move the alias in `config/corridors.yaml` (aliases must stay unique; tests enforce this). |

## Repository map

`.claude/skills/` (10 skills) · `harness/` · `prompts/` · `validation/` · `recheck/` · `noise_removal/` ·
`content_engineering/` · `analysis/` · `config/` · `data/{raw,processed,history,runs}` · `reports/{daily,weekly}` · `logs/` · `tests/`

## Limitations

See the "Limitations" section at the end of the latest daily report run notes and the list below.

- No registered-transaction price series (Kaveri/IGRS needs captcha/login), so "priced in?" cannot be measured.
- Karnataka RERA lookups are interactive; RERA numbers stay "Not verified" unless an agent saw them on the portal.
- X, Instagram and most LinkedIn content need a login and are not accessed; social coverage is limited to what web search surfaces publicly.
- Citation checks cannot read JS-rendered or paywalled pages; those are "inconclusive", not confirmed.
- Scores and scenarios start sparse and improve as the claims ledger accumulates; early editions will be mostly Unranked.
