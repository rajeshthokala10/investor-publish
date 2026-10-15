# Deployment (Railway)

Live site: **https://web-production-b8fbb.up.railway.app**. Railway project `bangalore-realestate-delta`, service `web`, environment `production`.

## How a change reaches the site
1. **Content.** The 06:00 and 18:00 IST batches refresh the website content. The `publish` step commits only the paths in `config/deploy.yaml` (`data/app/*.json`, the cover image, `reports/`) and pushes to `main`.
2. **CI.** GitHub Actions (`.github/workflows/deploy.yml`) runs the test suite and a Docker build check.
3. **Deploy.** Railway is connected to the repo with **Wait for CI**: it builds the `Dockerfile` and deploys only after CI passes. The health check is `/healthz`, with restart on failure.
4. **Smoke test.** The `smoke` job waits for the new deployment and checks the live site.

Code changes follow the same path (`git push` to `main`).

## Runtime
| Item | Setting |
|---|---|
| Image | `Dockerfile` (python:3.12-slim). Starts as root only to prepare the volume, then runs as user `web` (`app/entrypoint.py`). |
| Port | `$PORT` (Railway), behind Railway's proxy (`--proxy-headers`) |
| Volume | `/data`, holding the subscriber database (`APP_DB=/data/app.db`); survives redeploys |
| Variables | `ADMIN_TOKEN` (private; also in the local `.env`), `APP_DB` |
| Private API | `/api/*` returns 404 unless the request carries `Authorization: Bearer $ADMIN_TOKEN`. The local batch uses this to Bcc website subscribers. |
| Not on Railway | Research agents, Chrome and PDF rendering run on the publishing machine; the server only serves content |

## Commands
```bash
railway status                      # linked project/service
railway logs --service web          # runtime logs
railway up --service web --ci       # manual deploy from this folder
railway variable list --service web
python -m harness.cli batch --steps site,publish   # push refreshed content now (redeploys after CI)
```

## Optional: CLI deploys from GitHub Actions
Create a project token in the Railway dashboard (project → Settings → Tokens) and save it as the GitHub secret `RAILWAY_TOKEN`. Then run the workflow manually with "cli_deploy" ticked.
