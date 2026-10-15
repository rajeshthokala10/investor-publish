"""Daily Edition guardrails: numbers must come from cited facts; sources line lists only cited publishers."""
from harness.daily_paper import _blocks, line_status_rows, metro_svg, validate


def fact(i, text, pub="The Hindu"):
    return {"claim_id": i, "statement": text, "excerpt": text, "subject": text, "published_at": "2026-10-14",
            "value": None, "value_max": None, "period_years": None, "publisher": pub, "url": "https://x/" + i}


def paper(**kw):
    base = {"lead": {"kicker": "Metro", "headline": "Pink Line inspection", "standfirst": "", "paragraphs": []},
            "second": {"kicker": "", "headline": "", "paragraphs": []}, "front_briefs": [], "metro_intro": [],
            "metro_stories": [], "development_stories": [], "government_stories": [], "around": [], "watch": []}
    base.update(kw)
    return base


def test_invented_numbers_are_dropped():
    by = {"H-1": fact("H-1", "Pink Line faces 36 safety deficiencies")}
    p = paper(metro_stories=[{"headline": "36 deficiencies flagged", "text": "BMRCL must fix 36 items.", "ids": ["H-1"], "line": "pink"},
                             {"headline": "Opening in 40 days", "text": "The line opens in 40 days.", "ids": ["H-1"], "line": "pink"}])
    out, dropped = validate(p, by)
    assert [s["headline"] for s in out["metro_stories"]] == ["36 deficiencies flagged"] and len(dropped) == 1


def test_blocks_collect_all_cited_ids():
    p = paper(front_briefs=[{"headline": "a", "text": "b", "ids": ["C-1"]}],
              around=[{"zone": "east", "items": [{"headline": "c", "text": "d", "ids": ["H-2"]}]}])
    assert {i for b in _blocks(p) for i in b["ids"]} == {"C-1", "H-2"}


def test_metro_map_and_board_cover_every_line():
    svg = metro_svg()
    assert svg.count("<polyline") == 8 and "Majestic" in svg
    names = [r["name"] for r in line_status_rows()]
    assert {"Purple Line", "Green Line", "Yellow Line", "Pink Line", "Blue Line"} <= set(names)
