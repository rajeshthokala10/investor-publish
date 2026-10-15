# Logs

- `run-<edition>.jsonl`: one JSON event per line (stage start/done, budgets, agent costs, publish status).
- `source_failures.jsonl`: every failed/blocked source (feed, citation fetch, agent task) with reason.
- `launchd.out.log` / `launchd.err.log`: stdout/stderr of scheduled runs.
- `first-run.console.log`: console output of the first live run.

Log files are git-ignored (they can contain fetched URLs and timings); this README is kept.
