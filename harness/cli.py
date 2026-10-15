"""Command line entry point: python -m harness.cli <command>

  run        [--edition YYYY-MM-DD] [--force] [--from-stage STAGE] [--offline FIXTURE] [--no-agent]
  scheduled  run as launchd does: honours pause flag, retries with backoff, weekly on configured day
  status     last run, lock holder, scheduler state, next run
  pause | resume
  schedule   install | uninstall | status
  weekly     [--week-ending YYYY-MM-DD]

Exit codes: 0 ok / no_new_updates / partial, 2 research failed, 3 publication blocked,
4 another run holds the lock, 5 paused, 1 unexpected error.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import traceback
from datetime import date, datetime

from harness import scheduler
from harness.common import DATA, LOGS, ROOT, edition_window, load_config, now_ist, read_json
from harness.pipeline import STAGES, Ctx, run_pipeline
from harness.runtime import Budget, Checkpoints, Http, RunLock, RunLog

PAUSE = DATA / ".paused"


def do_run(edition: date, force=False, from_stage=None, offline=None, no_agent=False) -> int:
    lock = RunLock()
    if not lock.acquire():
        print(f"Another run is in progress: {lock.holder()}", file=sys.stderr)
        return 4
    try:
        log = RunLog(edition)
        if no_agent or offline:
            load_config("harness")["agent"]["enabled"] = False
        budget = Budget.from_config()
        if offline:
            budget.max_http = 0          # replays never touch the network
        ckpt = Checkpoints(edition)
        if force:
            ckpt.reset(None, STAGES)
        elif from_stage:
            ckpt.reset(from_stage, STAGES)
        saved = ckpt.manifest.get("window")
        if saved and not force:          # restarts keep the edition's original window (idempotent)
            window = tuple(datetime.fromisoformat(x) for x in saved)
        else:
            window = edition_window(edition)
            ckpt.manifest["window"] = [w.isoformat() for w in window]
        log("run_start", edition=edition.isoformat(), window_start=window[0].isoformat(),
            window_end=window[1].isoformat(), offline=bool(offline))
        ctx = Ctx(edition=edition, window=window, log=log, budget=budget, http=Http(budget, log), ckpt=ckpt,
                  offline_findings=offline)
        try:
            result = run_pipeline(ctx)
        except SystemExit as e:
            log("run_blocked", detail=str(e))
            return 3
        status = (result or {}).get("status", "unknown")
        log("run_end", status=status, http_requests=budget.http_used)
        return 2 if status == "failed" else 0
    except Exception:
        RunLog(edition)("run_error", detail=traceback.format_exc()[-2000:])
        traceback.print_exc()
        return 1
    finally:
        lock.release()


def do_scheduled() -> int:
    if PAUSE.exists():
        RunLog(now_ist().date())("scheduled_skip_paused", since=PAUSE.read_text().strip())
        return 5
    sched = load_config("schedule")
    edition = now_ist().date()
    rc = 1
    for attempt in range(1, sched["retries"]["max_attempts"] + 1):
        rc = do_run(edition)
        RunLog(edition)("scheduled_attempt", attempt=attempt, rc=rc)
        if rc in (0, 3, 4, 5):       # success, blocked (needs a human), already running, paused
            break
        if attempt < sched["retries"]["max_attempts"]:
            time.sleep(sched["retries"]["backoff_minutes"][attempt - 1] * 60)
    # rest of the application batch: monthly magazine, weekly summary, dashboard metrics, website data
    from harness.batch import run_batch
    run_batch(["magazine", "weekly", "clusters", "builders", "metrics", "site", "publish"] + (["email"] if rc == 0 else []))
    return rc


def do_status() -> int:
    lock = RunLock()
    runs = sorted((DATA / "runs").glob("*/manifest.json"))
    last = read_json(runs[-1]) if runs else None
    print(json.dumps({"root": str(ROOT), "lock": lock.holder() or "free", "paused": PAUSE.exists(),
                      "last_run_manifest": last, "scheduler": scheduler.status()}, indent=2, default=str))
    return 0


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="harness.cli")
    sub = p.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run")
    r.add_argument("--edition", type=date.fromisoformat, default=None)
    r.add_argument("--force", action="store_true", help="ignore checkpoints and redo every stage")
    r.add_argument("--from-stage", choices=STAGES)
    r.add_argument("--offline", help="findings fixture JSON (tests/replays); no live collection")
    r.add_argument("--no-agent", action="store_true", help="RSS-only run (no LLM research)")
    sub.add_parser("scheduled")
    sub.add_parser("status")
    sub.add_parser("pause")
    sub.add_parser("resume")
    s = sub.add_parser("schedule")
    s.add_argument("action", choices=["install", "uninstall", "status"])
    b = sub.add_parser("batch")
    b.add_argument("--steps", default=None, help="comma list: daily,magazine,weekly,metrics,site")
    b.add_argument("--force-magazine", action="store_true")
    sub.add_parser("serve")
    wsv = sub.add_parser("web")
    wsv.add_argument("action", choices=["install", "uninstall", "status"])
    em = sub.add_parser("email")
    em.add_argument("--edition", default=None)
    em.add_argument("--to", default=None, help="send only to this address (test); not recorded in the sent-log")
    em.add_argument("--dry-run", action="store_true", help="write .eml files to data/app/outbox instead of sending")
    m = sub.add_parser("magazine")
    m.add_argument("--edition", default=None, help="YYYY-MM (default: current month)")
    m.add_argument("--from-step", default="research", choices=["research", "process", "verify", "write", "render"])
    w = sub.add_parser("weekly")
    w.add_argument("--week-ending", type=date.fromisoformat, default=None)
    a = p.parse_args(argv)

    if a.cmd == "run":
        return do_run(a.edition or now_ist().date(), a.force, a.from_stage, a.offline, a.no_agent)
    if a.cmd == "scheduled":
        return do_scheduled()
    if a.cmd == "status":
        return do_status()
    if a.cmd == "pause":
        PAUSE.parent.mkdir(parents=True, exist_ok=True)
        PAUSE.write_text(now_ist().isoformat())
        print("Paused: scheduled runs will exit without researching until `resume`.")
        return 0
    if a.cmd == "resume":
        PAUSE.unlink(missing_ok=True)
        print(f"Resumed. Next scheduled run: {scheduler.next_run().isoformat()}")
        return 0
    if a.cmd == "schedule":
        if a.action == "install":
            print(scheduler.install())
            print(scheduler.install_evening())
        elif a.action == "uninstall":
            print(scheduler.uninstall())
        print(json.dumps({**scheduler.status(), "evening": scheduler.evening_status()}, indent=2, default=str))
        return 0
    if a.cmd == "batch":
        from harness.batch import run_batch
        return run_batch(a.steps.split(",") if a.steps else None, a.force_magazine)
    if a.cmd == "web":
        print({"install": scheduler.install_web, "uninstall": scheduler.uninstall_web}.get(a.action, lambda: "")())
        print(json.dumps(scheduler.web_status(), indent=2))
        return 0
    if a.cmd == "serve":
        import uvicorn
        uvicorn.run("app.server:app", host="127.0.0.1", port=8787)
        return 0
    if a.cmd == "email":
        from harness.mailer import send_delta
        print(json.dumps(send_delta(a.edition, a.to, True if a.dry_run else None), indent=2))
        return 0
    if a.cmd == "magazine":
        from harness.magazine import run_magazine
        return run_magazine(a.edition, a.from_step)
    if a.cmd == "weekly":
        from harness.weekly import build_weekly
        print(build_weekly(a.week_ending or now_ist().date()))
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(main())
