"""Render the magazine issue (10 A4 pages) to HTML and PDF.

Copy comes from <edition>.issue.json (validated writer output); tables of prices come
straight from publishable claims. Illustrations are generated SVG (skylines, a schematic
growth map), never photographs.
"""
from __future__ import annotations

import html
import math
import re
import statistics
from collections import Counter, defaultdict
from pathlib import Path

from harness.common import REPORTS, iso, now_ist, read_json, write_text
from harness.infographic import icon, skyline
from harness.registry import corridors, region_of

PAGES = 10
SCALES = [1.0, 0.94, 0.88, 0.82, 0.76, 0.7]
CENTRE = (12.972, 77.594)
# approximate positions of places on the growth map (WGS84)
PLACES = {
    "Whitefield": (12.970, 77.750), "Sarjapur Road": (12.905, 77.690), "Varthur": (12.940, 77.746),
    "KR Puram": (13.007, 77.695), "Budigere Cross": (13.040, 77.750), "Hebbal": (13.036, 77.597),
    "Yelahanka": (13.100, 77.596), "Thanisandra": (13.060, 77.633), "Electronic City": (12.845, 77.660),
    "Bannerghatta Rd": (12.880, 77.600), "Kanakapura Rd": (12.860, 77.540), "Mysore Rd": (12.930, 77.500),
    "Tumkur Rd": (13.040, 77.510), "Magadi Rd": (12.985, 77.470), "MG Road": CENTRE,
    "Hoskote": (13.070, 77.798), "Devanahalli": (13.247, 77.712), "Airport": (13.199, 77.706),
    "Doddaballapur": (13.292, 77.543), "Nelamangala": (13.098, 77.393), "Bidadi": (12.797, 77.390),
    "Harohalli": (12.680, 77.470), "Kanakapura": (12.550, 77.420), "Anekal": (12.708, 77.696),
    "Attibele": (12.778, 77.771), "Sarjapur": (12.860, 77.786), "Hosur": (12.740, 77.825),
    "Ramanagara": (12.720, 77.280), "Chikkaballapur": (13.435, 77.728),
}
LABEL_OFFSETS = {"Hebbal": (-7, 4, "end"), "Tumkur Rd": (-7, 4, "end"), "Magadi Rd": (-7, 4, "end"),
                 "Mysore Rd": (-7, 4, "end"), "Thanisandra": (6, -6, "start"), "Yelahanka": (7, -5, "start"),
                 "Kanakapura Rd": (-7, 6, "end"), "Bannerghatta Rd": (6, 12, "start"), "Varthur": (8, 10, "start"),
                 "Budigere Cross": (8, -6, "start"), "Electronic City": (8, 8, "start"), "Nelamangala": (-9, 4, "end")}
CITY_PTS = {"Whitefield", "Sarjapur Road", "Varthur", "KR Puram", "Budigere Cross", "Hebbal", "Yelahanka", "Thanisandra",
            "Electronic City", "Bannerghatta Rd", "Kanakapura Rd", "Mysore Rd", "Tumkur Rd", "Magadi Rd"}
ZONE_COLOR = {"east": "#2a78d6", "north": "#eb6834", "south": "#1baf7a", "west": "#eda100", "peripheral": "#4a3aa7"}
CAT_ICON = {"metro": "metro", "suburban_rail": "metro", "road": "road", "airport": "plane", "township": "building",
            "water": "water", "governance": "gavel", "policy": "gavel"}
CAT_LABEL = {"metro": "Metro", "suburban_rail": "Suburban rail", "road": "Roads", "airport": "Airport",
             "township": "Townships & hubs", "water": "Water", "governance": "Governance", "policy": "Policy"}


def e(s) -> str:
    return html.escape(str(s or ""))


def paras(ps) -> str:
    return "".join(f"<p>{e(p['text'])}</p>" for p in ps)


def km_xy(lat, lon, scale, cx, cy):
    dx = (lon - CENTRE[1]) * 111.32 * math.cos(math.radians(CENTRE[0]))
    dy = (lat - CENTRE[0]) * 110.57
    return cx + dx * scale, cy - dy * scale


def growth_map(highlight: set[str], w=760, h=560) -> str:
    scale, cx, cy = 5.2, w * 0.5, h * 0.52
    out = [f'<svg viewBox="0 0 {w} {h}" class="map" role="img" aria-label="Schematic growth map of Bengaluru">',
           f'<rect width="{w}" height="{h}" fill="#f4f8fd" rx="8"/>']
    for r, label, col in ((10, "Outer Ring Road", "#86b6ef"), (19, "Peripheral Ring Road / BBC (planned)", "#eb6834"),
                          (45, "Satellite Town Ring Road", "#4a3aa7")):
        out.append(f'<circle cx="{cx}" cy="{cy}" r="{r*scale}" fill="none" stroke="{col}" stroke-width="{2.5 if r>10 else 2}" '
                   f'stroke-dasharray="{"0" if r == 10 else "7 5"}" opacity=".9"/>')
        lx, ly = (cx - r*scale*0.71 - 4, cy + r*scale*0.71 + 14) if r == 10 else (cx + r*scale*0.71 + 4, cy - r*scale*0.71 - 4)
        out.append(f'<text x="{lx:.0f}" y="{ly:.0f}" text-anchor="{"end" if r == 10 else "start"}" class="ring">{e(label)}</text>')
    out.append(f'<circle cx="{cx}" cy="{cy}" r="{4*scale}" fill="#0d366b" opacity=".12"/>')
    for name, (lat, lon) in PLACES.items():
        x, y = km_xy(lat, lon, scale, cx, cy)
        if not (8 < x < w - 8 and 8 < y < h - 8):
            continue
        town = name not in CITY_PTS and name != "MG Road"
        hot = any(name.lower().split()[0] in hgt for hgt in highlight)
        if name == "Airport":
            out.append(f'<path d="M{x-9:.0f} {y+3:.0f} l18 -8 l-3 9 l-5 -1.5 l-3 5 l-.5 -6z" fill="#0d366b"/>')
            out.append(f'<text x="{x+12:.0f}" y="{y+4:.0f}" class="pl">KIA Airport</text>')
            continue
        col = "#e34948" if hot else ("#0d366b" if town else "#2a78d6")
        rr = 6 if town else 4.5
        out.append(f'<circle cx="{x:.0f}" cy="{y:.0f}" r="{rr}" fill="{col}" stroke="#fff" stroke-width="1.5"/>')
        dx, dy, anchor = LABEL_OFFSETS.get(name, (8, 4, "start"))
        out.append(f'<text x="{x+dx:.0f}" y="{y+dy:.0f}" text-anchor="{anchor}" class="{"pt" if town else "pl"}{" hot" if hot else ""}">{e(name)}</text>')
    out.append(f'<text x="14" y="{h-14}" class="cap">Schematic: positions approximate; rings drawn as circles for orientation only. '
               f'Red = growth towns featured in this issue.</text></svg>')
    return "".join(out)


def price_guide(claims: list[dict]) -> str:
    """Area price guide straight from claims; one basis per cell, never mixing land and built rates."""
    cells = defaultdict(list)
    for c in claims:
        if not c.get("psf_inr") or c["property_type"] not in ("apartment", "plot", "villa"):
            continue
        kind = "plot" if c["property_type"] == "plot" or c["price_basis"] == "land" else c["property_type"]
        place = (c.get("locality") or "").split(",")[0].strip().title() or corridors().get(c["corridor"], {}).get("name", "")
        if not place:
            continue
        hi = c["psf_inr"] * (c["value_max"] / c["value"]) if c.get("value_max") and c["value"] else c["psf_inr"]
        cells[(place, kind)].append((c["psf_inr"], hi, c["price_basis"], c["publisher"], region_of(c["corridor"])))
    places = sorted({p for p, _ in cells}, key=lambda p: (["east", "north", "south", "west", "peripheral", "unmapped"].index(
        next(v[4] for (pp, _), vs in cells.items() if pp == p for v in vs)), p))
    abbrev = {"super_built_up": "SBA", "carpet": "carpet", "built_up": "built-up", "land": "land", "unknown": ""}
    rows = []
    for p in places[:22]:
        tds, srcs, zone = [], set(), None
        for kind in ("apartment", "villa", "plot"):
            vs = cells.get((p, kind))
            if not vs:
                tds.append("<td class='na'>—</td>")
                continue
            basis = Counter(v[2] for v in vs).most_common(1)[0][0]
            vs = [v for v in vs if v[2] == basis]
            lo, hi = min(v[0] for v in vs), max(v[1] for v in vs)
            srcs |= {v[3] for v in vs}
            zone = vs[0][4]
            rng = f"₹{lo:,.0f}" + (f"–{hi:,.0f}" if hi > lo * 1.02 else "")
            tds.append(f"<td>{rng}<small> {abbrev.get(basis, basis)}</small></td>")
        zone = zone or "unmapped"
        rows.append(f"<tr><th><i style='background:{ZONE_COLOR.get(zone, '#8a8984')}'></i>{e(p)}</th>{''.join(tds)}"
                    f"<td class='src'>{e(', '.join(sorted(srcs))[:46])}</td></tr>")
    if not rows:
        return ""
    return ("<table class='guide'><thead><tr><th>Area</th><th>Apartments ₹/sq ft</th><th>Villas ₹/sq ft</th>"
            "<th>Plots ₹/sq ft (land)</th><th>Source</th></tr></thead><tbody>" + "".join(rows) + "</tbody></table>"
            "<p class='fine'>Quoted levels from the sources shown (asking, launch or research-house averages). SBA = super built-up area. "
            "Plot rates are per sq ft of land and are not comparable with built-up apartment rates.</p>")


def page(n: int, cls: str, body: str, label: str, section: str = "") -> str:
    folio = "" if n == 1 else (f'<div class="folio"><span>Bengaluru Property Review · {e(label)}</span>'
                               f'<span>{e(section)}</span><span>{n}</span></div>')
    return f'<section class="mp {cls}">{body}{folio}</section>'


def build(issue: dict, claims: list[dict], label: str, as_of: str) -> str:
    cv = issue["cover"]
    zones = {z["zone"]: z for z in issue["zones"]}
    towns = issue["growth_towns"]
    pubs = Counter(c["publisher"] for c in claims)

    # 1 cover --------------------------------------------------------------------------------
    p1 = (f'<div class="mast"><div class="mtitle">BENGALURU<br><b>PROPERTY REVIEW</b></div>'
          f'<div class="missue">{e(label)}<br><small>The city · its corridors · the plans reshaping them</small></div></div>'
          f'<div class="cover-art">{skyline("cover" + label, 900, 420, pins=["Whitefield", "Hebbal", "Devanahalli", "Sarjapur", "Hoskote", "Kanakapura"])}</div>'
          f'<h1 class="chead">{e(cv["headline"])}</h1><p class="csub">{e(cv["subhead"])}</p>'
          f'<ul class="clines">' + "".join(f"<li>{e(l)}</li>" for l in cv["cover_lines"][:4]) + "</ul>"
          + '<div class="cfig">' + "".join(f'<div><b>{e(k["value_text"])}</b><span>{e(k["label"])}</span></div>'
                                           for k in issue["key_figures"][:3]) + '</div>'
          f'<div class="cfoot">INSIDE · East · North · South · West · Beyond the city · The government’s plan · Plots vs villas vs apartments · Outlook</div>')

    # 2 editor + contents + glance -------------------------------------------------------------
    contents = [("The government’s plan for Bengaluru", 3), ("Growth map", 4), ("East Bengaluru", 5), ("North Bengaluru", 6),
                ("South & West Bengaluru", 7), ("Beyond the city: growth towns", 8), ("Plots, villas or apartments?", 9),
                ("Outlook & projects to watch", 10)]
    kf = "".join(f'<div class="kf"><div class="kv">{e(k["value_text"])}</div><div class="kl">{e(k["label"])}</div>'
                 f'<div class="kc">{e(k["context"])}</div></div>' for k in issue["key_figures"][:6])
    p2 = (f'<div class="two"><div><h2 class="kick">From the editor</h2>{paras(issue["editor_note"])}</div>'
          f'<div class="toc"><h2 class="kick">In this issue</h2>' + "".join(f"<div><span>{e(t)}</span><b>{n}</b></div>" for t, n in contents) + "</div></div>"
          f'<h2 class="band">Bengaluru at a glance</h2><div class="kfs">{kf}</div><div class="cols2">{paras(issue["glance"])}</div>')

    # 3-4 government ---------------------------------------------------------------------------
    order = ["metro", "suburban_rail", "airport", "road", "township", "water", "governance", "policy"]
    rows = sorted(issue["gov_rows"], key=lambda r: order.index(r["category"]))
    first = [r for r in rows if r["category"] in ("metro", "suburban_rail", "airport")]
    rest = [r for r in rows if r not in first]

    def gtable(rs):
        if not rs:
            return ""
        return ("<table class='gov'><thead><tr><th></th><th>Project</th><th>Where it stands</th><th>Timeline</th><th>Areas</th></tr></thead><tbody>"
                + "".join(f"<tr><td class='gi'>{icon(CAT_ICON[r['category']], 'ti')}<small>{CAT_LABEL[r['category']]}</small></td>"
                          f"<td><b>{e(r['project'])}</b></td><td>{e(r['status'])}</td><td>{e(r['timeline'])}</td><td>{e(r['areas'])}</td></tr>" for r in rs)
                + "</tbody></table>")
    p3 = (f'<div class="sect">THE BIG PICTURE</div><h1 class="feat">The government’s plan for Bengaluru</h1>'
          f'<div class="lede">{paras(issue["gov_intro"])}</div><h3 class="sub">Metro, suburban rail and airport</h3>{gtable(first)}')
    highlight = {t["name"].lower() for t in towns}
    p4 = (f'<div class="sect">THE BIG PICTURE</div><h2 class="feat2">Where the city is growing</h2>'
          f'<div class="mapwrap">{growth_map(highlight)}</div><div class="caption">{paras(issue["growth_map_caption"])}</div>'
          + (f'<h3 class="sub">Roads, townships, water and governance</h3>{gtable(rest)}' if rest else ""))

    # 5-7 zones --------------------------------------------------------------------------------
    def zone_block(z, compact=False):
        if not z:
            return ""
        mm = "".join(f"<tr><th>{e(m['name'])}</th><td class='pr'>{e(m['price_text']) or '—'}</td><td>{e(m['drivers'])}</td>"
                     f"<td>{e(m['watch'])}</td></tr>" for m in z["micro_markets"])
        table = ("<table class='mm'><thead><tr><th>Micro-market</th><th>Price levels</th><th>What drives it</th>"
                 f"<th>Watch</th></tr></thead><tbody>{mm}</tbody></table>") if mm else ""
        art = "" if compact else f'<div class="zart">{skyline("zone" + z["zone"], 900, 170, metro=True)}</div>'
        return (f'<div class="sect" style="color:{ZONE_COLOR[z["zone"]]}">{z["zone"].upper()} BENGALURU</div>'
                f'<h1 class="feat{"2" if compact else ""}">{e(z["title"])}</h1><p class="stand">{e(z["standfirst"])}</p>{art}'
                f'<div class="cols2">{paras(z["paragraphs"])}</div>{table}')
    p5 = zone_block(zones.get("east"))
    p6 = zone_block(zones.get("north"))
    p7 = zone_block(zones.get("south"), True) + '<hr class="rule">' + zone_block(zones.get("west"), True)

    # 8 growth towns -----------------------------------------------------------------------------
    cards = "".join(f'<div class="town">{skyline("t" + t["name"], 300, 70, metro=False)}<h4>{e(t["name"])}</h4>'
                    f'<p>{e(t["why"])}</p>' + (f'<p class="tp">{e(t["price_text"])}</p>' if t["price_text"] else "")
                    + f'<p class="tr"><b>Watch:</b> {e(t["risks"])}</p></div>' for t in towns[:9])
    p8 = (f'<div class="sect">BEYOND THE CITY</div><h1 class="feat">The next growth towns</h1>'
          f'<div class="lede">{paras(issue["growth_intro"])}</div><div class="towns">{cards}</div>')

    # 9 property types + price guide --------------------------------------------------------------
    pt = issue["property_types"]
    p9 = (f'<div class="sect">BUYER’S GUIDE</div><h1 class="feat2">Plots, villas or apartments?</h1>'
          f'<div class="three"><div><h4>{icon("road", "hi")} Villa plots</h4>{paras(pt["plots"])}</div>'
          f'<div><h4>{icon("building", "hi")} Villas</h4>{paras(pt["villas"])}</div>'
          f'<div><h4>{icon("crane", "hi")} Apartments</h4>{paras(pt["apartments"])}</div></div>'
          f'<div class="verdict">{paras(pt["verdict"])}</div><h3 class="sub">Price guide by area</h3>{price_guide(claims)}')

    # 10 outlook, projects, sources ------------------------------------------------------------
    watch = "".join(f"<li><b>{e(w['item'])}</b> — {e(w['why'])}</li>" for w in issue["watch_list"])
    projs = "".join(f"<tr><th>{e(p['name'])}</th><td>{e(p['developer'])}</td><td>{e(p['location'])}</td><td>{e(p['type'])}</td>"
                    f"<td>{e(p['detail'])}</td></tr>" for p in issue["projects"][:8])
    p10 = (f'<div class="sect">OUTLOOK</div><h1 class="feat2">What to expect next</h1><div class="cols2">{paras(issue["outlook"])}</div>'
           f'<h3 class="sub">On the watch list</h3><ul class="watch cols2">{watch}</ul>'
           f'<h3 class="sub">Projects to know</h3><table class="proj"><thead><tr><th>Project</th><th>Developer</th><th>Location</th>'
           f'<th>Type</th><th>Details</th></tr></thead><tbody>{projs}</tbody></table>'
           f'<div class="sources"><b>Sources for this issue</b> (information as of {e(as_of[:10])}): '
           + e(", ".join(f"{p}" for p, _ in pubs.most_common(40)))
           + ". Figures are attributed to the organisation that published them; prices are quoted levels, not valuations. "
             "Plans and timelines are as stated by the agencies concerned and can change. This magazine is for information only "
             "and is not investment advice.</div>")

    pages = [("cover", p1, ""), ("", p2, "Contents"), ("", p3, "Government"), ("", p4, "Growth map"), ("", p5, "East"),
             ("", p6, "North"), ("", p7, "South & West"), ("", p8, "Growth towns"), ("", p9, "Buyer’s guide"), ("", p10, "Outlook")]
    return "".join(page(i, cls, body, label, sec) for i, (cls, body, sec) in enumerate(pages, start=1))


CSS = """
@page { size: A4; margin: 0; }
* { box-sizing: border-box; }
body { margin: 0; background: #e9e7e1; color: #111; font-family: "Georgia", "Times New Roman", serif; }
.mp { width: 210mm; height: 297mm; padding: 14mm 14mm 17mm; margin: 0 auto; background: #fff; position: relative;
  overflow: hidden; break-after: page; font-size: calc(10.4px * var(--k)); line-height: 1.45; }
.mp p { margin: 0 0 7px; text-align: justify; hyphens: auto; }
.folio { position: absolute; bottom: 7mm; left: 14mm; right: 14mm; display: flex; justify-content: space-between;
  font: 8.5px "Helvetica Neue", Arial, sans-serif; color: #6b6a66; border-top: 1px solid #d9d8d2; padding-top: 3px; }
.sect { font: 700 10px "Helvetica Neue", Arial, sans-serif; letter-spacing: 2px; color: #e34948; margin-bottom: 2px; }
.feat { font: 900 calc(34px * var(--k))/1.02 Georgia, serif; color: #0d366b; margin: 0 0 6px; letter-spacing: -.5px; }
.feat2 { font: 900 calc(26px * var(--k))/1.05 Georgia, serif; color: #0d366b; margin: 0 0 6px; }
.stand { font: italic calc(13px * var(--k))/1.35 Georgia, serif; color: #333; margin: 0 0 8px; }
.lede p { font-size: calc(11.5px * var(--k)); }
.kick { font: 700 12px "Helvetica Neue", Arial, sans-serif; text-transform: uppercase; letter-spacing: 1px; color: #e34948; margin: 0 0 6px; }
.band { font: 800 13px "Helvetica Neue", Arial, sans-serif; text-transform: uppercase; letter-spacing: 1px; color: #fff;
  background: #0d366b; padding: 5px 9px; margin: 12px 0 8px; }
.sub { font: 800 11.5px "Helvetica Neue", Arial, sans-serif; text-transform: uppercase; letter-spacing: .8px; color: #0d366b;
  border-bottom: 2px solid #0d366b; padding-bottom: 2px; margin: 10px 0 6px; }
.cols2 { column-count: 2; column-gap: 7mm; }
.two { display: grid; grid-template-columns: 1.25fr 1fr; gap: 8mm; }
.three { display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 5mm; }
.three p { text-align: left; hyphens: manual; }
.three h4 { font: 800 13px "Helvetica Neue", Arial, sans-serif; color: #0d366b; margin: 0 0 4px; display: flex; gap: 6px; align-items: center; }
.hi { width: 22px; height: 22px; color: #e34948; }
.verdict { background: #fdf6e3; border-left: 4px solid #eda100; padding: 7px 10px; margin: 8px 0; }
.verdict p { margin: 0; font-style: italic; }
.toc div { display: flex; justify-content: space-between; border-bottom: 1px dotted #b9b8b2; padding: 4px 0;
  font: 12px "Helvetica Neue", Arial, sans-serif; }
.toc b { color: #e34948; }
.kfs { display: grid; grid-template-columns: repeat(3, 1fr); gap: 6px; margin-bottom: 8px; }
.kf { background: #eef5fe; border-top: 4px solid #0d366b; padding: 7px 9px; }
.kf:nth-child(even) { background: #fdf6e3; border-top-color: #e34948; }
.kv { font: 900 calc(25px * var(--k))/1 "Helvetica Neue", Arial, sans-serif; color: #0d366b; }
.kf:nth-child(even) .kv { color: #e34948; }
.kl { font: 700 10.5px "Helvetica Neue", Arial, sans-serif; margin-top: 3px; }
.kc { font: 9.5px "Helvetica Neue", Arial, sans-serif; color: #52514e; margin-top: 2px; }
table { width: 100%; border-collapse: collapse; font: calc(9.2px * var(--k))/1.3 "Helvetica Neue", Arial, sans-serif; margin: 4px 0 8px; }
th, td { text-align: left; vertical-align: top; padding: 4px 5px; border-bottom: 1px solid #e3e2dc; }
thead th { background: #0d366b; color: #fff; font-weight: 700; border: 0; }
tbody th { font-weight: 700; color: #0d366b; }
.gi { width: 62px; text-align: center; } .gi small { display: block; font-size: 8px; color: #52514e; }
.ti { width: 22px; height: 22px; color: #0d366b; }
.mm .pr, .guide td { white-space: nowrap; font-weight: 700; }
.guide th i { display: inline-block; width: 8px; height: 8px; border-radius: 2px; margin-right: 5px; }
.guide small { font-weight: 400; color: #6b6a66; } .guide .na { color: #b9b8b2; font-weight: 400; } .guide .src { font-weight: 400; color: #52514e; white-space: normal; }
.fine { font: 8.5px "Helvetica Neue", Arial, sans-serif; color: #6b6a66; }
.zart, .mapwrap { margin: 4px 0 8px; } .zart svg, .mapwrap svg, .cover-art svg { width: 100%; height: auto; display: block; border-radius: 4px; }
.map .ring { font: 600 11px "Helvetica Neue", Arial, sans-serif; fill: #52514e; }
.map .pl { font: 9.5px "Helvetica Neue", Arial, sans-serif; fill: #1c5cab; }
.map .pt { font: 700 11.5px "Helvetica Neue", Arial, sans-serif; fill: #0d366b; }
.map .hot { fill: #e34948; } .map .cap { font: 10px "Helvetica Neue", Arial, sans-serif; fill: #6b6a66; }
.caption p { font-style: italic; color: #333; }
.towns { display: grid; grid-template-columns: repeat(3, 1fr); gap: 5mm; }
.town { border: 1px solid #d9d8d2; border-radius: 4px; overflow: hidden; background: #fcfcfb; }
.town svg { width: 100%; height: auto; display: block; }
.town h4 { font: 900 14px Georgia, serif; color: #0d366b; margin: 5px 8px 3px; }
.town p { margin: 0 8px 5px; font-size: calc(9.6px * var(--k)); text-align: left; }
.town .tp { font: 700 10px "Helvetica Neue", Arial, sans-serif; color: #e34948; }
.town .tr { color: #52514e; }
.watch { margin: 0; padding-left: 16px; } .watch li { margin-bottom: 4px; }
.proj tbody th { width: 20%; } .watch li { break-inside: avoid; }
.sources { margin-top: 8px; padding-top: 6px; border-top: 2px solid #0d366b; font: 8.6px/1.4 "Helvetica Neue", Arial, sans-serif; color: #52514e; }
.rule { border: 0; border-top: 2px solid #0d366b; margin: 8px 0; }
/* cover */
.cover { padding: 0; background: #0d366b; color: #fff; }
.mast { display: flex; justify-content: space-between; align-items: flex-end; padding: 12mm 14mm 6mm; border-bottom: 3px solid #e34948; }
.mtitle { font: 900 30px/0.95 "Helvetica Neue", Arial, sans-serif; letter-spacing: 1px; }
.mtitle b { color: #ffcf5a; font-size: 40px; }
.missue { text-align: right; font: 700 15px "Helvetica Neue", Arial, sans-serif; }
.missue small { font-weight: 400; font-size: 10px; opacity: .85; }
.cover-art { padding: 6mm 14mm 0; }
.chead { font: 900 calc(50px * var(--k))/1.0 Georgia, serif; margin: 8mm 14mm 5mm; letter-spacing: -1px; }
.cover p.csub { font: calc(16px * var(--k))/1.4 Georgia, serif; margin: 0 14mm 6mm; color: #dbe7f7; text-align: left; }
.cfig { display: grid; grid-template-columns: repeat(3, 1fr); gap: 5mm; margin: 9mm 14mm 0; }
.cfig div { border-top: 3px solid #ffcf5a; padding-top: 4px; }
.cfig b { display: block; font: 900 calc(30px * var(--k))/1 "Helvetica Neue", Arial, sans-serif; color: #ffcf5a; }
.cfig span { font: calc(11px * var(--k)) "Helvetica Neue", Arial, sans-serif; color: #dbe7f7; }
.clines { list-style: none; padding: 0; margin: 0 14mm; display: grid; grid-template-columns: 1fr 1fr; gap: 3mm 8mm; }
.clines li { font: 700 calc(15px * var(--k))/1.25 "Helvetica Neue", Arial, sans-serif; border-left: 4px solid #e34948; padding-left: 8px; }
.cfoot { position: absolute; bottom: 9mm; left: 14mm; right: 14mm; font: 700 10px "Helvetica Neue", Arial, sans-serif;
  letter-spacing: 1px; color: #ffcf5a; border-top: 1px solid rgba(255,255,255,.3); padding-top: 4px; }
@media screen and (max-width: 820px) { .mp { width: 100%; height: auto; overflow: visible; padding: 16px; } .two, .three, .towns, .kfs { grid-template-columns: 1fr; } .cols2 { column-count: 1; } }
"""


FIT_JS = """
<script>
(function () {
  // Each page gets its own type scale: start generous, step down until the content's real bottom edge
  // sits above the footer line (measured from element boxes, not scrollHeight, so print matches screen).
  function bottom(pg) {
    var top = pg.getBoundingClientRect().top, b = 0;
    Array.prototype.forEach.call(pg.querySelectorAll('*'), function (el) {
      if (el.closest('.folio') || el.closest('.cfoot')) return;
      var r = el.getBoundingClientRect();
      if (r.height > 0 && r.bottom - top > b) b = r.bottom - top;
    });
    return b;
  }
  document.querySelectorAll('.mp').forEach(function (pg) {
    var limit = pg.clientHeight - 64;              // keep clear of the folio (~17 mm) + safety
    var k = pg.classList.contains('cover') ? 1.0 : 1.32;
    pg.style.setProperty('--k', k);
    while (bottom(pg) > limit && k > 0.62) {
      k = Math.round((k - 0.02) * 100) / 100;
      pg.style.setProperty('--k', k);
    }
    pg.dataset.k = k;
    pg.dataset.overflow = bottom(pg) > limit ? '1' : '0';
  });
})();
</script>
"""


def fit_report(page_html: Path) -> list[dict]:
    """Run the page in headless Chrome and read back each page's scale and overflow state."""
    import subprocess
    from harness.report import CHROME
    exe = next((x for x in CHROME if Path(x).exists()), None)
    if not exe:
        return []
    r = subprocess.run([exe, "--headless=new", "--disable-gpu", "--window-size=900,1300", "--dump-dom",
                        page_html.resolve().as_uri()], capture_output=True, text=True, timeout=120)
    return [{"k": float(k), "overflow": o == "1"} for k, o in
            re.findall(r'class="mp[^"]*"[^>]*data-k="([\d.]+)"[^>]*data-overflow="(\d)"', r.stdout)]


def render_issue(edition: str, log) -> Path:
    from harness.magazine import MAG_OUT, publishable
    from harness.pdf_edition import count_pages
    from harness.report import html_pdf
    issue = read_json(MAG_OUT / f"{edition}.issue.json")
    data = read_json(MAG_OUT / f"{edition}.json")
    claims = [c for c in data["claims"] if publishable(c)]
    out_dir = REPORTS / "magazine"
    label = issue["_meta"]["label"]
    body = build(issue, claims, label, data["as_of"])
    pdf = out_dir / f"bengaluru-property-review-{edition}.pdf"
    page_html = out_dir / f"bengaluru-property-review-{edition}.html"
    doc = (f"<!doctype html><html lang='en'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'>"
           f"<title>Bengaluru Property Review — {e(label)}</title><style>{CSS}:root{{--k:1}}</style></head><body>{body}{FIT_JS}</body></html>")
    write_text(page_html, doc)
    err = html_pdf(page_html, pdf)
    if err:
        raise SystemExit(err)
    n = count_pages(pdf)
    fits = fit_report(page_html)
    clipped = [i + 1 for i, f in enumerate(fits) if f["overflow"]]
    log("magazine_rendered", pages=n, scales=[f["k"] for f in fits], clipped_pages=clipped)
    if n != PAGES or clipped:
        raise SystemExit(f"magazine layout check failed: {n} pages, clipped pages {clipped}")
    return pdf
