"""Corridor gazetteer and source registry lookups."""
from __future__ import annotations

import math
import re
from functools import lru_cache
from urllib.parse import urlparse

from harness.common import load_config


@lru_cache(maxsize=None)
def _alias_patterns() -> list[tuple[re.Pattern, str, str]]:
    cfg = load_config("corridors")
    out = []
    for cid, c in cfg["corridors"].items():
        for alias in c["aliases"]:
            out.append((re.compile(r"(?<![\w])" + re.escape(alias.lower()) + r"(?![\w])"), cid, alias))
    # longest alias first so "Sarjapur Road" beats "Sarjapur", "Old Madras Road" beats shorter hits
    out.sort(key=lambda t: -len(t[2]))
    return out


def corridors() -> dict:
    return load_config("corridors")["corridors"]


def region_of(corridor_id: str) -> str:
    return corridors().get(corridor_id, {}).get("region", "unmapped")


def match_corridors(text: str | None) -> list[str]:
    """All corridors mentioned, most specific (longest alias) first, without duplicates."""
    low = (text or "").lower()
    seen, out = set(), []
    masked = low
    for pat, cid, _ in _alias_patterns():
        if pat.search(masked):
            # mask the matched span so "Sarjapur" inside "Sarjapur Road" is not re-counted
            masked = pat.sub(" ", masked)
            if cid not in seen:
                seen.add(cid)
                out.append(cid)
    return out


def primary_corridor(*texts: str | None) -> str:
    """Single primary corridor for a record: first text that matches wins (locality before title)."""
    for t in texts:
        hits = match_corridors(t)
        if hits:
            return hits[0]
    return "unmapped"


def haversine_km(a: tuple[float, float], b: tuple[float, float]) -> float:
    lat1, lon1, lat2, lon2 = map(math.radians, (*a, *b))
    h = math.sin((lat2 - lat1) / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2
    return 2 * 6371 * math.asin(math.sqrt(h))


def geo_check(corridor_id: str, lat, lon) -> str | None:
    """Return a warning if a map reference is far from its text-assigned corridor."""
    if lat is None or lon is None or corridor_id not in corridors():
        return None
    cfg = load_config("corridors")
    dists = {cid: haversine_km((lat, lon), tuple(c["centroid"])) for cid, c in cfg["corridors"].items()
             if cfg["corridors"][cid]["region"] != "peripheral"}
    own = dists.get(corridor_id)
    nearest = min(dists, key=dists.get)
    if own is not None and own > cfg["geo_check_km"] and nearest != corridor_id:
        return f"geo_mismatch: map point is {own:.1f} km from {corridor_id} centroid; nearest is {nearest}"
    return None


@lru_cache(maxsize=None)
def _domains():
    return sorted(load_config("sources")["domains"], key=lambda d: -len(d["suffix"]))


def domain_of(url: str) -> str:
    host = urlparse(url or "").netloc.lower()
    return host[4:] if host.startswith("www.") else host


def classify_source(url: str, agent_kind: str | None = None) -> dict:
    """tier, independence group, interested-party flag and display name for a URL."""
    cfg = load_config("sources")
    host = domain_of(url)
    for d in _domains():
        if host == d["suffix"] or host.endswith("." + d["suffix"]):
            tier = d["tier"]
            info = {"tier": tier, "group": d["group"], "name": d["name"]}
            break
    else:
        tier = cfg["source_kind_tiers"].get(agent_kind or "other", "unknown")
        # unknown domains are their own independence group
        info = {"tier": tier, "group": f"domain:{host}", "name": host}
    t = cfg["tiers"][info["tier"]]
    info.update(interested_party=t["interested_party"], weight=t["weight"], domain=host)
    return info


def infra_links(subject: str | None) -> list[tuple[str, dict]]:
    """Reference infrastructure entries whose match phrases appear in the subject text."""
    low = (subject or "").lower().replace("–", "-").replace("—", "-")
    out = []
    for key, entry in load_config("corridors")["infrastructure_links"].items():
        if any(re.search(r"(?<![\w])" + re.escape(m.replace("–", "-")) + r"(?![\w])", low) for m in entry["match"]):
            out.append((key, entry))
    return out


# Original data producers often relayed by media. Two outlets quoting the same producer are ONE source.
ORIGINATORS = [
    (r"\banarock\b", "anarock"), (r"knight\s*frank", "knight_frank"), (r"\bjll\b", "jll"), (r"\bcbre\b", "cbre"),
    (r"\bcolliers\b", "colliers"), (r"prop\s*equity", "propequity"), (r"cushman", "cushman"), (r"\bsavills\b", "savills"),
    (r"magic\s*bricks", "times_group_portal"), (r"99\s*acres", "info_edge"), (r"housing\.com", "rea_india"),
    (r"\bproptiger\b", "rea_india"), (r"square\s*yards", "square_yards"), (r"\bnobroker\b", "nobroker"),
    (r"nhb\s*residex|residex", "nhb"), (r"\bcrisil\b", "crisil"), (r"\bcredai\b", "credai"),
]


def originator_group(*texts: str | None) -> str | None:
    low = " ".join(t for t in texts if t).lower()
    for pat, group in ORIGINATORS:
        if re.search(pat, low):
            return group
    return None
