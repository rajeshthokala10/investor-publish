"""Daily Edition: a 5-page broadsheet-style newspaper PDF of Bengaluru development and metro news.

Facts = today's publishable claims + today's relevant headlines (headline-only facts, ids "H-").
A no-tools writer drafts the paper; code enforces that every number in the copy appears in the
facts it cites. The metro network map and line status board come from app/content/metro.json and
the latest magazine issue (no LLM). No market statistics in this edition by design.
"""
from __future__ import annotations

import html
import json
from pathlib import Path

from harness import agent
from harness.common import DATA, PROCESSED, PROMPTS, ROOT, iso, now_ist, read_json, sha, write_json, write_text
from harness.magazine_write import check_block, nums
from harness.registry import corridors, primary_corridor, region_of

PAGES = 5
P = {"type": "object", "additionalProperties": False, "required": ["text", "ids"],
     "properties": {"text": {"type": "string"}, "ids": {"type": "array", "items": {"type": "string"}}}}
STORY = {"type": "object", "additionalProperties": False, "required": ["headline", "text", "ids"],
         "properties": {"headline": {"type": "string"}, "text": {"type": "string"},
                        "ids": {"type": "array", "items": {"type": "string"}}}}
METRO_STORY = {**STORY, "required": ["headline", "text", "ids", "line"],
               "properties": {**STORY["properties"], "line": {"enum": ["purple", "green", "yellow", "pink", "blue", "orange",
                                                                         "red", "suburban", "general"]}}}
SCHEMA = {
    "type": "object", "additionalProperties": False,
    "required": ["lead", "second", "front_briefs", "metro_intro", "metro_stories", "development_stories",
                 "government_stories", "around", "watch", "launches", "investment_column"],
    "properties": {
        "lead": {"type": "object", "additionalProperties": False, "required": ["kicker", "headline", "standfirst", "paragraphs"],
                 "properties": {"kicker": {"type": "string"}, "headline": {"type": "string"}, "standfirst": {"type": "string"},
                                "paragraphs": {"type": "array", "items": P}}},
        "second": {"type": "object", "additionalProperties": False, "required": ["kicker", "headline", "paragraphs"],
                   "properties": {"kicker": {"type": "string"}, "headline": {"type": "string"},
                                  "paragraphs": {"type": "array", "items": P}}},
        "front_briefs": {"type": "array", "items": STORY},
        "metro_intro": {"type": "array", "items": P},
        "metro_stories": {"type": "array", "items": METRO_STORY},
        "development_stories": {"type": "array", "items": STORY},
        "government_stories": {"type": "array", "items": STORY},
        "around": {"type": "array", "items": {"type": "object", "additionalProperties": False, "required": ["zone", "items"],
                   "properties": {"zone": {"enum": ["east", "north", "south", "west", "outer"]},
                                  "items": {"type": "array", "items": STORY}}}},
        "launches": {"type": "array", "items": {"type": "object", "additionalProperties": False,
                     "required": ["headline", "text", "ids", "type", "area", "developer"],
                     "properties": {"headline": {"type": "string"}, "text": {"type": "string"},
                                    "ids": {"type": "array", "items": {"type": "string"}},
                                    "type": {"enum": ["villa", "plot", "apartment", "mixed", "commercial"]},
                                    "area": {"type": "string"}, "developer": {"type": "string"}}}},
        "investment_column": {"type": "object", "additionalProperties": False, "required": ["headline", "paragraphs"],
                              "properties": {"headline": {"type": "string"}, "paragraphs": {"type": "array", "items": P}}},
        "watch": {"type": "array", "items": {"type": "object", "additionalProperties": False, "required": ["item", "why", "ids"],
                  "properties": {"item": {"type": "string"}, "why": {"type": "string"},
                                 "ids": {"type": "array", "items": {"type": "string"}}}}},
    },
}
ZONE = {"east": "east", "north": "north", "south": "south", "west": "west", "peripheral": "outer", "unmapped": "city"}


# ------------------------------------------------------------------------------------------------ facts
def facts_for(d: dict) -> tuple[list[dict], dict]:
    from app.site_data import relevant_headline, REGION_NAME
    from harness.magazine import publishable
    from harness.report import fresh_claims, standalone
    by, rows = {}, []
    for c in fresh_claims(d):
        if not publishable(c):
            continue
        by[c["claim_id"]] = c
        rows.append({"id": c["claim_id"], "fact": standalone(c), "place": c.get("locality") or c["subject"],
                     "zone": ZONE.get(region_of(c["corridor"]), "city"), "kind": c["claim_type"],
                     "source": c["publisher"], "date": c["published_at"]})
    for s in d.get("stories", []):
        if s.get("novelty") == "repeat" or s.get("stale_flags"):
            continue
        zone = REGION_NAME.get((s.get("regions") or ["unmapped"])[0], "City-wide")
        if not relevant_headline(s["title"], zone):
            continue
        url = s.get("url") or s["lead"]["url"]
        hid = "H-" + sha(url, n=8)
        pub = (s.get("publishers") or [""])[0]
        by[hid] = {"claim_id": hid, "statement": s["title"], "excerpt": s["title"], "subject": s["title"],
                   "published_at": (s.get("published_at") or "")[:10], "value": None, "value_max": None,
                   "period_years": None, "publisher": pub, "url": url}
        rows.append({"id": hid, "fact": s["title"], "place": zone, "zone": zone.lower().replace("city-wide", "city"),
                     "kind": "headline", "source": pub, "date": (s.get("published_at") or "")[:10]})
    # today's project records (launches / phases), including villas and plots
    for p in d.get("projects", []):
        pid = "P-" + sha(p.get("url", ""), p.get("name", ""), n=8)
        text = (f"{p.get('developer') or 'A developer'} - project {p['name']} ({p.get('property_type')}, "
                f"{(p.get('status') or '').replace('_', ' ')}) in {p.get('locality') or 'Bengaluru'}")
        if p.get("unit_sizes"):
            text += f"; sizes {p['unit_sizes']}"
        by[pid] = {"claim_id": pid, "statement": text, "excerpt": (p.get("excerpt") or "") + " " + text, "subject": p["name"],
                   "published_at": p.get("published_at"), "value": None, "value_max": None, "period_years": None,
                   "publisher": p.get("publisher") or "", "url": p.get("url", "")}
        rows.append({"id": pid, "fact": text, "place": p.get("locality") or "", "kind": "project",
                     "zone": ZONE.get(region_of(primary_corridor(p.get("locality"), p.get("name"))), "city"),
                     "source": p.get("publisher") or "", "date": p.get("published_at")})
    # growth areas for the investment column: evidenced planned cities / clusters (evergreen context)
    for c in read_json(DATA / "app" / "clusters.json", {}).get("clusters", []):
        for i, f in enumerate(c.get("facts", [])[:3]):
            gid = "G-" + sha(c["name"], i, n=8)
            by[gid] = {"claim_id": gid, "statement": f["statement"], "excerpt": f["excerpt"], "subject": c["name"],
                       "published_at": f.get("published_at"), "value": None, "value_max": None, "period_years": None,
                       "publisher": f["publisher"], "url": f["url"]}
            rows.append({"id": gid, "fact": f"{c['name']} ({c['kind']}, stage: {c['stage']}): {f['statement']}",
                         "place": c["nearest_town"], "zone": "outer", "kind": "growth_area", "source": f["publisher"],
                         "date": f.get("published_at")})
    return rows[:220], by


# ------------------------------------------------------------------------------------------- validation
def validate(paper: dict, by: dict) -> tuple[dict, list[str]]:
    dropped = []

    def ok(text, ids, where):
        why = check_block(text, ids, by)
        if why:
            dropped.append(f"{where}: {why} :: {text[:70]}")
        return why is None

    for key in ("lead", "second"):
        art = paper[key]
        art["paragraphs"] = [p for p in art["paragraphs"] if ok(p["text"], p["ids"], key)]
        ids = [i for p in art["paragraphs"] for i in p["ids"]]
        for f in ("headline", "standfirst", "kicker"):
            if f in art and nums(art[f]) and not ok(art[f], ids, f"{key}.{f}"):
                art[f] = ""
    paper["metro_intro"] = [p for p in paper["metro_intro"] if ok(p["text"], p["ids"], "metro_intro")]
    for key in ("front_briefs", "metro_stories", "development_stories", "government_stories"):
        paper[key] = [s for s in paper[key] if ok(s["headline"] + " " + s["text"], s["ids"], key)]
    for z in paper["around"]:
        z["items"] = [s for s in z["items"] if ok(s["headline"] + " " + s["text"], s["ids"], f"around.{z['zone']}")]
    paper["around"] = [z for z in paper["around"] if z["items"]]
    paper["watch"] = [w for w in paper["watch"] if ok(w["item"] + " " + w["why"], w["ids"], "watch")]
    paper["launches"] = [l for l in paper.get("launches", []) if ok(l["headline"] + " " + l["text"], l["ids"], "launches")]
    col = paper.get("investment_column") or {"headline": "", "paragraphs": []}
    col["paragraphs"] = [p for p in col["paragraphs"] if ok(p["text"], p["ids"], "investment_column")]
    if col.get("headline") and nums(col["headline"]) and not ok(col["headline"], [i for p in col["paragraphs"] for i in p["ids"]], "column.headline"):
        col["headline"] = ""
    paper["investment_column"] = col
    return paper, dropped


def write_paper(edition: str, d: dict, window: dict, log) -> dict | None:
    if not agent.available()[0]:
        return None
    rows, by = facts_for(d)
    if not rows:
        return None
    prompt = ((PROMPTS / "daily_writer.md").read_text(encoding="utf-8")
              .replace("{{DATE}}", now_ist().strftime("%A, %d %B %Y"))
              .replace("{{WINDOW}}", f"{window['start'][:16].replace('T', ' ')} to {window['end'][:16].replace('T', ' ')}")
              .replace("{{FACTS}}", "\n".join(json.dumps(r, ensure_ascii=False) for r in rows)))
    out = ROOT / "reports" / "daily" / f"{edition}.paper_raw.json"
    res = agent.run_agent(prompt, SCHEMA, name=f"daily_writer_{edition}", out_path=out, budget_usd=1.0,
                          timeout_min=12, log=log, tools=[])
    out.unlink(missing_ok=True)       # raw draft is not a publication artefact
    if not res["ok"]:
        log("paper_writer_failed", error=res["error"])
        return None
    paper, dropped = validate(res["data"], by)
    paper["_meta"] = {"edition": edition, "facts": len(rows), "dropped": dropped, "written_at": iso(now_ist())}
    paper["_sources"] = {i: {"publisher": by[i]["publisher"], "url": by[i]["url"]} for i in by}
    write_json(PROCESSED / "daily_paper" / f"{edition}.json", paper)
    log("paper_written", facts=len(rows), dropped=len(dropped))
    return paper


# --------------------------------------------------------------------------------------------- metro map
def metro() -> dict:
    return read_json(ROOT / "app" / "content" / "metro.json")


def metro_svg(width=620, height=640, labels=True) -> str:
    m = metro()
    dash = {"operational": "", "under_construction": "10 6", "approved": "3 6", "proposed": "2 7"}
    out = [f'<svg viewBox="0 0 {width} {height}" class="metro-svg" role="img" aria-label="Namma Metro network (schematic)">',
           f'<rect width="{width}" height="{height}" rx="10" fill="#f7f9fc"/>']
    for ln in m["lines"]:
        pts = " ".join(f"{x},{y}" for _, x, y in ln["stations"])
        out.append(f'<polyline points="{pts}" fill="none" stroke="{ln["color"]}" stroke-width="6" stroke-linecap="round" '
                   f'stroke-linejoin="round" stroke-dasharray="{dash.get(ln["status"], "")}" opacity="{1 if ln["status"] == "operational" else .8}"/>')
    seen = {}
    for ln in m["lines"]:
        for name, x, y in ln["stations"]:
            seen.setdefault(name, [x, y, 0])
            seen[name][2] += 1
    terminals = {ln["stations"][0][0] for ln in m["lines"]} | {ln["stations"][-1][0] for ln in m["lines"]}
    for name, (x, y, n) in seen.items():
        r = 6 if n > 1 else 3.6
        out.append(f'<circle cx="{x}" cy="{y}" r="{r}" fill="#fff" stroke="#1b2430" stroke-width="{2 if n > 1 else 1.4}"><title>{html.escape(name)}</title></circle>')
        if labels and (n > 1 or name in terminals):
            out.append(f'<text x="{x + 9}" y="{y - 6}" class="ms">{html.escape(name)}</text>')
    out.append("</svg>")
    return "".join(out)


def line_status_rows() -> list[dict]:
    """Line board: status from metro.json, latest detail from the newest magazine issue's government table."""
    mags = sorted((PROCESSED / "magazine").glob("????-??.issue.json"))
    gov = read_json(mags[-1], {}).get("gov_rows", []) if mags else []
    rows = []
    for ln in metro()["lines"]:
        if ln["id"] == "orange2":
            continue
        key = ln["name"].split()[0].lower()
        cands = [g for g in gov if key in g["project"].lower()]
        detail = next((g for g in cands if "extension" not in g["project"].lower()), None) or (cands[0] if cands else None)
        text = ""
        if detail:
            text = (f"{detail['project']}: " if "extension" in detail["project"].lower() else "") + detail["status"]
        rows.append({"color": ln["color"], "name": ln["name"], "termini": " – ".join(ln["termini"]),
                     "status": ln["status_label"], "detail": text, "timeline": detail["timeline"] if detail else ""})
    return rows


def latest_issue() -> dict:
    mags = sorted((PROCESSED / "magazine").glob("????-??.issue.json"))
    return read_json(mags[-1], {}) if mags else {}


# ---------------------------------------------------------------------------------------------- render
def e(s) -> str:
    return html.escape(str(s or ""))


def paras(ps, dropcap=False) -> str:
    out = []
    for i, p in enumerate(ps):
        cls = ' class="dc"' if dropcap and i == 0 else ""
        out.append(f"<p{cls}>{e(p['text'])}</p>")
    return "".join(out)


def story(s, cls="st") -> str:
    return f'<article class="{cls}"><h3>{e(s["headline"])}</h3><p>{e(s["text"])}</p></article>'


def _blocks(paper: dict) -> list[dict]:
    out = list(paper["lead"]["paragraphs"]) + list(paper["second"]["paragraphs"]) + list(paper["metro_intro"])
    for k in ("front_briefs", "metro_stories", "development_stories", "government_stories", "watch", "launches"):
        out += paper.get(k, [])
    out += (paper.get("investment_column") or {}).get("paragraphs", [])
    for z in paper["around"]:
        out += z["items"]
    return out


def build_html(paper: dict, meta: dict, css: str, fit_js: str) -> str:
    date = now_ist().strftime("%A, %d %B %Y")
    w = meta["window"]
    lines = {ln["id"]: ln for ln in metro()["lines"]}
    chip = lambda lid: (f'<span class="chip" style="background:{lines[lid]["color"]}">{e(lines[lid]["name"].split(" (")[0])}</span>'  # noqa: E731
                        if lid in lines else '<span class="chip" style="background:#455">Metro</span>')
    masthead = (f'<header class="mast"><div class="mtop"><span>DAILY EDITION</span><span>{e(date)}</span><span>BENGALURU</span></div>'
                f'<h1>Bengaluru Property Review</h1><div class="mbar"><span>Development · Metro · Government · Around the city</span>'
                f'<span>News from {e(w["start"][:16].replace("T", " "))} to {e(w["end"][:16].replace("T", " "))} IST</span></div></header>')
    lead, second = paper["lead"], paper["second"]
    metro_box = "".join(f'<li>{chip(s["line"])}<b>{e(s["headline"])}</b></li>' for s in paper["metro_stories"][:4]) or \
        "<li>No metro announcements in the last three days. Line status: page 2.</li>"
    briefs = "".join(f'<li><b>{e(b["headline"])}.</b> {e(b["text"])}</li>' for b in paper["front_briefs"])
    p1 = (masthead +
          f'<div class="front"><div class="leadcol"><div class="kicker">{e(lead["kicker"])}</div><h2 class="lh">{e(lead["headline"])}</h2>'
          f'<p class="sf">{e(lead["standfirst"])}</p><div class="cols3">{paras(lead["paragraphs"], True)}</div>'
          f'<hr class="thin"><div class="kicker">{e(second["kicker"])}</div><h2 class="sh">{e(second["headline"])}</h2>'
          f'<div class="cols2">{paras(second["paragraphs"])}</div></div>'
          f'<aside class="side"><div class="box metro"><h4>METRO WATCH</h4><ul>{metro_box}</ul><p class="more">Full metro page → 2</p></div>'
          f'<div class="box"><h4>IN BRIEF</h4><ul class="briefs">{briefs}</ul></div>'
          f'<div class="box inside"><h4>INSIDE</h4><p>Metro &amp; Transport <b>2</b></p><p>City Development <b>3</b></p>'
          f'<p>Government &amp; Policy <b>4</b></p><p>Around Bengaluru <b>5</b></p></div></aside></div>')
    board = "".join(f'<tr><td><i style="background:{r["color"]}"></i></td><td><b>{e(r["name"])}</b><br><small>{e(r["termini"])}</small></td>'
                    f'<td><span class="st-{e(r["status"].split()[0].lower())}">{e(r["status"])}</span></td><td>{e(r["detail"])}'
                    f'{"<br><small>" + e(r["timeline"]) + "</small>" if r["timeline"] else ""}</td></tr>' for r in line_status_rows())
    p2 = (f'<div class="sect"><span>METRO &amp; TRANSPORT</span></div><div class="cols-intro">{paras(paper["metro_intro"])}</div>'
          f'<div class="metrogrid"><div class="map">{metro_svg()}<p class="cap">{e(metro()["note"].replace(" Train animation is illustrative, not live positions.", ""))}</p></div>'
          f'<div><h4 class="bh">Where every line stands</h4><table class="board">{board}</table></div></div>'
          f'<div class="stories3">' + "".join(f'<article class="st">{chip(s["line"])}<h3>{e(s["headline"])}</h3><p>{e(s["text"])}</p></article>'
                                               for s in paper["metro_stories"]) + "</div>")
    issue = latest_issue()
    pipe = [g for g in issue.get("gov_rows", []) if g["category"] in ("road", "township", "water", "airport", "governance")]
    pipeline_box = ("<div class='box pipe'><h4>PROJECTS IN THE PIPELINE</h4><table class='board'>"
                    + "".join(f"<tr><td><b>{e(g['project'])}</b><br><small>{e(g['areas'])}</small></td><td>{e(g['status'])}"
                              f"<br><small>{e(g['timeline'])}</small></td></tr>" for g in pipe[:8])
                    + f"</table><p class='cap'>Status as reported in the {e(issue.get('_meta', {}).get('label', 'latest'))} Bengaluru Property Review.</p></div>") if pipe else ""
    p3 = (f'<div class="sect"><span>CITY DEVELOPMENT</span></div><div class="stories2">'
          + ("".join(story(s) for s in paper["development_stories"]) or "<p>No new development announcements in this window.</p>")
          + "</div>" + pipeline_box)
    watch = "".join(f'<li><b>{e(x["item"])}</b> — {e(x["why"])}</li>' for x in paper["watch"])
    p4 = (f'<div class="sect"><span>GOVERNMENT &amp; POLICY</span></div><div class="stories2">'
          + ("".join(story(s) for s in paper["government_stories"]) or "<p>No new government decisions in this window.</p>") + "</div>"
          + (f'<div class="box watch"><h4>WHAT TO WATCH</h4><ul>{watch}</ul></div>' if watch else ""))
    zname = {"east": "East", "north": "North", "south": "South", "west": "West", "outer": "Beyond the city"}
    zones = "".join(f'<section class="zone z-{z["zone"]}"><h3>{zname[z["zone"]]}</h3>'
                    + "".join(f'<div class="zi"><b>{e(i["headline"])}</b><p>{e(i["text"])}</p></div>' for i in z["items"]) + "</section>"
                    for z in paper["around"])
    towns = issue.get("growth_towns", [])
    towns_box = ("<div class='box towns'><h4>GROWTH TOWNS TO WATCH</h4><div class='tgrid'>"
                 + "".join(f"<div><b>{e(t['name'])}</b><p>{e(t['why'])}</p></div>" for t in towns[:8]) + "</div></div>") if towns else ""
    cited = {i for blk in _blocks(paper) for i in blk.get("ids", [])}
    srcs = paper.get("_sources", {})
    pubs = sorted({srcs[i]["publisher"] for i in cited if i in srcs and srcs[i]["publisher"]})
    p5 = (f'<div class="sect"><span>AROUND BENGALURU</span></div><div class="zones">{zones or "<p>No area news in this window.</p>"}</div>'
          f'{towns_box}<div class="foot"><b>Sources for this edition:</b> {e(", ".join(pubs[:40]))}. News is attributed to the organisations that '
          f'published it; plans and dates are as announced and can change. Bengaluru Property Review · information only, not investment advice.</div>')
    pages = [p1, p2, p3, p4, p5]
    folio = lambda n, label: (f'<div class="folio"><span>Bengaluru Property Review · Daily Edition</span><span>{e(label)}</span>'  # noqa: E731
                              f'<span>{e(date)} · {n}</span></div>')
    labels = ["Front page", "Metro & Transport", "City Development", "Government & Policy", "Around Bengaluru"]
    body = "".join(f'<section class="mp{" first" if n == 1 else ""}">{pg}{folio(n, labels[n - 1])}</section>' for n, pg in enumerate(pages, 1))
    return (f"<!doctype html><html lang='en'><head><meta charset='utf-8'><title>Bengaluru Property Review — Daily Edition {e(meta['edition'])}</title>"
            f"<style>{css}</style></head><body>{body}{fit_js}</body></html>")


PAPER_CSS = """
@page { size: A4; margin: 0; }
* { box-sizing: border-box; }
body { margin: 0; background: #ddd; color: #111; font-family: Georgia, "Times New Roman", serif; }
.mp { width: 210mm; height: 297mm; padding: 11mm 12mm 15mm; margin: 0 auto; background: #fbfaf6; position: relative; overflow: hidden;
  break-after: page; font-size: calc(10.2px * var(--k)); line-height: 1.42; }
.mp p { margin: 0 0 6px; text-align: justify; hyphens: auto; }
.mast { border-bottom: 3px double #111; margin-bottom: 8px; }
.mtop, .mbar { display: flex; justify-content: space-between; font: 700 9px Arial, sans-serif; letter-spacing: 1.2px; color: #333; }
.mtop { border-bottom: 1px solid #111; padding-bottom: 3px; }
.mast h1 { font: 900 calc(46px * var(--k))/1 "Times New Roman", Georgia, serif; text-align: center; margin: 6px 0 4px; letter-spacing: -1px; }
.mbar { border-top: 1px solid #111; padding: 3px 0; font-weight: 400; letter-spacing: .4px; }
.mbar span:first-child { color: #c4161c; font-weight: 700; }
.front { display: grid; grid-template-columns: 1fr 58mm; gap: 6mm; }
.kicker { font: 800 10px Arial, sans-serif; letter-spacing: 1.5px; text-transform: uppercase; color: #c4161c; margin: 2px 0; }
.lh { font: 900 calc(34px * var(--k))/1.04 "Times New Roman", Georgia, serif; margin: 0 0 6px; letter-spacing: -.5px; }
.sh { font: 800 calc(21px * var(--k))/1.1 "Times New Roman", Georgia, serif; margin: 0 0 5px; }
.sf { font: italic calc(13px * var(--k))/1.35 Georgia, serif; color: #333; text-align: left !important; }
.cols3 { column-count: 3; column-gap: 5mm; column-rule: 1px solid #ccc; }
.cols2 { column-count: 2; column-gap: 5mm; column-rule: 1px solid #ccc; }
.dc::first-letter { float: left; font: 900 3.1em/0.85 "Times New Roman", serif; margin: 3px 5px 0 0; color: #c4161c; }
.thin { border: 0; border-top: 1px solid #111; margin: 8px 0 6px; }
.side { border-left: 1px solid #111; padding-left: 5mm; }
.box { margin-bottom: 8px; }
.box h4 { font: 800 11px Arial, sans-serif; letter-spacing: 1.4px; margin: 0 0 5px; padding: 3px 6px; background: #111; color: #fff; }
.box.metro h4 { background: #c4161c; }
.box ul { margin: 0; padding: 0; list-style: none; }
.box li { padding: 5px 0; border-bottom: 1px dotted #999; font-size: calc(10px * var(--k)); line-height: 1.35; }
.box li b { display: block; font-family: "Times New Roman", serif; font-size: 1.08em; }
.briefs li b { display: inline; }
.box .more { font: 700 9.5px Arial, sans-serif; color: #c4161c; margin-top: 4px; }
.inside p { display: flex; justify-content: space-between; border-bottom: 1px dotted #999; margin: 0; padding: 4px 0; font: 11px Arial, sans-serif; }
.inside b { color: #c4161c; }
.chip { display: inline-block; font: 800 8.5px Arial, sans-serif; color: #fff; padding: 1px 6px; border-radius: 8px; letter-spacing: .4px; margin-bottom: 2px; }
.sect { border-top: 4px solid #111; border-bottom: 1px solid #111; margin-bottom: 8px; padding: 4px 0; }
.sect span { font: 900 calc(20px * var(--k)) "Times New Roman", serif; letter-spacing: 2px; }
.cols-intro p { font-size: calc(11.5px * var(--k)); font-style: italic; }
.metrogrid { display: grid; grid-template-columns: 1.1fr 1fr; gap: 5mm; margin: 4px 0 8px; }
.metro-svg { width: 100%; height: auto; aspect-ratio: 620 / 640; display: block; border: 1px solid #ccc; border-radius: 8px; }
.metro-svg .ms { font: 600 8.5px Arial, sans-serif; fill: #1b2430; paint-order: stroke; stroke: #f7f9fc; stroke-width: 3px; }
.cap { font: italic 8.5px Arial, sans-serif; color: #555; text-align: left !important; margin-top: 3px; }
.bh { font: 800 11px Arial, sans-serif; letter-spacing: 1px; text-transform: uppercase; margin: 0 0 4px; }
.board { width: 100%; border-collapse: collapse; font: calc(9px * var(--k))/1.3 Arial, sans-serif; }
.board td { border-bottom: 1px solid #ddd; padding: 4px 4px; vertical-align: top; }
.board i { display: inline-block; width: 12px; height: 12px; border-radius: 50%; margin-top: 2px; }
.board small { color: #555; }
.board span { font-weight: 700; white-space: nowrap; }
.st-operational { color: #1f7a3a; } .st-under { color: #b26a00; } .st-approved { color: #1f5fb4; } .st-proposed { color: #8a1c1c; }
.stories2, .stories3 { column-count: 2; column-gap: 6mm; column-rule: 1px solid #ccc; }
.stories3 { column-count: 3; }
.st { break-inside: avoid; margin-bottom: 9px; padding-bottom: 7px; border-bottom: 1px solid #ddd; }
.st h3 { font: 800 calc(15px * var(--k))/1.15 "Times New Roman", serif; margin: 2px 0 4px; }
.watch { margin-top: 6px; } .watch li b { display: inline; }
.zones { display: grid; grid-template-columns: 1fr 1fr; gap: 5mm; }
.pipe, .towns { margin-top: 10px; } .pipe .board td { font-size: calc(9.4px * var(--k)); }
.tgrid { display: grid; grid-template-columns: 1fr 1fr; gap: 4px 6mm; } .tgrid div { border-bottom: 1px dotted #999; padding: 3px 0; }
.tgrid b { font-family: "Times New Roman", serif; font-size: 1.1em; } .tgrid p { margin: 1px 0 0; text-align: left; }
.zone h3 { font: 900 15px "Times New Roman", serif; border-bottom: 3px solid #111; margin: 0 0 5px; padding-bottom: 2px; }
.z-east h3 { border-color: #1f6fd1; } .z-north h3 { border-color: #f07c1a; } .z-south h3 { border-color: #1f9d55; }
.z-west h3 { border-color: #e8b100; } .z-outer h3 { border-color: #7b3fa0; }
.zi { margin-bottom: 6px; } .zi b { font-family: "Times New Roman", serif; font-size: 1.1em; } .zi p { margin: 2px 0 0; }
.foot { margin-top: 10px; padding-top: 6px; border-top: 2px solid #111; font: calc(8.6px * var(--k))/1.4 Arial, sans-serif; color: #444; }
.folio { position: absolute; left: 12mm; right: 12mm; bottom: 7mm; display: flex; justify-content: space-between; font: 8.5px Arial, sans-serif;
  color: #444; border-top: 1px solid #111; padding-top: 3px; }
@media screen and (max-width: 820px) { .mp { width: 100%; height: auto; overflow: visible; } .front, .metrogrid, .zones { grid-template-columns: 1fr; }
  .cols3, .cols2, .stories2, .stories3 { column-count: 1; } .side { border: 0; padding: 0; } }
"""


def render_paper(edition: str, paper: dict, meta: dict, out_pdf: Path, html_pdf) -> tuple[int, str | None]:
    from harness.magazine_render import FIT_JS, fit_report
    from harness.pdf_edition import count_pages
    fit = FIT_JS.replace("? 1.0 : 1.32", "? 1.0 : 1.25")
    doc = build_html(paper, meta, PAPER_CSS, fit)
    page = out_pdf.with_suffix(".paper.html")
    write_text(page, doc)
    err = html_pdf(page, out_pdf)
    if err:
        return 0, err
    n = count_pages(out_pdf)
    clipped = [i + 1 for i, f in enumerate(fit_report(page)) if f["overflow"]]
    return n, (None if n == PAGES and not clipped else f"paper layout: {n} pages, clipped {clipped}")


# ------------------------------------------------------------------ magazine-style daily: Bangalore Realestate Delta
DELTA_NAME = "Bangalore Realestate Delta"


def build_delta_html(paper: dict, meta: dict) -> str:
    """Same visual language as the monthly magazine (harness/magazine_render.py), news only."""
    from harness.infographic import skyline
    from harness.magazine_render import CSS as MAG_CSS
    date = now_ist().strftime("%A, %d %B %Y")
    short = now_ist().strftime("%d %B %Y")
    w = meta["window"]
    lines = {ln["id"]: ln for ln in metro()["lines"]}
    chip = lambda lid: (f'<span class="lchip" style="background:{lines[lid]["color"]}">{e(lines[lid]["name"].split(" (")[0])}</span>'  # noqa: E731
                        if lid in lines else '<span class="lchip" style="background:#455a64">Metro</span>')
    lead, second = paper["lead"], paper["second"]
    cover_lines = [s["headline"] for s in (paper["metro_stories"][:1] + paper.get("launches", [])[:1]
                                           + paper["development_stories"][:1] + paper["government_stories"][:1])]
    if (paper.get("investment_column") or {}).get("headline"):
        cover_lines = cover_lines[:3] + ["Investment column: " + paper["investment_column"]["headline"]]
    p1 = (f'<div class="mast"><div class="mtitle">BANGALORE<br><b>REALESTATE DELTA</b></div>'
          f'<div class="missue">{e(short)}<br><small>Daily · Metro · Development · Government · Around the city</small></div></div>'
          f'<div class="cover-art">{skyline("delta" + short, 900, 380, pins=["Whitefield", "Hebbal", "Majestic", "Sarjapur", "Hoskote", "Kengeri"])}</div>'
          f'<div class="ckick">{e(lead["kicker"]).upper()}</div><h1 class="chead">{e(lead["headline"])}</h1>'
          f'<p class="csub">{e(lead["standfirst"])}</p>'
          f'<ul class="clines">' + "".join(f"<li>{e(c)}</li>" for c in cover_lines[:4]) + "</ul>"
          f'<div class="cfoot">INSIDE · Top stories · Metro &amp; Transport · Launches &amp; Development · Government · Investment column · Around Bengaluru</div>')
    briefs = "".join(f'<div class="brief"><h4>{e(b["headline"])}</h4><p>{e(b["text"])}</p></div>' for b in paper["front_briefs"])
    p2 = (f'<div class="sect">TODAY’S TOP STORIES</div><h1 class="feat">{e(lead["headline"])}</h1>'
          f'<p class="stand">{e(lead["standfirst"])}</p><div class="cols2">{paras(lead["paragraphs"])}</div>'
          + (f'<hr class="rule"><div class="sect">{e(second["kicker"]).upper()}</div><h2 class="feat2">{e(second["headline"])}</h2>'
             f'<div class="cols2">{paras(second["paragraphs"])}</div>' if second["paragraphs"] else "")
          + (f'<h3 class="sub">In brief</h3><div class="briefs3">{briefs}</div>' if briefs else ""))
    board = "".join(f'<tr><td><i class="ldot" style="background:{r["color"]}"></i></td><td><b>{e(r["name"])}</b><br><small>{e(r["termini"])}</small></td>'
                    f'<td><b class="st-{e(r["status"].split()[0].lower())}">{e(r["status"])}</b></td><td>{e(r["detail"])}'
                    f'{"<br><small>" + e(r["timeline"]) + "</small>" if r["timeline"] else ""}</td></tr>' for r in line_status_rows())
    mstories = "".join(f'<div class="mcard">{chip(s["line"])}<h4>{e(s["headline"])}</h4><p>{e(s["text"])}</p></div>' for s in paper["metro_stories"])
    p3 = (f'<div class="sect">METRO &amp; TRANSPORT</div><h1 class="feat2">Namma Metro and rail today</h1>'
          f'<div class="lede">{paras(paper["metro_intro"])}</div>'
          f'<div class="two mgrid"><div class="mapbox">{metro_svg()}</div><div><h3 class="sub">Where every line stands</h3>'
          f'<table class="board">{board}</table></div></div>'
          f'<div class="mcards">{mstories or "<p>No metro announcements in this window.</p>"}</div>')
    issue = latest_issue()
    pipe = [g for g in issue.get("gov_rows", []) if g["category"] in ("road", "township", "water", "airport", "governance")]
    ptable = ("<h3 class='sub'>Projects in the pipeline</h3><table class='gov'><thead><tr><th>Project</th><th>Where it stands</th>"
              "<th>Timeline</th><th>Areas</th></tr></thead><tbody>"
              + "".join(f"<tr><td><b>{e(g['project'])}</b></td><td>{e(g['status'])}</td><td>{e(g['timeline'])}</td><td>{e(g['areas'])}</td></tr>"
                        for g in pipe[:7]) + "</tbody></table>") if pipe else ""
    tcol = {"villa": "#7b3fa0", "plot": "#1baf7a", "apartment": "#2a78d6", "mixed": "#eb6834", "commercial": "#546e7a"}
    launches = "".join(f'<div class="lcard"><span class="lchip" style="background:{tcol.get(l["type"], "#546e7a")}">{e(l["type"].upper())}</span>'
                       f'<h4>{e(l["headline"])}</h4><p class="lmeta">{e(l["developer"])} · {e(l["area"])}</p><p>{e(l["text"])}</p></div>'
                       for l in paper.get("launches", []))
    p4 = (f'<div class="sect">PROJECTS, LAUNCHES &amp; DEVELOPMENT</div><h1 class="feat2">What is being built</h1>'
          + (f'<h3 class="sub">New launches · villas, plots &amp; apartments</h3><div class="lgrid">{launches}</div>'
             if launches else '<h3 class="sub">New launches</h3><p>No new villa, plot or apartment launches were reported in this window.</p>')
          + '<h3 class="sub">City development</h3><div class="cols2">'
          + ("".join(f'<div class="story"><h4>{e(s["headline"])}</h4><p>{e(s["text"])}</p></div>' for s in paper["development_stories"]) or "<p>No new development announcements.</p>")
          + f'</div>{ptable}')
    zname = {"east": "EAST", "north": "NORTH", "south": "SOUTH", "west": "WEST", "outer": "BEYOND THE CITY"}
    zcol = {"east": "#2a78d6", "north": "#eb6834", "south": "#1baf7a", "west": "#eda100", "outer": "#4a3aa7"}
    zones = "".join(f'<div class="zoneblk"><div class="sect" style="color:{zcol[z["zone"]]}">{zname[z["zone"]]} BENGALURU</div>'
                    + "".join(f'<div class="story"><h4>{e(i["headline"])}</h4><p>{e(i["text"])}</p></div>' for i in z["items"][:3]) + "</div>"
                    for z in paper["around"])
    towns = issue.get("growth_towns", [])[:6]
    tcards = "".join(f'<div class="town">{skyline("dt" + t["name"], 300, 60, metro=False)}<h4>{e(t["name"])}</h4><p>{e(t["why"])}</p></div>' for t in towns)
    watch = "".join(f'<li><b>{e(x["item"])}</b> — {e(x["why"])}</li>' for x in paper["watch"])
    cited = {i for blk in _blocks(paper) for i in blk.get("ids", [])}
    srcs = paper.get("_sources", {})
    pubs = sorted({srcs[i]["publisher"] for i in cited if i in srcs and srcs[i]["publisher"]})
    col = paper.get("investment_column") or {}
    column = (f'<div class="icol"><div class="icol-k">INVESTMENT COLUMN</div><h2>{e(col.get("headline", ""))}</h2>{paras(col.get("paragraphs", []))}'
              f'<p class="icol-d">Considerations, not investment advice. Check approvals, title and RERA registration before buying.</p></div>'
              if col.get("paragraphs") else "")
    gov = "".join(f'<div class="story"><h4>{e(s["headline"])}</h4><p>{e(s["text"])}</p></div>' for s in paper["government_stories"][:6])
    p5 = (f'<div class="sect">GOVERNMENT, GROWTH AREAS &amp; AROUND BENGALURU</div><h1 class="feat2">Decisions, growth areas and the city</h1>'
          f'<div class="two"><div><h3 class="sub">Government &amp; policy</h3>{gov or "<p>No new government decisions.</p>"}</div><div>{column}</div></div>'
          f'<h3 class="sub">Around Bengaluru</h3><div class="zgrid">{zones or "<p>No area news in this window.</p>"}</div>'
          
          + (f'<h3 class="sub">What to watch next</h3><ul class="watch cols2">{watch}</ul>' if watch else "")
          + f'<div class="sources"><b>Sources for this edition</b> (news from {e(w["start"][:16].replace("T", " "))} to {e(w["end"][:16].replace("T", " "))} IST): '
          + e(", ".join(pubs)) + ". News is attributed to the organisations that published it; plans and dates are as announced and can change. "
            "Information only, not investment advice.</div>")
    labels = ["", "Top stories", "Metro & Transport", "Projects & Development", "Government, Growth & Around"]
    body = ""
    for n, (pg, lab) in enumerate(zip([p1, p2, p3, p4, p5], labels), 1):
        folio = "" if n == 1 else (f'<div class="folio"><span>{DELTA_NAME} · {e(date)}</span><span>{e(lab)}</span><span>{n}</span></div>')
        body += f'<section class="mp{" cover" if n == 1 else ""}">{pg}{folio}</section>'
    extra = """
.ckick { font: 800 12px "Helvetica Neue", Arial, sans-serif; letter-spacing: 2px; color: #ffcf5a; margin: 7mm 14mm 0; }
.cover .chead { margin-top: 2mm; }
.mtitle b { font-size: 36px; }
.briefs3 { display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 5mm; }
.brief h4, .story h4, .mcard h4, .town h4 { font: 800 calc(13.5px * var(--k))/1.2 Georgia, serif; color: #0d366b; margin: 0 0 3px; }
.brief { border-top: 3px solid #e34948; padding-top: 4px; } .brief p, .story p, .mcard p, .town p { text-align: left; }
.story { border-bottom: 1px solid #e3e2dc; padding-bottom: 5px; margin-bottom: 6px; }
.mapbox svg { width: 100%; height: auto; aspect-ratio: 620 / 640; border: 1px solid #d9d8d2; border-radius: 6px; }
.metro-svg .ms { font: 600 8px Arial, sans-serif; fill: #1b2430; paint-order: stroke; stroke: #f7f9fc; stroke-width: 3px; }
.board { font: calc(8.8px * var(--k))/1.3 "Helvetica Neue", Arial, sans-serif; }
.board td { padding: 3px 4px; } .board small { color: #6b6a66; } .ldot { display: inline-block; width: 11px; height: 11px; border-radius: 50%; }
.st-operational { color: #13693b; } .st-under { color: #8a5300; } .st-approved { color: #1c4f9c; } .st-proposed { color: #9b1c1c; }
.mcards { display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 4mm; margin-top: 6px; }
.mcard { background: #f4f8fd; border-top: 3px solid #0d366b; padding: 6px 8px; }
.lchip { display: inline-block; font: 800 8.5px Arial, sans-serif; color: #fff; padding: 1px 6px; border-radius: 8px; margin-bottom: 3px; }
.zgrid { display: grid; grid-template-columns: 1fr 1fr; gap: 2mm 7mm; }
.zoneblk .sect { margin-top: 4px; }
.towns { grid-template-columns: repeat(3, 1fr); gap: 4mm; } .town h4 { margin: 4px 8px 2px; } .town p { margin: 0 8px 6px; }
.two { gap: 6mm; }
.lgrid { display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 4mm; margin-bottom: 6px; }
.lcard { border: 1px solid #d9d8d2; border-top: 3px solid #0d366b; padding: 6px 8px; background: #fcfcfb; }
.lcard h4 { font: 800 calc(13px * var(--k))/1.2 Georgia, serif; color: #0d366b; margin: 2px 0; } .lcard p { text-align: left; margin: 0 0 3px; }
.lmeta { font: 700 calc(9px * var(--k)) Arial, sans-serif; color: #52514e; }
.icol { background: #fdf6e3; border-left: 4px solid #eda100; padding: 8px 12px; }
.icol-k { font: 800 10px Arial, sans-serif; letter-spacing: 2px; color: #8a5300; }
.icol h2 { font: 800 calc(18px * var(--k))/1.15 Georgia, serif; color: #0d366b; margin: 3px 0 6px; }
.icol p { text-align: left; } .icol-d { font: italic calc(8.5px * var(--k)) Arial, sans-serif; color: #6b6a66; }
.mgrid { grid-template-columns: 84mm 1fr; align-items: start; }
"""
    from harness.magazine_render import FIT_JS
    return (f"<!doctype html><html lang='en'><head><meta charset='utf-8'><title>{DELTA_NAME} — {e(short)}</title>"
            f"<style>{MAG_CSS}{extra}:root{{--k:1}}</style></head><body>{body}{FIT_JS.replace('? 1.0 : 1.32', '? 1.0 : 1.25')}</body></html>")


def render_delta(edition: str, paper: dict, meta: dict, out_pdf: Path, html_pdf) -> tuple[int, str | None]:
    from harness.magazine_render import fit_report
    from harness.pdf_edition import count_pages
    page = out_pdf.with_suffix(".delta.html")
    write_text(page, build_delta_html(paper, meta))
    err = html_pdf(page, out_pdf)
    if err:
        return 0, err
    n = count_pages(out_pdf)
    clipped = [i + 1 for i, f in enumerate(fit_report(page)) if f["overflow"]]
    return n, (None if n == PAGES and not clipped else f"delta layout: {n} pages, clipped {clipped}")
