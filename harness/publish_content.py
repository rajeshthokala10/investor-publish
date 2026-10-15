"""Commit refreshed website content and push (triggers the GitHub Actions -> Railway deploy).

Only the paths in config/deploy.yaml are staged, so code, secrets and raw research never ride along.
"""
from __future__ import annotations

import subprocess

from harness.common import ROOT, load_config, now_ist


def _git(*args) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True, timeout=180)


def publish_content(log=None) -> str:
    cfg = load_config("deploy")
    if not cfg["auto_publish"]:
        return "skipped (auto_publish off)"
    existing = [p for p in cfg["paths"] if (ROOT / p).exists()]
    _git("add", "--", *existing)
    if _git("diff", "--cached", "--quiet").returncode == 0:
        return "no content changes"
    staged = _git("diff", "--cached", "--name-only").stdout.split()
    outside = [f for f in staged if not any(f == p or f.startswith(p.rstrip("/") + "/") for p in cfg["paths"])]
    if outside:          # something else was already staged by hand: do not publish it
        return f"skipped: other files staged ({', '.join(outside[:3])})"
    msg = f"content: {now_ist().strftime('%Y-%m-%d %H:%M')} IST refresh\n\nAutomated publish of website content by the batch."
    c = _git("commit", "-m", msg)
    if c.returncode != 0:
        return f"commit failed: {c.stderr[-200:]}"
    p = _git("push", cfg["remote"], cfg["branch"])
    result = "pushed" if p.returncode == 0 else f"push failed: {p.stderr[-200:]}"
    if log:
        log("content_published", result=result, files=len(staged))
    return result
