---
name: price-normalisation
description: Normalise quoted Bengaluru property prices to INR per sq ft on the SAME basis (land, carpet, built-up, super built-up) and keep price kinds separate (asking, developer quote, reported/registered transaction, analyst estimate). Use whenever prices are compared, charted or scored.
---
# Price normalisation

**Purpose.** Make prices comparable only where they genuinely measure the same thing.

**Inputs.** Claim/project `value`, `unit`, `price_basis`, `price_kind`.

**Outputs.** `psf_inr`, `total_inr`, `comparability` = `<basis_class>|<price_kind>` (e.g. `land_rate|developer_quote`, `saleable_rate|asking`), `normalisation_note`.

**Permitted tools.** `analysis/prices.py` only. No web access needed.

**Evidence requirements.**
- Conversions: 1 sq yd = 9 sq ft; 1 sq m = 10.7639; 1 acre = 43,560; 1 guntha = 1,089; 1 cent = 435.6; lakh = 1e5; crore = 1e7.
- **Never** compare a plot land rate with an apartment saleable-area rate. `comparable()` requires identical basis AND kind and a known basis.
- Affordability index (`analysis/model.py`) divides by the city median of the same comparability class, computed only when ≥3 corridors have data.
- Infographic and report show the normalised ₹/sq ft with the original quote in brackets.

**Failure handling.** Unrecognised units → `normalisation_note`, no psf. Unknown basis → flagged `price_basis_unknown`, excluded from comparisons.

**Acceptance criteria.** `tests/test_prices_and_calculations.py` passes.
