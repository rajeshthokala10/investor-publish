---
name: noise-removal
description: Remove duplicate and syndicated articles, detect old news republished with new dates, group repeated project ads, separate facts from marketing, and flag unsupported "guaranteed appreciation" claims. Use in the Deduplicate stage or when the report repeats itself.
---
# Noise removal

**Purpose.** One story counts once; marketing never becomes evidence.

**Inputs.** RSS items, extracted claims, `data/history/seen_stories.json`.

**Outputs.** `stories[]` with `novelty` (new/update/repeat) and `stale_flags`; claim `syndication_id`, `novelty`, flags `unsupported_guarantee`, `marketing_language`, `outside_window`, `undated`, `republished_old_event`.

**Permitted tools.** `noise_removal/dedupe.py`, `noise_removal/marketing.py`.

**Evidence requirements.**
- URL canonicalisation (tracking params, AMP, mobile hosts) before comparison.
- Title shingle Jaccard ≥ 0.55 → same story; excerpt Jaccard ≥ 0.7 across publishers → same syndication cluster (one vote in verification).
- Story fingerprints already archived in an earlier edition with no new fact keys → `repeat` (suppressed); with new facts → `update`.
- Original excerpts are preserved; nothing is rewritten during normalisation.

**Failure handling.** When unsure whether two items are the same story, keep both (false merges hide news; false splits are caught by syndication voting).

**Acceptance criteria.** `tests/test_noise_removal.py` and `tests/test_pipeline_offline.py::test_next_day_same_news_is_repeat` pass.
