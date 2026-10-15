"""Corridor x property-type scoring and growth scenarios.

Attractiveness (1-5) and evidence confidence are computed separately from the
claims ledger. Only claims with a usable verification status contribute, and each
factor records the claim IDs behind it so every score is traceable.
"""
from __future__ import annotations

import statistics
from collections import defaultdict
from datetime import timedelta

from harness.common import load_config, parse_date
from harness.registry import corridors
from validation.calculations import cagr_from_total, cumulative_pct, illustrative_investment, real_rate

PTYPES = ["plot", "villa", "apartment"]


def _band(value: float, bands: list[float], direction: str) -> int:
    score = 1 + sum(value >= b for b in bands)          # 1..5
    return score if direction == "+" else 6 - score


def appreciation_rate(c: dict) -> float | None:
    if c["metric"] == "cagr_pct" and c["value"] is not None:
        return float(c["value"])
    if c["metric"] == "appreciation_pct" and c["value"] is not None and c.get("period_years"):
        return cagr_from_total(float(c["value"]), float(c["period_years"]))
    return None


def build_model(ledger: list[dict], infra: dict, today) -> dict:
    sc = load_config("scoring")
    usable = set(sc["usable_statuses"])
    horizon = today - timedelta(days=365 * 3)
    live = [c for c in ledger if c["verification_status"] in usable
            and (parse_date(c["published_at"]) or today) >= horizon]

    # --- corridor-level points (shared by property types) ---------------------------
    points = defaultdict(lambda: defaultdict(float))
    refs = defaultdict(lambda: defaultdict(list))
    for item in infra.values():
        stage = item.get("stage")
        if not stage or stage == "none":
            continue
        for cor in item.get("corridors", []):
            points[cor]["infra_points"] += sc["infra_stage_points"][stage]
            refs[cor]["infra_points"].extend(item.get("claim_ids", [])[:3])
    for c in live:
        if c["claim_type"] == "employment":
            points[c["corridor"]]["employment_points"] += 0.5
            refs[c["corridor"]]["employment_points"].append(c["claim_id"])
        if c["claim_type"] == "civic_risk" or (c["claim_type"] == "supply_demand" and "oversupply" in c["statement"].lower()):
            points[c["corridor"]]["risk_points"] += 0.5
            refs[c["corridor"]]["risk_points"].append(c["claim_id"])

    # --- price index: psf relative to the city median of the same comparability class
    by_class = defaultdict(list)
    for c in live:
        if c.get("psf_inr") and c["property_type"] in PTYPES:
            by_class[c["comparability"]].append(c)
    medians = {k: statistics.median(x["psf_inr"] for x in v) for k, v in by_class.items()
               if len({x["corridor"] for x in v}) >= 3}

    cells = []
    for cor in corridors():
        for pt in PTYPES:
            metrics, mrefs, strong, total = {}, {}, 0, 0
            cell_claims = [c for c in live if c["corridor"] == cor and c["property_type"] == pt]
            rates = [(appreciation_rate(c), c) for c in cell_claims]
            rates = [(r, c) for r, c in rates if r is not None]
            if rates:
                metrics["cagr_pct"] = statistics.median(r for r, _ in rates)
                mrefs["cagr_pct"] = [c["claim_id"] for _, c in rates]
            ylds = [c for c in cell_claims if c["metric"] == "rental_yield_pct" and c["value"] is not None]
            if ylds:
                metrics["rental_yield_pct"] = statistics.median(c["value"] for c in ylds)
                mrefs["rental_yield_pct"] = [c["claim_id"] for c in ylds]
            idx = [(c["psf_inr"] / medians[c["comparability"]], c) for c in cell_claims
                   if c.get("psf_inr") and c["comparability"] in medians]
            if idx:
                metrics["price_index"] = statistics.median(v for v, _ in idx)
                mrefs["price_index"] = [c["claim_id"] for _, c in idx]
            for m in ("infra_points", "employment_points", "risk_points"):
                if points[cor][m]:
                    metrics[m] = points[cor][m]
                    mrefs[m] = sorted(set(refs[cor][m]))

            factors = {}
            for name, f in sc["factors"].items():
                if f["metric"] in metrics:
                    factors[name] = {"value": round(metrics[f["metric"]], 2),
                                     "score": _band(metrics[f["metric"]], f["bands"], f["direction"]),
                                     "claim_ids": mrefs[f["metric"]][:6]}
            ids = {i for f in factors.values() for i in f["claim_ids"]}
            led = {c["claim_id"]: c for c in ledger}
            for i in ids:
                if i in led:
                    total += 1
                    strong += led[i]["verification_status"] in ("verified_primary", "corroborated")
            share = strong / total if total else 0.0
            if len(factors) >= sc["confidence"]["high"]["min_factors"] and share >= sc["confidence"]["high"]["min_strong_share"]:
                conf = "High"
            elif len(factors) >= sc["confidence"]["medium"]["min_factors"] and share >= sc["confidence"]["medium"]["min_strong_share"]:
                conf = "Medium"
            else:
                conf = "Low"
            if len(factors) >= sc["min_factors_for_rank"]:
                wsum = sum(sc["factors"][k]["weight"] for k in factors)
                attract = round(sum(sc["factors"][k]["weight"] * v["score"] for k, v in factors.items()) / wsum, 2)
            else:
                attract = None
            cells.append({"corridor": cor, "region": corridors()[cor]["region"], "property_type": pt,
                          "factors": factors, "attractiveness": attract, "confidence": conf,
                          "strong_evidence_share": round(share, 2),
                          "rank_status": "Ranked" if attract is not None else "Unranked",
                          "unranked_reason": None if attract is not None else
                          f"only {len(factors)} of {len(sc['factors'])} factors evidenced (need {sc['min_factors_for_rank']})",
                          "scenarios": scenarios(rates, sc)})
    ranked = sorted((c for c in cells if c["attractiveness"] is not None),
                    key=lambda c: (-c["attractiveness"], c["corridor"], c["property_type"]))
    for i, c in enumerate(ranked, 1):
        c["rank"] = i
    return {"cells": cells, "price_medians": {k: round(v) for k, v in medians.items()}}


def _round(x: float, step: float) -> float:
    return round(round(x / step) * step, 2)


def scenarios(rates: list[tuple[float, dict]], sc: dict) -> dict:
    cfg = sc["scenarios"]
    groups = {c.get("origin_group") or c["group"] for _, c in rates}
    if len(groups) < cfg["min_appreciation_sources"]:
        return {"status": "Insufficient evidence to estimate",
                "reason": f"{len(groups)} independent appreciation source group(s); need {cfg['min_appreciation_sources']}",
                "evidence_claim_ids": [c["claim_id"] for _, c in rates]}
    hist = statistics.median(r for r, _ in rates)
    base = min(max(hist * cfg["base_haircut"], cfg["floor_pct"]), cfg["cap_pct"])
    rows = {}
    for name, delta in (("conservative", cfg["conservative_delta_pp"]), ("base", 0.0),
                        ("optimistic", cfg["optimistic_delta_pp"])):
        g = _round(min(max(base + delta, cfg["floor_pct"]), cfg["cap_pct"]), cfg["round_to"])
        rows[name] = {"annual_pct": g,
                      "real_annual_pct": round(real_rate(g, cfg["inflation_pct"]), 1),
                      "cumulative_pct": {str(y): round(cumulative_pct(g, y)) for y in cfg["horizons"]}}
    return {"status": "estimated", "historical_median_cagr_pct": round(hist, 1),
            "assumptions": (f"Base = {cfg['base_haircut']} x median historical CAGR ({hist:.1f}%) from "
                            f"{len(groups)} independent source groups, clamped to [{cfg['floor_pct']}%, {cfg['cap_pct']}%]; "
                            f"conservative {cfg['conservative_delta_pp']:+} pp, optimistic {cfg['optimistic_delta_pp']:+} pp; "
                            f"real = after {cfg['inflation_pct']}% inflation. Nominal capital appreciation only."),
            "scenarios": rows, "evidence_claim_ids": [c["claim_id"] for _, c in rates]}


def illustrations(cells: list[dict]) -> list[dict]:
    sc = load_config("scoring")
    out = []
    for cell in cells:
        s = cell["scenarios"]
        if s["status"] != "estimated":
            continue
        y = cell["factors"].get("rental_yield", {}).get("value")
        for years in sc["scenarios"]["horizons"]:
            out.append({"corridor": cell["corridor"], "property_type": cell["property_type"], "scenario": "base",
                        **illustrative_investment(sc["illustrative_investment"], cell["property_type"],
                                                  s["scenarios"]["base"]["annual_pct"], years, y,
                                                  inflation_pct=sc["scenarios"]["inflation_pct"])})
    return out
