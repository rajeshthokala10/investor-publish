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
| `com.bengaluru-rei.evening` | 18:00 IST: evening news refresh (RSS + metro/government research, last 12 h) → website news + `reports/daily/<date>-evening.md`; no PDF, no email | installed with `make schedule` |
| `com.bengaluru-rei.web` | Website on 127.0.0.1:8787, auto-restart, starts at login | `make web-install` / `make web-stop` |

## Bangalore Realestate Delta — daily magazine (06:00 IST)
The daily PDF "Bangalore Realestate Delta" is a 5-page magazine in the monthly magazine's style (`harness/daily_paper.py::build_delta_html`, prompt `prompts/daily_writer.md`): cover · top stories · Metro & Transport (network map + line board) · Development & Government (+ projects in the pipeline) · Around Bengaluru (+ growth towns, what to watch). News only, no statistics.
- **Page 1:** front page with the lead and second stories, Metro Watch and In Brief.
- **Page 2:** Metro & Transport, with the network map and the line status board.
- **Page 3:** City Development, with the projects-in-the-pipeline box.
- **Page 4:** Government & Policy, with What to Watch.
- **Page 5:** Around Bengaluru by zone, with the growth-towns box.

No market statistics appear in this edition. If the writer is unavailable, the condensed analyst layout is used instead.

## Website content protection
- Page data is embedded server-side. `/api/*` answers only on this machine, and no API docs are served.
- Deterrents in `app/static/guard.js`:
  - no right-click, devtools/view-source/save/print shortcuts, text copy or image drag;
  - the page blurs when the window loses focus (screen-capture tools) or when devtools look open;
  - printing is disabled and a light watermark is shown.
- Browsers cannot technically prevent OS screenshots or phone cameras; these measures deter casual copying.

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

## "Bangalore RealEstate Delta" email
- Sent by the batch after the website refresh, once per edition.
  - **From:** `info@raditsoftware.com`.
  - **Subject:** "Bangalore RealEstate Delta".
  - **To:** `EMAIL_TO` from `.env`.
  - **Bcc:** every active subscriber. Bcc addresses go only to the SMTP envelope, never into the message headers.
- **Settings:** `config/email.yaml` (from address, subject, attachments, site URL). Secrets and recipients live in `.env`, which is git-ignored (template: `.env.example`).
- **Sending for real:** add `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER` and `SMTP_PASSWORD` for the info@raditsoftware.com mailbox to `.env`. Until then every run is a dry run that writes `data/app/outbox/<date>/delta.eml` and `envelope.txt`.
- **Commands:** `make email-preview` writes a dry run; `make email` sends; `python -m harness.cli email --to you@example.com` sends a single test copy and is not logged.
- **Attachments:** the daily 5-page PDF, plus the magazine on the first email after each new issue.
- **Unsubscribe:** recipients reply to info@raditsoftware.com with "unsubscribe" (List-Unsubscribe mailto). Mark them with `app.store.unsubscribe(email)`, or let them use `/unsubscribe` with a signed link.

## Subscribers
Stored locally in `data/app/app.db`; they receive the daily delta email in Bcc unless unsubscribed.
Export: `curl http://127.0.0.1:8787/api/admin/subscribers` (localhost only). See `docs/ROADMAP.md` for delivery.
