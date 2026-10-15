---
name: fact-checking
description: Verify and independently recheck claims before publication - citation support checks, primary-source/independent-corroboration rules, contradiction detection, link checks, recomputed calculations and publication gates. Use before publishing or when a claim's status is questioned.
---
# Fact-checking and rechecking

**Purpose.** Guarantee that unsupported claims cannot silently become verified facts.

**Inputs.** Claims after deduplication; `prompts/recheck.md`; `validation/gates.py`.

**Outputs.** `verification_status` ∈ {verified_primary, corroborated, single_source, interested_party_claim, unverified, contradicted}, `confidence` + reason, `citation_check`, `recheck` verdicts, `contradictions[]`, gate results.

**Permitted tools.** HTTP GET of cited pages (rate-limited, budgeted); an independent headless reviewer with WebFetch only; `validation/verification.py`, `recheck/*.py`.

**Evidence requirements.**
- Status is assigned ONLY by `validation/verification.py`; the agent schema has no status field (additionalProperties: false).
- Citation check: ≥60% of excerpt word-trigrams and every number must be on the page → `citation_confirmed`; <20% on a substantial page → `citation_failed` → unverified.
- Corroboration counts distinct independence groups, excluding interested parties and syndicated copies.
- Recheck reviewer verdict `not_supported` downgrades the claim and re-runs analysis.
- Each claim retains ID, URL, publisher, published date, event date, retrieval timestamp, excerpt, status, confidence and reason.

**Failure handling.** Blocked/JS pages → `inconclusive` (status unchanged but confidence not raised). Hard gate failure → report written to `reports/daily/_blocked/`, exit code 3.

**Acceptance criteria.** `tests/test_verification.py` passes; daily JSON `meta.gates.passed == true`; contradictions shown in section 8.
