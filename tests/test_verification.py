"""Unsupported claims must never silently become verified facts."""
import json

import jsonschema
import pytest

from harness.common import SCHEMAS
from harness.registry import classify_source
from noise_removal.dedupe import syndication_clusters
from validation.gates import run_gates
from validation.verification import USABLE, evidenced_stage, verify


def mk(cid, url, excerpt="Fixture Meadows has 300 plots at Budigere Cross.", flags=(), value=None, unit=None,
       subject="Fixture Meadows", metric="none", claim_type="project_launch", infra_stage="none"):
    src = classify_source(url)
    return {"claim_id": cid, "statement": "s", "publisher": src["name"], "claim_type": claim_type, "subject": subject, "corridor": "budigere_cross",
            "property_type": "plot", "metric": metric, "value": value, "unit": unit, "price_kind": "developer_quote",
            "url": url, "excerpt": excerpt, "flags": list(flags), "tier": src["tier"], "group": src["group"],
            "interested_party": src["interested_party"], "infra_stage": infra_stage}


def run(claims):
    out, contra = verify(claims, syndication_clusters(claims))
    return {c["claim_id"]: c for c in out}, contra


def test_same_group_copies_do_not_corroborate():
    by, _ = run([mk("C-1", "https://timesofindia.indiatimes.com/a"), mk("C-2", "https://economictimes.indiatimes.com/b")])
    assert by["C-1"]["verification_status"] == "single_source"


def test_two_independent_groups_corroborate_and_syndicated_copy_counts_once():
    ex = "Fictional Developer launched Fixture Meadows, a 300-plot development at Budigere Cross on Tuesday."
    claims = [mk("C-1", "https://www.thehindu.com/a", ex), mk("C-2", "https://www.deccanherald.com/b", ex)]
    by, _ = run(claims)
    # identical excerpt across publishers = one press release -> still one vote
    assert by["C-1"]["verification_status"] == "single_source"
    claims[1]["excerpt"] = "Budigere Cross gets Fixture Meadows: 300 plots by Fictional Developer, DH reports."
    by, _ = run(claims)
    assert by["C-1"]["verification_status"] == "corroborated"


def test_two_outlets_relaying_one_research_house_are_one_source():
    a = mk("C-1", "https://www.deccanherald.com/a", "Sarjapur Road prices rose 63% in three years, ANAROCK data showed.")
    b = mk("C-2", "https://www.outlookbusiness.com/b", "According to Anarock, average prices on Sarjapur Road rose 79%.")
    a["origin_group"] = b["origin_group"] = "anarock"
    by, _ = run([a, b])
    assert by["C-1"]["verification_status"] == "single_source"
    from harness.registry import originator_group
    assert originator_group("per ANAROCK Research") == "anarock" and originator_group("no producer named") is None


def test_interested_parties_never_corroborate_each_other():
    claims = [mk("C-1", "https://www.99acres.com/x", "Prices in Gunjur are rising fast, say agents."),
              mk("C-2", "https://www.magicbricks.com/y", "Gunjur demand is booming according to listings."),
              mk("C-3", "https://www.youtube.com/watch?v=z", "Gunjur will be the next Whitefield.")]
    by, _ = run(claims)
    assert all(c["verification_status"] == "interested_party_claim" for c in by.values())


@pytest.mark.parametrize("flag", ["unsupported_guarantee", "citation_failed", "stage_overstated"])
def test_disqualifying_flags_force_unverified_even_from_official_source(flag):
    by, _ = run([mk("C-1", "https://english.bmrc.co.in/x", flags=[flag])])
    assert by["C-1"]["verification_status"] == "unverified"


def test_missing_excerpt_is_unverified():
    by, _ = run([mk("C-1", "https://english.bmrc.co.in/x", excerpt="  ")])
    assert by["C-1"]["verification_status"] == "unverified"


def test_conflicting_values_are_contradicted():
    claims = [mk("C-1", "https://www.thehindu.com/a", "Priced at Rs 9,500 per sq ft.", value=9500, unit="INR/sqft", metric="price_psf"),
              mk("C-2", "https://www.deccanherald.com/b", "Starts at Rs 12,000 per sq ft.", value=12000, unit="INR/sqft", metric="price_psf")]
    by, contra = run(claims)
    assert by["C-1"]["verification_status"] == by["C-2"]["verification_status"] == "contradicted"
    assert len(contra) == 1


def test_overstated_stage_downgrades_but_missing_stage_only_drops_it():
    from validation.verification import stage_flags
    over = {"infra_stage": "awarded", "statement": "PRR contract awarded", "excerpt": "Government is considering PRR."}
    plain = {"infra_stage": "awarded", "statement": "Update on PRR", "excerpt": "Government is considering PRR."}
    assert "stage_overstated" in stage_flags(over)
    assert stage_flags(plain) == ["stage_not_evidenced_in_excerpt"]


def test_stage_requires_evidence_phrase():
    assert evidenced_stage({"infra_stage": "awarded", "excerpt": "The contract was awarded to XYZ Infra."}) == "awarded"
    assert evidenced_stage({"infra_stage": "awarded", "excerpt": "Government is considering the project."}) is None
    assert evidenced_stage({"infra_stage": "operational", "excerpt": "The line was inaugurated on Sunday."}) == "operational"


def test_agent_cannot_supply_a_verification_status():
    schema = json.loads((SCHEMAS / "agent_findings.schema.json").read_text())
    bad = {"task_id": "t", "queries_run": [], "sources_attempted": [], "projects": [], "claims": [{
        "statement": "x", "claim_type": "other", "subject": "x", "locality": None, "property_type": "na",
        "url": "https://x.com", "publisher": "x", "published_at": None, "event_date": None, "excerpt": "x",
        "source_kind": "news", "metric": "none", "value": None, "value_max": None, "unit": None, "period_years": None,
        "price_basis": "na", "price_kind": "na", "infra_stage": "none", "verification_status": "verified_primary"}]}
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(bad, schema)


def test_gate_blocks_usable_claim_with_guarantee():
    from datetime import datetime, timedelta
    from harness.common import IST
    c = mk("C-1", "https://www.thehindu.com/a", flags=["unsupported_guarantee"])
    c.update(verification_status="single_source", publisher="The Hindu", retrieved_at="2026-10-15T05:00:00+05:30",
             published_at="2026-10-14")
    end = datetime(2026, 10, 15, 6, tzinfo=IST)
    d = {"claims": [c], "model": {"cells": []}, "coverage": {}, "feeds": {"failed": []}}
    g = run_gates(d, (end - timedelta(hours=72), end))
    assert not g["passed"] and any(x.startswith("G2") for x in g["hard_failures"])
    assert "single_source" in USABLE


def test_infra_tracker_rollback_on_reanalysis():
    from analysis.trackers import rollback_edition, update_infra
    c = {"claim_id": "C-1", "claim_type": "infrastructure", "subject": "Namma Metro Blue Line", "corridor": "orr_east",
         "evidenced_stage": "under_construction", "verification_status": "single_source", "event_date": None,
         "published_at": "2026-10-14"}
    t = {}
    assert update_infra(t, [c], "2026-10-15")
    c["verification_status"] = "unverified"          # downgraded by recheck
    rollback_edition(t, "2026-10-15")
    update_infra(t, [c], "2026-10-15")
    assert t["namma_metro_blue"]["stage"] is None and t["namma_metro_blue"]["stage_history"] == []
