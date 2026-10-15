# Working on this repository

Bengaluru Property Review: an evidence-first Bengaluru real-estate research pipeline + magazine + web app.
Start with `README.md`, `docs/ARCHITECTURE.md`, `docs/OPERATIONS.md`.

## Rules that must not be broken
- Verification statuses are assigned only by `validation/verification.py`. Never let model output set them.
- Agents get exactly the tools in `config/harness.yaml` plus `--strict-mcp-config`; writers get no tools.
- Any LLM-written number must appear in the claims it cites (`harness/magazine_write.py::check_block`,
  `harness/metrics_build.py::validate`). Keep these checks when adding new generated content.
- Never compare land rates with built-up/saleable rates; one comparability class per comparison.
- One data producer per chart series.
- Do not send emails, publish externally or buy data without the owner's explicit approval.

## Commands
`make test` · `make batch` · `make site` · `make serve` · `python -m harness.cli --help`

## Conventions
- Python 3.11+, stdlib + pyyaml/requests/jsonschema/markdown/fastapi/uvicorn. Atomic JSON writes via `harness.common.write_json`.
- Config lives in `config/*.yaml`; prompts in `prompts/`; skills in `.claude/skills/`.
- Tests use isolated roots via the `BREI_ROOT` env var; never write test data into `data/`.
