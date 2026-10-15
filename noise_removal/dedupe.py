"""Deduplication, syndication grouping and stale-news detection.

* canonical_url: strips tracking params, AMP and mobile variants.
* Articles with near-identical titles (token Jaccard) form one story cluster.
* Claims whose excerpts are near-identical across different publishers are one
  syndication cluster: a press release copied by five outlets is ONE source.
* Stale: published outside the window, or an event date far older than the
  publication date (old news republished), or a story fingerprint already seen in
  a previous edition with no new facts.
"""
from __future__ import annotations

import re
from datetime import date, datetime, timedelta
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

from harness.common import norm_text, parse_date, sha, tokens

TRACKING = re.compile(r"^(utm_|fbclid|gclid|ref|refsrc|from|cmpid|ito|ocid|src|source|amp)", re.I)
STOP = set("the a an of in on at to for and or is are was were be by with from as its it this that new "
           "bengaluru bangalore karnataka city news update says said".split())


def canonical_url(url: str) -> str:
    p = urlparse((url or "").strip())
    host = p.netloc.lower()
    for pre in ("www.", "m.", "amp.", "mobile."):
        if host.startswith(pre):
            host = host[len(pre):]
    path = re.sub(r"/amp/?$|\.amp$|/amp(?=/)", "", p.path).rstrip("/") or "/"
    q = urlencode([(k, v) for k, v in parse_qsl(p.query) if not TRACKING.match(k)])
    return urlunparse(("https", host, path, "", q, ""))


def shingles(text: str, n: int = 2) -> set:
    toks = [t for t in tokens(text) if t not in STOP]
    if len(toks) < n:
        return set(toks)
    return {" ".join(toks[i:i + n]) for i in range(len(toks) - n + 1)}


def jaccard(a: set, b: set) -> float:
    return len(a & b) / len(a | b) if a and b else 0.0


def cluster(items: list[dict], text_of, threshold: float) -> list[list[int]]:
    """Single-link clustering on shingle Jaccard; returns lists of indices."""
    sh = [shingles(text_of(x)) for x in items]
    parent = list(range(len(items)))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    for i in range(len(items)):
        for j in range(i + 1, len(items)):
            if jaccard(sh[i], sh[j]) >= threshold:
                parent[find(j)] = find(i)
    groups: dict[int, list[int]] = {}
    for i in range(len(items)):
        groups.setdefault(find(i), []).append(i)
    return list(groups.values())


def story_fingerprint(title: str) -> str:
    toks = sorted(t for t in tokens(title) if t not in STOP)[:12]
    return "S-" + sha(" ".join(toks))


def dedupe_articles(items: list[dict], threshold: float = 0.55) -> list[dict]:
    """Collapse exact-URL duplicates, then cluster near-identical titles into stories."""
    by_url: dict[str, dict] = {}
    for it in items:
        cu = canonical_url(it["url"])
        if cu in by_url:
            by_url[cu].setdefault("duplicate_urls", []).append(it["url"])
            continue
        it = dict(it, canonical_url=cu)
        by_url[cu] = it
    uniq = list(by_url.values())
    stories = []
    for idx in cluster(uniq, lambda x: x["title"], threshold):
        members = sorted((uniq[i] for i in idx), key=lambda x: (x.get("published_at") or "9999", x["url"]))
        lead = members[0]
        stories.append({
            "story_id": story_fingerprint(lead["title"]),
            "title": lead["title"],
            "lead": lead,
            "members": [{"url": m["url"], "publisher": m["publisher"], "group": m["group"],
                         "published_at": m.get("published_at")} for m in members],
            "publishers": sorted({m["publisher"] for m in members}),
            "independent_groups": sorted({m["group"] for m in members if not m["interested_party"]}),
            "corridors": sorted({c for m in members for c in m.get("corridors", [])}),
            "regions": sorted({r for m in members for r in m.get("regions", [])}),
            "published_at": lead.get("published_at"),
        })
    return stories


def syndication_clusters(claims: list[dict], threshold: float = 0.7) -> dict[str, str]:
    """claim_id -> syndication cluster id (claims sharing near-identical excerpts across publishers)."""
    out = {}
    for idx in cluster(claims, lambda c: c.get("excerpt", ""), threshold):
        cid = "SYN-" + sha(*sorted(claims[i]["claim_id"] for i in idx))
        for i in idx:
            out[claims[i]["claim_id"]] = cid
    return out


def staleness(published_at, event_date, window: tuple[datetime, datetime], max_event_lag_days: int = 30) -> list[str]:
    """Flags: outside_window, undated, republished_old_event."""
    flags = []
    pub = parse_date(published_at)
    start, end = window[0].date(), window[1].date()
    if pub is None:
        flags.append("undated")
    elif pub < start or pub > end:
        flags.append("outside_window")
    ev = parse_date(event_date)
    if ev and pub and (pub - ev) > timedelta(days=max_event_lag_days):
        flags.append("republished_old_event")
    return flags


def classify_against_history(fingerprint: str, fact_keys: set[str], seen: dict) -> str:
    """new | update (seen story, new facts) | repeat (seen story, no new facts)."""
    prev = seen.get(fingerprint)
    if not prev:
        return "new"
    return "update" if fact_keys - set(prev.get("fact_keys", [])) else "repeat"


def subject_key(subject: str) -> str:
    return " ".join(t for t in norm_text(subject).split() if t not in STOP)[:80]
