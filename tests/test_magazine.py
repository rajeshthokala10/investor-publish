"""Magazine guardrails: only publishable evidence; numbers in copy must come from cited claims."""
from harness.magazine import publishable
from harness.magazine_write import check_block, validate


def claim(cid, status="single_source", tier="reputable_media", flags=(), stmt="ANAROCK: Q3 2026 sales rose 12% to 16,670 units",
          check="confirmed"):
    return {"claim_id": cid, "verification_status": status, "tier": tier, "flags": list(flags), "statement": stmt,
            "excerpt": stmt, "subject": "Bengaluru housing sales", "published_at": "2026-10-01", "value": 16670,
            "value_max": None, "period_years": None, "citation_check": {"result": check}}


def test_publishable_rules():
    assert publishable(claim("C-1"))
    assert not publishable(claim("C-2", status="unverified"))
    assert publishable(claim("C-3", status="interested_party_claim", tier="developer"))       # own announcement, attributed
    assert not publishable(claim("C-4", status="interested_party_claim", tier="broker_marketing"))
    assert not publishable(claim("C-5", status="interested_party_claim", tier="developer", flags=["unsupported_guarantee"]))
    assert not publishable(claim("C-6", status="interested_party_claim", tier="developer", check="inconclusive"))


def test_numbers_must_come_from_cited_claims():
    by = {"C-1": claim("C-1")}
    assert check_block("ANAROCK says sales rose 12% to 16,670 units.", ["C-1"], by) is None
    assert "18000" in check_block("Sales rose to 18,000 units.", ["C-1"], by)
    assert check_block("Sales rose.", ["C-9"], by) == "no valid claim cited"


def test_validate_drops_invented_figures_and_strips_cover_numbers():
    by = {"C-1": claim("C-1")}
    para_ok = {"text": "Sales rose 12%.", "claim_ids": ["C-1"]}
    para_bad = {"text": "Prices will rise 25% next year.", "claim_ids": ["C-1"]}
    issue = {"cover": {"headline": "Sales up 40%", "subhead": "x", "cover_lines": ["9 hot towns", "Metro plans"], "claim_ids": ["C-1"]},
             "editor_note": [para_ok, para_bad], "glance": [], "gov_intro": [], "growth_map_caption": [], "growth_intro": [],
             "outlook": [], "property_types": {"plots": [], "villas": [], "apartments": [], "verdict": []},
             "key_figures": [{"label": "Sales", "value_text": "16,670", "context": "Q3", "claim_ids": ["C-1"]},
                             {"label": "Price", "value_text": "₹99,999", "context": "", "claim_ids": ["C-1"]}],
             "gov_rows": [], "growth_towns": [], "watch_list": [], "projects": [], "zones": []}
    out, dropped = validate(issue, by, None)
    assert out["editor_note"] == [para_ok]
    assert [k["value_text"] for k in out["key_figures"]] == ["16,670"]
    assert "40" not in out["cover"]["headline"] and out["cover"]["cover_lines"] == ["Metro plans"]
    assert len(dropped) == 3
