---
name: source-discovery
description: Find, classify and register public sources for Bengaluru real-estate research (government, RERA, agencies, developers, media, research houses, portals, social). Use when adding sources, when a feed fails, or when a new publisher appears in findings.
---
# Source discovery

**Purpose.** Keep `config/sources.yaml` an accurate registry of where evidence comes from, how much weight it carries, and which sources are NOT independent of each other.

**Inputs.** `config/sources.yaml`; `logs/source_failures.jsonl`; unknown domains in the latest `reports/daily/<date>.json` (`claims[].tier == "unknown"`).

**Outputs.** Edits to `config/sources.yaml`: `domains[]` (suffix, tier, group, name), `rss_feeds[]`, `google_news.queries[]`, `known_unavailable[]`.

**Permitted tools.** WebSearch, WebFetch (public pages only), Read/Edit on `config/sources.yaml`. `curl -I` to test a feed. No logins, no paywall/captcha bypass, no scraping behind authentication.

**Evidence requirements.**
- Tier from what the source *is*: government/statutory → `primary_official`; K-RERA → `regulator`; developers, brokers, portals, consultancies and influencers are interested parties.
- `group` = owner/newsroom family. Same group (e.g. TOI / ET / Bangalore Mirror = `times_group`) never counts as independent confirmation.
- Record HTTP status and date for any source added to `known_unavailable`.

**Failure handling.** Feeds returning 401/403/406 stay out of `rss_feeds` and go into `known_unavailable` with the status code and date. Never add a workaround that defeats access controls.

**Acceptance criteria.** `pytest tests/test_geography_and_schedule.py` passes; every new domain has tier + group; `python -m harness.cli run --no-agent --edition <today>` shows `feeds_failed=0` or the failures are listed in `known_unavailable`.
