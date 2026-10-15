# Operations runbook

## Everyday
| Task | Command |
|---|---|
| Open the website | http://127.0.0.1:8787 |
| Full batch now | `make batch` (or `python -m harness.cli batch`) |
| Refresh website data only | `make site` |
| This month's magazine | `make magazine` (≈ $8–10 of Claude usage) |
| Status of everything | `make status` |
| Pause / resume scheduled runs | `make pause` / `make resume` |
| Tests | `make test` |

## Services (macOS launchd)
| Label | What | Install / remove |
|---|---|---|
| `com.bengaluru-rei.daily` | 06:00 IST: daily pipeline (with retries), then magazine (if month missing), weekly, metrics, site | `make schedule` / `python -m harness.cli schedule uninstall` |
| `com.bengaluru-rei.web` | Website on 127.0.0.1:8787, auto-restart, starts at login | `make web-install` / `make web-stop` |

## Logs
`logs/run-<date>.jsonl` (all steps), `logs/source_failures.jsonl`, `logs/launchd.{out,err}.log` (batch),
`logs/web.{out,err}.log` (website). The website footer shows the last batch status; `GET /api/status` lists recent runs.

## Recovery
| Symptom | Fix |
|---|---|
| Mac was off at 06:00 | `make batch` (the daily window is anchored to that day's 06:00 slot) |
| Batch partial | `GET /api/status` → see the failing step; re-run that step: `python -m harness.cli batch --steps metrics,site` |
| Daily brief blocked by a gate | See `reports/daily/_blocked/<date>.json` → `meta.gates.hard_failures`; fix, then `python -m harness.cli run --from-stage publish` |
| Magazine layout check failed | `python -m harness.cli magazine --from-step write` (re-writes within limits) |
| Website down | `make web-install` (reinstalls service); check `logs/web.err.log` |
| Charts empty | Chart.js loads from cdn.jsdelivr.net — needs internet; data is in `/api/metrics` |
| Disk full | Free space; nothing in this app exceeds a few MB per day |

## Costs
Daily research ≈ $2–3 (cap $12), magazine ≈ $8–10 per month (cap $30), metrics ≈ $0.3/day. Caps live in
`config/harness.yaml` and `config/magazine.yaml`. Set `agent.enabled: false` for zero-cost RSS-only days.

## Subscribers
Stored locally in `data/app/app.db` (status `pending`). No email is sent automatically.
Export: `curl http://127.0.0.1:8787/api/admin/subscribers` (localhost only). See `docs/ROADMAP.md` for delivery.
