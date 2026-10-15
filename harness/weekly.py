"""Weekly trend summary built from the last 7 daily datasets (reports/daily/*.json)."""
from __future__ import annotations

from collections import Counter, defaultdict
from datetime import date, timedelta

import markdown as md

from harness.common import PROCESSED, REPORTS, iso, now_ist, read_json, write_json, write_text
from harness.registry import corridors
from validation.verification import USABLE


def build_weekly(week_ending: date) -> dict:
    days = [week_ending - timedelta(days=i) for i in range(6, -1, -1)]
    sets = [(d, read_json(REPORTS / "daily" / f"{d.isoformat()}.json")) for d in days]
    sets = [(d, s) for d, s in sets if s]
    name = lambda c: corridors().get(c, {}).get("name", c)  # noqa: E731
    L = [f"# Weekly trend summary — week ending {week_ending.isoformat()}", "",
         f"Editions included: {', '.join(d.isoformat() for d, _ in sets) or 'none'} "
         f"({len(sets)} of 7). Generated {iso(now_ist())}.", "",
         "Daily headlines are not repeated here; this page tracks what persisted or moved over the week.", ""]
    if not sets:
        L += ["No daily datasets for this week."]
    else:
        claims = {c["claim_id"]: c for _, s in sets for c in s["claims"]}.values()
        usable = [c for c in claims if c["verification_status"] in USABLE]
        L += ["## New launches by corridor and property type", ""]
        launches = Counter((c["corridor"], c["property_type"]) for c in usable if c["claim_type"] == "project_launch")
        projects = {p["project_id"]: p for _, s in sets for p in s.get("projects", [])}
        L += ["| Corridor | Type | Verified launch claims |", "|---|---|---|"] + \
             [f"| {name(k[0])} | {k[1]} | {v} |" for k, v in launches.most_common()] if launches else ["None verified."]
        L += ["", f"Projects tracked this week: {len(projects)}.", "", "## Verified pricing changes", ""]
        prices = defaultdict(list)
        for c in usable:
            if c.get("psf_inr"):
                prices[(c["corridor"], c["comparability"])].append((c["published_at"] or "", c["psf_inr"], c["claim_id"]))
        moved = [(k, sorted(v)) for k, v in prices.items() if len(v) >= 2]
        L += [f"- {name(k[0])} ({k[1]}): {v[0][1]:,.0f} → {v[-1][1]:,.0f} ₹/sqft ({v[0][2]} → {v[-1][2]}) — "
              "different sources/projects; not a like-for-like index." for k, v in moved] or \
             ["No corridor had two or more comparable usable price observations this week."]
        L += ["", "## Infrastructure milestones", ""]
        stages = [s for _, sd in sets for s in sd.get("stage_changes", [])]
        L += [f"- {s['name']}: → {s['stage'].replace('_', ' ')} (`{s['claim_id']}`)" for s in stages] or ["No evidenced stage changes."]
        L += ["", "## Changes in investment rankings", ""]
        first, last = sets[0][1]["model"]["cells"], sets[-1][1]["model"]["cells"]
        f = {(c["corridor"], c["property_type"]): c["attractiveness"] for c in first}
        moves = [f"- {name(c['corridor'])} {c['property_type']}: {f.get((c['corridor'], c['property_type'])) or 'Unranked'} → "
                 f"{c['attractiveness'] or 'Unranked'}" for c in last if f.get((c["corridor"], c["property_type"])) != c["attractiveness"]]
        L += moves or ["No ranking changes."]
        L += ["", "## Emerging supply and liquidity risks", ""]
        risks = [c for c in usable if c["claim_type"] in ("supply_demand", "civic_risk")]
        L += [f"- {c['statement']} ([{c['publisher']}]({c['url']}))" for c in risks[:15]] or ["None evidenced."]
        L += ["", "## Forecast assumptions that need revision", ""]
        contra = [x for _, s in sets for x in s.get("contradictions", [])]
        est = [c for c in last if c["scenarios"]["status"] == "estimated"]
        L += [f"- {len(contra)} contradiction(s) this week; review any scenario that uses those claims."]
        L += [f"- {len(est)} corridor/type cells have estimable scenarios; the rest remain 'Insufficient evidence to estimate'."]
        baseline = read_json(PROCESSED / "market_baseline.json", {})
        L += [f"- Market baseline last refreshed: {baseline.get('refreshed_on', 'never')}."]
    body = "\n".join(L) + "\n"
    out = REPORTS / "weekly" / f"{week_ending.isoformat()}"
    write_text(out.with_suffix(".md"), body)
    write_text(out.with_suffix(".html"), "<!doctype html><meta charset=utf-8><title>Weekly summary</title>"
               "<body style='font-family:system-ui;max-width:900px;margin:auto;padding:16px'>"
               + md.markdown(body, extensions=["tables"]))
    write_json(out.with_suffix(".json"), {"week_ending": week_ending.isoformat(), "editions": [d.isoformat() for d, _ in sets]})
    return {"path": str(out.with_suffix(".md")), "editions": len(sets)}
