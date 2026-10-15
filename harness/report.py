"""Publish + archive: Markdown, HTML, JSON and PDF (with infographic cover) from ONE validated dataset."""
from __future__ import annotations

import shutil
import statistics
import subprocess
from collections import Counter, defaultdict
from pathlib import Path

import markdown as md

from harness.common import (HISTORY, PROCESSED, REPORTS, ROOT, iso, load_config, now_ist, read_json, sha,
                            write_json, write_text)
from harness.infographic import render_infographic
from harness.registry import corridors
from validation.gates import run_gates
from validation.verification import USABLE

STATUS = {"verified_primary": "✅ Verified (official source)", "corroborated": "✅ Corroborated",
          "single_source": "◑ Single source", "interested_party_claim": "⚠ Interested-party claim",
          "unverified": "✖ Unverified", "contradicted": "⚠ Contradicted", "pending": "… pending"}
PT = {"plot": "Plots", "villa": "Villas", "apartment": "Apartments"}
TEMPLATES = ROOT / "content_engineering" / "templates"


def esc(s) -> str:
    return str(s if s is not None else "Not verified").replace("|", "/").replace("\n", " ")


def link(c) -> str:
    return f"[{esc(c['publisher'])}]({c['url']})"


def cor_name(cid: str) -> str:
    return corridors().get(cid, {}).get("name", "Unmapped location")


def inr(x) -> str:
    if x is None:
        return "Not verified"
    if x >= 1e7:
        return f"₹{x / 1e7:.2f} cr"
    if x >= 1e5:
        return f"₹{x / 1e5:.1f} lakh"
    return f"₹{x:,.0f}"


def run_status(d: dict) -> tuple[str, str]:
    agent_ok = sum(v["ok"] for v in d["coverage"].values())
    feeds_ok = len(d["feeds"]["ok"])
    if agent_ok == 0 and feeds_ok == 0:
        return "failed", "Research failed: no source could be collected. This is NOT a 'no news' day."
    fresh = [c for c in d["claims"] if c["novelty"] != "repeat" and c["verification_status"] in USABLE
             and "outside_window" not in c["flags"] and c["origin"] != "agent:market_baseline"]
    partial = any(not v["ok"] for v in d["coverage"].values()) or d["feeds"]["failed"] or d.get("budget_exceeded_at")
    if not fresh and not [s for s in d["stories"] if s["novelty"] == "new" and not s["stale_flags"]]:
        return ("partial" if partial else "no_new_updates",
                "No new verified updates in the window." + (" Coverage was partial." if partial else ""))
    return ("partial", "Completed with partial coverage (see Sources and Coverage Gaps).") if partial \
        else ("ok", "Completed with full planned coverage.")


STALE = {"outside_window", "republished_old_event"}


def fresh_claims(d: dict) -> list[dict]:
    """Claims that are genuinely new in this window (not repeats, not baseline, not old news re-dated)."""
    return [c for c in d["claims"] if c["novelty"] != "repeat" and c["origin"] != "agent:market_baseline"
            and not STALE & set(c["flags"])]


def collapse(claims: list[dict]) -> list[dict]:
    """One row per claim_key; extra sources become 'also reported by' links (copies are not extra evidence)."""
    out, by = [], {}
    for c in claims:
        k = c.get("claim_key", c["claim_id"])
        if k in by:
            by[k]["_also"].append(c)
        else:
            by[k] = dict(c, _also=[])
            out.append(by[k])
    return out


def brief_items(d: dict, n: int = 7) -> list[dict]:
    order = {"infrastructure": 0, "policy": 0, "legal": 1, "project_launch": 1, "price": 2, "transaction": 2,
             "supply_demand": 2, "employment": 3, "civic_risk": 3, "appreciation": 3, "rental": 3}
    rank = {"verified_primary": 0, "corroborated": 1, "single_source": 2}
    items = [c for c in fresh_claims(d) if c["verification_status"] in ("verified_primary", "corroborated")
             or (c["verification_status"] == "single_source" and c["confidence"] == "Medium")]
    items.sort(key=lambda c: (rank[c["verification_status"]], c["region"] != "east", order.get(c["claim_type"], 4)))
    out, seen = [], set()
    for c in items:
        if c["claim_key"] in seen or c["url"] in seen:      # one brief item per fact and per article
            continue
        seen.update({c["claim_key"], c["url"]})
        out.append(c)
    return out[:n]


def standalone(c) -> str:
    """Statement that reads on its own: context-dependent ones ("The same notice…") get their subject prefixed."""
    from harness.infographic import ANAPHORA
    return f"{c['subject']}: {c['statement']}" if ANAPHORA.match(c["statement"]) else c["statement"]


def claim_row(c) -> str:
    also = c.get("_also") or []
    more = (" · also: " + ", ".join(link(x) for x in also[:4])) if also else ""
    return (f"| {esc(c['statement'])} | {esc(cor_name(c['corridor']))} | {c['published_at'] or 'undated'} | "
            f"{STATUS[c['verification_status']]} ({c['confidence']}) | {link(c)} `{c['claim_id']}`{more} |")


CLAIM_HEAD = "| What | Where | Published | Status | Source |\n|---|---|---|---|---|"


def build_markdown(d: dict, meta: dict) -> str:
    L = []
    w = meta["window"]
    L += [f"# Bengaluru Real Estate Intelligence — {meta['edition']}",
          "",
          f"**Edition:** {meta['edition']} · **Window (IST):** {w['start']} → {w['end']} (72 hours)  ",
          f"**Generated:** {meta['generated_at']} · **Run status:** `{meta['status']}` — {meta['status_text']}",
          "",
          "> Research summary, not investment advice. Forecasts are uncertain scenarios, not promised returns. "
          "Every figure carries its source and verification status; anything marked unverified is not established fact.",
          ""]
    if meta["gates"]["warnings"]:
        L += ["**Publication warnings:** " + "; ".join(meta["gates"]["warnings"]), ""]

    # 1 brief
    L += ["## 1. Today’s Bengaluru Property Brief", ""]
    brief = brief_items(d)
    if meta["status"] == "failed":
        L += ["**Research failed.** No sources could be collected, so absence of items below says nothing about the market.", ""]
    elif not brief:
        L += ["No new verified, material change was found in the window. Unverified leads, if any, are listed in section 8 and section 10.", ""]
    else:
        for c in brief:
            L.append(f"- **{esc(standalone(c))}** — {cor_name(c['corridor'])}. "
                     f"{STATUS[c['verification_status']]}, {c['confidence']} confidence. {link(c)} `{c['claim_id']}`")
        L.append("")

    # 2 east deep dive
    L += ["## 2. East Bengaluru Deep Dive", ""]
    projects = read_json(PROCESSED / "projects.json", {})
    for cid, cor in corridors().items():
        if cor["region"] != "east":
            continue
        cl = [c for c in fresh_claims(d) if c["corridor"] == cid]
        pj = [p for p in projects.values() if p["corridor"] == cid and p["project_id"] in d["projects_today"]]
        L += [f"### {cor['name']}"]
        if cor.get("straddles"):
            L += [f"*Also described as {', '.join(cor['straddles'])} Bengaluru in listings; counted once, under East.*"]
        if not cl and not pj:
            L += ["No new evidence in the window.", ""]
            continue
        groups = [("Launches & project updates", ("project_launch", "project_update")),
                  ("Pricing evidence", ("price", "transaction", "rental", "appreciation")),
                  ("Catalysts (infrastructure, jobs, policy)", ("infrastructure", "employment", "policy", "legal")),
                  ("Risks (civic, supply, execution)", ("civic_risk", "supply_demand", "other"))]
        good = [c for c in cl if c["verification_status"] in USABLE]
        weak = [c for c in cl if c["verification_status"] not in USABLE]
        for title, types in groups:
            rows = [c for c in good if c["claim_type"] in types]
            if rows:
                L += ["", f"**{title}**", "", CLAIM_HEAD] + [claim_row(c) for c in collapse(rows)]
        if weak:
            srcs = Counter(c["publisher"] for c in weak)
            L += ["", f"*Not established:* {len(weak)} unverified or interested-party claim(s) from "
                  + ", ".join(f"{k} ({v})" for k, v in srcs.most_common(4))
                  + " — listed in section 8, not used as evidence."]
        if pj:
            L += ["", "**Projects seen in this edition**", "",
                  "| Project | Developer | Type | Status | RERA | Quoted price | Basis / kind | Possession | Confidence |",
                  "|---|---|---|---|---|---|---|---|---|"]
            for p in pj:
                obs = p["price_observations"]
                price = "; ".join(f"{o['bound']}: {o['value']:g} {o['unit'] or ''}".strip()
                                  + (f" (≈₹{o['psf_inr']:,.0f}/sqft {o['basis']})" if o["psf_inr"] and o["psf_inr"] != o["value"] else "")
                                  for o in obs) or "Not verified"
                basis = ", ".join(sorted({f"{o['basis']} / {o['kind']}" for o in obs})) or "Not verified"
                L.append(f"| [{esc(p['name'])}]({p['sources'][0]['url']}) | {esc(p['developer'])} | {esc(p['property_type'])} | "
                         f"{esc(p['status'])} | {(esc(p['rera']['number']) + ' — ' + p['rera']['status']) if p['rera']['number'] else 'Not verified'} | {esc(price)} | {esc(basis)} | "
                         f"{esc(p['possession'])} | {p['confidence']} |")
        L.append("")

    # 3 N/S/W
    L += ["## 3. North, South and West Bengaluru", ""]
    for reg in ("north", "south", "west", "peripheral"):
        cl = collapse([c for c in fresh_claims(d) if c["region"] == reg])
        name = load_config("corridors")["regions"][reg]["name"]
        if not cl:
            L += [f"**{name}:** no new evidence in the window.", ""]
            continue
        good = [c for c in cl if c["verification_status"] in USABLE]
        weak = len(cl) - len(good)
        L += [f"**{name}**", ""]
        if good:
            L += [CLAIM_HEAD] + [claim_row(c) for c in good[:8]] + [""]
            if len(good) > 8:
                L += [f"*{len(good) - 8} further item(s) in the JSON export.*", ""]
        else:
            L += ["No usable (verified or single-source) evidence in the window.", ""]
        if weak:
            L += [f"*Not established:* {weak} unverified or interested-party claim(s) — see section 8.", ""]

    # 4 comparison
    L += ["## 4. Plots vs Villas vs High-Rise Apartments", "",
          "Scores are 1–5 from evidenced factors only (momentum, rental yield, affordability, connectivity, employment, risk). "
          "Plot prices are **land rates** and apartment prices are usually **super built-up (saleable)** rates — they are "
          "never compared as if equivalent. *Unranked* means the evidence base is too thin to score.", "",
          "| Corridor | Plots | Villas | Apartments |", "|---|---|---|---|"]
    cells = {(c["corridor"], c["property_type"]): c for c in d["model"]["cells"]}
    for cid, cor in sorted(corridors().items(), key=lambda kv: (kv[1]["region"] != "east", kv[1]["region"], kv[0])):
        if cor["region"] == "peripheral":
            continue
        row = [cor["name"]]
        for pt in ("plot", "villa", "apartment"):
            cell = cells[(cid, pt)]
            if cell["attractiveness"] is None:
                row.append(f"Unranked ({len(cell['factors'])}/6 factors)")
            else:
                row.append(f"**{cell['attractiveness']:.1f}** · {cell['confidence']} conf. · #{cell['rank']}")
        L.append("| " + " | ".join(row) + " |")
    if d["model"]["price_medians"]:
        L += ["", "City medians used for affordability (same basis and price kind only): " +
              "; ".join(f"{k}: ₹{v:,}/sqft" for k, v in d["model"]["price_medians"].items())]
    L.append("")

    # 5 government
    L += ["## 5. Government Moves in the Last 72 Hours", "",
          "Stage ladder: Proposed → Announced → Approved → Funded → Tendered → Awarded → Under construction → Operational. "
          "A stage is shown only when the quoted source text evidences it.", ""]
    gov = collapse([c for c in fresh_claims(d) if c["claim_type"] in ("infrastructure", "policy", "legal")])
    if not gov:
        L += ["No government or infrastructure development published in the window was captured.", ""]
    else:
        infra = read_json(PROCESSED / "infrastructure.json", {})
        L += ["| Development | Stage (evidenced) | Published / event date | Corridors possibly affected | Status | Source |",
              "|---|---|---|---|---|---|"]
        for c in gov:
            item = next((v for v in infra.values() if c["claim_id"] in v["claim_ids"]), None)
            cors = [x for x in (item["corridors"] if item else [c["corridor"]]) if x != "unmapped"]
            affected = (", ".join(cor_name(x) for x in cors) or "City-wide / not corridor-specific")[:160]
            stage = (c["evidenced_stage"] or "").replace("_", " ").title() or \
                ("Stage not evidenced" if c["infra_stage"] != "none" else "—")
            L.append(f"| {esc(c['statement'])} | {stage} | {c['published_at'] or 'undated'} / {c['event_date'] or 'not stated'} | "
                     f"{esc(affected)} | {STATUS[c['verification_status']]} | {link(c)} `{c['claim_id']}` |")
        L.append("")
    if d.get("stage_changes"):
        L += ["**Tracked status changes this edition**", ""]
        for s in d["stage_changes"]:
            ev = s.get("event_date")
            old = ev and ev < meta["window"]["start"][:10]
            L.append(f"- {s['name']}: {(s['from'] or 'untracked').replace('_', ' ')} → **{s['stage'].replace('_', ' ')}** "
                     f"(claim `{s['claim_id']}`; affects {', '.join(cor_name(x) for x in s['corridors'][:6]) or 'city-wide / not mapped'})"
                     + (f" — *tracker initialised from an older event dated {ev}; not new news*" if old else ""))
        L.append("")
    L += ["*Priced in?* The system does not have registered-price time series, so it cannot measure whether an announcement "
          "is already reflected in prices. Treat corridor price claims made after an announcement as asking prices, not proof of "
          "value. Timing and dependencies are as stated by the cited source and remain uncertain until the next stage is evidenced.", ""]

    # 6 scenarios
    sc = load_config("scoring")
    L += ["## 6. Growth Scenarios", "",
          f"Formula: Future value = Purchase price × (1 + annual growth rate)^years. Real = after {sc['scenarios']['inflation_pct']}% "
          "assumed inflation. Capital appreciation only; rent shown separately in the illustration.", ""]
    est = [c for c in d["model"]["cells"] if c["scenarios"]["status"] == "estimated"]
    if not est:
        L += ["**Insufficient evidence to estimate** for every corridor and property type in this edition: no cell has "
              f"appreciation evidence from at least {sc['scenarios']['min_appreciation_sources']} independent source groups.", ""]
    else:
        L += ["| Corridor · type | Scenario | Annual (nominal) | Annual (real) | 3 yr | 5 yr | 10 yr | Evidence |",
              "|---|---|---|---|---|---|---|---|"]
        for c in est:
            for name, r in c["scenarios"]["scenarios"].items():
                cp = r["cumulative_pct"]
                L.append(f"| {cor_name(c['corridor'])} · {PT[c['property_type']]} | {name.title()} | {r['annual_pct']}% | "
                         f"{r['real_annual_pct']}% | +{cp['3']}% | +{cp['5']}% | +{cp['10']}% | "
                         f"{', '.join('`' + i + '`' for i in c['scenarios']['evidence_claim_ids'][:4])} |")
        L += ["", "Assumptions: " + est[0]["scenarios"]["assumptions"], ""]
        if d.get("illustrations"):
            ii = sc["illustrative_investment"]
            L += [f"**Illustrative investment (base scenario, {inr(ii['purchase_price_inr'])} purchase, "
                  f"{ii['financing']['ltv_pct']}% loan at {ii['financing']['interest_rate_pct']}%)** — assumptions, not evidence:", "",
                  "| Corridor · type | Years | Sale price | Acquisition costs | Holding costs | Net rent | Interest | Selling costs | Net profit | Net return p.a. (nominal / real) |",
                  "|---|---|---|---|---|---|---|---|---|---|"]
            for x in d["illustrations"]:
                L.append(f"| {cor_name(x['corridor'])} · {PT[x['property_type']]} | {x['years']} | {inr(x['sale_price'])} | "
                         f"{inr(x['acquisition_costs'])} | {inr(x['holding_costs'])} | {inr(x['net_rent'])} | {inr(x['financing_interest'])} | "
                         f"{inr(x['selling_costs'])} | {inr(x['net_profit'])} | {x['net_return_on_outlay_pct_pa']}% / {x['real_net_return_pct_pa']}% |")
            L += ["", "Excluded: " + "; ".join(ii["excluded"]) + ".", ""]
    L += [f"Unestimated cells: {sum(c['scenarios']['status'] != 'estimated' for c in d['model']['cells'])} of "
          f"{len(d['model']['cells'])} — *Insufficient evidence to estimate*.", ""]

    # 7 opportunities
    L += ["## 7. Opportunities to Investigate", ""]
    ranked = sorted((c for c in d["model"]["cells"] if c["attractiveness"] is not None), key=lambda c: c["rank"])
    if not ranked:
        L += ["No corridor/property-type combination met the evidence threshold for ranking "
              f"(≥{sc['min_factors_for_rank']} evidenced factors). Nothing is ranked rather than ranking on thin data.", ""]
    else:
        by = {c["claim_id"]: c for c in d["claims"]}
        for c in ranked[:6]:
            pos = [f"{k} {v['score']}/5" for k, v in c["factors"].items() if v["score"] >= 4]
            neg = [f"{k} {v['score']}/5" for k, v in c["factors"].items() if v["score"] <= 2]
            contra = [x for x in d.get("contradictions", []) if c["corridor"] in x["claim_key"]]
            L.append(f"{c['rank']}. **{cor_name(c['corridor'])} — {PT[c['property_type']]}**: attractiveness "
                     f"{c['attractiveness']:.1f}/5, evidence confidence {c['confidence']}. "
                     f"Supports: {', '.join(pos) or 'no factor ≥4'}. Disconfirming: {', '.join(neg) or 'none scored ≤2'}"
                     f"{'; ' + str(len(contra)) + ' contradiction(s)' if contra else ''}. "
                     f"Missing factors: {', '.join(k for k in sc['factors'] if k not in c['factors']) or 'none'}.")
        L.append("")

    # 8 risks
    L += ["## 8. Risks, Contradictions and Unverified Claims", ""]
    if d.get("contradictions"):
        L += ["**Unresolved contradictions**", "", "| Subject | Metric | Values reported |", "|---|---|---|"]
        for x in d["contradictions"]:
            vals = "; ".join((f"{esc(v['unit'])}" if x["metric"] == "reviewer verdicts" else f"{v['value']:g} {v['unit'] or ''}")
                             + f" ([{esc(v['publisher'])}]({v['url']}))" for v in x["values"])
            L.append(f"| {esc(x['subject'])} | {x['metric']} | {vals} |")
        L.append("")
    weak = [c for c in fresh_claims(d) if c["verification_status"] in ("unverified", "interested_party_claim", "contradicted")]
    if weak:
        L += ["**Claims that are NOT established fact**", "", "| Claim | Status | Why | Flags | Source |", "|---|---|---|---|---|"]
        for c in weak[:30]:
            flags = ", ".join(f for f in c["flags"] if f not in ("citation_confirmed",)) or "—"
            L.append(f"| {esc(c['statement'])} | {STATUS[c['verification_status']]} | {esc(c['confidence_reason'])} | {flags} | {link(c)} |")
        L.append("")
    risk = [c for c in fresh_claims(d) if c["claim_type"] in ("civic_risk", "supply_demand") and c["verification_status"] in USABLE]
    stale = [c for c in d["claims"] if "republished_old_event" in c["flags"]]
    if stale:
        L += ["**Old news republished with new dates (not counted as new)**", ""] + [
            f"- {esc(c['statement'])} — published {c['published_at']}, event {c['event_date']} ({link(c)})" for c in stale] + [""]
    if risk:
        L += ["**Evidenced risks**", "", CLAIM_HEAD] + [claim_row(c) for c in risk] + [""]
    pflags = [(p, f) for p in projects.values() if p["project_id"] in d["projects_today"] for f in p["flags"]]
    if pflags:
        L += ["**Project data conflicts**", ""] + [f"- {esc(p['name'])}: {esc(f)}" for p, f in pflags] + [""]
    if not (d.get("contradictions") or weak or risk or pflags or stale):
        L += ["None recorded in this edition.", ""]

    # 9 changes
    L += ["## 9. What Changed Since Yesterday", ""] + meta["changes"] + [""]

    # 10 sources
    L += ["## 10. Sources and Coverage Gaps", ""]
    L += [f"- RSS feeds collected: {len(d['feeds']['ok'])}; failed: {len(d['feeds']['failed'])}"]
    for f in d["feeds"]["failed"]:
        L.append(f"  - {f['source']}: {f['reason']}")
    for t, v in d["coverage"].items():
        L.append(f"- Research task `{t}`: {'ok' if v['ok'] else 'FAILED — ' + str(v['error'])}"
                 f" (cost ${v.get('cost_usd', 0):.2f})" + (f" — {esc(v.get('notes'))}" if v.get("notes") else ""))
    rec = d.get("recheck", {})
    L.append(f"- Independent recheck: {rec.get('reviewed', 0)} of {rec.get('targets', 0)} consequential claims reviewed; "
             f"{len(rec.get('downgraded', []))} downgraded" + (f"; reviewer error: {rec['agent_error']}" if rec.get("agent_error") else ""))
    L.append(f"- Links checked: {rec.get('links_checked', 0)}; unreachable: {len(rec.get('links_unreachable', []))}")
    tiers = Counter(c["tier"] for c in d["claims"])
    L.append("- Claims by source tier: " + ", ".join(f"{k} {v}" for k, v in tiers.most_common()))
    L += ["", "**Inaccessible or not-accessed sources**", ""]
    seen = set()
    for u in d["unavailable"]:
        key = (u["source"], u["status"])
        if key not in seen:
            seen.add(key)
            L.append(f"- {esc(u['source'])}: {u['status']}" + (f" — {esc(u.get('note'))}" if u.get("note") else ""))
    for u in load_config("sources")["known_unavailable"]:
        L.append(f"- {u['source']}: {u['reason']}")
    leads = [s for s in d["stories"] if s["novelty"] == "new" and not s["stale_flags"]]
    cited = {c["url"] for c in d["claims"]}
    leads = [s for s in leads if s["lead"]["url"] not in cited][:20]
    if leads:
        L += ["", "**Headlines detected but not verified (leads only — not used as evidence)**", ""]
        for s in leads:
            more = f" (+{len(s['members']) - 1} similar)" if len(s["members"]) > 1 else ""
            L.append(f"- [{esc(s['title'])}]({s['lead']['url']}) — {esc(s['lead']['publisher'])}, {s['published_at'] or 'undated'}{more}")
    reps = sum(s["novelty"] == "repeat" for s in d["stories"])
    stale = sum(bool(s["stale_flags"]) for s in d["stories"])
    L += ["", f"Noise removed: {sum(len(s['members']) - 1 for s in d['stories'])} duplicate/syndicated headline copies grouped; "
          f"{reps} repeat stories suppressed; {stale} stale or undated stories excluded from 'new'.", ""]
    L += ["**Cited sources**", "", "| Claim | Publisher | Tier | Published | Retrieved | Citation check | Status |", "|---|---|---|---|---|---|---|"]
    for c in sorted(d["claims"], key=lambda c: c["claim_id"]):
        chk = (c.get("citation_check") or {}).get("result", "not_checked")
        L.append(f"| `{c['claim_id']}` | [{esc(c['publisher'])}]({c['url']}) | {c['tier']} | {c['published_at'] or 'undated'} | "
                 f"{c['retrieved_at']} | {chk} | {STATUS[c['verification_status']]} |")
    return "\n".join(L) + "\n"


def changes_since_previous(d: dict, edition: str) -> list[str]:
    snaps = sorted(p for p in (HISTORY / "editions").glob("*.json") if p.stem < edition)
    if not snaps:
        return ["First edition — no previous report to compare against. Baseline records created."]
    prev = read_json(snaps[-1])
    out = [f"Compared with edition {snaps[-1].stem}:"]
    prev_ids = set(prev.get("claim_ids", []))
    new = [c for c in d["claims"] if c["claim_id"] not in prev_ids]
    out.append(f"- {len(new)} new claim(s), {sum(c['verification_status'] in USABLE for c in new)} usable.")
    out.append(f"- {len(d.get('stage_changes', []))} infrastructure stage change(s).")
    prev_rank = {(r["corridor"], r["property_type"]): r for r in prev.get("ranks", [])}
    for c in d["model"]["cells"]:
        p = prev_rank.get((c["corridor"], c["property_type"]))
        if p and p["attractiveness"] != c["attractiveness"]:
            out.append(f"- {cor_name(c['corridor'])} {PT[c['property_type']]}: {p['attractiveness'] or 'Unranked'} → {c['attractiveness'] or 'Unranked'}")
    prev_status = prev.get("statuses", {})
    flips = [c for c in d["claims"] if c["claim_id"] in prev_status and prev_status[c["claim_id"]] != c["verification_status"]]
    for c in flips:
        out.append(f"- `{c['claim_id']}` status {prev_status[c['claim_id']]} → {c['verification_status']}")
    return out


CHROME = ["/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
          "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge", "google-chrome", "chromium"]


def html_pdf(html_path: Path, pdf_path: Path) -> str | None:
    for exe in CHROME:
        if Path(exe).exists() or shutil.which(exe):
            # desktop-width window: page-fit scripts must measure the print layout, not a mobile breakpoint
            r = subprocess.run([exe, "--headless=new", "--disable-gpu", "--no-pdf-header-footer", "--window-size=1200,1600",
                                f"--print-to-pdf={pdf_path}", html_path.resolve().as_uri()],
                               capture_output=True, text=True, timeout=180)
            if pdf_path.exists() and pdf_path.stat().st_size > 0:
                return None
            return f"PDF render failed: {r.stderr[-300:]}"
    return "no Chromium-based browser found for PDF rendering"


def render_daily(ctx, d: dict) -> dict:
    ed = ctx.edition.isoformat()
    gates = run_gates(d, ctx.window)
    status, text = run_status(d)
    meta = {"edition": ed, "window": {"start": iso(ctx.window[0]), "end": iso(ctx.window[1])},
            "generated_at": iso(now_ist()), "status": status, "status_text": text, "gates": gates,
            "changes": changes_since_previous(d, ed)}
    out_dir = REPORTS / "daily" if gates["passed"] else REPORTS / "daily" / "_blocked"
    body = build_markdown(d, meta)
    dataset = {"meta": meta, "brief_claim_ids": [c["claim_id"] for c in brief_items(d)], **{
        k: d.get(k) for k in ("claims", "contradictions", "model", "illustrations", "stage_changes", "coverage",
                              "unavailable", "feeds", "recheck")},
        "projects": [p for p in read_json(PROCESSED / "projects.json", {}).values() if p["project_id"] in d["projects_today"]],
        "stories": [{k: s[k] for k in ("story_id", "title", "publishers", "published_at", "novelty", "stale_flags", "regions")}
                    | {"url": s["lead"]["url"]} for s in d["stories"]]}
    write_json(out_dir / f"{ed}.json", dataset)
    write_text(out_dir / f"{ed}.md", body)
    css = (TEMPLATES / "report.css").read_text(encoding="utf-8")
    html_body = md.markdown(body, extensions=["tables", "sane_lists"])
    html_body = html_body.replace("<a href=", '<a target="_blank" rel="noopener" href=')
    info = render_infographic(d, meta)
    page = (f"<!doctype html><html lang='en'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'>"
            f"<title>Bengaluru REI {ed}</title><style>{css}</style></head><body>"
            f"{'<div class=blocked>PUBLICATION BLOCKED: ' + '; '.join(gates['hard_failures']) + '</div>' if not gates['passed'] else ''}"
            f"{info}<main class='report'>{html_body}</main></body></html>")
    html_path = out_dir / f"{ed}.html"
    write_text(html_path, page)
    # Daily Edition PDF: 5-page newspaper of development + metro news (no statistics);
    # falls back to the condensed analyst layout if the news writer is unavailable.
    from harness.daily_paper import render_delta, write_paper
    paper = write_paper(ed, d, meta["window"], ctx.log)
    if paper:   # "Bangalore Realestate Delta": magazine-style daily, news only
        pages, pdf_err = render_delta(ed, paper, meta, out_dir / f"{ed}.pdf", html_pdf)
    else:
        from harness.pdf_edition import render_pdf
        pages, pdf_err = render_pdf(d, meta, info, css, out_dir / f"{ed}.pdf", html_pdf)
    if pdf_err:
        ctx.log("pdf_failed", detail=pdf_err)
    else:
        ctx.log("pdf_rendered", pages=pages)
    ctx.log("published", status=status, gates_passed=gates["passed"], dir=str(out_dir))
    d["publish"] = {"status": status, "gates": gates, "dir": str(out_dir), "pdf_error": pdf_err, "meta": meta}
    if not gates["passed"]:
        raise SystemExit(f"publication gates failed: {gates['hard_failures'][:5]}")
    return d


def archive_edition(ctx, d: dict) -> dict:
    ed = ctx.edition.isoformat()
    seen = read_json(HISTORY / "seen_stories.json", {})
    for s in d["stories"]:
        seen.setdefault(s["story_id"], {"first_seen": ed, "title": s["title"], "fact_keys": []})
        seen[s["story_id"]]["last_seen"] = ed
        fk = set(seen[s["story_id"]]["fact_keys"]) | {s["lead"]["canonical_url"]}
        seen[s["story_id"]]["fact_keys"] = sorted(fk)
    for c in d["claims"]:
        sid = "S-" + sha(c["url"])
        seen.setdefault(sid, {"first_seen": ed, "title": c["statement"][:120], "fact_keys": []})
        seen[sid]["last_seen"] = ed
        seen[sid]["fact_keys"] = sorted(set(seen[sid]["fact_keys"]) | {c["fact_key"]})
    write_json(HISTORY / "seen_stories.json", seen)
    write_json(HISTORY / "editions" / f"{ed}.json", {
        "edition": ed, "status": d["publish"]["status"],
        "claim_ids": sorted(c["claim_id"] for c in d["claims"]),
        "statuses": {c["claim_id"]: c["verification_status"] for c in d["claims"]},
        "ranks": [{"corridor": c["corridor"], "property_type": c["property_type"], "attractiveness": c["attractiveness"],
                   "confidence": c["confidence"]} for c in d["model"]["cells"]],
        "stage_changes": d.get("stage_changes", []), "projects_today": d["projects_today"],
        "brief": [c["claim_id"] for c in brief_items(d)]})
    ctx.log("archived", edition=ed)
    return {"edition": ed, "status": d["publish"]["status"]}
