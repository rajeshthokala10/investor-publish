# Roadmap / future work

## Delivery & audience
- [ ] Email delivery for subscribers via a transactional provider (double opt-in, unsubscribe link, bounce handling).
      Needs explicit approval and an API key in `.env` (never in git). Hook: after `site` step in `harness/batch.py`.
- [ ] Web push / WhatsApp channel for the 6 am brief.
- [ ] Public deployment: Dockerfile + reverse proxy (Caddy/Nginx) with HTTPS; move SQLite → Postgres if multi-instance.
- [ ] Admin login (currently admin endpoints are localhost-only).

## Data depth
- [ ] Registered-transaction prices (Kaveri/IGRS) if a lawful bulk source becomes available → real "priced-in" analysis.
- [ ] K-RERA project lookups (respecting captcha/terms) to verify RERA numbers.
- [ ] Accumulate quarterly series month over month (ledger already stores claims) → longer growth charts per producer.
- [ ] Builder league table from quarterly filings (bookings, launches) of listed developers (BSE/NSE).
- [ ] Interactive map (Leaflet + OSM tiles) with corridor polygons instead of centroids.

## Product
- [ ] Article pages per corridor/town with history of claims and charts.
- [ ] Search and filters (zone, property type, budget).
- [ ] Magazine archive page; per-issue HTML reader.
- [ ] Self-host Chart.js and fonts for fully offline operation.
- [ ] Kannada edition of the magazine.

## Engineering
- [ ] CI (GitHub Actions): `make test`, lint, offline pipeline replay.
- [ ] UI tests (Playwright) for landing page rendering and subscribe flow.
- [ ] Observability: export `job_runs` and costs to a small admin dashboard.
- [ ] Cost guard: monthly spend cap across daily + magazine + metrics.
