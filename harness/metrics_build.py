"""Website metrics: KPIs, growth series, area prices and top builders, from publishable evidence.

An LLM with no tools proposes the structure; code enforces:
* every value must appear (as digits) in the claim it cites;
* every point of one series must come from ONE data producer (origin group) - no
  stitching different firms' numbers into a fake trend;
* series need >= 2 points; builders need >= 1 valid metric or tracked project.
Deterministic stats (projects tracked per developer) are added without the LLM.
"""
from __future__ import annotations

import json
from collections import Counter, defaultdict
from pathlib import Path

from harness import agent
from harness.common import DATA, PROCESSED, iso, now_ist, read_json, write_json
from harness.magazine_write import nums

APP_DATA = DATA / "app"

_num = {"type": "number"}
_str = {"type": "string"}
SCHEMA = {
    "type": "object", "additionalProperties": False, "required": ["kpis", "series", "area_prices", "builders"],
    "properties": {
        "kpis": {"type": "array", "items": {"type": "object", "additionalProperties": False,
                 "required": ["label", "value", "display", "change", "period", "claim_id"],
                 "properties": {"label": _str, "value": _num, "display": _str, "change": _str, "period": _str, "claim_id": _str}}},
        "series": {"type": "array", "items": {"type": "object", "additionalProperties": False,
                   "required": ["id", "title", "unit", "chart", "note", "points"],
                   "properties": {"id": _str, "title": _str, "unit": _str, "chart": {"enum": ["line", "bar"]}, "note": _str,
                                  "points": {"type": "array", "items": {"type": "object", "additionalProperties": False,
                                             "required": ["label", "sort", "value", "claim_id"],
                                             "properties": {"label": _str, "sort": _num, "value": _num, "claim_id": _str}}}}}},
        "area_prices": {"type": "array", "items": {"type": "object", "additionalProperties": False,
                        "required": ["area", "zone", "low", "high", "basis", "claim_id"],
                        "properties": {"area": _str, "zone": {"enum": ["east", "north", "south", "west", "outer"]},
                                       "low": _num, "high": _num, "basis": _str, "claim_id": _str}}},
        "builders": {"type": "array", "items": {"type": "object", "additionalProperties": False,
                     "required": ["name", "headline", "metric_label", "metric_value", "metric_display", "projects", "claim_ids"],
                     "properties": {"name": _str, "headline": _str, "metric_label": _str, "metric_value": _num,
                                    "metric_display": _str, "projects": {"type": "array", "items": _str},
                                    "claim_ids": {"type": "array", "items": _str}}}},
    },
}

PROMPT = """You prepare data for the "Bengaluru Property Review" website dashboard from the FACT BANK.

Produce:
- kpis: 6-8 headline city metrics (sales, launches, average price ₹/sq ft, price growth, rental
  yield, unsold stock, office leasing). value = the number, display = short formatted text
  (e.g. "16,670", "₹9,450", "+12%"), change = short context ("+12% YoY"), period ("Q3 2026").
- series: 3-6 growth series for charts. Each series uses figures from ONE research firm only
  (e.g. all ANAROCK). Points can come from numbers stated inside a claim (e.g. "rose from
  Rs 4,975 in 2019 to Rs 9,450 in Q2 2026" gives two points). sort = a sortable number for
  the period (2019, 2025.75 for Q3 2025, 2026.5 for Q2 2026...). At least 2 points each.
- area_prices: ₹/sq ft levels by area for apartments (or plots, with basis "land"), 6-16 rows.
- builders: 6-10 leading developers active in Bengaluru, each with a one-line headline, one
  metric (bookings ₹ crore, units, acres, GDV...) and their Bengaluru projects named in facts.

RULES: every number you output must appear in the cited claim. Never compute, average,
convert or extrapolate. Use the claim id(s) you relied on. If data is thin, return fewer rows.

FACT BANK (JSON lines):
{facts}

Return ONLY the JSON object required by the schema."""


def _claim_nums(c: dict) -> set[str]:
    s = nums(c["statement"]) | nums(c["excerpt"])
    for v in (c.get("value"), c.get("value_max")):
        if v is not None:
            s |= nums(f"{v:g}")
    return s


def _ok(value, c) -> bool:
    return c is not None and nums(f"{value:g}") <= _claim_nums(c)


def validate(raw: dict, by: dict) -> tuple[dict, list[str]]:
    dropped = []
    kpis = []
    for k in raw["kpis"]:
        c = by.get(k["claim_id"])
        if _ok(k["value"], c) and nums(k["display"] + " " + k["change"]) <= _claim_nums(c) | nums(k["period"]):
            kpis.append({**k, "source": c["publisher"], "url": c["url"]})
        else:
            dropped.append(f"kpi {k['label']}")
    series = []
    for s in raw["series"]:
        pts = [p for p in s["points"] if _ok(p["value"], by.get(p["claim_id"]))]
        if pts:
            groups = Counter(by[p["claim_id"]].get("origin_group") or by[p["claim_id"]]["group"] for p in pts)
            main = groups.most_common(1)[0][0]
            pts = [p for p in pts if (by[p["claim_id"]].get("origin_group") or by[p["claim_id"]]["group"]) == main]
        pts = sorted({p["sort"]: p for p in pts}.values(), key=lambda p: p["sort"])
        if len(pts) >= 2:
            srcs = sorted({by[p["claim_id"]]["publisher"] for p in pts})
            series.append({**s, "points": [{**p, "source": by[p["claim_id"]]["publisher"], "url": by[p["claim_id"]]["url"]}
                                           for p in pts], "sources": srcs})
        else:
            dropped.append(f"series {s['id']} ({len(pts)} valid points)")
    areas = []
    for a in raw["area_prices"]:
        c = by.get(a["claim_id"])
        if _ok(a["low"], c) and _ok(a["high"], c):
            areas.append({**a, "source": c["publisher"], "url": c["url"]})
        else:
            dropped.append(f"area {a['area']}")
    builders = []
    for b in raw["builders"]:
        cs = [by[i] for i in b["claim_ids"] if i in by]
        allowed = set().union(*(_claim_nums(c) for c in cs)) if cs else set()
        if cs and nums(f"{b['metric_value']:g}") <= allowed and nums(b["headline"] + " " + b["metric_display"]) <= allowed:
            builders.append({**b, "sources": sorted({c["publisher"] for c in cs}), "url": cs[0]["url"]})
        else:
            dropped.append(f"builder {b['name']}")
    return {"kpis": kpis, "series": series, "area_prices": areas, "builders": builders}, dropped


def tracked_projects_by_developer() -> list[dict]:
    projects = read_json(PROCESSED / "projects.json", {})
    by = defaultdict(list)
    for p in projects.values():
        dev = (p.get("developer") or "").strip()
        if dev:
            key = dev.split()[0].lower()
            by[key].append(p)
    out = []
    for key, ps in by.items():
        names = Counter(p["developer"] for p in ps).most_common(1)[0][0]
        out.append({"developer": names, "tracked_projects": len(ps),
                    "projects": sorted({p["name"] for p in ps})[:6],
                    "types": sorted({p.get("property_type") or "" for p in ps} - {""})})
    return sorted(out, key=lambda x: (-x["tracked_projects"], x["developer"]))


def build_metrics(log) -> dict:
    from harness.magazine import MAG_OUT, publishable
    from harness.magazine_write import fact_bank
    claims = {}
    for p in sorted(MAG_OUT.glob("????-??.json")):
        for c in read_json(p)["claims"]:
            if publishable(c):
                claims[c["claim_id"]] = c
    for c in read_json(PROCESSED / "claims_ledger.json", {}).values():
        if publishable(c):
            claims.setdefault(c["claim_id"], c)
    by = dict(claims)
    facts = "\n".join(json.dumps(r, ensure_ascii=False) for r in fact_bank(list(claims.values())))
    res = agent.run_agent(PROMPT.replace("{facts}", facts), SCHEMA, name="metrics_builder",
                          out_path=APP_DATA / "metrics_raw.json", budget_usd=1.5, timeout_min=15, log=log, tools=[])
    if res["ok"]:
        metrics, dropped = validate(res["data"], by)
    else:
        prior = read_json(APP_DATA / "metrics.json")
        if prior:
            log("metrics_kept_previous", reason=res["error"])
            return prior
        metrics, dropped = {"kpis": [], "series": [], "area_prices": [], "builders": []}, [f"builder failed: {res['error']}"]
    metrics["tracked_developers"] = tracked_projects_by_developer()
    metrics["generated_at"] = iso(now_ist())
    metrics["dropped"] = dropped
    write_json(APP_DATA / "metrics.json", metrics)
    log("metrics_built", kpis=len(metrics["kpis"]), series=len(metrics["series"]), areas=len(metrics["area_prices"]),
        builders=len(metrics["builders"]), dropped=len(dropped))
    return metrics
