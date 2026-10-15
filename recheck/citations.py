"""Citation support check: does the cited page actually contain the quoted excerpt?

confirmed     >= 60% of the excerpt's word trigrams and every number in it are on the page
failed        page fetched with substantial text but < 20% of trigrams present
inconclusive  blocked, JS-rendered, paywalled or partial match
"""
from __future__ import annotations

import re

from harness.common import tokens
from harness.collect_rss import strip_html

NUM = re.compile(r"\d[\d,]*(?:\.\d+)?")


def page_text(html: str) -> str:
    html = re.sub(r"(?is)<(script|style|noscript)[^>]*>.*?</\1>", " ", html or "")
    return strip_html(html)


def trigrams(text: str) -> set:
    t = tokens(text)
    return {" ".join(t[i:i + 3]) for i in range(len(t) - 2)}


def support(excerpt: str, page: str) -> tuple[str, float]:
    ex = trigrams(excerpt)
    if not ex:
        return "inconclusive", 0.0
    pg = trigrams(page)
    share = len(ex & pg) / len(ex)
    nums = {n.replace(",", "") for n in NUM.findall(excerpt)}
    page_nums = {n.replace(",", "") for n in NUM.findall(page)}
    if share >= 0.6 and nums <= page_nums:
        return "confirmed", share
    if share < 0.2 and len(page) > 3000:
        return "failed", share
    return "inconclusive", share


def check_url(http, url: str, excerpt: str, source: str) -> dict:
    r = http.get(url, source=source)
    if r is None:
        return {"result": "inconclusive", "share": 0.0, "http": None, "note": "no response"}
    if r.status_code >= 400:
        return {"result": "inconclusive", "share": 0.0, "http": r.status_code, "note": "blocked or missing"}
    ctype = r.headers.get("content-type", "")
    if "html" not in ctype and "text" not in ctype:
        return {"result": "inconclusive", "share": 0.0, "http": r.status_code, "note": f"non-HTML ({ctype[:40]})"}
    result, share = support(excerpt, page_text(r.text))
    return {"result": result, "share": round(share, 2), "http": r.status_code, "final_url": r.url, "note": None}
