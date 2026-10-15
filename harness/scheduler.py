"""macOS launchd scheduler (detected environment). Linux fallback: prints a crontab line.

launchd's StartCalendarInterval uses the machine's local time zone. The installer
converts the configured time (06:00 Asia/Kolkata) to local time and refuses to install
silently if the local zone observes DST (the slot would drift); it prints a warning.
If the Mac is asleep at the slot, launchd runs the job once on wake. If it is powered
off, the run is missed: see README "Recovery".
"""
from __future__ import annotations

import os
import platform
import plistlib
import shutil
import subprocess
import sys
from datetime import datetime, time, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from harness.common import LOGS, ROOT, load_config

PLIST_DIR = Path.home() / "Library" / "LaunchAgents"


def label() -> str:
    return load_config("schedule")["launchd_label"]


def plist_path() -> Path:
    return PLIST_DIR / f"{label()}.plist"


def local_slot() -> tuple[int, int, str | None]:
    s = load_config("schedule")
    hh, mm = (int(x) for x in s["daily_run_time"].split(":"))
    target_tz = ZoneInfo(s["timezone"])
    today = datetime.now(target_tz).date()
    slot = datetime.combine(today, time(hh, mm), tzinfo=target_tz).astimezone()  # system local
    warn = None
    local = datetime.now().astimezone().tzinfo
    jan, jul = datetime(2026, 1, 15).astimezone(), datetime(2026, 7, 15).astimezone()
    if jan.utcoffset() != jul.utcoffset():
        warn = (f"System time zone {local} observes DST; 06:00 {s['timezone']} will drift by an hour part of the year. "
                f"Set the Mac to Asia/Kolkata or re-run `schedule install` after DST changes.")
    return slot.hour, slot.minute, warn


def next_run(now: datetime | None = None) -> datetime:
    s = load_config("schedule")
    tz = ZoneInfo(s["timezone"])
    hh, mm = (int(x) for x in s["daily_run_time"].split(":"))
    now = (now or datetime.now(tz)).astimezone(tz)
    cand = datetime.combine(now.date(), time(hh, mm), tzinfo=tz)
    return cand if cand > now else cand + timedelta(days=1)


def build_plist() -> dict:
    hh, mm, _ = local_slot()
    path_env = ":".join(dict.fromkeys([str(Path(sys.executable).parent), str(Path.home() / ".local/bin"),
                                       str(Path(shutil.which("claude") or "/usr/local/bin/claude").parent),
                                       "/opt/homebrew/bin", "/usr/local/bin", "/usr/bin", "/bin", "/usr/sbin", "/sbin"]))
    return {
        "Label": label(),
        "ProgramArguments": [sys.executable, "-m", "harness.cli", "scheduled"],
        "WorkingDirectory": str(ROOT),
        "StartCalendarInterval": {"Hour": hh, "Minute": mm},
        "EnvironmentVariables": {"PATH": path_env, "PYTHONUNBUFFERED": "1", "HOME": str(Path.home())},
        "StandardOutPath": str(LOGS / "launchd.out.log"),
        "StandardErrorPath": str(LOGS / "launchd.err.log"),
        "RunAtLoad": False,
        "ProcessType": "Background",
    }


def _uid() -> int:
    return os.getuid()


def install() -> str:
    if platform.system() != "Darwin":
        return linux_hint()
    hh, mm, warn = local_slot()
    PLIST_DIR.mkdir(parents=True, exist_ok=True)
    LOGS.mkdir(exist_ok=True)
    p = plist_path()
    subprocess.run(["launchctl", "bootout", f"gui/{_uid()}/{label()}"], capture_output=True)
    with open(p, "wb") as fh:
        plistlib.dump(build_plist(), fh)
    r = subprocess.run(["launchctl", "bootstrap", f"gui/{_uid()}", str(p)], capture_output=True, text=True)
    if r.returncode != 0:
        return f"launchctl bootstrap failed: {r.stderr.strip()}"
    return f"Installed {p} (local {hh:02d}:{mm:02d})." + (f"\nWARNING: {warn}" if warn else "")


def uninstall() -> str:
    if platform.system() != "Darwin":
        return "Remove the crontab line manually (crontab -e)."
    subprocess.run(["launchctl", "bootout", f"gui/{_uid()}/{label()}"], capture_output=True)
    if plist_path().exists():
        plist_path().unlink()
    return f"Removed {label()}."


def status() -> dict:
    out = {"platform": platform.system(), "plist": str(plist_path()), "plist_exists": plist_path().exists(),
           "loaded": False, "next_run_ist": next_run().isoformat(), "system_tz": str(datetime.now().astimezone().tzinfo),
           "paused": (ROOT / "data" / ".paused").exists()}
    if platform.system() == "Darwin":
        r = subprocess.run(["launchctl", "print", f"gui/{_uid()}/{label()}"], capture_output=True, text=True)
        out["loaded"] = r.returncode == 0
        if r.returncode == 0:
            for line in r.stdout.splitlines():
                ln = line.strip()
                if ln.startswith(("state =", "last exit code", "runs =")):
                    out[ln.split("=")[0].strip()] = ln.split("=", 1)[1].strip()
        if out["plist_exists"]:
            with open(plist_path(), "rb") as fh:
                out["calendar"] = plistlib.load(fh)["StartCalendarInterval"]
    return out


def linux_hint() -> str:
    return (f"CRON_TZ=Asia/Kolkata\n0 6 * * * cd {ROOT} && {sys.executable} -m harness.cli scheduled "
            f">> {LOGS}/cron.log 2>&1")


# ---------------------------------------------------------------------------------- web app service
WEB_LABEL = "com.bengaluru-rei.web"
WEB_PORT = 8787


def web_plist_path() -> Path:
    return PLIST_DIR / f"{WEB_LABEL}.plist"


def install_web() -> str:
    """Keep the website running at http://127.0.0.1:8787 (restarts on crash and at login)."""
    if platform.system() != "Darwin":
        return f"Run: cd {ROOT} && {sys.executable} -m uvicorn app.server:app --host 127.0.0.1 --port {WEB_PORT}"
    PLIST_DIR.mkdir(parents=True, exist_ok=True)
    subprocess.run(["launchctl", "bootout", f"gui/{_uid()}/{WEB_LABEL}"], capture_output=True)
    plist = {"Label": WEB_LABEL, "WorkingDirectory": str(ROOT),
             "ProgramArguments": [sys.executable, "-m", "uvicorn", "app.server:app", "--host", "127.0.0.1", "--port", str(WEB_PORT)],
             "EnvironmentVariables": build_plist()["EnvironmentVariables"], "RunAtLoad": True, "KeepAlive": True,
             "StandardOutPath": str(LOGS / "web.out.log"), "StandardErrorPath": str(LOGS / "web.err.log")}
    with open(web_plist_path(), "wb") as fh:
        plistlib.dump(plist, fh)
    r = subprocess.run(["launchctl", "bootstrap", f"gui/{_uid()}", str(web_plist_path())], capture_output=True, text=True)
    return f"Web app service installed: http://127.0.0.1:{WEB_PORT}" if r.returncode == 0 else f"bootstrap failed: {r.stderr.strip()}"


def uninstall_web() -> str:
    subprocess.run(["launchctl", "bootout", f"gui/{_uid()}/{WEB_LABEL}"], capture_output=True)
    web_plist_path().unlink(missing_ok=True)
    return "Web app service removed."


def web_status() -> dict:
    r = subprocess.run(["launchctl", "print", f"gui/{_uid()}/{WEB_LABEL}"], capture_output=True, text=True)
    state = next((l.split("=", 1)[1].strip() for l in r.stdout.splitlines() if l.strip().startswith("state =")), None)
    return {"loaded": r.returncode == 0, "state": state, "url": f"http://127.0.0.1:{WEB_PORT}"}


# ------------------------------------------------------------------------------ evening news refresh
EVENING_LABEL = "com.bengaluru-rei.evening"


def install_evening() -> str:
    if platform.system() != "Darwin":
        return f"CRON_TZ=Asia/Kolkata\n0 18 * * * cd {ROOT} && {sys.executable} -m harness.cli batch --steps refresh,site"
    s = load_config("schedule")
    hh, mm = (int(x) for x in s["evening_run_time"].split(":"))
    slot = datetime.combine(datetime.now(ZoneInfo(s["timezone"])).date(), time(hh, mm), tzinfo=ZoneInfo(s["timezone"])).astimezone()
    p = PLIST_DIR / f"{EVENING_LABEL}.plist"
    subprocess.run(["launchctl", "bootout", f"gui/{_uid()}/{EVENING_LABEL}"], capture_output=True)
    plist = dict(build_plist(), Label=EVENING_LABEL, StartCalendarInterval={"Hour": slot.hour, "Minute": slot.minute},
                 ProgramArguments=[sys.executable, "-m", "harness.cli", "batch", "--steps", "refresh,site,publish"],
                 StandardOutPath=str(LOGS / "evening.out.log"), StandardErrorPath=str(LOGS / "evening.err.log"))
    with open(p, "wb") as fh:
        plistlib.dump(plist, fh)
    r = subprocess.run(["launchctl", "bootstrap", f"gui/{_uid()}", str(p)], capture_output=True, text=True)
    return f"Evening refresh installed ({slot.hour:02d}:{slot.minute:02d} local)" if r.returncode == 0 else f"bootstrap failed: {r.stderr.strip()}"


def evening_status() -> dict:
    r = subprocess.run(["launchctl", "print", f"gui/{_uid()}/{EVENING_LABEL}"], capture_output=True, text=True)
    s = load_config("schedule")
    hh, mm = (int(x) for x in s["evening_run_time"].split(":"))
    tz = ZoneInfo(s["timezone"])
    now = datetime.now(tz)
    nxt = datetime.combine(now.date(), time(hh, mm), tzinfo=tz)
    nxt = nxt if nxt > now else nxt + timedelta(days=1)
    return {"loaded": r.returncode == 0, "next_run_ist": nxt.isoformat()}
