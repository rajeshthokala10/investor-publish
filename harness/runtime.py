"""Run-scoped machinery: logging, budgets, rate-limited HTTP, lock, checkpoints."""
from __future__ import annotations

import fcntl
import json
import os
import time
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from urllib.parse import urlparse

import requests

from harness.common import LOGS, RUNS, append_jsonl, iso, load_config, now_ist, read_json, write_json


class BudgetExceeded(RuntimeError):
    pass


class RunLog:
    def __init__(self, edition: date):
        self.path = LOGS / f"run-{edition.isoformat()}.jsonl"
        self.failures = LOGS / "source_failures.jsonl"
        self.edition = edition

    def __call__(self, event: str, **kw):
        rec = {"ts": iso(now_ist()), "event": event, **kw}
        append_jsonl(self.path, rec)
        print(f"[{rec['ts']}] {event} " + " ".join(f"{k}={v}" for k, v in kw.items() if k != "detail"), flush=True)

    def source_failure(self, source: str, reason: str, **kw):
        append_jsonl(self.failures, {"ts": iso(now_ist()), "edition": self.edition.isoformat(),
                                     "source": source, "reason": reason, **kw})
        self("source_failure", source=source, reason=reason)


@dataclass
class Budget:
    deadline: float
    max_http: int
    http_used: int = 0
    agent_usd: float = 0.0
    counters: dict = field(default_factory=dict)

    @classmethod
    def from_config(cls) -> "Budget":
        b = load_config("harness")["budgets"]
        return cls(deadline=time.time() + b["max_runtime_minutes"] * 60, max_http=b["max_http_requests"])

    def time_left(self) -> float:
        return self.deadline - time.time()

    def check_time(self, what: str):
        if self.time_left() <= 0:
            raise BudgetExceeded(f"runtime budget exhausted before {what}")

    def take(self, counter: str, limit: int) -> bool:
        used = self.counters.get(counter, 0)
        if used >= limit:
            return False
        self.counters[counter] = used + 1
        return True


class Http:
    """requests wrapper: per-domain spacing, bounded retries, global request budget."""

    def __init__(self, budget: Budget, log: RunLog):
        cfg = load_config("harness")["http"]
        self.cfg, self.budget, self.log = cfg, budget, log
        self.session = requests.Session()
        self.session.headers["User-Agent"] = cfg["user_agent"]
        self._last: dict[str, float] = {}

    def get(self, url: str, *, source: str, method: str = "GET") -> requests.Response | None:
        domain = urlparse(url).netloc
        backoffs = [0] + list(self.cfg["backoff_seconds"])[: self.cfg["retries"]]
        last_err = None
        for wait in backoffs:
            if wait:
                time.sleep(wait)
            if self.budget.http_used >= self.budget.max_http:
                self.log.source_failure(source, "http request budget exhausted", url=url)
                return None
            if self.budget.time_left() <= 5:
                self.log.source_failure(source, "runtime budget exhausted", url=url)
                return None
            gap = self.cfg["per_domain_min_interval_seconds"] - (time.time() - self._last.get(domain, 0))
            if gap > 0:
                time.sleep(gap)
            self._last[domain] = time.time()
            self.budget.http_used += 1
            try:
                r = self.session.request(method, url, timeout=self.cfg["timeout_seconds"], allow_redirects=True)
            except requests.RequestException as e:
                last_err = f"{type(e).__name__}: {e}"[:200]
                continue
            if r.status_code in (429, 500, 502, 503, 504):
                last_err = f"HTTP {r.status_code}"
                continue
            if r.status_code >= 400:
                # 401/403/406 etc: do not retry and never attempt to bypass
                self.log.source_failure(source, f"HTTP {r.status_code}", url=url)
                return r
            return r
        self.log.source_failure(source, last_err or "unknown error", url=url)
        return None


class RunLock:
    """Exclusive non-blocking lock; prevents overlapping runs. Released on process exit."""

    def __init__(self, path: Path = LOGS / ".run.lock"):
        self.path = path
        self.fh = None

    def acquire(self) -> bool:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.fh = open(self.path, "a+")
        try:
            fcntl.flock(self.fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            self.fh.close()
            self.fh = None
            return False
        self.fh.seek(0)
        self.fh.truncate()
        self.fh.write(json.dumps({"pid": os.getpid(), "started": iso(now_ist())}))
        self.fh.flush()
        return True

    def holder(self) -> str:
        try:
            return self.path.read_text()
        except FileNotFoundError:
            return ""

    def release(self):
        if self.fh:
            fcntl.flock(self.fh, fcntl.LOCK_UN)
            self.fh.close()
            self.fh = None


class Checkpoints:
    """Per-edition stage outputs + manifest; completed stages are skipped on restart."""

    def __init__(self, edition: date):
        self.dir = RUNS / edition.isoformat()
        self.manifest_path = self.dir / "manifest.json"
        self.manifest = read_json(self.manifest_path, {"edition": edition.isoformat(), "stages": {}})

    def done(self, stage: str) -> bool:
        return self.manifest["stages"].get(stage, {}).get("status") == "done"

    def load(self, stage: str):
        return read_json(self.dir / f"{stage}.json")

    def save(self, stage: str, output, status: str = "done", **meta):
        write_json(self.dir / f"{stage}.json", output)
        self.manifest["stages"][stage] = {"status": status, "at": iso(now_ist()), **meta}
        write_json(self.manifest_path, self.manifest)

    def reset(self, from_stage: str | None, order: list[str]):
        stages = order if from_stage is None else order[order.index(from_stage):]
        for s in stages:
            self.manifest["stages"].pop(s, None)
        write_json(self.manifest_path, self.manifest)
