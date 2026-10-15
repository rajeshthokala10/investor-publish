---
name: corridor-research
description: Research a Bengaluru region or corridor (East first: Whitefield, Sarjapur Road, Varthur–Gunjur, Panathur–Balagere, Budigere Cross, KR Puram–Hoskote) for launches, prices, jobs, connectivity, supply/absorption, rental/resale, civic risks. Use for corridor deep dives or when maintaining config/corridors.yaml.
---
# Regional and corridor research

**Purpose.** Produce evidence (not opinions) per corridor and keep the corridor map consistent so no project is double-counted.

**Inputs.** `config/corridors.yaml` (regions, corridors, aliases, centroids, `straddles`, `infrastructure_links`), `config/research_tasks.yaml` (task focus text), the 72-hour window.

**Outputs.** Agent findings conforming to `validation/schemas/agent_findings.schema.json` (written by the harness to `data/raw/<edition>/agent/<task>.json`); corridor map edits.

**Permitted tools.** WebSearch, WebFetch only (this is enforced: the harness starts the agent with `--tools WebSearch,WebFetch`). Map edits: Read/Edit on `config/corridors.yaml`.

**Evidence requirements.**
- Every claim: URL, publisher, verbatim excerpt, published date (and event date if stated). No excerpt → do not report it.
- `locality` is the most specific place the source names; the harness assigns the corridor via the gazetteer (longest alias wins) so the agent never assigns regions.
- Distinguish announcement-driven interest (MoUs, proposals, "plans") from completed infrastructure and measured demand (absorption, leasing, registrations).
- Assess per corridor: launches/phases, pricing (with basis), employment, connectivity, supply/absorption, rental/resale, water/flooding/traffic, execution/oversupply/affordability risk.

**Failure handling.** If a corridor has no evidence in the window, report nothing for it. The report says "No new evidence in the window"; it never fills the gap.

**Acceptance criteria.** Aliases unique across corridors (`tests/test_geography_and_schedule.py::test_every_alias_maps_to_exactly_one_corridor`); each corridor has a `classification_note`; projects with map points far from their corridor centroid are flagged `geo_mismatch`.
