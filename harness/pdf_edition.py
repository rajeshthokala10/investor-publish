"""Five-page PDF edition: infographic cover + four condensed pages, from the same validated dataset.

Page 1  infographic cover
Page 2  Today's brief · East Bengaluru deep dive
Page 3  North/South/West · Plots vs villas vs apartments · Government moves
Page 4  Growth scenarios · Opportunities · Risks, contradictions and unverified claims
Page 5  What changed · Sources and coverage gaps · Method

Row limits keep each section on its page; the renderer then verifies the page count and
shrinks the type scale if needed. The full detail stays in the HTML/Markdown/JSON report.
"""
from __future__ import annotations

import html
import re
from collections import Counter
from pathlib import Path

from harness.common import PROCESSED, load_config, read_json, write_text
from harness.registry import corridors
from validation.verification import USABLE

PAGES = 5
SCALES = [1.0, 0.92, 0.85, 0.78, 0.72]


def e(s) -> str:
    return html.escape(str(s if s is not None else "Not verified"))


def short(s: str, n: int) -> str:
    s = s or ""
    return s if len(s) <= n else s[: n - 1].rsplit(" ", 1)[0] + "…"


def table(head: list[str], rows: list[list[str]], cls: str = "") -> str:
    if not rows:
        return ""
    th = "".join(f"<th>{h}</th>" for h in head)
    body = "".join("<tr>" + "".join(f"<td>{c}</td>" for c in r) + "</tr>" for r in rows)
    return f'<table class="t {cls}"><thead><tr>{th}</tr></thead><tbody>{body}</tbody></table>'


def src(c) -> str:
    return f'<a href="{e(c["url"])}">{e(c["publisher"])}</a>'


def badge(status: str) -> str:
    from harness.infographic import _badge
    return _badge(status)


def page(title: str, num: int, body: str, meta: dict) -> str:
    return (f'<section class="pg"><header class="ph"><span>Bengaluru Real Estate Intelligence · {meta["edition"]}</span>'
            f'<span>Page {num} of {PAGES}</span></header><h2 class="pt">{title}</h2>{body}'
            f'<footer class="pf">Window {meta["window"]["start"][:16].replace("T", " ")} → {meta["window"]["end"][:16].replace("T", " ")} IST · '
            f'Run status: {e(meta["status"])} · Research, not investment advice · Full report: reports/daily/{meta["edition"]}.html</footer></section>')


def build_pages(d: dict, meta: dict) -> str:
    from harness.report import brief_items, cor_name, fresh_claims, standalone
    fresh = fresh_claims(d)
    usable = [c for c in fresh if c["verification_status"] in USABLE]
    projects = read_json(PROCESSED / "projects.json", {})
    sc = load_config("scoring")

    # ---------------- page 2 -----------------------------------------------------------
    brief = brief_items(d, 5)
    if meta["status"] == "failed":
        b = "<p><b>Research failed.</b> No sources could be collected; absence of items says nothing about the market.</p>"
    elif not brief:
        b = "<p>No new verified, material change was found in the window.</p>"
    else:
        b = "<ul class='brief'>" + "".join(
            f"<li><b>{e(short(standalone(c), 220))}</b> — {e(cor_name(c['corridor']))}. {badge(c['verification_status'])} "
            f"{c['confidence']} confidence · {src(c)} <code>{c['claim_id']}</code></li>" for c in brief) + "</ul>"
    rows = []
    for cid, cor in corridors().items():
        if cor["region"] != "east":
            continue
        cu = [c for c in usable if c["corridor"] == cid]
        weak = sum(1 for c in fresh if c["corridor"] == cid and c["verification_status"] not in USABLE)
        pj = [p for p in projects.values() if p["corridor"] == cid and p["project_id"] in d["projects_today"]]
        top = (f"{e(short(cu[0]['statement'], 120))} ({src(cu[0])})" if cu else "No usable update in the window")
        rows.append([f"<b>{e(cor['name'].split('(')[0].strip())}</b>", top, str(len(cu)), str(weak),
                     e(", ".join(short(p["name"], 30) for p in pj)) or "—"])
    east = table(["Corridor", "Most consequential usable item", "Usable", "Unverified", "Projects seen"], rows)
    pj_rows = []
    for p in projects.values():
        if p["project_id"] in d["projects_today"]:
            obs = p["price_observations"]
            price = "; ".join(f"{o['value']:g} {o['unit'] or ''}".strip() + (f" ≈₹{o['psf_inr']:,.0f}/sqft {o['basis']}" if o["psf_inr"] and o["psf_inr"] != o["value"] else "")
                              for o in obs[:2]) or "Not verified"
            pj_rows.append([f'<a href="{e(p["sources"][0]["url"])}">{e(short(p["name"], 40))}</a>', e(p["developer"]),
                            e(cor_name(p["corridor"]).split("(")[0]), e(p["property_type"]), e(p["status"]),
                            e(p["rera"]["number"]) if p["rera"]["number"] else "Not verified", e(short(price, 60)), p["confidence"]])
    p2 = (f"<h3>1. Today’s Bengaluru Property Brief</h3>{b}<h3>2. East Bengaluru Deep Dive</h3>{east}"
          + (f"<h4>Project tracker — seen in this edition</h4>"
             + table(["Project", "Developer", "Corridor", "Type", "Status", "RERA", "Quoted price", "Conf."], pj_rows[:8])
             if pj_rows else "")
          + "<p class='note'>Unverified and interested-party claims are counted but not used as evidence; they are listed on page 4.</p>")

    # ---------------- page 3 -----------------------------------------------------------
    nsw = ""
    for reg in ("north", "south", "west", "peripheral"):
        name = load_config("corridors")["regions"][reg]["name"]
        good = [c for c in usable if c["region"] == reg]
        weak = sum(1 for c in fresh if c["region"] == reg and c["verification_status"] not in USABLE)
        items = "".join(f"<li>{e(short(c['statement'], 150))} — {src(c)} {badge(c['verification_status'])}</li>" for c in good[:3])
        nsw += (f"<p class='reg'><b>{name}:</b> {len(good)} usable, {weak} unverified.</p>"
                + (f"<ul>{items}</ul>" if items else ""))
    cells = {(c["corridor"], c["property_type"]): c for c in d["model"]["cells"]}
    mrows = []
    for cid, cor in sorted(corridors().items(), key=lambda kv: (kv[1]["region"] != "east", kv[1]["region"], kv[0])):
        if cor["region"] == "peripheral":
            continue
        cellv = []
        for pt in ("plot", "villa", "apartment"):
            c = cells[(cid, pt)]
            cellv.append(f"<b>{c['attractiveness']:.1f}</b> · {c['confidence']}" if c["attractiveness"] is not None
                         else f"Unranked ({len(c['factors'])}/6)")
        mrows.append([e(cor["name"].split("(")[0].strip()), cor["region"].title(), *cellv])
    gov = [c for c in fresh if c["claim_type"] in ("infrastructure", "policy", "legal")]
    grows = [[e(short(c["statement"], 130)), (c.get("evidenced_stage") or "—").replace("_", " ").title(),
              f"{c['published_at'] or 'undated'} / {c['event_date'] or 'n/s'}", badge(c["verification_status"]), src(c)]
             for c in gov[:6]]
    p3 = (f"<h3>3. North, South and West Bengaluru</h3>{nsw}"
          f"<h3>4. Plots vs Villas vs High-Rise Apartments</h3>"
          f"<p class='note'>Score 1–5 only where ≥{sc['min_factors_for_rank']} of 6 factors are evidenced; land rates (plots) are never compared with saleable rates (apartments).</p>"
          + table(["Corridor", "Region", "Plots", "Villas", "Apartments"], mrows, "dense")
          + "<h3>5. Government Moves in the Last 72 Hours</h3>"
          + (table(["Development", "Stage (evidenced)", "Published / event", "Status", "Source"], grows)
             or "<p>No government or infrastructure development published in the window was captured.</p>")
          + (f"<p class='note'>{len(gov) - 6} more in the full report.</p>" if len(gov) > 6 else ""))

    # ---------------- page 4 -----------------------------------------------------------
    est = [c for c in d["model"]["cells"] if c["scenarios"]["status"] == "estimated"]
    if est:
        srows = []
        for c in est[:4]:
            for name, r in c["scenarios"]["scenarios"].items():
                cp = r["cumulative_pct"]
                srows.append([f"{e(cor_name(c['corridor']).split('(')[0])} · {c['property_type']}", name.title(), f"{r['annual_pct']}%",
                              f"{r['real_annual_pct']}%", f"+{cp['3']}%", f"+{cp['5']}%", f"+{cp['10']}%"])
        scen = table(["Corridor · type", "Scenario", "Nominal p.a.", "Real p.a.", "3 yr", "5 yr", "10 yr"], srows) + \
            f"<p class='note'>{e(est[0]['scenarios']['assumptions'])}</p>"
    else:
        scen = (f"<p><b>Insufficient evidence to estimate</b> for every corridor and property type: no cell has appreciation evidence "
                f"from ≥{sc['scenarios']['min_appreciation_sources']} independent original sources (media relaying the same research "
                f"house count once). Formula when estimable: FV = P × (1 + g)<sup>years</sup>; base = {sc['scenarios']['base_haircut']} × "
                f"historical median CAGR, capped at {sc['scenarios']['cap_pct']}%, real after {sc['scenarios']['inflation_pct']}% inflation.</p>")
    ranked = sorted((c for c in d["model"]["cells"] if c["attractiveness"] is not None), key=lambda c: c["rank"])
    opp = ("<ol>" + "".join(f"<li><b>{e(cor_name(c['corridor']))} — {c['property_type']}</b>: {c['attractiveness']:.1f}/5, "
                            f"confidence {c['confidence']}</li>" for c in ranked[:5]) + "</ol>") if ranked else \
        (f"<p>No corridor/property type met the evidence threshold (≥{sc['min_factors_for_rank']} evidenced factors). "
         "Nothing is ranked rather than ranking on thin data.</p>")
    contra = "".join(f"<li><b>{e(x['subject'])}</b> ({e(x['metric'])}): {e(x.get('resolution'))}</li>" for x in d.get("contradictions", [])[:4])
    weak = [c for c in fresh if c["verification_status"] in ("unverified", "interested_party_claim", "contradicted")]
    wrows = [[e(short(c["statement"], 115)), badge(c["verification_status"]), e(short(c["confidence_reason"], 70)), src(c)] for c in weak[:9]]
    stale = [c for c in d["claims"] if "republished_old_event" in c["flags"]]
    p4 = (f"<h3>6. Growth Scenarios</h3>{scen}<h3>7. Opportunities to Investigate</h3>{opp}"
          f"<h3>8. Risks, Contradictions and Unverified Claims</h3>"
          + (f"<p><b>Unresolved contradictions</b></p><ul>{contra}</ul>" if contra else "")
          + (table(["Claim (not established fact)", "Status", "Why", "Source"], wrows) if wrows else "<p>None in this edition.</p>")
          + (f"<p class='note'>{len(weak) - 9} more unverified/interested-party claims in the full report.</p>" if len(weak) > 9 else "")
          + (f"<p class='note'>{len(stale)} item(s) were old news republished with new dates and were not counted as new.</p>" if stale else ""))

    # ---------------- page 5 -----------------------------------------------------------
    changes = "".join(f"<li>{e(x.lstrip('- '))}</li>" for x in meta["changes"][:8])
    cov = "".join(f"<li>Research task <code>{t}</code>: {'ok' if v['ok'] else 'FAILED — ' + e(v['error'])}</li>"
                  for t, v in d["coverage"].items())
    rec = d.get("recheck", {})
    stats = (f"<li>RSS feeds collected {len(d['feeds']['ok'])}, failed {len(d['feeds']['failed'])}; "
             f"{len(d['stories'])} distinct stories after de-duplication</li>"
             f"<li>Claims {len(d['claims'])}: " + ", ".join(f"{k.replace('_', ' ')} {v}" for k, v in Counter(c['verification_status'] for c in d['claims']).most_common()) + "</li>"
             f"<li>Independent recheck: {rec.get('reviewed', 0)} of {rec.get('targets', 0)} consequential claims reviewed, "
             f"{len(rec.get('downgraded', []))} downgraded; links checked {rec.get('links_checked', 0)}</li>")
    unavailable = "".join(f"<li>{e(u['source'])}: {e(short(u['reason'], 110))}</li>" for u in load_config("sources")["known_unavailable"][:8])
    cited = sorted((c for c in d["claims"] if c["verification_status"] in USABLE), key=lambda c: c["claim_id"])[:12]
    crow = [[f"<code>{c['claim_id']}</code>", src(c), c["tier"].replace("_", " "), c["published_at"] or "undated",
             (c.get("citation_check") or {}).get("result", "not checked")] for c in cited]
    p5 = (f"<h3>9. What Changed Since Yesterday</h3><ul>{changes}</ul>"
          f"<h3>10. Sources and Coverage Gaps</h3><ul>{stats}{cov}</ul>"
          f"<h4>Not accessed / unavailable</h4><ul class='small'>{unavailable}</ul>"
          f"<h4>Usable evidence cited (first 12)</h4>" + table(["Claim", "Publisher", "Tier", "Published", "Citation check"], crow, "dense")
          + "<p class='note'>Method: claims carry URL, verbatim excerpt, publication/event dates and retrieval time; statuses are set by code "
            "(official → verified; ≥2 independent original sources → corroborated; one reputable source → single source; developers, "
            "brokers, portals, consultancies and influencers → interested party). Guarantee language, failed citation checks and failed "
            "or split independent reviews force ‘unverified’.</p>")
    return "".join(page(t, n, b, meta) for n, (t, b) in enumerate([
        ("Brief and East Bengaluru", p2), ("Regions, property types and government", p3),
        ("Scenarios, opportunities and risks", p4), ("Changes, sources and coverage", p5)], start=2))


PDF_CSS = """
.pg { break-before: page; page: a4; font-size: calc(10.5px * var(--k)); line-height: 1.38; color: #0b0b0b; }
@page a4 { size: A4; margin: 11mm 12mm; }
.ph, .pf { display: flex; justify-content: space-between; font-size: 9px; color: #52514e; }
.ph { border-bottom: 2px solid #0d366b; padding-bottom: 3px; margin-bottom: 6px; }
.pf { border-top: 1px solid #d9d8d2; padding-top: 3px; margin-top: 8px; display: block; }
.pt { font: 800 calc(20px * var(--k))/1.15 Georgia, serif; color: #0d366b; margin: 4px 0 6px; }
.pg h3 { font-size: calc(13px * var(--k)); background: #0d366b; color: #fff; padding: 4px 8px; margin: 10px 0 6px; text-transform: uppercase; letter-spacing: .4px; }
.pg h4 { font-size: calc(11.5px * var(--k)); margin: 8px 0 4px; color: #0d366b; }
.pg ul, .pg ol { margin: 4px 0 6px 18px; padding: 0; } .pg li { margin: 2px 0; }
.pg .brief li { margin-bottom: 5px; }
.pg p { margin: 4px 0; } .pg .note { color: #52514e; font-size: calc(9.5px * var(--k)); }
.pg .reg { margin: 6px 0 2px; } .pg .small { font-size: calc(9.5px * var(--k)); }
.pg code { font-size: .85em; background: #f0efec; padding: 0 3px; border-radius: 2px; }
.pg a { color: #1c5cab; text-decoration: none; }
.t { width: 100%; border-collapse: collapse; margin: 4px 0 6px; font-size: calc(9.5px * var(--k)); }
.t th { background: #eef5fe; color: #0d366b; text-align: left; padding: 3px 5px; border-bottom: 1.5px solid #0d366b; }
.t td { padding: 3px 5px; border-bottom: 1px solid #e7e6e1; vertical-align: top; }
.t.dense td, .t.dense th { padding: 2px 5px; }
.t tr { break-inside: avoid; }
"""


def count_pages(pdf: Path) -> int:
    data = pdf.read_bytes()
    return len(re.findall(rb"/Type\s*/Page(?!s)", data))


def render_pdf(d: dict, meta: dict, info_html: str, css: str, out_pdf: Path, html_pdf) -> tuple[int, str | None]:
    """Render, verify exactly PAGES pages, shrinking the type scale if a section overflows."""
    pages = build_pages(d, meta)
    tmp = out_pdf.with_suffix(".print.html")
    last = (0, None)
    for k in SCALES:
        doc = (f"<!doctype html><html lang='en'><head><meta charset='utf-8'><title>Bengaluru REI {meta['edition']}</title>"
               f"<style>{css}{PDF_CSS}:root{{--k:{k}}}</style></head><body>{info_html}{pages}</body></html>")
        write_text(tmp, doc)
        err = html_pdf(tmp, out_pdf)
        if err:
            return 0, err
        n = count_pages(out_pdf)
        last = (n, None if n == PAGES else f"PDF has {n} pages at scale {k}")
        if n <= PAGES:
            break
    tmp.unlink(missing_ok=True)
    return last
