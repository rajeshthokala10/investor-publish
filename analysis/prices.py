"""Price normalisation.

Converts quoted prices to INR per square foot ON THE SAME BASIS the source used.
It never converts between bases: a land rate for a plot and a super built-up rate for
an apartment stay in different comparability classes and are never ranked together.
"""
from __future__ import annotations

import re

SQFT_PER = {"sqft": 1.0, "sqyd": 9.0, "sqm": 10.7639, "acre": 43560.0, "guntha": 1089.0,
            "cent": 435.6, "hectare": 107639.0}
MONEY = [(re.compile(r"\b(crores?|cr)\b"), 1e7), (re.compile(r"\b(lakhs?|lacs?|lac|l)\b"), 1e5),
         (re.compile(r"\b(thousand|k)\b"), 1e3)]
AREA = [(re.compile(r"sq\.? ?f(ee)?t|sqft|sft|psf|square f(ee|oo)t"), "sqft"),
        (re.compile(r"sq\.? ?y(ar)?d|sqyd|square yards?|gaj"), "sqyd"),
        (re.compile(r"sq\.? ?m(etre|eter)?\b|sqm|square met"), "sqm"),
        (re.compile(r"\bacres?\b"), "acre"), (re.compile(r"\bguntas?|\bgunthas?"), "guntha"),
        (re.compile(r"\bcents?\b"), "cent"), (re.compile(r"\bhectares?\b"), "hectare")]

# Comparability: the same number means different things on different bases.
BASIS_CLASS = {"land": "land_rate", "carpet": "carpet_rate", "built_up": "built_up_rate",
               "super_built_up": "saleable_rate", "unknown": "unknown_basis", "na": "unknown_basis"}


def parse_unit(unit: str | None) -> tuple[float, str | None]:
    """('INR crore/acre') -> (1e7, 'acre'); ('INR/sqft') -> (1, 'sqft'); ('INR lakh') -> (1e5, None)."""
    u = (unit or "").lower().replace("₹", "inr ")
    mult = 1.0
    for pat, m in MONEY:
        if pat.search(u):
            mult = m
            break
    area = None
    for pat, a in AREA:
        if pat.search(u):
            area = a
            break
    return mult, area


def normalise_price(value, unit, basis: str, price_kind: str) -> dict:
    """Return per-sqft value (if the unit is per-area) or total INR, plus comparability class."""
    out = {"psf_inr": None, "total_inr": None, "basis": basis or "unknown",
           "comparability": f"{BASIS_CLASS.get(basis or 'unknown', 'unknown_basis')}|{price_kind or 'na'}",
           "normalisation_note": None}
    if value is None:
        out["normalisation_note"] = "no numeric value"
        return out
    mult, area = parse_unit(unit)
    if area:
        out["psf_inr"] = round(value * mult / SQFT_PER[area], 2)
        if area != "sqft":
            out["normalisation_note"] = f"converted from {unit} (1 {area} = {SQFT_PER[area]:g} sqft)"
    elif unit and re.search(r"inr|rs|rupee|₹|crore|lakh|cr\b", unit.lower()):
        out["total_inr"] = round(value * mult, 2)
    else:
        out["normalisation_note"] = f"unrecognised unit '{unit}'"
    return out


def comparable(a: dict, b: dict) -> bool:
    """Two normalised prices may be compared only on the same known basis and price kind."""
    return (a["comparability"] == b["comparability"]
            and not a["comparability"].startswith("unknown_basis")
            and a["psf_inr"] is not None and b["psf_inr"] is not None)


def conflicting(a: float, b: float, tolerance: float = 0.15) -> bool:
    lo, hi = sorted((a, b))
    return lo > 0 and (hi - lo) / lo > tolerance
