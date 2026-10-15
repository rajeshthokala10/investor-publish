"""One batch job for the whole application.

  daily     72-hour research pipeline -> daily brief (MD/HTML/JSON/5-page PDF)
  magazine  monthly magazine, built when the current month has no issue yet
  weekly    weekly summary on the configured weekday
  metrics   dashboard KPIs, growth series, area prices, top builders (validated)
  site      data/app/site.json + downloads for the web app
  refresh   evening news refresh (RSS + metro/government research, last 12 h) -> website news
  email     "Bangalore RealEstate Delta" email to EMAIL_TO + subscribers (dry run without SMTP settings)

Each step is recorded in the app database (job_runs) so the website can show
when data was last refreshed and whether the run was complete.
"""
from __future__ import annotations

import traceback

from harness.common import DATA, LOGS, REPORTS, load_config, now_ist
from harness.runtime import RunLock, RunLog


def run_batch(steps: list[str] | None = None, force_magazine: bool = False) -> int:
    from app import store
    from app.site_data import build_site
    from harness.cli import do_run
    from harness.magazine import run_magazine
    from harness.metrics_build import build_metrics
    from harness.weekly import build_weekly

    steps = steps or ["daily", "magazine", "weekly", "metrics", "site", "email"]
    lock = RunLock(LOGS / ".batch.lock")
    if not lock.acquire():
        print("Another batch is running")
        return 4
    today = now_ist().date()
    log = RunLog(today)
    job = store.start_job()
    results, rc = {}, 0
    try:
        for step in steps:
            try:
                if step == "daily":
                    code = do_run(today)
                    results[step] = {0: "ok", 2: "research_failed", 3: "blocked_by_gate", 4: "locked"}.get(code, f"error {code}")
                    rc = rc or (code if code in (2, 3) else 0)
                elif step == "magazine":
                    month = today.strftime("%Y-%m")
                    exists = (REPORTS / "magazine" / f"bengaluru-property-review-{month}.pdf").exists()
                    if exists and not force_magazine:
                        results[step] = "skipped (issue exists for this month)"
                    else:
                        results[step] = "ok" if run_magazine(month, "research") == 0 else "failed"
                elif step == "weekly":
                    if now_ist().strftime("%A") == load_config("schedule")["weekly_summary_day"]:
                        results[step] = f"ok ({build_weekly(today)['editions']} editions)"
                    else:
                        results[step] = "skipped (not weekly day)"
                elif step == "metrics":
                    m = build_metrics(log)
                    results[step] = f"ok ({len(m['kpis'])} KPIs, {len(m['series'])} series, {len(m['builders'])} builders)"
                elif step == "site":
                    s = build_site(log)
                    results[step] = f"ok ({len(s['news']['headlines'])} headlines)"
                elif step == "refresh":
                    from harness.news_refresh import refresh
                    r = refresh(log)
                    results[step] = f"ok ({len(r['stories'])} headlines, {len(r['claims'])} verified items)"
                elif step == "email":
                    from harness.mailer import send_delta
                    r = send_delta(today.isoformat(), log=log)
                    results[step] = f"{r['status']} ({r.get('mode', '')}, {r.get('sent', 0)} sent)"
            except SystemExit as e:
                results[step] = f"failed: {e}"
                rc = rc or 1
            except Exception:
                results[step] = "error: " + traceback.format_exc(limit=2)[-300:]
                rc = rc or 1
            log("batch_step", step=step, result=results[step])
        status = "ok" if rc == 0 else "partial"
        store.finish_job(job, status, results)
        return rc
    finally:
        lock.release()
