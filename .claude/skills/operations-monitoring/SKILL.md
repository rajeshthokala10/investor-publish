---
name: operations-monitoring
description: Run, schedule, pause, resume, monitor and recover the Bengaluru Real Estate Intelligence pipeline (launchd at 06:00 Asia/Kolkata, retries, locks, checkpoints, budgets, logs). Use for "is it running", failures, missed runs or schedule changes.
---
# Scheduling and operational monitoring

**Purpose.** Keep the daily run reliable and honest about its own state.

**Inputs.** `config/schedule.yaml`, `config/harness.yaml`, `logs/run-<date>.jsonl`, `logs/source_failures.jsonl`, `logs/launchd.*.log`, `data/runs/<date>/manifest.json`.

**Outputs.** launchd agent `~/Library/LaunchAgents/com.bengaluru-rei.daily.plist`; status JSON; recovered runs.

**Permitted tools.** Bash: `python -m harness.cli {run,scheduled,status,pause,resume,schedule,weekly}`, `launchctl print gui/$UID/com.bengaluru-rei.daily`.

**Procedures.**
- Status: `python -m harness.cli status` (lock, pause flag, last manifest, launchd state, next run).
- Missed run (Mac off): `python -m harness.cli run --edition YYYY-MM-DD` (window anchored to that day's 06:00 IST slot).
- Resume after crash: rerun the same command; completed stages are skipped via checkpoints, agent outputs are reused (no double spend).
- Redo one stage onward: `--from-stage verify`; redo all: `--force`.
- Pause/resume: `pause` writes `data/.paused`; scheduled runs exit 5 until `resume`.

**Failure handling.** Exit codes: 2 research failed, 3 publication blocked (needs a human), 4 locked, 5 paused. The scheduled wrapper retries only codes 1/2, with 10/30-minute backoff.

**Acceptance criteria.** `schedule status` shows `loaded: true`, the calendar slot, and `next_run_ist`; never claim scheduling is active without that output.
