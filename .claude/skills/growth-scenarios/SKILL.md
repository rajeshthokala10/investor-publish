---
name: growth-scenarios
description: Build conservative/base/optimistic appreciation scenarios and illustrative cost-aware investment calculations for corridor × property type (plots, villas, apartments), and the transparent attractiveness score kept separate from evidence confidence.
---
# Growth-scenario analysis

**Purpose.** Show what plausible outcomes look like under explicit assumptions, and refuse to estimate when evidence is thin.

**Inputs.** Claims ledger (`data/processed/claims_ledger.json`), infrastructure tracker, `config/scoring.yaml`.

**Outputs.** `model.cells[]` (factors with claim IDs, attractiveness 1–5 or Unranked, confidence High/Medium/Low, scenarios), `illustrations[]`; sections 4, 6, 7 of the report.

**Permitted tools.** `analysis/model.py`, `validation/calculations.py`. No web access.

**Evidence requirements.**
- Future value = Purchase price × (1 + g)^years. Cumulative and real (after `inflation_pct`) shown for 3/5/10 years.
- Scenarios need appreciation evidence from ≥ `min_appreciation_sources` independent groups with usable status; else **"Insufficient evidence to estimate."**
- Base = `base_haircut` × historical median CAGR, clamped to [floor, cap]; conservative/optimistic = fixed pp offsets; rounded to 0.5 pp (no false precision).
- Capital appreciation and rent are separated; illustrations list acquisition, holding, vacancy, selling and financing costs and the excluded items.
- Attractiveness needs ≥ `min_factors_for_rank` evidenced factors; otherwise "Unranked". Confidence is computed from factor coverage and share of strong evidence, never from the score.

**Failure handling.** Never infer a trend from a few listings or one broker; interested-party claims are not usable inputs.

**Acceptance criteria.** Gate G3/G4 pass; `recheck/recheck.py::recompute` reports no calc errors; tests in `tests/test_prices_and_calculations.py` pass.
