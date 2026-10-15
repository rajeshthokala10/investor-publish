"""Server-rendered one-page articles for planned cities & growth clusters (/growth/<slug>)."""
from __future__ import annotations

import html
import math
import re

from harness.common import DATA, load_config, read_json

KIND = {"township": "Township", "knowledge_city": "Knowledge city", "tech_city": "Tech city", "ai_city": "AI city",
        "industrial": "Industrial cluster", "aerospace_defence": "Aerospace & defence", "electronics_semiconductor": "Electronics",
        "logistics": "Logistics", "layout": "BDA layout", "smart_city": "Smart city", "corridor": "Corridor",
        "airport_region": "Airport region", "other": "Cluster"}
STAGE = {"proposed": "Proposed", "announced": "Announced", "approved": "Approved", "funded": "Funded", "tendered": "Tendered",
         "awarded": "Awarded", "under_construction": "Under construction", "operational": "Operational", "unclear": "Stage unclear"}
INVEST = {"budget_allocation": "Government budget allocation", "approved_project_cost": "Approved project cost",
          "expected_investment": "Expected investment", "mou_pledge": "MoU / pledged investment",
          "private_commitment": "Private commitment", "none": ""}


META = re.compile(r"\s*\((?:[^()]*?(?:search summary|page not retrievable|not retrievable|not confirmed by a fetched|blog|unverified)[^()]*)\)", re.I)


def clean(s) -> str:
    """Remove research-process notes (e.g. '(search summary of X; page not retrievable)') from reader-facing text."""
    return META.sub("", str(s or "")).strip()


def e(s) -> str:
    return html.escape(clean(s) if s is not None else "")


def clusters() -> list[dict]:
    return read_json(DATA / "app" / "clusters.json", {}).get("clusters", [])


def fmt_num(v) -> str:
    if v is None:
        return ""
    return f"{v:,.0f}" if float(v).is_integer() else f"{v:,.2f}".rstrip("0").rstrip(".")


def summary(c: dict) -> dict:
    return {"slug": c["slug"], "name": c["name"], "full_name": c.get("full_name"), "kind": KIND.get(c["kind"], "Cluster"),
            "kind_id": c["kind"], "stage": STAGE.get(c["stage"], c["stage"]), "stage_id": c["stage"], "agency": c.get("agency"),
            "town": c["nearest_town"], "distance_km": c.get("distance_km_approx"), "coords": c.get("coords"),
            "where": (f"≈{c['distance_km_approx']} km from centre" if c.get("distance_km_approx")
                      else ("Ring corridor around the city" if c["kind"] == "corridor" else "Within Bengaluru")),
            "area": f"{fmt_num(c['area_acres'])} acres" if c.get("area_acres") else "",
            "investment": (f"₹{fmt_num(c['investment_inr_crore'])} crore" if c.get("investment_inr_crore") else (c.get("investment_text") or "")),
            "investment_kind": INVEST.get(c.get("investment_kind") or "none", ""),
            "headline": (c.get("article") or {}).get("headline") or c["name"],
            "standfirst": (c.get("article") or {}).get("standfirst") or (c.get("highlights") or [""])[0]}


def mini_map(c: dict) -> str:
    cfg = load_config("clusters")
    cy, cx = cfg["centre"]
    w = h = 300
    out = [f'<svg viewBox="0 0 {w} {h}" class="amap" role="img" aria-label="Location relative to Bengaluru">',
           f'<rect width="{w}" height="{h}" rx="14" fill="#f3f7fd"/>']
    scale = 1.6
    for r in (20, 40, 60, 80):
        out.append(f'<circle cx="{w/2}" cy="{h/2}" r="{r*scale}" fill="none" stroke="#c9d8ee" stroke-dasharray="4 5"/>'
                   f'<text x="{w/2}" y="{h/2 - r*scale + 12}" class="rk" text-anchor="middle">{r} km</text>')
    out.append(f'<circle cx="{w/2}" cy="{h/2}" r="6" fill="#0d366b"/><text x="{w/2 + 9}" y="{h/2 + 16}" class="rl">Bengaluru (MG Road)</text>')
    if c.get("coords"):
        la, lo = c["coords"]
        dx = (lo - cx) * 111.32 * math.cos(math.radians(cy)) * scale
        dy = (la - cy) * 110.57 * scale
        x, y = max(14, min(w - 14, w / 2 + dx)), max(14, min(h - 14, h / 2 - dy))
        out.append(f'<line x1="{w/2}" y1="{h/2}" x2="{x:.0f}" y2="{y:.0f}" stroke="#e34948" stroke-width="2" stroke-dasharray="5 4"/>'
                   f'<circle cx="{x:.0f}" cy="{y:.0f}" r="9" fill="#e34948" stroke="#fff" stroke-width="3"/>'
                   f'<text x="{x:.0f}" y="{y - 14:.0f}" class="rs" text-anchor="middle">{e(c["nearest_town"])}</text>')
    out.append(f'<text x="12" y="{h - 10}" class="rk">N ↑ · positions approximate</text></svg>')
    return "".join(out)


def page(slug: str) -> str | None:
    c = next((x for x in clusters() if x["slug"] == slug), None)
    if not c:
        return None
    a = c.get("article") or {"headline": c["name"], "standfirst": "", "paragraphs": c.get("highlights", []), "key_facts": [],
                             "whats_next": []}
    s = summary(c)
    core_labels = {"type", "stage", "developed by", "agency", "location", "area", "investment", "timeline", "nearest town",
                   "distance from city centre", "distance"}
    facts = "".join(f"<div><span>{e(k['label'])}</span><b>{e(k['value'])}</b></div>" for k in a["key_facts"]
                    if k["label"].strip().lower() not in core_labels)
    core = [("Type", s["kind"]), ("Stage", s["stage"]), ("Developed by", c.get("agency")), ("Location", c.get("location_text")),
            ("Distance from city centre", f"≈ {s['distance_km']} km (straight line)" if s["distance_km"] else s["where"]),
            ("Area", s["area"]), ("Investment", f"{s['investment']} · {s['investment_kind']}" if s["investment"] else None),
            ("Timeline", c.get("timeline_text"))]
    core_html = "".join(f"<div><span>{e(k)}</span><b>{e(v)}</b></div>" for k, v in core if v)
    nxt = "".join(f"<li>{e(x)}</li>" for x in a["whats_next"])
    risks = "".join(f"<li>{e(x)}</li>" for x in c.get("risks", []))
    srcs = "".join(f'<li><a href="{e(f["url"])}" rel="noopener" target="_blank">{e(f["publisher"])}</a>'
                   f'{" · " + e(f["published_at"]) if f.get("published_at") else ""}</li>' for f in c["facts"])
    others = "".join(f'<a href="/growth/{e(o["slug"])}">{e(o["name"])}</a>' for o in clusters() if o["slug"] != slug)
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{e(c['name'])} · Bengaluru Property Review</title><meta name="description" content="{e(a['standfirst'])}">
<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&family=Playfair+Display:wght@700;800;900&display=swap" rel="stylesheet">
<link rel="stylesheet" href="/styles.css"></head>
<body class="protected">
<div class="shield" id="shield" aria-hidden="true"><div><b>Bengaluru Property Review</b><span>Content protected</span></div></div>
<div class="watermark" aria-hidden="true"></div>
<header class="topbar"><a class="brand" href="/"><span class="logo" aria-hidden="true"><svg viewBox="0 0 32 32"><rect width="32" height="32" rx="7"/><path d="M7 25V13h5v12M14 25V7h5v18M21 25V16h5v9"/></svg></span>
<span class="brand-text"><b>Bengaluru</b> Property Review</span></a>
<nav class="nav"><a href="/#growth">Growth clusters</a><a href="/#metro-sec">Metro</a><a href="/#news">News</a></nav>
<a class="btn btn-gold btn-sm" href="/#subscribe">Subscribe</a></header>
<main>
<section class="art-hero"><div class="wrap">
  <a class="back" href="/#growth">← All planned cities &amp; clusters</a>
  <p class="art-kick"><span class="kchip k-{e(c['kind'])}">{e(s['kind'])}</span><span class="schip s-{e(c['stage'])}">{e(s['stage'])}</span></p>
  <h1>{e(a['headline'])}</h1><p class="art-sf">{e(a['standfirst'])}</p>
</div></section>
<section class="wrap art-body">
  <article>{''.join(f'<p>{e(p)}</p>' for p in a['paragraphs'])}
    {f'<h3>What happens next</h3><ul class="art-list">{nxt}</ul>' if nxt else ''}
    {f'<h3>Risks to watch</h3><ul class="art-list risk">{risks}</ul>' if risks else ''}
    <p class="art-src-h">Sources</p><ul class="art-src">{srcs}</ul>
  </article>
  <aside>
    <div class="art-card">{mini_map(c)}</div>
    <div class="art-card kf"><h4>At a glance</h4>{core_html}{facts}</div>
  </aside>
</section>
<section class="wrap more-clusters"><h4>More planned cities &amp; clusters</h4><div>{others}</div></section>
</main>
<footer class="footer"><p class="wrap disclaimer">© Bengaluru Property Review. Information only, not investment advice. Figures are attributed to
the organisations that published them; distances are approximate straight-line estimates; plans and timelines can change.</p></footer>
<script src="/guard.js"></script></body></html>"""
