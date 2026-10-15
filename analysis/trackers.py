"""Persistent project and infrastructure trackers (data/processed/)."""
from __future__ import annotations

from analysis.prices import normalise_price
from harness.common import norm_text, sha
from harness.registry import infra_links, region_of
from noise_removal.dedupe import subject_key
from validation.verification import USABLE

STAGES = ["proposed", "announced", "approved", "funded", "tendered", "awarded", "under_construction", "operational"]
PROJECT_FIELDS = ["developer", "locality", "property_type", "launch_date", "status", "unit_sizes", "charges_included",
                  "charges_excluded", "possession", "lat", "lon"]


def project_id(name: str, developer: str | None) -> str:
    dev = norm_text(developer or "").split()
    return "P-" + sha(subject_key(name), dev[0] if dev else "")


def merge_projects(tracker: dict, records: list[dict], edition: str) -> list[str]:
    """Upsert project records; returns ids first seen in this edition."""
    new = []
    for r in records:
        pid = r["project_id"]
        p = tracker.get(pid)
        if p is None:
            p = tracker[pid] = {"project_id": pid, "name": r["name"], "first_seen": edition,
                                "sources": [], "price_observations": [], "rera": {"number": None, "status": "Not verified"},
                                "open_questions": [], "flags": [], "infra_links": []}
            for f in PROJECT_FIELDS:
                p[f] = None
            new.append(pid)
        p["last_seen"] = edition
        p["corridor"], p["region"] = r["corridor"], region_of(r["corridor"])
        for f in PROJECT_FIELDS:
            if r.get(f) not in (None, "", "unknown"):
                if p.get(f) not in (None, "", "unknown") and p[f] != r[f] and f in ("launch_date", "possession", "developer"):
                    p["flags"].append(f"conflict:{f}: '{p[f]}' vs '{r[f]}' ({r['url']})")
                p[f] = r[f]
        if r.get("rera_number"):
            if p["rera"]["number"] and p["rera"]["number"] != r["rera_number"]:
                p["flags"].append(f"conflict:rera_number: {p['rera']['number']} vs {r['rera_number']}")
            p["rera"]["number"] = r["rera_number"]
            p["rera"]["status"] = (f"Agent reported seeing it on the K-RERA portal ({edition}); not independently re-checked"
                                   if r.get("rera_checked_on_portal") else "Not verified")
            p["rera"]["checked_on"] = edition if r.get("rera_checked_on_portal") else None
        src = {"url": r["url"], "publisher": r["publisher"], "tier": r["tier"], "published_at": r["published_at"],
               "retrieved_at": r["retrieved_at"], "excerpt": r["excerpt"]}
        if all(s["url"] != src["url"] for s in p["sources"]):
            p["sources"].append(src)
        if r.get("price_min") is not None:
            for label, val in (("min", r["price_min"]), ("max", r.get("price_max"))):
                if val is None:
                    continue
                n = normalise_price(val, r.get("price_unit"), r.get("price_basis"), r.get("price_kind"))
                obs = {"bound": label, "value": val, "unit": r.get("price_unit"), "basis": r.get("price_basis"),
                       "kind": r.get("price_kind"), "psf_inr": n["psf_inr"], "total_inr": n["total_inr"],
                       "comparability": n["comparability"], "url": r["url"], "edition": edition}
                if not any(o["url"] == obs["url"] and o["bound"] == label and o["value"] == val for o in p["price_observations"]):
                    p["price_observations"].append(obs)
        for q in r.get("open_questions", []):
            if q not in p["open_questions"]:
                p["open_questions"].append(q)
        for link in r.get("infra_links", []):
            if link not in p["infra_links"]:
                p["infra_links"].append(link)
        if r.get("geo_flag") and r["geo_flag"] not in p["flags"]:
            p["flags"].append(r["geo_flag"])
        p["flags"] = sorted(set(p["flags"]))
        p["confidence"] = ("Medium" if any(s["tier"] in ("primary_official", "regulator", "reputable_media") for s in p["sources"])
                           and len(p["sources"]) >= 2 else "Low")
    return new


def rollback_edition(tracker: dict, edition: str) -> None:
    """Undo stage moves made by `edition` so re-analysis (e.g. after a recheck downgrade) starts clean."""
    for key in list(tracker):
        item = tracker[key]
        item["stage_history"] = [h for h in item["stage_history"] if h["edition"] != edition]
        item["stage"] = item["stage_history"][-1]["stage"] if item["stage_history"] else None
        item["notes"] = [n for n in item["notes"] if not n.startswith(edition + ":")]
        if item.get("first_seen") == edition and not item["stage_history"]:
            del tracker[key]


def update_infra(tracker: dict, claims: list[dict], edition: str) -> list[dict]:
    """Apply infrastructure/policy claims. Only usable claims with an evidenced stage move a stage.

    Returns stage-change events. Stages never move backwards silently: a lower stage
    from a later source is recorded as a note for review.
    """
    events = []
    for c in claims:
        if c["claim_type"] not in ("infrastructure", "policy", "legal"):
            continue
        links = infra_links(c["subject"])
        key = links[0][0] if links else "X-" + sha(subject_key(c["subject"]))
        item = tracker.setdefault(key, {
            "infra_id": key, "name": links[0][1]["name"] if links else c["subject"], "type": c["claim_type"],
            "stage": None, "stage_history": [], "corridors": [], "claim_ids": [], "notes": [], "first_seen": edition})
        cors = set(item["corridors"]) | ({c["corridor"]} if c["corridor"] != "unmapped" else set())
        for _, e in links:
            cors |= set(e["corridors"])
        item["corridors"] = sorted(cors)
        if c["claim_id"] not in item["claim_ids"]:
            item["claim_ids"].append(c["claim_id"])
        item["last_seen"] = edition
        stage = c.get("evidenced_stage")
        if not stage or c["verification_status"] not in USABLE:
            continue
        prev = item["stage"]
        if prev is None or STAGES.index(stage) > STAGES.index(prev):
            item["stage"] = stage
            entry = {"stage": stage, "event_date": c["event_date"], "published_at": c["published_at"],
                     "claim_id": c["claim_id"], "edition": edition}
            if not any(h["claim_id"] == c["claim_id"] for h in item["stage_history"]):
                item["stage_history"].append(entry)
                events.append({"infra_id": key, "name": item["name"], "from": prev, "to": stage,
                               "claim_id": c["claim_id"], "corridors": item["corridors"]})
        elif STAGES.index(stage) < STAGES.index(prev):
            note = f"{edition}: source {c['claim_id']} describes stage '{stage}' (tracked: '{prev}') - review"
            if note not in item["notes"]:
                item["notes"].append(note)
    return events
