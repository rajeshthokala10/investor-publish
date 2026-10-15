---
name: project-tracking
description: Extract and maintain structured project records (name, developer, corridor, type, launch/status, RERA, sizes, prices with basis and kind, charges, possession, infra links, sources, confidence, open questions) in data/processed/projects.json.
---
# Project extraction and tracking

**Purpose.** One record per real project, merged across days, with every value traceable to a source.

**Inputs.** `projects[]` from agent findings; existing `data/processed/projects.json`.

**Outputs.** `data/processed/projects.json` (keyed `P-<hash(name, developer)>`), the "Projects seen in this edition" tables in the daily report and JSON export.

**Permitted tools.** WebSearch/WebFetch (agent stage); `analysis/trackers.py::merge_projects` for merging. No manual edits to values without a source.

**Evidence requirements.**
- Unknown field → `null`, rendered as **"Not verified"**. Never infer a RERA number, price or date.
- RERA status is "Not verified" unless the agent saw the number on rera.karnataka.gov.in itself; even then it is labelled agent-reported with the date.
- Each price observation keeps value, unit, **basis** (land / carpet / built-up / super built-up / unknown) and **kind** (asking / developer quote / reported transaction / registered transaction / analyst estimate).
- Conflicting launch dates, possession, developer or RERA numbers are kept as `conflict:` flags, not overwritten silently.

**Failure handling.** Records without a URL are dropped at extraction. Geo mismatches are flagged, not "corrected".

**Acceptance criteria.** `tests/test_pipeline_offline.py` passes (sq yd land rate normalised to ₹/sq ft, RERA shown as "Not verified").
