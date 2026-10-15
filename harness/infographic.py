"""Infographic cover page (newspaper-style, after the user's reference template).

Layout: bold headline + subtitle -> skyline hero with corridor pins + two KPI tiles ->
bar chart / highlights / growth drivers -> price or evidence chart / type matrix /
outlook -> corridor card strip -> source footer.

Every number on this page comes from the validated dataset of the edition, with
its verification status. Illustrations are generated SVG (no stock photography).
When evidence is thin, tiles fall back to honest counts rather than market claims.
"""
from __future__ import annotations

import html
import random
import re
from collections import Counter

from harness.registry import corridors
from validation.verification import USABLE

REGION_COLOR = {"east": "#2a78d6", "north": "#eb6834", "south": "#1baf7a", "west": "#eda100",
                "peripheral": "#4a3aa7", "unmapped": "#8a8984"}
REGION_LABEL = {"east": "East", "north": "North", "south": "South", "west": "West", "peripheral": "Peripheral",
                "unmapped": "Unmapped"}
BADGE = {"verified_primary": ("✓", "Official", "good"), "corroborated": ("✓", "Corroborated", "good"),
         "single_source": ("◑", "Single source", "warn"), "interested_party_claim": ("!", "Interested party", "serious"),
         "unverified": ("✕", "Unverified", "critical"), "contradicted": ("!", "Contradicted", "critical")}
METRIC_LABEL = {"units_sold": "units sold", "units_launched": "units launched", "price_psf": "per sq ft",
                "appreciation_pct": "price appreciation", "cagr_pct": "annual growth (CAGR)",
                "rental_yield_pct": "rental yield", "jobs": "jobs", "investment_inr": "investment",
                "unsold_inventory": "unsold units", "price_total": "quoted price"}

ICONS = {
    "building": '<path d="M8 40V10h16v30M24 40V18h12v22M4 40h36M12 15h3M17 15h3M12 21h3M17 21h3M12 27h3M17 27h3M28 23h4M28 29h4"/>',
    "crane": '<path d="M10 40V6M10 6h26M10 12l8-6M30 6v10M27 16h6v6h-6zM4 40h16M18 40V26h14v14"/>',
    "metro": '<rect x="9" y="6" width="26" height="26" rx="5"/><path d="M9 20h26M15 27h.01M29 27h.01M14 32l-4 7M30 32l4 7"/>',
    "road": '<path d="M16 40 20 6M28 6l4 34M24 10v4M24 20v4M24 30v4"/>',
    "water": '<path d="M22 6c7 10 11 16 11 21a11 11 0 0 1-22 0c0-5 4-11 11-21z"/>',
    "plane": '<path d="M6 26 40 12l-6 16-10-3-6 9-1-11z"/>',
    "briefcase": '<rect x="6" y="14" width="32" height="22" rx="3"/><path d="M16 14V9h12v5M6 24h32"/>',
    "alert": '<path d="M22 6 40 38H4z"/><path d="M22 18v9M22 32h.01"/>',
    "check": '<path d="M8 23l9 9 19-19"/>',
    "gavel": '<path d="M14 12l12 12M20 6l12 12M10 16l12-12M8 38h20M24 22 38 36"/>',
    "chart": '<path d="M6 38h32M10 32V22M18 32V16M26 32V20M34 32V10"/>',
}


def icon(name: str, cls: str = "ico") -> str:
    return (f'<svg class="{cls}" viewBox="0 0 44 44" fill="none" stroke="currentColor" stroke-width="2.4" '
            f'stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">{ICONS[name]}</svg>')


def e(s) -> str:
    return html.escape(str(s if s is not None else ""))


def skyline(seed: str, w: int = 760, h: int = 230, pins: list[str] = (), metro: bool = True) -> str:
    """Deterministic generated skyline illustration with optional corridor pins and metro viaduct."""
    rnd = random.Random(seed)
    seed = re.sub(r"\W", "", seed)          # used in an SVG id: spaces/parentheses break url(#…)
    parts = [f'<svg viewBox="0 0 {w} {h}" class="sky" role="img" aria-label="Illustrative skyline">',
             f'<defs><linearGradient id="g{seed}" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#cde2fb"/>'
             f'<stop offset="1" stop-color="#f4f8fd"/></linearGradient></defs>',
             f'<rect width="{w}" height="{h}" fill="url(#g{seed})"/>',
             f'<path d="M0 {h*.62} Q{w*.3} {h*.52} {w*.6} {h*.6} T{w} {h*.56} V{h} H0z" fill="#b7d3f6" opacity=".6"/>']
    x = 0
    base = h * 0.80
    while x < w:
        bw = rnd.randint(int(w * .025), int(w * .06))
        bh = rnd.randint(int(h * .18), int(h * .62))
        tone = rnd.choice(["#184f95", "#256abf", "#2a78d6", "#5598e7", "#104281", "#86b6ef"])
        parts.append(f'<rect x="{x}" y="{base-bh:.0f}" width="{bw}" height="{bh}" fill="{tone}" rx="1.5"/>')
        for wy in range(int(base - bh + 6), int(base - 4), 9):
            for wx in range(x + 3, x + bw - 3, 6):
                if rnd.random() < .55:
                    parts.append(f'<rect x="{wx}" y="{wy}" width="2.5" height="4" fill="#e8f1fc" opacity=".75"/>')
        x += bw + rnd.randint(2, 8)
    # trees
    for tx in range(6, w, 23):
        r = rnd.randint(5, 9)
        parts.append(f'<circle cx="{tx}" cy="{base+2}" r="{r}" fill="#1baf7a" opacity=".85"/>')
    parts.append(f'<rect y="{base+6}" width="{w}" height="{h-base}" fill="#e7ecef"/>')
    if metro:
        vy = base - 10
        parts.append(f'<path d="M0 {vy+30} C{w*.3} {vy+6}, {w*.6} {vy-4}, {w} {vy-16}" stroke="#9aa3ab" stroke-width="9" fill="none"/>')
        for px in range(30, w, 70):
            t = px / w
            py = (1 - t) ** 3 * (vy + 30) + 3 * (1 - t) ** 2 * t * (vy + 6) + 3 * (1 - t) * t * t * (vy - 4) + t ** 3 * (vy - 16)
            parts.append(f'<rect x="{px-3}" y="{py+4:.0f}" width="6" height="{base+6-py-4:.0f}" fill="#b9c0c6"/>')
        parts.append(f'<rect x="{w*.18:.0f}" y="{vy+8:.0f}" width="{w*.16:.0f}" height="9" rx="4" fill="#4a3aa7" '
                     f'transform="rotate(-3 {w*.26:.0f} {vy+12:.0f})"/>')
    n = len(pins)
    for i, name in enumerate(pins):
        px = w * (i + 0.6) / (n + 0.2)
        py = 26 + (i % 2) * 34
        parts.append(f'<g><path d="M{px:.0f} {py+30} l-7 -12 a8 8 0 1 1 14 0z" fill="#0d366b"/>'
                     f'<circle cx="{px:.0f}" cy="{py+15}" r="3" fill="#fff"/>'
                     f'<rect x="{px+9:.0f}" y="{py+5}" width="{len(name)*6.4+10:.0f}" height="17" rx="3" fill="#fff" opacity=".92"/>'
                     f'<text x="{px+14:.0f}" y="{py+17}" font-size="11" font-weight="600" fill="#0b0b0b">{e(name)}</text></g>')
    parts.append("</svg>")
    return "".join(parts)


def bar_chart(rows: list[tuple[str, float, str, str]], unit: str, w: int = 520, h: int = 250) -> str:
    """rows: (label, value, region, tooltip). Single measure, colored by region (identity), direct labels."""
    if not rows:
        return '<p class="empty">No evidence to chart in this edition.</p>'
    top = max(v for _, v, _, _ in rows) or 1
    n = len(rows)
    pad_l, pad_b, pad_t = 8, 58, 26
    slot = (w - pad_l * 2) / n
    bw = min(46, slot - 2)
    out = [f'<svg viewBox="0 0 {w} {h}" class="chart" role="img" aria-label="Bar chart">',
           f'<line x1="0" x2="{w}" y1="{h-pad_b}" y2="{h-pad_b}" stroke="#c3c2b7" stroke-width="1"/>']
    for i, (label, v, reg, tip) in enumerate(rows):
        bh = (h - pad_b - pad_t) * v / top
        x = pad_l + i * slot + (slot - bw) / 2
        y = h - pad_b - bh
        col = REGION_COLOR.get(reg, "#8a8984")
        out.append(f'<g class="bar"><title>{e(tip)}</title>'
                   f'<path d="M{x:.1f} {h-pad_b} V{y+4:.1f} q0 -4 4 -4 h{bw-8:.1f} q4 0 4 4 V{h-pad_b}z" fill="{col}"/>'
                   f'<rect x="{x-1:.1f}" y="{pad_t-20}" width="{bw+2:.1f}" height="{h-pad_t:.0f}" fill="transparent"/>'
                   f'<text x="{x+bw/2:.1f}" y="{y-6:.1f}" text-anchor="middle" class="val">{v:g}{unit}</text>')
        words = label.split()
        lines, cur = [], ""
        for wd in words:
            if len(cur) + len(wd) > 12 and cur:
                lines.append(cur)
                cur = wd
            else:
                cur = (cur + " " + wd).strip()
        lines.append(cur)
        for j, ln in enumerate(lines[:3]):
            out.append(f'<text x="{x+bw/2:.1f}" y="{h-pad_b+15+j*12}" text-anchor="middle" class="lbl">{e(ln)}</text>')
        out.append("</g>")
    out.append("</svg>")
    regs = sorted({r for _, _, r, _ in rows}, key=list(REGION_COLOR).index)
    if len(regs) > 1:
        out.append('<div class="legend">' + "".join(
            f'<span><i style="background:{REGION_COLOR[r]}"></i>{REGION_LABEL[r]}</span>' for r in regs) + "</div>")
    return "".join(out)


def _badge(status: str) -> str:
    sym, lab, cls = BADGE.get(status, ("?", status, "warn"))
    return f'<span class="badge {cls}">{sym} {lab}</span>'


def _fmt(v, metric, unit) -> str:
    u = (unit or "").lower()
    if metric.endswith("_pct") or "%" in u:
        return f"{v:g}%"
    if metric == "price_psf":
        return f"₹{v:,.0f}"
    if "crore" in u:
        return f"₹{v:g} cr"
    if v >= 1000:
        return f"{v:,.0f}"
    return f"{v:g}"


def _tile_value(c) -> str:
    """Per-area prices are always shown in normalised Rs/sq ft (never the raw sq yd/acre number)."""
    if c["metric"] == "price_psf" and c.get("psf_inr"):
        return f"₹{c['psf_inr']:,.0f}"
    return _fmt(c["value"], c["metric"], c["unit"])


def _tile_caption(c) -> str:
    cap = METRIC_LABEL[c["metric"]]
    if c["metric"] == "price_psf":
        cap += f" · {c['price_basis'].replace('_', ' ')} basis · {c['price_kind'].replace('_', ' ')}"
        if c.get("unit") and c.get("psf_inr") and c["value"] != c["psf_inr"]:
            cap += f" (quoted {c['value']:,.0f} {c['unit']})"
    if c["metric"] == "appreciation_pct":
        cap += f" over {c['period_years']:g} yrs" if c.get("period_years") else " (period not stated)"
    return cap


ANAPHORA = re.compile(r"^(the same|this|that|these|those|it|they|also|separately|meanwhile|another)\b", re.I)


def _short(s: str, n: int) -> str:
    return s if len(s) <= n else s[: n - 1].rsplit(" ", 1)[0] + "…"


def render_infographic(d: dict, meta: dict) -> str:
    from harness.report import brief_items, cor_name, fresh_claims
    claims = d["claims"]
    fresh = fresh_claims(d)
    usable = [c for c in fresh if c["verification_status"] in USABLE]
    brief = brief_items(d, 4)

    # headline -------------------------------------------------------------------------------
    if meta["status"] == "failed":
        head, sub = "Research failed today", "No sources could be collected. This is not a 'no news' day."
    elif brief:
        stmt = brief[0]["statement"]
        # statements that lean on context ("The same notice says…") are headed by their subject instead
        head = _short(brief[0]["subject"] if ANAPHORA.match(stmt) else stmt, 95)
        sub = (f"{len(usable)} usable (verified, corroborated or single-source) updates in the 72 hours to {meta['window']['end'][:16].replace('T', ' ')} IST · "
               f"{_badge(brief[0]['verification_status'])} lead item from {e(brief[0]['publisher'])}")
    else:
        head, sub = "No verified market-moving change today", "The window was searched; leads that could not be verified are listed in the report."
    head_html = re.sub(r"(₹\s?\d[\d,.]*(?:\s?(?:crore|cr|lakh))?|\b\d[\d,.]*\s?%|\b\d[\d,.]*\s(?:crore|lakh|km|units|acres?|plots|jobs)\b)",
                       r'<em>\1</em>', e(head))

    # KPI tiles ------------------------------------------------------------------------------
    numeric = [c for c in usable if c["value"] is not None and c["metric"] in METRIC_LABEL]
    numeric.sort(key=lambda c: (c["metric"] not in ("units_sold", "units_launched", "price_psf"), c["region"] != "east"))
    tiles = []
    for c, (ic, tone) in zip(numeric[:2], [("building", "blue"), ("crane", "sand")]):
        tiles.append(f'<div class="tile {tone}"><h4>{e(_short(c["subject"], 48))}</h4><div class="tile-body">{icon(ic, "big-ico")}'
                     f'<div><div class="num">{_tile_value(c)}</div>'
                     f'<div class="cap">{e(_tile_caption(c))}</div>'
                     f'<div class="src">{_badge(c["verification_status"])} {e(c["publisher"])}</div></div></div></div>')
    fallbacks = [("building", "blue", "Usable updates", len(usable), "sourced items in the 72-hour window"),
                 ("crane", "sand", "Projects tracked today", len(d.get("projects_today", [])), "launches, phases & updates")]
    for ic, tone, title, n, cap in fallbacks[len(tiles):]:
        tiles.append(f'<div class="tile {tone}"><h4>{title}</h4><div class="tile-body">{icon(ic, "big-ico")}'
                     f'<div><div class="num">{n}</div><div class="cap">{cap}</div>'
                     f'<div class="src">Edition count (system data)</div></div></div></div>')

    # chart 1: ranked attractiveness, else evidence volume by corridor --------------------------
    ranked = sorted((c for c in d["model"]["cells"] if c["attractiveness"] is not None), key=lambda c: c["rank"])
    if len(ranked) >= 3:
        rows = [(f"{cor_name(c['corridor']).split('(')[0]} {c['property_type']}", c["attractiveness"], c["region"],
                 f"{cor_name(c['corridor'])} · {c['property_type']}: {c['attractiveness']}/5, {c['confidence']} confidence")
                for c in ranked[:8]]
        chart1_title, chart1_note, unit = "Top evidence-scored opportunities", "Attractiveness 1–5 (evidence confidence shown in report)", ""
    else:
        cnt = Counter(c["corridor"] for c in usable if c["corridor"] != "unmapped")
        note = "Usable (sourced) updates by corridor, this edition"
        if not cnt:
            cnt = Counter(c["corridor"] for c in fresh if c["corridor"] != "unmapped")
            note = "All captured claims by corridor (none usable yet; mostly unverified)"
        rows = [(cor_name(k).split("(")[0].split("–")[0].strip(), v, corridors()[k]["region"],
                 f"{cor_name(k)}: {v} claim(s)") for k, v in cnt.most_common(8)]
        chart1_title, chart1_note, unit = "Where the news was", note, ""

    # highlights ------------------------------------------------------------------------------
    ic_for = {"infrastructure": "metro", "policy": "gavel", "legal": "gavel", "project_launch": "crane", "project_update": "crane",
              "price": "chart", "transaction": "chart", "employment": "briefcase", "civic_risk": "water", "supply_demand": "building"}
    highlights = "".join(
        f'<li>{icon(ic_for.get(c["claim_type"], "check"), "li-ico")}<div>{e(_short(c["statement"], 120))}'
        f'<small>{e(cor_name(c["corridor"]))} · {_badge(c["verification_status"])}</small></div></li>' for c in brief) \
        or '<li class="empty">No verified highlights in this window.</li>'

    # growth drivers: infrastructure items with an evidenced stage -------------------------------
    from harness.common import PROCESSED, read_json
    infra = read_json(PROCESSED / "infrastructure.json", {})
    staged = sorted((v for v in infra.values() if v.get("stage")),
                    key=lambda v: (-["proposed", "announced", "approved", "funded", "tendered", "awarded",
                                      "under_construction", "operational"].index(v["stage"]), v["name"]))[:5]
    di = {"metro": "metro", "rail": "metro", "road": "road", "ring": "road", "expressway": "road", "tunnel": "road",
          "water": "water", "cauvery": "water", "airport": "plane"}
    drivers = "".join(
        f'<li>{icon(next((v for k, v in di.items() if k in s["name"].lower()), "gavel"), "li-ico ring")}'
        f'<div>{e(_short(s["name"], 60))}<small>Stage: <b>{s["stage"].replace("_", " ")}</b> · '
        f'{e(", ".join(cor_name(c).split("(")[0].strip() for c in s["corridors"][:3]))}</small></div></li>' for s in staged) \
        or '<li class="empty">No infrastructure stage evidenced yet.</li>'

    # chart 2: price evidence on ONE comparability class ----------------------------------------
    price = [c for c in claims if c["verification_status"] in USABLE and c.get("psf_inr") and c["corridor"] != "unmapped"]
    classes = Counter(c["comparability"] for c in price)
    if classes:
        cls, _ = classes.most_common(1)[0]
        by = {}
        for c in price:
            if c["comparability"] == cls:
                by.setdefault(c["corridor"], []).append(c["psf_inr"])
    else:
        cls, by = None, {}
    if len(by) >= 2:
        import statistics
        prow = sorted(((cor_name(k).split("(")[0].split("–")[0].strip(), round(statistics.median(v) / 1000, 1),
                        corridors()[k]["region"], f"{cor_name(k)}: median ₹{statistics.median(v):,.0f}/sqft from {len(v)} source(s)")
                       for k, v in by.items()), key=lambda r: -r[1])[:6]
        basis, kind = cls.split("|")
        chart2 = bar_chart(prow, "k", w=430, h=220)
        chart2_title = "Price evidence (₹ ’000 / sq ft)"
        chart2_note = f"Same basis only: {basis.replace('_', ' ')}, {kind.replace('_', ' ')}. Not comparable with other bases."
    else:
        mix = Counter(c["verification_status"] for c in fresh)
        order = ["verified_primary", "corroborated", "single_source", "interested_party_claim", "unverified", "contradicted"]
        prow = [(BADGE[s][1], mix[s], "east" if s in USABLE else "unmapped", f"{BADGE[s][1]}: {mix[s]}") for s in order if mix[s]]
        chart2 = bar_chart(prow, "", w=430, h=220)
        chart2_title = "How much of today’s news checks out"
        chart2_note = "Claims by verification status (blue = usable evidence, grey = not established)."

    # type matrix (east) ---------------------------------------------------------------------
    cells = {(c["corridor"], c["property_type"]): c for c in d["model"]["cells"]}
    mrows = []
    for cid, cor in corridors().items():
        if cor["region"] != "east":
            continue
        tds = []
        for pt in ("plot", "villa", "apartment"):
            c = cells[(cid, pt)]
            tds.append(f'<td class="sc">{c["attractiveness"]:.1f}</td>' if c["attractiveness"] is not None
                       else f'<td class="un">{len(c["factors"])}/6</td>')
        mrows.append(f'<tr><th>{e(cor["name"].split("(")[0].split("&")[0].strip())}</th>{"".join(tds)}</tr>')

    # outlook --------------------------------------------------------------------------------
    est = [c for c in d["model"]["cells"] if c["scenarios"]["status"] == "estimated"]
    if est:
        outlook = "".join(f'<li>{icon("check", "li-ico ok")}<div>{e(cor_name(c["corridor"]))} {c["property_type"]}: base-case scenario '
                          f'{c["scenarios"]["scenarios"]["base"]["annual_pct"]}%/yr (range {c["scenarios"]["scenarios"]["conservative"]["annual_pct"]}–'
                          f'{c["scenarios"]["scenarios"]["optimistic"]["annual_pct"]}%)<small>Scenario, not a forecast · evidence confidence {c["confidence"]}</small></div></li>' for c in est[:4])
    else:
        outlook = (f'<li>{icon("alert", "li-ico warn")}<div><b>Insufficient evidence to estimate</b> growth scenarios today: no '
                   f'corridor has appreciation data from 2+ independent sources.</div></li>')
    risks = [c for c in fresh if c["claim_type"] in ("civic_risk", "supply_demand") and c["verification_status"] in USABLE][:2]
    outlook += "".join(f'<li>{icon("alert", "li-ico warn")}<div>Risk: {e(_short(c["statement"], 90))}</div></li>' for c in risks)
    if d.get("contradictions"):
        outlook += f'<li>{icon("alert", "li-ico warn")}<div>{len(d["contradictions"])} unresolved contradiction(s) flagged.</div></li>'

    # corridor strip ---------------------------------------------------------------------------
    cards = []
    for cid, cor in corridors().items():
        if cor["region"] != "east":
            continue
        top = next((c for c in usable if c["corridor"] == cid), None)
        weak = sum(1 for c in fresh if c["corridor"] == cid and c["verification_status"] not in USABLE)
        line = _short(top["statement"], 70) if top else (
            f"No usable update · {weak} unverified claim(s)" if weak else "No new update")
        cards.append(f'<div class="card">{skyline(cid, 240, 90, metro=False)}<b>{e(cor["name"].split("(")[0].strip())}</b>'
                     f'<span>{e(line)}</span></div>')

    pubs = Counter(c["publisher"] for c in usable)
    pins = [corridors()[k]["name"].split("(")[0].split("–")[0].split("&")[0].strip()
            for k in ("whitefield", "kr_puram_hoskote", "budigere_cross", "varthur_gunjur", "sarjapur_road")]
    return f"""
<section class="info" aria-label="Edition infographic">
  <header class="ihead">
    <h1>{head_html}</h1>
    <p class="sub">{sub}</p>
    <p class="edition">Bengaluru Real Estate Intelligence · Edition {meta['edition']} · Window {meta['window']['start'][:16].replace('T', ' ')} → {meta['window']['end'][:16].replace('T', ' ')} IST · Status: {e(meta['status'])}</p>
  </header>
  <div class="row r1">
    <div class="hero">{skyline("hero" + meta['edition'], pins=pins)}</div>
    {''.join(tiles)}
  </div>
  <div class="row r2">
    <div class="panel"><h3>{chart1_title}</h3><p class="note">{chart1_note}</p>{bar_chart(rows, unit)}</div>
    <div class="panel"><h3>Market highlights</h3><ul class="list">{highlights}</ul></div>
    <div class="panel"><h3>Key growth drivers</h3><ul class="list">{drivers}</ul></div>
  </div>
  <div class="row r3">
    <div class="panel"><h3>{chart2_title}</h3><p class="note">{chart2_note}</p>{chart2}</div>
    <div class="panel"><h3>Plots vs villas vs apartments — East</h3>
      <table class="matrix"><tr><th></th><th>Plots</th><th>Villas</th><th>Apts</th></tr>{''.join(mrows)}</table>
      <p class="note">Score 1–5 where ≥3 factors are evidenced; otherwise factors evidenced out of 6 (unranked).</p></div>
    <div class="panel red"><h3>Outlook</h3><ul class="list">{outlook}</ul></div>
  </div>
  <h3 class="strip-title">East Bengaluru’s key corridors</h3>
  <div class="strip">{''.join(cards)}</div>
  <footer class="ifoot"><span><b>Sources:</b> {e(', '.join(p for p, _ in pubs.most_common(6))) or 'see report'} — full citations, retrieval times and verification status in the report.</span>
  <span class="tag">Research, not investment advice · Illustrations are generated, not photographs</span></footer>
</section>
"""
