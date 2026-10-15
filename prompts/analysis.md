# Analysis guidance

Use when interpreting `model.cells` or writing a manual corridor deep dive.

- Read the factor table, not just the score: each factor lists the claim IDs behind it.
  A 4.0 built from three single-source claims is weaker than a 3.5 from official data;
  that is what `confidence` and `strong_evidence_share` express.
- Keep **attractiveness** and **evidence confidence** separate in every sentence.
  "Ranked 2nd with Low confidence" is a valid and important statement.
- Unranked is an answer. Do not rank by intuition to fill the table.
- Announcements vs outcomes: connectivity points weight stages (operational 1.0 … proposed
  0.05). A corridor whose score rests on proposals is speculative.
- Priced in? Without registered-price time series we cannot measure it. Say so; point to
  asking-price changes after an announcement only as weak, interested-party evidence.
- Scenarios: base = 0.8 × historical median CAGR, clamped to [-2%, 12%]; ±pp offsets.
  State the assumptions, show real (after-inflation) figures, separate rent from capital.
- Disconfirming evidence is mandatory for every opportunity: risks, contradictions, missing
  factors, oversupply, water/flooding, execution delays.
- Never infer a market trend from a few listings or one broker claim.
