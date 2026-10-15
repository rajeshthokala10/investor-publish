"""Discover -> Collect -> Extract -> Normalise -> Deduplicate -> Verify -> Analyse -> Recheck -> Publish -> Archive.

Each stage reads the previous stage's checkpoint (data/runs/<edition>/<stage>.json)
and writes its own. A restarted run skips completed stages. Outputs for an edition
are written to fixed paths, so re-running an edition overwrites rather than duplicates.
"""
from __future__ import annotations

import concurrent.futures as cf
from dataclasses import dataclass
from pathlib import Path
from datetime import date, datetime, timedelta

from analysis.model import build_model, illustrations
from analysis.prices import normalise_price
from analysis.trackers import merge_projects, project_id, rollback_edition, update_infra
from harness import agent
from harness.collect_rss import collect as collect_rss
from harness.common import (HISTORY, IST, PROCESSED, PROMPTS, iso, load_config, now_ist, parse_date, read_json, sha,
                            write_json)
from harness.registry import classify_source, geo_check, originator_group, primary_corridor, region_of
from harness.runtime import Budget, BudgetExceeded, Checkpoints, Http, RunLog
from noise_removal.dedupe import (classify_against_history, dedupe_articles, staleness, story_fingerprint,
                                  syndication_clusters)
from noise_removal.marketing import flags_for, marketing_profile
from harness.report import archive_edition, render_daily
from recheck.citations import check_url
from recheck.recheck import run_recheck
from validation.verification import USABLE, evidenced_stage, stage_flags, verify

STAGES = ["discover", "collect", "extract", "normalise", "deduplicate", "verify", "analyse", "recheck", "publish", "archive"]


@dataclass
class Ctx:
    edition: date
    window: tuple[datetime, datetime]
    log: RunLog
    budget: Budget
    http: Http
    ckpt: Checkpoints
    offline_findings: str | None = None   # path to findings fixture (tests / replays): skips live collection


# ----------------------------------------------------------------------------------- discover
def discover(ctx: Ctx, _prev) -> dict:
    tasks = load_config("research_tasks")["tasks"]
    baseline = read_json(PROCESSED / "market_baseline.json", {})
    refresh = load_config("harness")["agent"]["baseline_refresh_days"]
    last = parse_date(baseline.get("refreshed_on"))
    due = last is None or (ctx.edition - last).days >= refresh
    planned = [t for t in tasks if t["cadence"] == "daily" or (t["cadence"] == "baseline" and due)]
    ok, why = agent.available()
    src = load_config("sources")
    return {"window": {"start": iso(ctx.window[0]), "end": iso(ctx.window[1])},
            "rss_feeds": len(src["rss_feeds"]), "google_news_queries": len(src["google_news"]["queries"]),
            "agent_available": ok, "agent_note": why, "tasks": planned,
            "skipped_tasks": [{"id": t["id"], "reason": "baseline fresh"} for t in tasks if t not in planned],
            "known_unavailable": src["known_unavailable"]}


# ------------------------------------------------------------------------------------ collect
def _leads(items, regions, n):
    picked = [i for i in items if set(i["regions"]) & set(regions)]
    picked.sort(key=lambda i: i.get("published_at") or "", reverse=True)
    seen, out = set(), []
    for i in picked:
        k = story_fingerprint(i["title"])
        if k not in seen:
            seen.add(k)
            out.append(i)
    return out[:n]


def collect(ctx: Ctx, plan: dict) -> dict:
    if ctx.offline_findings:
        fx = read_json(Path(ctx.offline_findings))
        return {"rss": fx["rss"], "agent_results": fx["agent_results"], "mode": "offline-fixture"}
    rss = collect_rss(ctx.edition, ctx.http, ctx.log)
    cfg = load_config("harness")["agent"]
    results = {}
    if not plan["agent_available"]:
        ctx.log("agent_skipped", reason=plan["agent_note"])
        return {"rss": rss, "agent_results": {t["id"]: {"ok": False, "error": plan["agent_note"]} for t in plan["tasks"]},
                "mode": "live"}
    abudget = agent.AgentBudget(cfg["max_budget_usd_per_run"])
    out_dir = agent.raw_agent_dir(ctx.edition)
    schema = agent.findings_schema()

    def run_task(task):
        path = out_dir / f"{task['id']}.json"
        prompt = agent.build_research_prompt(task, ctx.window, _leads(rss["items"], task["lead_regions"],
                                                                      cfg["leads_per_task"]))
        prior = read_json(path)
        # Reuse within an edition unless the prompt template or the task focus changed (RSS leads
        # differ on every collection, so they are not part of the key - restarts never pay twice).
        template = PROMPTS / "research_agent.md"
        key = sha(template.read_text(encoding="utf-8"), task["focus"], task["cadence"])
        if prior and prior.get("structured_output") and not prior.get("is_error") \
                and prior.get("prompt_key") == key:
            ctx.log("agent_reuse_checkpoint", task=task["id"])        # restart: do not pay twice
            return task["id"], {"ok": True, "data": prior["structured_output"], "cost_usd": 0.0,
                                "started": prior["started"], "finished": prior["finished"], "reused": True}
        per = cfg["max_budget_usd_per_task"]
        if not abudget.reserve(per):
            return task["id"], {"ok": False, "error": "run agent budget exhausted", "cost_usd": 0.0}
        remaining_min = max(ctx.budget.time_left() / 60 - 10, 1)
        res = agent.run_agent(prompt, schema, name=task["id"], out_path=path, budget_usd=per, prompt_key=key,
                              timeout_min=min(cfg["task_timeout_minutes"], remaining_min), log=ctx.log)
        abudget.settle(per, res["cost_usd"])
        return task["id"], res

    with cf.ThreadPoolExecutor(max_workers=cfg["parallel_tasks"]) as ex:
        for tid, res in ex.map(run_task, plan["tasks"]):
            results[tid] = res
    ctx.log("collect_done", agent_ok=sum(r["ok"] for r in results.values()), agent_usd=round(abudget.spent, 2))
    return {"rss": rss, "agent_results": results, "agent_usd": round(abudget.spent, 2), "mode": "live"}


# ------------------------------------------------------------------------------------ extract
def _claim_record(raw: dict, task: str, retrieved_at: str, window) -> dict:
    src = classify_source(raw["url"], raw.get("source_kind"))
    corridor = primary_corridor(raw.get("locality"), raw.get("subject"), raw.get("statement"))
    prof = marketing_profile(raw.get("excerpt"), raw.get("statement"))
    flags = flags_for(prof) + staleness(raw.get("published_at"), raw.get("event_date"), window)
    if src["interested_party"]:
        flags.append("interested_party")
    origin = originator_group(raw.get("excerpt"), raw.get("statement"))
    if origin and origin != src["group"]:
        flags.append(f"relays:{origin}")
    return {
        "origin_group": origin or src["group"],
        "claim_id": "C-" + sha(raw["url"], raw["statement"], raw["metric"], raw.get("value")),
        "statement": raw["statement"].strip(), "claim_type": raw["claim_type"], "subject": raw["subject"].strip(),
        "locality": raw.get("locality"), "corridor": corridor, "region": region_of(corridor),
        "property_type": raw["property_type"], "url": raw["url"].strip(), "domain": src["domain"],
        "publisher": raw.get("publisher") or src["name"], "tier": src["tier"], "group": src["group"],
        "interested_party": src["interested_party"], "published_at": raw.get("published_at"),
        "event_date": raw.get("event_date"), "retrieved_at": retrieved_at, "excerpt": (raw.get("excerpt") or "").strip(),
        "metric": raw["metric"], "value": raw.get("value"), "value_max": raw.get("value_max"), "unit": raw.get("unit"),
        "period_years": raw.get("period_years"), "price_basis": raw.get("price_basis", "na"),
        "price_kind": raw.get("price_kind", "na"), "infra_stage": raw.get("infra_stage", "none"),
        "verification_status": "pending", "confidence": "pending", "confidence_reason": "",
        "flags": sorted(set(flags)), "marketing": prof, "origin": f"agent:{task}",
    }


def extract(ctx: Ctx, col: dict) -> dict:
    claims, projects, unavailable, coverage = {}, [], [], {}
    for tid, res in col["agent_results"].items():
        coverage[tid] = {"ok": res.get("ok", False), "error": res.get("error"), "cost_usd": res.get("cost_usd", 0)}
        if not res.get("ok"):
            continue
        data, retrieved = res["data"], res.get("finished") or iso(now_ist())
        for s in data.get("sources_attempted", []):
            if s["status"] not in ("ok", "not_attempted"):
                unavailable.append({"task": tid, **s})
        for raw in data.get("claims", []):
            if not raw.get("url", "").startswith("http"):
                continue
            c = _claim_record(raw, tid, retrieved, ctx.window)
            claims.setdefault(c["claim_id"], c)
        for p in data.get("projects", []):
            if not p.get("url", "").startswith("http"):
                continue
            src = classify_source(p["url"])
            cor = primary_corridor(p.get("locality"), p.get("name"))
            projects.append({**p, "project_id": project_id(p["name"], p.get("developer")), "corridor": cor,
                             "tier": src["tier"], "retrieved_at": retrieved, "origin": f"agent:{tid}",
                             "geo_flag": geo_check(cor, p.get("lat"), p.get("lon"))})
        coverage[tid]["notes"] = data.get("notes")
    ctx.log("extracted", claims=len(claims), projects=len(projects))
    return {"claims": list(claims.values()), "projects": projects, "articles": col["rss"]["items"],
            "unavailable": unavailable, "coverage": coverage,
            "feeds": {"ok": col["rss"]["feeds_ok"], "failed": col["rss"]["feeds_failed"]}}


# ---------------------------------------------------------------------------------- normalise
def normalise(ctx: Ctx, ex: dict) -> dict:
    for c in ex["claims"]:
        n = normalise_price(c["value"], c["unit"], c["price_basis"], c["price_kind"]) \
            if c["metric"] in ("price_psf", "price_total") else {"psf_inr": None, "total_inr": None,
                                                                 "comparability": "n/a", "normalisation_note": None}
        c.update(psf_inr=n["psf_inr"], total_inr=n["total_inr"], comparability=n["comparability"],
                 normalisation_note=n["normalisation_note"])
        if c["metric"] == "price_psf" and c["price_basis"] == "unknown":
            c["flags"] = sorted(set(c["flags"]) | {"price_basis_unknown"})
    return ex


# -------------------------------------------------------------------------------- deduplicate
def deduplicate(ctx: Ctx, ex: dict) -> dict:
    seen = read_json(HISTORY / "seen_stories.json", {})
    ed = ctx.edition.isoformat()
    # exact duplicate claims: same URL + same normalised statement
    # and the same figure from the same page extracted twice (e.g. by two research tasks)
    uniq = {}
    for c in ex["claims"]:
        k = (c["url"], c["metric"], c["value"]) if c["metric"] != "none" and c["value"] is not None \
            else (c["url"], c["statement"].lower())
        uniq.setdefault(k, c)
    claims = list(uniq.values())
    syn = syndication_clusters(claims)
    for c in claims:
        fp = "F-" + sha(c["subject"].lower(), c["metric"], c["value"], c["infra_stage"])
        c["fact_key"] = fp
        story = "S-" + sha(c["url"])
        prev = seen.get(story)
        c["novelty"] = "new" if not prev or prev.get("first_seen") == ed else \
            classify_against_history(story, {fp}, seen)
    stories = dedupe_articles(ex["articles"])
    for s in stories:
        prev = seen.get(s["story_id"])
        s["novelty"] = "new" if not prev or prev.get("first_seen") == ed else \
            classify_against_history(s["story_id"], {s["lead"]["canonical_url"]}, seen)
        s["stale_flags"] = staleness(s["published_at"], None, ctx.window)
    ex.update(claims=claims, stories=stories, syndication=syn)
    ctx.log("deduplicated", claims=len(claims), stories=len(stories),
            repeats=sum(s["novelty"] == "repeat" for s in stories))
    return ex


# ------------------------------------------------------------------------------------- verify
def _priority(c):
    order = {"infrastructure": 0, "policy": 0, "legal": 1, "project_launch": 1, "price": 2, "appreciation": 2,
             "rental": 2, "employment": 3, "supply_demand": 3, "civic_risk": 3}
    return (c["region"] != "east", order.get(c["claim_type"], 4), c["interested_party"])


def verify_stage(ctx: Ctx, d: dict) -> dict:
    limit = load_config("harness")["budgets"]["max_citation_checks"]
    for c in sorted(d["claims"], key=_priority):
        if not ctx.budget.take("citation", limit) or ctx.budget.time_left() < 600:
            c["citation_check"] = {"result": "not_checked", "note": "citation budget"}
            continue
        chk = check_url(ctx.http, c["url"], c["excerpt"], source=f"citation:{c['domain']}")
        c["citation_check"] = chk
        if chk["result"] == "confirmed":
            c["flags"] = sorted(set(c["flags"]) | {"citation_confirmed"})
        elif chk["result"] == "failed":
            c["flags"] = sorted(set(c["flags"]) | {"citation_failed"})
    for c in d["claims"]:
        c["evidenced_stage"] = evidenced_stage(c)
        c["flags"] = sorted(set(c["flags"]) | set(stage_flags(c)))
    claims, contradictions = verify(d["claims"], d["syndication"])
    d["contradictions"] = contradictions
    ctx.log("verified", **{s: sum(c["verification_status"] == s for c in claims)
                           for s in ("verified_primary", "corroborated", "single_source", "interested_party_claim",
                                     "unverified", "contradicted")})
    return d


# ------------------------------------------------------------------------------------ analyse
def analyse(ctx: Ctx, d: dict) -> dict:
    ed = ctx.edition.isoformat()
    ledger = read_json(PROCESSED / "claims_ledger.json", {})
    for c in d["claims"]:
        prev = ledger.get(c["claim_id"])
        c["first_seen"] = prev["first_seen"] if prev else ed
        ledger[c["claim_id"]] = c
    projects = read_json(PROCESSED / "projects.json", {})
    for p in d["projects"]:
        p["publisher"] = p.get("publisher") or classify_source(p["url"])["name"]
    merge_projects(projects, d["projects"], ed)
    infra = read_json(PROCESSED / "infrastructure.json", {})
    rollback_edition(infra, ed)
    update_infra(infra, d["claims"], ed)
    d["model"] = build_model(list(ledger.values()), infra, ctx.edition)
    d["illustrations"] = illustrations(d["model"]["cells"])
    d["stage_changes"] = [{"infra_id": k, "name": v["name"], "corridors": v["corridors"], **h,
                           "from": (v["stage_history"][i - 1]["stage"] if i else None)}
                          for k, v in infra.items() for i, h in enumerate(v["stage_history"]) if h["edition"] == ed]
    d["projects_today"] = sorted({p["project_id"] for p in d["projects"]})
    write_json(PROCESSED / "claims_ledger.json", ledger)
    write_json(PROCESSED / "projects.json", projects)
    write_json(PROCESSED / "infrastructure.json", infra)
    if d["coverage"].get("market_baseline", {}).get("ok"):
        write_json(PROCESSED / "market_baseline.json", {"refreshed_on": ed,
                                                        "claim_ids": [c["claim_id"] for c in d["claims"]
                                                                      if c["origin"] == "agent:market_baseline"]})
    return d


# ------------------------------------------------------------------------------------ recheck
def recheck_stage(ctx: Ctx, d: dict) -> dict:
    return run_recheck(ctx, d, reanalyse=analyse)


# ------------------------------------------------------------------------------------ publish
def publish(ctx: Ctx, d: dict) -> dict:
    return render_daily(ctx, d)


# ------------------------------------------------------------------------------------ archive
def archive(ctx: Ctx, d: dict) -> dict:
    return archive_edition(ctx, d)


STAGE_FUNCS = {"discover": discover, "collect": collect, "extract": extract, "normalise": normalise,
               "deduplicate": deduplicate, "verify": verify_stage, "analyse": analyse, "recheck": recheck_stage,
               "publish": publish, "archive": archive}


def run_pipeline(ctx: Ctx) -> dict:
    prev = None
    for stage in STAGES:
        if ctx.ckpt.done(stage):
            ctx.log("stage_skip_checkpoint", stage=stage)
            prev = ctx.ckpt.load(stage)
            continue
        try:
            ctx.budget.check_time(stage)
        except BudgetExceeded as e:
            ctx.log("budget_exceeded", stage=stage, detail=str(e))
            if stage in ("publish", "archive", "recheck"):
                pass      # always try to publish what was verified, with partial-coverage banner
            else:
                prev = dict(prev or {}, budget_exceeded_at=stage)
                ctx.ckpt.save(stage, prev, status="skipped_budget")
                continue
        ctx.log("stage_start", stage=stage)
        out = STAGE_FUNCS[stage](ctx, prev)
        ctx.ckpt.save(stage, out)
        ctx.log("stage_done", stage=stage)
        prev = out
    return prev
