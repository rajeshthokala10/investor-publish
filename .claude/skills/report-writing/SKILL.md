---
name: report-writing
description: Write the daily Bengaluru property report (Markdown, HTML, PDF with infographic cover, JSON) and the weekly trend summary from the validated dataset, following content_engineering/style_guide.md. Use when changing report structure, wording or the infographic template.
---
# Report writing

**Purpose.** Clear, sourced, non-repetitive reports in ten fixed sections, plus a newspaper-style infographic cover.

**Inputs.** The validated dataset (publish stage), `content_engineering/style_guide.md`, `content_engineering/templates/report.css`, `harness/infographic.py`.

**Outputs.** `reports/daily/<date>.{md,html,pdf,json}`; `reports/weekly/<date>.{md,html,json}`.

**Permitted tools.** `harness/report.py`, `harness/infographic.py`, `harness/weekly.py`; headless Chrome for PDF. No external publishing, email or upload.

**Evidence requirements.**
- All formats render from the same dataset; every factual line links to its source and shows its verification status.
- Brief only carries verified/corroborated or citation-confirmed single-source items.
- Infographic numbers come from usable claims (normalised ₹/sq ft, period stated for appreciation); otherwise honest counts.
- "No new updates" and "Research failed" are distinct statuses with distinct wording.

**Failure handling.** If PDF rendering fails, the HTML/MD/JSON still publish and the failure is logged (`pdf_failed`).

**Acceptance criteria.** `tests/test_pipeline_offline.py::test_outputs_from_one_dataset` passes; no section padded with repeats.
