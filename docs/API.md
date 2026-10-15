# API (http://127.0.0.1:8787)

Interactive docs: `/api/docs`.

| Method | Path | Returns |
|---|---|---|
| GET | `/api/site` | Everything the landing page renders (news, metrics, builders, plans, towns, zones, quotes, downloads) |
| GET | `/api/news` | `{insights[], headlines[]}`: today's usable insights and Bengaluru real-estate headlines |
| GET | `/api/metrics` | `{kpis[], series[], area_prices[]}`; every value has `source` + `url` |
| GET | `/api/builders` | `{builders[], tracked_developers[]}` |
| GET | `/api/plans` | `{plans[], growth_towns[]}` |
| GET | `/api/status` | Last refresh, recent batch runs, subscriber count |
| POST | `/api/subscribe` | Body `{email, name?, interests?[]}` → `{ok, message}` (422 on invalid email) |
| GET | `/download/{file}` | `magazine-latest.pdf`, `daily-brief-latest.pdf`, `magazine-cover.png` (allow-list only) |
| GET | `/api/admin/subscribers` | Localhost only |
| POST | `/api/admin/refresh` | Localhost only; rebuilds metrics + site data in the background |
| GET | `/healthz` | `{ok, site_data}` |
