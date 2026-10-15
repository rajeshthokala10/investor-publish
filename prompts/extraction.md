# Extraction rules (claims and projects)

Output must validate against `validation/schemas/agent_findings.schema.json`.

1. One claim = one checkable statement (a launch, a price, a stage, a policy change, a risk).
   Split compound sentences. Keep the statement faithful to the source; never strengthen it.
2. `excerpt` is copied verbatim (≤400 chars) and must contain every number, date, place and
   stage word in `statement`. If you cannot quote it, drop the claim.
3. `subject` names the thing (project, infrastructure item, policy, market) consistently, e.g.
   "Namma Metro Blue Line Phase 2A", "Sobha Townpark", "Karnataka guidance value revision".
4. Dates: `published_at` as shown on the page; `event_date` only when the text states it.
5. Prices: value + unit exactly as quoted; `price_basis` (land / carpet / built_up /
   super_built_up / unknown) and `price_kind` (asking / developer_quote / reported_transaction /
   registered_transaction / analyst_estimate). Ranges → `value` (min) and `value_max`.
6. Appreciation: `appreciation_pct` + `period_years`, or `cagr_pct`. No period → `period_years: null`
   (the analysis will not use it for scenarios).
7. `infra_stage` only when the excerpt itself shows that stage (see
   `content_engineering/taxonomy.yaml`). MoU / pledge = announced. DPR = proposed.
8. `source_kind` describes the publisher, not the topic: a news story about a developer
   launch is `news`; the developer's own page is `developer`.
9. Marketing language ("guaranteed", "assured returns", "will double") is quoted in the
   excerpt and reported as a claim by that party, never restated as fact.
10. Projects: every unknown field is null. `rera_checked_on_portal` true only when seen on
    rera.karnataka.gov.in. Put unresolved points in `open_questions`.
