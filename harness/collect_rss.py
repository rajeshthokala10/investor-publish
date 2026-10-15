"""Deterministic collection: publisher RSS feeds and Google News RSS search (no logins, no scraping)."""
from __future__ import annotations

import html
import re
import xml.etree.ElementTree as ET
from datetime import datetime
from email.utils import parsedate_to_datetime
from urllib.parse import quote_plus

from harness.common import IST, RAW, iso, load_config, now_ist, sha, write_text
from harness.registry import classify_source, domain_of, match_corridors, region_of
from harness.runtime import Http, RunLog

RELEVANCE = re.compile(
    r"\b(real estate|realty|property|properties|housing|home ?buyers?|apartment|flat|villa|plot|plotted|layout|"
    r"launch|rera|developer|metro|bmrcl|namma metro|suburban|k-ride|ring road|strr|prr|flyover|underpass|"
    r"expressway|highway|tunnel|airport|bwssb|cauvery|water supply|flood|drain|sewage|lake|traffic|bda|bmrda|gba|"
    r"greater bengaluru|zoning|master plan|guidance value|stamp duty|registration|office|leasing|tech park|"
    r"jobs|kiadb|industrial|rent|rental|price|sq ?ft|crore|lakh|land)\b", re.I)
CITY = re.compile(r"\b(bengaluru|bangalore|karnataka)\b", re.I)


def _text(el, tag):
    x = el.find(tag)
    return (x.text or "").strip() if x is not None and x.text else ""


def strip_html(s: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", s or ""))).strip()


def parse_feed(xml_text: str, feed_id: str) -> list[dict]:
    root = ET.fromstring(xml_text)
    items = []
    for it in root.iter("item"):
        title = strip_html(_text(it, "title"))
        link = _text(it, "link")
        pub = _text(it, "pubDate")
        try:
            pub_dt = parsedate_to_datetime(pub).astimezone(IST) if pub else None
        except (TypeError, ValueError):
            pub_dt = None
        src = it.find("source")
        publisher_url = src.get("url") if src is not None else link
        publisher = (src.text or "").strip() if src is not None and src.text else ""
        if src is not None and title.endswith(" - " + publisher):
            title = title[: -len(publisher) - 3]
        items.append({
            "title": title,
            "url": link,
            "publisher_url": publisher_url,
            "publisher": publisher or domain_of(link),
            "published_at": iso(pub_dt) if pub_dt else None,
            "summary": strip_html(_text(it, "description"))[:500],
            "feed": feed_id,
        })
    return items


def relevant(item: dict) -> bool:
    text = f"{item['title']} {item['summary']}"
    if not RELEVANCE.search(text):
        return False
    return bool(CITY.search(text) or match_corridors(text) or item["feed"].startswith("gnews"))


def collect(edition, http: Http, log: RunLog) -> dict:
    cfg = load_config("sources")
    budget_items = load_config("harness")["budgets"]["max_rss_items"]
    feeds = [(f["id"], f["url"]) for f in cfg["rss_feeds"]]
    gq = cfg["google_news"]
    feeds += [(f"gnews:{q}", gq["base"].format(q=quote_plus(q))) for q in gq["queries"]]

    raw_dir = RAW / edition.isoformat() / "rss"
    out, ok, failed = [], [], []
    retrieved = iso(now_ist())
    for feed_id, url in feeds:
        r = http.get(url, source=feed_id)
        if r is None or r.status_code != 200:
            failed.append({"source": feed_id, "url": url, "reason": "no response" if r is None else f"HTTP {r.status_code}"})
            continue
        write_text(raw_dir / f"{sha(feed_id)}.xml", r.text)  # raw capture: public RSS only
        try:
            items = parse_feed(r.text, feed_id)
        except ET.ParseError as e:
            failed.append({"source": feed_id, "url": url, "reason": f"parse error: {e}"})
            log.source_failure(feed_id, f"parse error: {e}")
            continue
        ok.append(feed_id)
        for item in items:
            if len(out) >= budget_items:
                break
            if not relevant(item):
                continue
            src = classify_source(item["publisher_url"])
            text = f"{item['title']} {item['summary']}"
            cors = match_corridors(text)
            item.update(
                article_id="A-" + sha(item["url"]),
                retrieved_at=retrieved,
                domain=src["domain"], tier=src["tier"], group=src["group"],
                interested_party=src["interested_party"],
                corridors=cors,
                regions=sorted({region_of(c) for c in cors}) or ["unmapped"],
            )
            out.append(item)
    log("rss_collected", feeds_ok=len(ok), feeds_failed=len(failed), items=len(out))
    return {"items": out, "feeds_ok": ok, "feeds_failed": failed, "retrieved_at": retrieved}
