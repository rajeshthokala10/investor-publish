"""Builds tests/fixtures/findings_sample.json: synthetic, clearly fictional data exercising every rule."""
import json
from pathlib import Path


def claim(**kw):
    base = dict(statement="", claim_type="other", subject="", locality=None, property_type="na", url="",
                publisher="", published_at="2026-10-14", event_date=None, excerpt="", source_kind="news",
                metric="none", value=None, value_max=None, unit=None, period_years=None, price_basis="na",
                price_kind="na", infra_stage="none")
    base.update(kw)
    return base


def build():
    claims = [
        # official, evidenced stage
        claim(statement="BMRCL says Blue Line Phase 2A viaduct work between KR Puram and Silk Board is 90% complete",
              claim_type="infrastructure", subject="Namma Metro Blue Line Phase 2A", locality="KR Puram",
              url="https://english.bmrc.co.in/fixture-blue-line", publisher="BMRCL", source_kind="infrastructure_agency",
              excerpt="Civil work on the Phase 2A viaduct between KR Puram and Silk Board is 90% complete, BMRCL said.",
              infra_stage="under_construction", event_date="2026-10-13"),
        # stage claimed but not evidenced in excerpt
        claim(statement="Peripheral Ring Road has been awarded", claim_type="infrastructure",
              subject="Peripheral Ring Road / Bengaluru Business Corridor", locality="Budigere Cross",
              url="https://www.deccanherald.com/fixture-prr", publisher="Deccan Herald",
              excerpt="The government is considering options for the long-pending Peripheral Ring Road project.",
              infra_stage="awarded"),
        # same press release syndicated by two Times-group outlets + one independent outlet
        claim(statement="Fictional Developer launches 300 villa plots at Budigere Cross", claim_type="project_launch",
              subject="Fixture Meadows", locality="Budigere Cross", property_type="plot",
              url="https://timesofindia.indiatimes.com/fixture-a", publisher="Times of India",
              excerpt="Fictional Developer on Tuesday launched Fixture Meadows, a 300-plot villa plot development at Budigere Cross."),
        claim(statement="Fictional Developer launches 300 villa plots at Budigere Cross", claim_type="project_launch",
              subject="Fixture Meadows", locality="Budigere Cross", property_type="plot",
              url="https://economictimes.indiatimes.com/fixture-b", publisher="Economic Times",
              excerpt="Fictional Developer on Tuesday launched Fixture Meadows, a 300-plot villa plot development at Budigere Cross."),
        claim(statement="Fictional Developer launches 300 villa plots at Budigere Cross", claim_type="project_launch",
              subject="Fixture Meadows", locality="Budigere Cross", property_type="plot",
              url="https://www.thehindu.com/fixture-c", publisher="The Hindu",
              excerpt="Fixture Meadows, launched by Fictional Developer, has 300 plots near Budigere Cross on Old Madras Road."),
        # guarantee language from a broker
        claim(statement="Broker says Gunjur plots guaranteed to double in 3 years", claim_type="appreciation",
              subject="Gunjur plots", locality="Gunjur", property_type="plot", url="https://www.youtube.com/watch?v=fixture",
              publisher="YouTube channel", source_kind="social_media", metric="appreciation_pct", value=100, period_years=3,
              unit="%", excerpt="Guaranteed returns! Prices will double in 3 years, book now."),
        # contradictory prices for one project
        claim(statement="Fixture Heights apartments priced at Rs 9,500 per sq ft", claim_type="price", subject="Fixture Heights",
              locality="Sarjapur Road", property_type="apartment", url="https://www.thehindu.com/fixture-price-1",
              publisher="The Hindu", metric="price_psf", value=9500, unit="INR/sqft", price_basis="super_built_up",
              price_kind="developer_quote", excerpt="Fixture Heights is priced at Rs 9,500 per sq ft on super built-up area."),
        claim(statement="Fixture Heights apartments priced at Rs 12,000 per sq ft", claim_type="price", subject="Fixture Heights",
              locality="Sarjapur Road", property_type="apartment", url="https://www.deccanherald.com/fixture-price-2",
              publisher="Deccan Herald", metric="price_psf", value=12000, unit="INR/sqft", price_basis="super_built_up",
              price_kind="developer_quote", excerpt="Units at Fixture Heights start at Rs 12,000 per sq ft (super built-up)."),
        # plot land rate in sq yd (must normalise and stay in land class)
        claim(statement="Plots in Fixture Meadows quoted at Rs 45,000 per sq yd", claim_type="price", subject="Fixture Meadows",
              locality="Budigere Cross", property_type="plot", url="https://www.thehindu.com/fixture-c",
              publisher="The Hindu", metric="price_psf", value=45000, unit="INR/sqyd", price_basis="land",
              price_kind="developer_quote", excerpt="Plots are quoted at Rs 45,000 per sq yd."),
        # appreciation evidence from two independent groups (Whitefield apartments)
        claim(statement="Whitefield apartment prices rose 50% over five years", claim_type="appreciation",
              subject="Whitefield apartment prices", locality="Whitefield", property_type="apartment",
              url="https://www.thehindu.com/fixture-appr", publisher="The Hindu", metric="appreciation_pct", value=50,
              period_years=5, unit="%", excerpt="Average apartment prices in Whitefield rose 50% over the last five years."),
        claim(statement="Whitefield apartment values grew at a CAGR of 9 per cent", claim_type="appreciation",
              subject="Whitefield apartment values", locality="Whitefield", property_type="apartment",
              url="https://www.deccanherald.com/fixture-cagr", publisher="Deccan Herald", metric="cagr_pct", value=9,
              period_years=5, unit="%", excerpt="Apartment values in Whitefield grew at a CAGR of 9 per cent."),
        # old event republished
        claim(statement="Purple Line extension to Whitefield opened", claim_type="infrastructure",
              subject="Namma Metro Purple Line", locality="Whitefield", url="https://www.ndtv.com/fixture-old",
              publisher="NDTV", published_at="2026-10-14", event_date="2023-10-09",
              excerpt="The Purple Line extension to Whitefield was opened to the public.", infra_stage="operational"),
        # civic risk
        claim(statement="Varthur residents report flooding after heavy rain", claim_type="civic_risk",
              subject="Varthur flooding", locality="Varthur", url="https://www.thehindu.com/fixture-flood",
              publisher="The Hindu", excerpt="Several apartment complexes in Varthur were flooded after heavy rain on Monday."),
    ]
    projects = [dict(name="Fixture Meadows", developer="Fictional Developer", locality="Budigere Cross", property_type="plot",
                     launch_date="2026-10-13", status="launched", rera_number="PRM/KA/RERA/0000/FIXTURE",
                     rera_checked_on_portal=False, unit_sizes="1200-2400 sq ft", price_min=45000, price_max=None,
                     price_unit="INR/sqyd", price_basis="land", price_kind="developer_quote", charges_included=None,
                     charges_excluded="GST, registration", possession="2028", infra_links=["Peripheral Ring Road"],
                     lat=13.03, lon=77.755, url="https://www.thehindu.com/fixture-c", publisher="The Hindu",
                     published_at="2026-10-14", excerpt="Fixture Meadows, launched by Fictional Developer, has 300 plots.",
                     open_questions=["RERA number not checked on portal"])]
    findings = {"task_id": "east_launches_prices", "queries_run": ["fixture"], "sources_attempted": [
        {"source": "x.com", "status": "login_required", "note": "fixture"}], "claims": claims, "projects": projects,
        "notes": "synthetic fixture"}
    rss = {"items": [
        {"title": "Fixture Meadows launch at Budigere Cross", "url": "https://www.thehindu.com/fixture-c?utm_source=x",
         "publisher_url": "https://www.thehindu.com", "publisher": "The Hindu", "published_at": "2026-10-14T09:00:00+05:30",
         "summary": "", "feed": "gnews:test", "article_id": "A-1", "retrieved_at": "2026-10-15T05:00:00+05:30",
         "domain": "thehindu.com", "tier": "reputable_media", "group": "the_hindu_group", "interested_party": False,
         "corridors": ["budigere_cross"], "regions": ["east"]},
        {"title": "Fixture Meadows launch at Budigere Cross", "url": "https://www.thehindu.com/fixture-c",
         "publisher_url": "https://www.thehindu.com", "publisher": "The Hindu", "published_at": "2026-10-14T09:00:00+05:30",
         "summary": "", "feed": "thehindu", "article_id": "A-2", "retrieved_at": "2026-10-15T05:00:00+05:30",
         "domain": "thehindu.com", "tier": "reputable_media", "group": "the_hindu_group", "interested_party": False,
         "corridors": ["budigere_cross"], "regions": ["east"]},
        {"title": "Old story: Whitefield metro line opens", "url": "https://www.ndtv.com/old", "publisher_url": "https://www.ndtv.com",
         "publisher": "NDTV", "published_at": "2023-10-09T09:00:00+05:30", "summary": "", "feed": "gnews:test",
         "article_id": "A-3", "retrieved_at": "2026-10-15T05:00:00+05:30", "domain": "ndtv.com", "tier": "reputable_media",
         "group": "ndtv", "interested_party": False, "corridors": ["whitefield"], "regions": ["east"]}],
        "feeds_ok": ["fixture"], "feeds_failed": [], "retrieved_at": "2026-10-15T05:00:00+05:30"}
    return {"rss": rss, "agent_results": {"east_launches_prices": {"ok": True, "data": findings, "cost_usd": 0,
                                                                     "finished": "2026-10-15T05:30:00+05:30"}}}


if __name__ == "__main__":
    Path(__file__).with_name("fixtures").mkdir(exist_ok=True)
    Path(__file__).with_name("fixtures").joinpath("findings_sample.json").write_text(json.dumps(build(), indent=1))
