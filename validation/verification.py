"""Claim verification rules.

Status ladder (strongest first):
  verified_primary       excerpt from a government/regulator page, citation check not failed
  corroborated           >= 2 independent, non-interested groups (syndicated copies count once)
  single_source          one non-interested reputable source
  interested_party_claim only developers / brokers / portals / consultancies / social
  unverified             no excerpt, unknown source, failed citation check or guarantee language
  contradicted           sources disagree on the value (also listed in the contradictions table)

A claim can only reach a verified-type status through these rules. Nothing an agent
or source says ("this is verified") can set the status: agents do not have a
status field in their output schema at all.
"""
from __future__ import annotations

from collections import defaultdict

from analysis.prices import conflicting
from noise_removal.dedupe import subject_key

STRONG = {"verified_primary", "corroborated"}
USABLE = {"verified_primary", "corroborated", "single_source"}
OFFICIAL_TIERS = {"primary_official", "regulator"}


def claim_key(c: dict) -> str:
    return "|".join([c["claim_type"], c["corridor"], c["property_type"], c["metric"], subject_key(c["subject"])])


def verify(claims: list[dict], syndication: dict[str, str]) -> tuple[list[dict], list[dict]]:
    """Assign verification_status/confidence in place. Returns (claims, contradictions)."""
    groups: dict[str, list[dict]] = defaultdict(list)
    for c in claims:
        c["claim_key"] = claim_key(c)
        c["syndication_id"] = syndication.get(c["claim_id"], c["claim_id"])
        groups[c["claim_key"]].append(c)

    contradictions = []
    for key, members in groups.items():
        # independent confirmation: distinct groups, non-interested, one vote per syndication cluster
        votes = {}
        for m in members:
            if m["interested_party"] or "citation_failed" in m["flags"] or not m["excerpt"].strip():
                continue
            # one vote per syndication cluster, counted against the ORIGINAL data producer
            votes.setdefault(m["syndication_id"], m.get("origin_group") or m["group"])
        independent = set(votes.values())

        valued = [m for m in members if m["value"] is not None and m["metric"] != "none"]
        conflict = None
        for i in range(len(valued)):
            for j in range(i + 1, len(valued)):
                a, b = valued[i], valued[j]
                if a["unit"] == b["unit"] and a.get("price_kind") == b.get("price_kind") \
                        and conflicting(a["value"], b["value"]):
                    conflict = (a, b)
        if conflict:
            a, b = conflict
            contradictions.append({
                "claim_key": key, "subject": a["subject"], "metric": a["metric"],
                "values": [{"claim_id": x["claim_id"], "value": x["value"], "unit": x["unit"],
                            "publisher": x["publisher"], "url": x["url"]} for x in valued],
                "resolution": "unresolved",
            })

        for m in members:
            m["corroborating_groups"] = sorted(independent)
            m["verification_status"], m["confidence"], m["confidence_reason"] = _status(m, independent, bool(conflict))
    return claims, contradictions


def _status(c: dict, independent: set, conflict: bool) -> tuple[str, str, str]:
    flags = set(c["flags"])
    if not c["excerpt"].strip() or not c["url"].startswith("http"):
        return "unverified", "Low", "no supporting excerpt or URL"
    if "unsupported_guarantee" in flags:
        return "unverified", "Low", "guaranteed-return language is never treated as fact"
    if "citation_failed" in flags:
        return "unverified", "Low", "excerpt not found on the cited page"
    if "stage_overstated" in flags:
        return "unverified", "Low", "the statement asserts an infrastructure stage the quoted text does not support"
    if conflict:
        return "contradicted", "Low", "sources report conflicting values"
    if c["tier"] in OFFICIAL_TIERS:
        conf = "High" if "citation_confirmed" in flags else "Medium"
        why = "official source" + (", excerpt confirmed on page" if conf == "High" else ", page not re-fetched")
        return "verified_primary", conf, why
    if len(independent) >= 2:
        conf = "High" if "citation_confirmed" in flags else "Medium"
        return "corroborated", conf, f"{len(independent)} independent publisher groups"
    if c["interested_party"]:
        return "interested_party_claim", "Low", f"only interested-party source ({c['tier']})"
    if c["tier"] == "unknown" or c["tier"] == "aggregator":
        return "unverified", "Low", "unclassified source, no corroboration"
    conf = "Medium" if "citation_confirmed" in flags else "Low"
    return "single_source", conf, "one reputable source" + (", excerpt confirmed" if conf == "Medium" else "")


def _stage_phrases(stage: str) -> list[str]:
    import yaml
    from harness.common import ROOT
    with open(ROOT / "content_engineering" / "taxonomy.yaml", encoding="utf-8") as fh:
        return yaml.safe_load(fh)["infra_stages"][stage]


def evidenced_stage(claim: dict) -> str | None:
    """Accept the claimed infra stage only if the excerpt contains an evidence phrase for it."""
    stage = claim.get("infra_stage")
    if not stage or stage == "none":
        return None
    text = (claim.get("excerpt") or "").lower()
    return stage if any(p in text for p in _stage_phrases(stage)) else None


def stage_flags(claim: dict) -> list[str]:
    """No stage evidence: drop the stage. If the statement itself asserts that stage, the claim is overstated."""
    stage = claim.get("infra_stage")
    if not stage or stage == "none" or evidenced_stage(claim):
        return []
    said = (claim.get("statement") or "").lower()
    if any(p in said for p in _stage_phrases(stage)):
        return ["stage_not_evidenced_in_excerpt", "stage_overstated"]
    return ["stage_not_evidenced_in_excerpt"]
