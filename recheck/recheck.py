"""Recheck stage: independent second pass before publishing.

1. Select consequential claims (brief candidates, stage changes, inputs to ranked
   cells and scenarios).
2. Independent LLM review (optional, budgeted): a fresh agent re-reads each cited page
   and answers supported / not_supported / unable. not_supported downgrades the claim.
3. Link check of every cited URL (HTTP status recorded; dead links flagged).
4. Recompute every scenario and illustration with validation.calculations.
5. Re-run analysis if any claim was downgraded so rankings never rest on it.
"""
from __future__ import annotations

import json

from harness import agent
from harness.common import PROMPTS, load_config
from validation.calculations import cumulative_pct, illustrative_investment
from validation.verification import USABLE

REVIEW_SCHEMA = {
    "type": "object", "additionalProperties": False, "required": ["reviews"],
    "properties": {"reviews": {"type": "array", "items": {
        "type": "object", "additionalProperties": False, "required": ["claim_id", "verdict", "reason"],
        "properties": {"claim_id": {"type": "string"},
                       "verdict": {"enum": ["supported", "not_supported", "unable"]},
                       "reason": {"type": "string", "maxLength": 300}}}}}}


def consequential(d: dict, n: int) -> list[dict]:
    ids = set()
    for cell in d["model"]["cells"]:
        for f in cell["factors"].values():
            ids.update(f["claim_ids"])
        ids.update(cell["scenarios"].get("evidence_claim_ids", []))
    ids.update(s["claim_id"] for s in d.get("stage_changes", []))
    today = [c for c in d["claims"] if c["verification_status"] in USABLE and c["novelty"] != "repeat"]
    today.sort(key=lambda c: (c["region"] != "east", c["claim_type"] not in ("infrastructure", "policy", "project_launch")))
    ids.update(c["claim_id"] for c in today[:n])
    by = {c["claim_id"]: c for c in d["claims"]}
    return [by[i] for i in ids if i in by][:n]


def agent_review(ctx, claims: list[dict]) -> dict:
    cfg = load_config("harness")["recheck"]
    if not cfg["agent_review"] or not claims:
        return {}
    ok, why = agent.available()
    if not ok:
        ctx.log("recheck_agent_skipped", reason=why)
        return {}
    payload = [{"claim_id": c["claim_id"], "statement": c["statement"], "url": c["url"], "excerpt": c["excerpt"]}
               for c in claims]
    prompt = (PROMPTS / "recheck.md").read_text(encoding="utf-8").replace("{{CLAIMS}}", json.dumps(payload, indent=1))
    res = agent.run_agent(prompt, REVIEW_SCHEMA, name="recheck_review",
                          out_path=agent.raw_agent_dir(ctx.edition) / "recheck_review.json",
                          budget_usd=cfg["agent_review_budget_usd"], timeout_min=15, log=ctx.log)
    if not res["ok"]:
        return {"_error": res["error"]}
    return {r["claim_id"]: r for r in res["data"]["reviews"]}


def merge_verdict_history(ctx, reviews: dict) -> dict:
    """Verdicts accumulate per edition. LLM reviewers can disagree between runs; a split is never
    resolved in the claim's favour: it is downgraded and shown as a contradiction."""
    from harness.common import read_json, write_json
    path = agent.raw_agent_dir(ctx.edition) / "recheck_verdicts.json"
    hist = read_json(path, {})
    for cid, r in reviews.items():
        if cid.startswith("_"):
            continue
        entries = hist.setdefault(cid, [])
        if not entries or entries[-1] != r:
            entries.append(r)
    write_json(path, hist)
    return hist


def run_recheck(ctx, d: dict, reanalyse) -> dict:
    cfg = load_config("harness")
    targets = consequential(d, cfg["recheck"]["agent_review_max_claims"])
    reviews = agent_review(ctx, targets)
    history = merge_verdict_history(ctx, reviews)
    downgraded = []
    for c in d["claims"]:
        hist = history.get(c["claim_id"], [])
        if not hist:
            continue
        c["recheck"] = hist[-1]
        c["recheck_history"] = hist
        verdicts = {h["verdict"] for h in hist}
        if "not_supported" in verdicts and c["verification_status"] in USABLE | {"interested_party_claim"}:
            split = "supported" in verdicts
            c["flags"] = sorted(set(c["flags"]) | {"recheck_failed"} | ({"reviewer_split"} if split else set()))
            c["verification_status"], c["confidence"] = "unverified", "Low"
            neg = next(h for h in hist if h["verdict"] == "not_supported")
            c["confidence_reason"] = ("independent reviews disagreed; held back pending human review: " if split
                                      else "independent recheck: ") + neg["reason"]
            if split:
                d.setdefault("contradictions", []).append({
                    "claim_key": c.get("claim_key", c["claim_id"]), "subject": c["subject"], "metric": "reviewer verdicts",
                    "values": [{"claim_id": c["claim_id"], "value": 0, "unit": f"{h['verdict']}: {h['reason']}",
                                "publisher": c["publisher"], "url": c["url"]} for h in hist],
                    "resolution": "unresolved - needs human review"})
            downgraded.append(c["claim_id"])

    # link checks on everything that will be cited
    limit = cfg["budgets"]["max_link_checks"]
    links = {}
    for c in d["claims"]:
        if c["url"] in links:
            continue
        cc = c.get("citation_check") or {}
        if cc.get("http"):
            links[c["url"]] = cc["http"]
            continue
        if not ctx.budget.take("link", limit):
            links[c["url"]] = None
            continue
        r = ctx.http.get(c["url"], source=f"linkcheck:{c['domain']}")
        links[c["url"]] = r.status_code if r is not None else None
    for c in d["claims"]:
        st = links.get(c["url"])
        c["link_status"] = st
        if st in (404, 410):
            c["flags"] = sorted(set(c["flags"]) | {"dead_link"})

    if downgraded:
        ctx.log("recheck_downgraded", n=len(downgraded))
        d = reanalyse(ctx, d)

    d["recheck"] = {"reviewed": len(reviews) - (1 if "_error" in reviews else 0), "targets": len(targets),
                    "downgraded": downgraded, "agent_error": reviews.get("_error") if isinstance(reviews, dict) else None,
                    "links_checked": sum(v is not None for v in links.values()),
                    "links_unreachable": sorted(u for u, v in links.items() if v is None or v >= 400),
                    "calc_errors": recompute(d)}
    return d


def recompute(d: dict) -> list[str]:
    """Independently recompute scenario cumulative figures and illustrations."""
    sc = load_config("scoring")
    errors = []
    for cell in d["model"]["cells"]:
        s = cell["scenarios"]
        if s["status"] != "estimated":
            continue
        for name, row in s["scenarios"].items():
            g = row["annual_pct"]
            if not (sc["scenarios"]["floor_pct"] <= g <= sc["scenarios"]["cap_pct"]):
                errors.append(f"{cell['corridor']}/{cell['property_type']}/{name}: rate {g} outside bounds")
            for y, v in row["cumulative_pct"].items():
                if abs(round(cumulative_pct(g, int(y))) - v) > 0:
                    errors.append(f"{cell['corridor']}/{cell['property_type']}/{name}/{y}y: {v} != recomputed")
    for ill in d.get("illustrations", []):
        y = next((c["factors"].get("rental_yield", {}).get("value") for c in d["model"]["cells"]
                  if c["corridor"] == ill["corridor"] and c["property_type"] == ill["property_type"]), None)
        again = illustrative_investment(sc["illustrative_investment"], ill["property_type"], ill["growth_pct"],
                                        ill["years"], y, inflation_pct=sc["scenarios"]["inflation_pct"])
        if again["net_profit"] != ill["net_profit"]:
            errors.append(f"illustration {ill['corridor']}/{ill['property_type']}/{ill['years']}y mismatch")
    return errors
