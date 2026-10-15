"""Shared paths, config loading, time handling, hashing and atomic JSON IO."""
from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
import unicodedata
from datetime import date, datetime, time, timedelta
from functools import lru_cache
from pathlib import Path
from zoneinfo import ZoneInfo

import yaml

ROOT = Path(os.environ.get("BREI_ROOT", Path(__file__).resolve().parent.parent))
CONFIG = ROOT / "config"
DATA = ROOT / "data"
RAW = DATA / "raw"
PROCESSED = DATA / "processed"
HISTORY = DATA / "history"
RUNS = DATA / "runs"
REPORTS = ROOT / "reports"
LOGS = ROOT / "logs"
SCHEMAS = ROOT / "validation" / "schemas"
PROMPTS = ROOT / "prompts"

IST = ZoneInfo("Asia/Kolkata")


@lru_cache(maxsize=None)
def load_config(name: str) -> dict:
    with open(CONFIG / f"{name}.yaml", encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def now_ist() -> datetime:
    return datetime.now(IST)


def iso(dt: datetime) -> str:
    return dt.astimezone(IST).isoformat(timespec="seconds")


def parse_date(value) -> date | None:
    """Parse YYYY-MM-DD (or a longer ISO string) into a date; None if unparseable."""
    if not value:
        return None
    if isinstance(value, datetime):
        return value.astimezone(IST).date()
    if isinstance(value, date):
        return value
    m = re.match(r"(\d{4})-(\d{2})-(\d{2})", str(value))
    if not m:
        return None
    try:
        return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    except ValueError:
        return None


def edition_window(edition: date, now: datetime | None = None) -> tuple[datetime, datetime]:
    """Window for an edition: ends at the scheduled slot (or now, if earlier), spans window_hours.

    Anchoring to the slot keeps late re-runs of the same edition idempotent; a run
    started before the slot (e.g. the first manual run) ends at its own start time.
    """
    sched = load_config("schedule")
    tz = ZoneInfo(sched["timezone"])
    hh, mm = (int(x) for x in sched["daily_run_time"].split(":"))
    slot = datetime.combine(edition, time(hh, mm), tzinfo=tz)
    now = now or datetime.now(tz)
    end = min(slot, now) if now.date() == edition else slot
    end = end.replace(microsecond=0)
    return end - timedelta(hours=sched["window_hours"]), end


def sha(*parts, n: int = 10) -> str:
    h = hashlib.sha1("\x1f".join("" if p is None else str(p) for p in parts).encode("utf-8"))
    return h.hexdigest()[:n]


def norm_text(s: str | None) -> str:
    s = unicodedata.normalize("NFKC", s or "").lower()
    s = re.sub(r"[^\w\s%.]", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def tokens(s: str | None) -> list[str]:
    return [t for t in norm_text(s).split() if len(t) > 1]


def read_json(path: Path, default=None):
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except FileNotFoundError:
        return default


def write_json(path: Path, obj) -> None:
    """Atomic write with stable formatting (idempotent outputs diff cleanly)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".tmp-", suffix=".json")
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        json.dump(obj, fh, ensure_ascii=False, indent=2, sort_keys=True, default=str)
        fh.write("\n")
    os.replace(tmp, path)


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".tmp-")
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        fh.write(text)
    os.replace(tmp, path)


def append_jsonl(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(obj, ensure_ascii=False, default=str) + "\n")
