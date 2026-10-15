"""Planned cities & clusters: numbers must be evidenced, distances approximate, articles validated."""
from harness.clusters import locate, slugify, validate_article, validate_cluster


def cluster(**kw):
    c = {"name": "KWIN City", "full_name": None, "kind": "knowledge_city", "agency": "KIADB", "location_text": "near Doddaballapur",
         "nearest_town": "Doddaballapur", "distance_km_stated": None, "area_acres": 5800, "investment_inr_crore": 48000,
         "investment_kind": "expected_investment", "investment_text": None, "jobs_expected": 99999, "stage": "announced",
         "timeline_text": None, "anchors": [], "connectivity": [], "highlights": ["Spans 5,800 acres", "Will create 2 lakh jobs"],
         "risks": [], "facts": [{"statement": "KWIN City spans 5,800 acres", "url": "https://example.com/a", "publisher": "The Hindu",
                                 "published_at": "2026-05-26", "excerpt": "KWIN City, spread over 5,800 acres, is expected to draw Rs 48,000 crore."}]}
    c.update(kw)
    return c


def test_unevidenced_numbers_are_removed():
    c, notes = validate_cluster(cluster(), {})
    assert c["area_acres"] == 5800 and c["investment_inr_crore"] == 48000
    assert c["jobs_expected"] is None                                   # 99999 not in any excerpt
    assert c["highlights"] == ["Spans 5,800 acres"]                      # "2 lakh" not evidenced
    assert c["slug"] == "kwin-city" and c["distance_km_approx"] == 36


def test_cluster_without_facts_or_with_failed_citations_is_dropped():
    assert validate_cluster(cluster(facts=[]), {})[0] is None
    f = cluster()["facts"][0]
    assert validate_cluster(cluster(), {f["url"] + f["excerpt"]: {"result": "failed"}})[0] is None


def test_locations_corridors_and_in_city():
    assert locate(cluster(kind="corridor", nearest_town="Bengaluru", location_text="Tumakuru Road to Hosur Road"))["coords"] is None
    inside = locate(cluster(kind="layout", nearest_town="Bengaluru", location_text="north Bengaluru"))
    assert inside["coords"] is None and inside["within_city"]
    assert locate(cluster(nearest_town="Hesaraghatta"))["distance_km_approx"] == 23


def test_article_numbers_validated():
    c, _ = validate_cluster(cluster(), {})
    a = {"slug": "kwin-city", "headline": "KWIN City takes shape", "standfirst": "A 5,800-acre plan",
         "paragraphs": ["It spans 5,800 acres.", "It will host 300 firms."], "key_facts": [{"label": "Area", "value": "5,800 acres"},
                                                                                         {"label": "Firms", "value": "300"}],
         "whats_next": ["DPR due"]}
    a, notes = validate_article(a, c)
    assert a["paragraphs"] == ["It spans 5,800 acres."] and [k["label"] for k in a["key_facts"]] == ["Area"]
    assert slugify("Bidadi Township / AI City") == "bidadi-township-ai-city"
