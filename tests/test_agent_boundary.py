"""The research/writer agents must get exactly the tools we list - no MCP connectors, no file or shell tools."""
import json
import subprocess

from harness import agent


def capture(monkeypatch, tmp_path, **kw):
    seen = {}

    def fake_run(cmd, **_):
        seen["cmd"] = cmd
        return subprocess.CompletedProcess(cmd, 0, stdout=json.dumps({"structured_output": {"x": 1}, "total_cost_usd": 0}), stderr="")

    monkeypatch.setattr(agent.subprocess, "run", fake_run)
    log = type("L", (), {"__call__": lambda *a, **k: None, "source_failure": lambda *a, **k: None})()
    agent.run_agent("p", {"type": "object"}, name="t", out_path=tmp_path / "o.json", budget_usd=0.1, timeout_min=1, log=log, **kw)
    return seen["cmd"]


def test_research_agent_gets_only_web_tools_and_no_mcp(monkeypatch, tmp_path):
    cmd = capture(monkeypatch, tmp_path)
    assert cmd[cmd.index("--tools") + 1] == "WebSearch,WebFetch"
    assert "--strict-mcp-config" in cmd and "--mcp-config" not in cmd
    assert "--dangerously-skip-permissions" not in cmd


def test_writer_gets_no_tools(monkeypatch, tmp_path):
    cmd = capture(monkeypatch, tmp_path, tools=[])
    assert cmd[cmd.index("--tools") + 1] == "" and "--allowedTools" not in cmd
    assert "--strict-mcp-config" in cmd
