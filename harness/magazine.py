"""Monthly magazine edition: research -> process (verify) -> write -> render.

Research and verification reuse the daily pipeline's agent bridge, extraction, price
normalisation, syndication detection, citation checks and verification rules. Only
claims with a usable status (verified_primary / corroborated / single_source) or
attributed interested-party facts (e.g. a developer announcing its own launch) reach the
writer; unverified material is left out of the magazine rather than printed with a label.
"""
from __future__ import annotations

import concurrent.futures as cf
from datetime import datetime, timedelta
from pathlib import Path

from analysis.prices import normalise_price
from analysis.trackers import merge_projects, project_id, update_infra
from harness import agent
from harness.common import (DATA, IST, PROCESSED, PROMPTS, iso, load_config, now_ist, read_json, sha, write_json)
from harness.pipeline import _claim_record
from harness.registry import classify_source, geo_check, primary_corridor
from harness.runtime import Budget, Http, RunLock, RunLog
from noise_removal.dedupe import syndication_clusters
from recheck.citations import check_url
from validation.verification import USABLE, evidenced_stage, stage_flags, verify

MAG_RAW = DATA / "raw" / "magazine"
MAG_OUT = PROCESSED / "magazine"


def cfg() -> dict:
    return load_config("magazine")


def window(as_of: datetime) -> tuple[datetime, datetime]:
    return as_of - timedelta(days=30 * cfg()["lookback_months"]), as_of


def research(edition: str, log: RunLog) -> dict:
    c = cfg()
    out_dir = MAG_RAW / edition
    schema = agent.findings_schema()
    template = (PROMPTS / "magazine_research.md").read_text(encoding="utf-8")
    as_of = iso(now_ist())
    abudget = agent.AgentBudget(c["agent"]["max_budget_usd_per_run"])
    per = c["agent"]["max_budget_usd_per_task"]

    def run(task):
        path = out_dir / f"{task['id']}.json"
        prompt = (template.replace("{{TASK_ID}}", task["id"]).replace("{{FOCUS}}", task["focus"].strip())
                  .replace("{{AS_OF}}", as_of[:10]).replace("{{LOOKBACK}}", str(c["lookback_months"])))
        prior = read_json(path)
        if prior and prior.get("structured_output") and not prior.get("is_error"):
            log("magazine_reuse", task=task["id"])      # restart: never pay twice for one edition
            return task["id"], {"ok": True, "data": prior["structured_output"], "cost_usd": 0.0,
                                "finished": prior["finished"]}
        if not abudget.reserve(per):
            return task["id"], {"ok": False, "error": "magazine budget exhausted", "cost_usd": 0.0}
        res = agent.run_agent(prompt, schema, name=task["id"], out_path=path, budget_usd=per,
                              timeout_min=c["agent"]["task_timeout_minutes"], log=log)
        abudget.settle(per, res["cost_usd"])
        return task["id"], res

    with cf.ThreadPoolExecutor(max_workers=c["agent"]["parallel_tasks"]) as ex:
        results = dict(ex.map(run, c["tasks"]))
    summary = {t: {"ok": r["ok"], "error": r.get("error"), "cost_usd": r.get("cost_usd", 0)} for t, r in results.items()}
    write_json(out_dir / "_research_summary.json", summary)
    log("magazine_research_done", ok=sum(r["ok"] for r in results.values()), usd=round(abudget.spent, 2))
    return results


def process(edition: str, results: dict, log: RunLog) -> dict:
    """Extract, normalise, check citations, verify; merge into the shared ledger/trackers."""
    as_of = now_ist()
    win = window(as_of)
    claims, projects = {}, []
    for tid, res in results.items():
        if not res.get("ok"):
            continue
        retrieved = res.get("finished") or iso(as_of)
        for raw in res["data"].get("claims", []):
            if raw.get("url", "").startswith("http"):
                c = _claim_record(raw, f"magazine:{tid}", retrieved, win)
                c["flags"] = [f for f in c["flags"] if f != "outside_window"]   # lookback window, not 72h
                claims.setdefault(c["claim_id"], c)
        for p in res["data"].get("projects", []):
            if p.get("url", "").startswith("http"):
                src = classify_source(p["url"])
                cor = primary_corridor(p.get("locality"), p.get("name"))
                projects.append({**p, "project_id": project_id(p["name"], p.get("developer")), "corridor": cor,
                                 "tier": src["tier"], "retrieved_at": retrieved, "origin": f"magazine:{tid}",
                                 "publisher": p.get("publisher") or src["name"],
                                 "geo_flag": geo_check(cor, p.get("lat"), p.get("lon"))})
    claims = list(claims.values())
    # same figure from the same page extracted by two tasks -> one claim
    uniq = {}
    for c in claims:
        k = (c["url"], c["metric"], c["value"]) if c["metric"] != "none" and c["value"] is not None else (c["url"], c["statement"].lower())
        uniq.setdefault(k, c)
    claims = list(uniq.values())
    for c in claims:
        n = normalise_price(c["value"], c["unit"], c["price_basis"], c["price_kind"]) \
            if c["metric"] in ("price_psf", "price_total") else {"psf_inr": None, "total_inr": None, "comparability": "n/a"}
        c.update(psf_inr=n["psf_inr"], total_inr=n["total_inr"], comparability=n["comparability"])
        c["evidenced_stage"] = evidenced_stage(c)
        c["flags"] = sorted(set(c["flags"]) | set(stage_flags(c)))

    budget = Budget.from_config()
    budget.max_http = cfg()["citation_checks"] + 50
    http = Http(budget, log)
    checked = {}
    for c in sorted(claims, key=lambda c: c["interested_party"]):
        if budget.http_used >= cfg()["citation_checks"]:
            c["citation_check"] = {"result": "not_checked"}
            continue
        key = (c["url"], c["excerpt"])
        if key not in checked:
            checked[key] = check_url(http, c["url"], c["excerpt"], source=f"citation:{c['domain']}")
        c["citation_check"] = checked[key]
        if checked[key]["result"] == "confirmed":
            c["flags"] = sorted(set(c["flags"]) | {"citation_confirmed"})
        elif checked[key]["result"] == "failed":
            c["flags"] = sorted(set(c["flags"]) | {"citation_failed"})
    claims, contradictions = verify(claims, syndication_clusters(claims))
    for c in claims:
        c.setdefault("novelty", "background")
        c["first_seen"] = edition

    # shared evidence base: the daily scorer benefits from magazine research
    ledger = read_json(PROCESSED / "claims_ledger.json", {})
    for c in claims:
        ledger.setdefault(c["claim_id"], c)
    write_json(PROCESSED / "claims_ledger.json", ledger)
    tracker = read_json(PROCESSED / "projects.json", {})
    merge_projects(tracker, projects, f"magazine-{edition}")
    write_json(PROCESSED / "projects.json", tracker)
    infra = read_json(PROCESSED / "infrastructure.json", {})
    update_infra(infra, claims, f"magazine-{edition}")
    write_json(PROCESSED / "infrastructure.json", infra)

    data = {"edition": edition, "as_of": iso(as_of), "claims": claims, "projects": projects,
            "contradictions": contradictions,
            "coverage": {t: {"ok": r.get("ok"), "error": r.get("error")} for t, r in results.items()}}
    write_json(MAG_OUT / f"{edition}.json", data)
    from collections import Counter
    log("magazine_processed", claims=len(claims), **Counter(c["verification_status"] for c in claims))
    return data


def reverify(edition: str, log: RunLog) -> dict:
    """Re-run classification + verification on stored claims (keeps citation checks; no web calls).

    Used after source-registry or taxonomy updates."""
    data = read_json(MAG_OUT / f"{edition}.json")
    for c in data["claims"]:
        src = classify_source(c["url"])
        if not src["group"].startswith("domain:"):          # registry knows this domain now
            c.update(tier=src["tier"], group=src["group"], interested_party=src["interested_party"], domain=src["domain"])
            if c.get("origin_group", "").startswith("domain:") or not c.get("origin_group"):
                c["origin_group"] = src["group"]
        flags = set(c["flags"]) - {"interested_party", "stage_not_evidenced_in_excerpt", "stage_overstated"}
        if c["interested_party"]:
            flags.add("interested_party")
        c["evidenced_stage"] = evidenced_stage(c)
        c["flags"] = sorted(flags | set(stage_flags(c)))
        c["verification_status"] = "pending"
    claims, contradictions = verify(data["claims"], syndication_clusters(data["claims"]))
    data.update(claims=claims, contradictions=contradictions)
    write_json(MAG_OUT / f"{edition}.json", data)
    from collections import Counter
    log("magazine_reverified", **Counter(c["verification_status"] for c in claims))
    return data


def publishable(c: dict) -> bool:
    """What may appear in the magazine: usable evidence, or a party's own announcement, attributed."""
    if c["verification_status"] in USABLE:
        return True
    bad = {"unsupported_guarantee", "citation_failed", "recheck_failed", "stage_overstated", "marketing_language"}
    return (c["verification_status"] == "interested_party_claim" and not bad & set(c["flags"])
            and c["tier"] in ("developer", "research_house", "operator")
            and (c.get("citation_check") or {}).get("result") == "confirmed")


def run_magazine(edition: str | None = None, from_step: str = "research") -> int:
    edition = edition or now_ist().strftime("%Y-%m")
    lock = RunLock(DATA.parent / "logs" / ".magazine.lock")
    if not lock.acquire():
        print("Another magazine run is in progress")
        return 4
    log = RunLog(now_ist().date())
    try:
        steps = ["research", "process", "verify", "write", "render"]
        start = steps.index(from_step)
        results = None
        if start <= 0:
            results = research(edition, log)
        if start <= 1:
            if results is None:
                results = {p.stem: {"ok": True, "data": read_json(p)["structured_output"], "finished": read_json(p)["finished"]}
                           for p in sorted((MAG_RAW / edition).glob("mag_*.json")) if read_json(p).get("structured_output")}
            process(edition, results, log)
        from harness.magazine_write import write_issue
        from harness.magazine_render import render_issue
        if start <= 2:
            reverify(edition, log)
        if start <= 3:
            write_issue(edition, log)
        path = render_issue(edition, log)
        print(f"Magazine: {path}")
        return 0
    finally:
        lock.release()
