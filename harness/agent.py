"""Bridge to the headless research agent (Claude Code CLI, `claude -p`).

Tool boundary: the agent is started with ONLY the tools listed in
config/harness.yaml (WebSearch, WebFetch). It cannot read or write files or run
commands; it returns JSON that the harness validates against a schema before
anything is stored. Web content is untrusted data (see prompts/research_agent.md).
"""
from __future__ import annotations

import json
import shutil
import subprocess
import threading
from pathlib import Path

import jsonschema

from harness.common import PROMPTS, RAW, SCHEMAS, iso, load_config, now_ist, read_json, sha, write_json
from harness.runtime import RunLog


class AgentBudget:
    def __init__(self, cap_usd: float):
        self.cap, self.spent, self.reserved = cap_usd, 0.0, 0.0
        self.lock = threading.Lock()

    def reserve(self, amount: float) -> bool:
        with self.lock:
            if self.spent + self.reserved + amount > self.cap + 1e-9:
                return False
            self.reserved += amount
            return True

    def settle(self, reserved: float, actual: float):
        with self.lock:
            self.reserved -= reserved
            self.spent += actual


def available() -> tuple[bool, str]:
    cfg = load_config("harness")["agent"]
    if not cfg["enabled"]:
        return False, "agent disabled in config/harness.yaml"
    if not shutil.which(cfg["command"]):
        return False, f"'{cfg['command']}' CLI not found on PATH"
    return True, "ok"


def run_agent(prompt: str, schema: dict, *, name: str, out_path: Path, budget_usd: float,
              timeout_min: float, log: RunLog, tools: list[str] | None = None, prompt_key: str | None = None) -> dict:
    """Run one headless agent call. Returns {ok, data, cost_usd, error}. Never raises."""
    cfg = load_config("harness")["agent"]
    cwd = out_path.parent / f".cwd-{name}"
    cwd.mkdir(parents=True, exist_ok=True)   # empty dir: no repo files in the agent's context
    tools = ",".join(cfg["tools"] if tools is None else tools)     # [] = no tools at all (writer)
    cmd = [cfg["command"], "-p", "--output-format", "json", "--tools", tools] + \
        (["--allowedTools", tools] if tools else []) + [
           "--json-schema", json.dumps({k: v for k, v in schema.items() if k != "$schema"}), "--max-budget-usd", f"{budget_usd:.2f}",
           "--no-session-persistence", "--disable-slash-commands",
           "--strict-mcp-config"]          # no MCP servers/connectors: the tool list above is the whole boundary
    if cfg.get("model"):
        cmd += ["--model", cfg["model"]]
    started = iso(now_ist())
    log("agent_start", task=name, budget_usd=budget_usd)
    try:
        proc = subprocess.run(cmd, input=prompt, capture_output=True, text=True, cwd=cwd,
                              timeout=timeout_min * 60)
    except subprocess.TimeoutExpired:
        log.source_failure(f"agent:{name}", f"timeout after {timeout_min} min")
        return {"ok": False, "data": None, "cost_usd": budget_usd, "error": "timeout", "started": started}
    finished = iso(now_ist())
    try:
        envelope = json.loads(proc.stdout)
    except json.JSONDecodeError:
        log.source_failure(f"agent:{name}", f"non-JSON output rc={proc.returncode}", stderr=proc.stderr[-500:])
        return {"ok": False, "data": None, "cost_usd": 0.0, "error": "bad output", "started": started}
    cost = float(envelope.get("total_cost_usd") or 0.0)
    data = envelope.get("structured_output")
    write_json(out_path, {"task": name, "prompt_sha": sha(prompt), "prompt_key": prompt_key, "started": started, "finished": finished, "cost_usd": cost,
                          "subtype": envelope.get("subtype"), "is_error": envelope.get("is_error"),
                          "structured_output": data})
    if envelope.get("is_error") or data is None:
        err = envelope.get("subtype") or "no structured output"
        log.source_failure(f"agent:{name}", err)
        return {"ok": False, "data": None, "cost_usd": cost, "error": err, "started": started}
    try:
        jsonschema.validate(data, schema)
    except jsonschema.ValidationError as e:
        log.source_failure(f"agent:{name}", f"schema violation: {e.message[:200]}")
        return {"ok": False, "data": None, "cost_usd": cost, "error": "schema violation", "started": started}
    log("agent_done", task=name, cost_usd=round(cost, 3), claims=len(data.get("claims", [])),
        projects=len(data.get("projects", [])))
    return {"ok": True, "data": data, "cost_usd": cost, "error": None, "started": started, "finished": finished}


def build_research_prompt(task: dict, window: tuple, leads: list[dict]) -> str:
    template = (PROMPTS / "research_agent.md").read_text(encoding="utf-8")
    def fmt(l):
        when = (l["published_at"] or "undated")[:16]
        if "news.google.com" in l["url"]:
            # Google News links are JS redirects that WebFetch cannot open: search for the headline instead
            return f"- [{when}] {l['title']} — {l['publisher']} (find via WebSearch: \"{l['title'][:90]}\")"
        return f"- [{when}] {l['title']} — {l['publisher']} {l['url']}"
    lead_lines = "\n".join(fmt(l) for l in leads) or "- (no leads for this task)"
    window_rule = ("Only report developments PUBLISHED or MATERIALLY UPDATED inside the window, plus older "
                   "background only when needed to interpret them (mark it with its true dates)."
                   if task["cadence"] == "daily" else
                   "This is a baseline task: historical evidence from the last 3 years is in scope; "
                   "always record the period each figure describes in period_years and the statement.")
    return (template
            .replace("{{TASK_ID}}", task["id"])
            .replace("{{FOCUS}}", task["focus"].strip())
            .replace("{{WINDOW_START}}", iso(window[0]))
            .replace("{{WINDOW_END}}", iso(window[1]))
            .replace("{{WINDOW_RULE}}", window_rule)
            .replace("{{LEADS}}", lead_lines))


def findings_schema() -> dict:
    return read_json(SCHEMAS / "agent_findings.schema.json")


def raw_agent_dir(edition) -> Path:
    return RAW / edition.isoformat() / "agent"
