"""Evening (18:00 IST) news refresh for the website.

Collects public RSS headlines and runs the metro + government research tasks over the last
12 hours, verifies the claims with the same rules as the daily pipeline, writes an evening
research note (reports/daily/<date>-evening.md) and data/app/news_refresh.json, which the
website merges ahead of the morning news. The Daily Edition PDF is NOT rebuilt (06:00 only).
"""
from __future__ import annotations

import concurrent.futures as cf
from datetime import timedelta

from harness import agent
from harness.collect_rss import collect as collect_rss
from harness.common import DATA, REPORTS, iso, load_config, now_ist, read_json, write_json, write_text
from harness.pipeline import _claim_record, _leads
from harness.runtime import Budget, Http, RunLog
from noise_removal.dedupe import dedupe_articles, syndication_clusters
from recheck.citations import check_url
from validation.verification import USABLE, evidenced_stage, stage_flags, verify

TASKS = ("metro_watch", "government_watch")
HOURS = 12


def refresh(log: RunLog | None = None) -> dict:
    now = now_ist()
    log = log or RunLog(now.date())
    window = (now - timedelta(hours=HOURS), now.replace(microsecond=0))
    budget = Budget.from_config()
    http = Http(budget, log)
    rss = collect_rss(now.date(), http, log)
    stories = dedupe_articles([i for i in rss["items"] if (i.get("published_at") or "") >= window[0].isoformat()])

    cfg = load_config("harness")["agent"]
    tasks = [t for t in load_config("research_tasks")["tasks"] if t["id"] in TASKS]
    schema = agent.findings_schema()
    out_dir = DATA / "raw" / now.date().isoformat() / "evening"
    ok, why = agent.available()

    def run(task):
        prompt = agent.build_research_prompt(task, window, _leads(rss["items"], task["lead_regions"], cfg["leads_per_task"]))
        return task["id"], agent.run_agent(prompt, schema, name=f"evening_{task['id']}", out_path=out_dir / f"{task['id']}.json",
                                           budget_usd=cfg["max_budget_usd_per_task"], timeout_min=cfg["task_timeout_minutes"], log=log)

    results = {}
    if ok:
        with cf.ThreadPoolExecutor(max_workers=2) as ex:
            results = dict(ex.map(run, tasks))
    else:
        log("evening_agent_skipped", reason=why)

    claims = {}
    for tid, res in results.items():
        if res.get("ok"):
            for raw in res["data"].get("claims", []):
                if raw.get("url", "").startswith("http"):
                    c = _claim_record(raw, f"evening:{tid}", res.get("finished") or iso(now), window)
                    claims.setdefault(c["claim_id"], c)
    claims = list(claims.values())
    for c in claims:
        c["evidenced_stage"] = evidenced_stage(c)
        c["flags"] = sorted(set(c["flags"]) | set(stage_flags(c)))
        if budget.take("citation", 60):
            chk = check_url(http, c["url"], c["excerpt"], source=f"citation:{c['domain']}")
            c["citation_check"] = chk
            if chk["result"] in ("confirmed", "failed"):
                c["flags"] = sorted(set(c["flags"]) | {f"citation_{chk['result']}"})
    claims, _ = verify(claims, syndication_clusters(claims))
    fresh = [c for c in claims if c["verification_status"] in USABLE
             and not {"outside_window", "republished_old_event"} & set(c["flags"])]

    data = {"generated_at": iso(now), "window": {"start": iso(window[0]), "end": iso(window[1])},
            "claims": fresh, "stories": [{"title": s["title"], "url": s["lead"]["url"], "publishers": s["publishers"],
                                          "published_at": s["published_at"], "regions": s["regions"]} for s in stories],
            "tasks": {t: {"ok": r.get("ok"), "error": r.get("error"), "cost_usd": r.get("cost_usd", 0)} for t, r in results.items()}}
    write_json(DATA / "app" / "news_refresh.json", data)
    write_text(REPORTS / "daily" / f"{now.date().isoformat()}-evening.md", note_md(data))
    log("evening_refresh", stories=len(stories), claims=len(fresh), usd=round(sum(r.get("cost_usd", 0) for r in results.values()), 2))
    return data


def note_md(data: dict) -> str:
    w = data["window"]
    L = [f"# Evening research note — {data['generated_at'][:10]}", "",
         f"Window (IST): {w['start']} → {w['end']} · generated {data['generated_at']}", ""]
    metro = [c for c in data["claims"] if c["origin"].endswith("metro_watch")]
    gov = [c for c in data["claims"] if not c["origin"].endswith("metro_watch")]
    for title, rows in (("Metro & rail", metro), ("Government & development", gov)):
        L += [f"## {title}", ""]
        L += [f"- {c['statement']} — [{c['publisher']}]({c['url']}) ({c['published_at'] or 'undated'})" for c in rows] or \
             ["- No new verified item in this window."]
        L.append("")
    L += ["## Headlines (last 12 hours)", ""]
    L += [f"- [{s['title']}]({s['url']}) — {', '.join(s['publishers'][:2])}" for s in data["stories"][:30]] or ["- None."]
    for t, r in data["tasks"].items():
        L.append(f"\n_Task {t}: {'ok' if r['ok'] else 'failed: ' + str(r['error'])}_")
    return "\n".join(L) + "\n"
