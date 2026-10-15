import plistlib
from collections import Counter
from datetime import date, datetime, timedelta

from harness import scheduler
from harness.common import IST, edition_window, load_config
from harness.registry import corridors, geo_check, infra_links, match_corridors, primary_corridor


def test_every_alias_maps_to_exactly_one_corridor():
    counts = Counter(a.lower() for c in corridors().values() for a in c["aliases"])
    dupes = [a for a, n in counts.items() if n > 1]
    assert not dupes, f"aliases in more than one corridor: {dupes}"


def test_regions_and_straddles_are_valid():
    regions = set(load_config("corridors")["regions"])
    for cid, c in corridors().items():
        assert c["region"] in regions, cid
        assert set(c.get("straddles", [])) <= regions, cid
        assert c.get("classification_note"), f"{cid} needs a classification note"


def test_longest_alias_wins_and_project_counted_once():
    assert primary_corridor("Sarjapur Road, near Dommasandra") == "sarjapur_road"
    assert primary_corridor("off Old Madras Road") == "kr_puram_hoskote"
    assert primary_corridor("Budigere Cross") == "budigere_cross"
    assert match_corridors("Whitefield and Varthur") == ["whitefield", "varthur_gunjur"]
    assert primary_corridor(None, "Unknown place") == "unmapped"


def test_geo_check_flags_far_map_points():
    assert geo_check("whitefield", 12.97, 77.75) is None
    assert "geo_mismatch" in geo_check("whitefield", 12.85, 77.66)   # Electronic City coordinates


def test_infrastructure_links():
    keys = [k for k, _ in infra_links("Namma Metro Blue Line Phase 2A")]
    assert keys == ["namma_metro_blue"]
    assert infra_links("Sarjapur–Hebbal metro DPR")[0][0] == "sarjapur_hebbal_metro"
    for _, e in load_config("corridors")["infrastructure_links"].items():
        assert set(e["corridors"]) <= set(corridors())


def test_window_is_72h_and_anchored_to_slot():
    late = datetime(2026, 10, 15, 14, 0, tzinfo=IST)
    s, e = edition_window(date(2026, 10, 15), now=late)
    assert e == datetime(2026, 10, 15, 6, 0, tzinfo=IST) and e - s == timedelta(hours=72)
    early = datetime(2026, 10, 15, 5, 30, tzinfo=IST)
    s, e = edition_window(date(2026, 10, 15), now=early)
    assert e == early and e - s == timedelta(hours=72)


def test_next_run_is_6am_ist():
    assert scheduler.next_run(datetime(2026, 10, 15, 5, 0, tzinfo=IST)) == datetime(2026, 10, 15, 6, 0, tzinfo=IST)
    assert scheduler.next_run(datetime(2026, 10, 15, 6, 0, tzinfo=IST)) == datetime(2026, 10, 16, 6, 0, tzinfo=IST)


def test_plist_is_well_formed():
    p = scheduler.build_plist()
    assert p["ProgramArguments"][-2:] == ["harness.cli", "scheduled"]
    assert set(p["StartCalendarInterval"]) == {"Hour", "Minute"}
    plistlib.dumps(p)
