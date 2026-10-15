---
name: infrastructure-monitoring
description: Track government, planning and infrastructure developments (metro, suburban rail, roads, zoning, water/sewerage, employment hubs, policy, legal) on the Proposed→Announced→Approved→Funded→Tendered→Awarded→Under construction→Operational ladder, assigning a stage only when quoted text evidences it.
---
# Government and infrastructure monitoring

**Purpose.** Report what actually changed in the last 72 hours, at what stage, affecting which corridors, without treating proposals, MoUs, approvals and completed works as equivalent.

**Inputs.** `government_watch` and `east_catalysts_risks` task findings; `content_engineering/taxonomy.yaml` (`infra_stages` evidence phrases); `config/corridors.yaml` (`infrastructure_links`).

**Outputs.** `data/processed/infrastructure.json` (stage + stage_history + notes), section 5 of the daily report, `stage_changes` in the JSON export.

**Permitted tools.** WebSearch, WebFetch; prefer agency sites (bmrc.co.in, kride.in, BDA, BWSSB, KIADB, NHAI, karnataka.gov.in, PIB) over coverage.

**Evidence requirements.**
- Publication date AND underlying event date.
- `validation/verification.py::evidenced_stage`: the stage must appear in the excerpt via an evidence phrase; otherwise the claim gets `stage_not_evidenced_in_excerpt` and is **unverified**.
- Only usable claims (verified_primary / corroborated / single_source) move the tracker; stages never move backwards silently (a review note is written instead).
- Old events republished with new dates are flagged `republished_old_event` and are not new.

**Failure handling.** If no agency page is reachable, say so in coverage gaps; never infer a stage from a headline.

**Acceptance criteria.** Gate G6 passes (every stage change rests on a usable claim with an evidenced stage); `tests/test_verification.py::test_stage_requires_evidence_phrase` passes.
