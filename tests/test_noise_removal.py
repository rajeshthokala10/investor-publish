from datetime import datetime

from harness.common import IST
from noise_removal.dedupe import (canonical_url, classify_against_history, dedupe_articles, staleness,
                                  syndication_clusters)
from noise_removal.marketing import flags_for, marketing_profile

WINDOW = (datetime(2026, 10, 12, 6, tzinfo=IST), datetime(2026, 10, 15, 6, tzinfo=IST))


def art(title, url, publisher="The Hindu", group="the_hindu_group", pub="2026-10-14T10:00:00+05:30", interested=False):
    return {"title": title, "url": url, "publisher": publisher, "group": group, "published_at": pub,
            "interested_party": interested, "corridors": [], "regions": ["east"]}


def test_canonical_url_strips_tracking_amp_and_mobile():
    a = canonical_url("https://m.thehindu.com/news/x/amp/?utm_source=tw&id=5")
    b = canonical_url("https://www.thehindu.com/news/x?id=5")
    assert a == b == "https://thehindu.com/news/x?id=5"


def test_same_url_and_syndicated_titles_collapse_to_one_story():
    items = [art("Metro Blue Line work 90% complete, says BMRCL", "https://thehindu.com/a?utm_source=x"),
             art("Metro Blue Line work 90% complete, says BMRCL", "https://www.thehindu.com/a"),
             art("BMRCL: Metro Blue Line work 90% complete", "https://deccanherald.com/b", "Deccan Herald", "printers_mysore"),
             art("Varthur lake overflows after rain", "https://thehindu.com/c")]
    stories = dedupe_articles(items)
    assert len(stories) == 2
    metro = next(s for s in stories if "Blue" in s["title"])
    assert len(metro["members"]) == 2                      # exact URL duplicate removed, syndicated copy grouped
    assert metro["independent_groups"] == ["printers_mysore", "the_hindu_group"]


def test_press_release_copies_form_one_syndication_cluster():
    ex = "Fictional Developer on Tuesday launched Fixture Meadows, a 300-plot villa plot development at Budigere Cross."
    claims = [{"claim_id": "C-1", "excerpt": ex}, {"claim_id": "C-2", "excerpt": ex + " "},
              {"claim_id": "C-3", "excerpt": "Varthur residents report flooding after rain on Monday night."}]
    syn = syndication_clusters(claims)
    assert syn["C-1"] == syn["C-2"] != syn["C-3"]


def test_staleness_flags():
    assert staleness("2026-10-14", None, WINDOW) == []
    assert staleness("2026-09-01", None, WINDOW) == ["outside_window"]
    assert staleness(None, None, WINDOW) == ["undated"]
    assert staleness("2026-10-14", "2023-10-09", WINDOW) == ["republished_old_event"]


def test_history_classification_new_update_repeat():
    seen = {"S-1": {"fact_keys": ["F-a"]}}
    assert classify_against_history("S-2", {"F-a"}, seen) == "new"
    assert classify_against_history("S-1", {"F-a"}, seen) == "repeat"
    assert classify_against_history("S-1", {"F-a", "F-b"}, seen) == "update"


def test_guarantee_and_hype_detection():
    p = marketing_profile("Guaranteed returns! Prices will double in 3 years. Limited period offer, book now.")
    assert "unsupported_guarantee" in flags_for(p)
    assert "marketing_language" in flags_for(p)
    neutral = marketing_profile("The project has 300 plots and is registered with K-RERA.")
    assert flags_for(neutral) == []
