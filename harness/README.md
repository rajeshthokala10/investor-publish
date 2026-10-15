# Harness

`pipeline.py` runs **Discover → Collect → Extract → Normalise → Deduplicate → Verify → Analyse → Recheck → Publish → Archive**.
Each stage reads the previous checkpoint and writes `data/runs/<edition>/<stage>.json`;
`manifest.json` records stage status and the edition's window.

| Concern | Where | Setting |
|---|---|---|
| Tool boundary (LLM) | `agent.py` | agent started with `--tools WebSearch,WebFetch` only; empty cwd; JSON-schema output validated before use |
| Time budget | `runtime.Budget` | `budgets.max_runtime_minutes` |
| HTTP budget, rate limit, retries | `runtime.Http` | `budgets.max_http_requests`, `http.per_domain_min_interval_seconds`, `http.retries`, `http.backoff_seconds` |
| LLM spend | `agent.AgentBudget` | `agent.max_budget_usd_per_task`, `agent.max_budget_usd_per_run`, `recheck.agent_review_budget_usd` |
| Overlap protection | `runtime.RunLock` | `fcntl` lock on `logs/.run.lock` (exit 4 if held) |
| Checkpoints / restart | `runtime.Checkpoints` | completed stages skipped; agent outputs reused on restart |
| Idempotent outputs | fixed paths per edition; content-hash IDs; atomic writes (`common.write_json`) |
| Failure vs no-news | `report.run_status` | `failed` / `partial` / `no_new_updates` / `ok` |
| Secrets | none in repo; Claude CLI auth lives in the macOS keychain; optional `.env` is git-ignored |
| Scheduling | `scheduler.py` | launchd `StartCalendarInterval`, retries in `cli.do_scheduled` |
