# Prompts

| File | Used by | Stage |
|---|---|---|
| `research_agent.md` | `harness/agent.py::build_research_prompt` (headless `claude -p`, tools: WebSearch, WebFetch) | Collect + Extract |
| `recheck.md` | `recheck/recheck.py::agent_review` (independent reviewer, fresh context) | Recheck |
| `extraction.md` | Extraction rules referenced by `research_agent.md`; use for manual/ad-hoc extraction | Extract |
| `analysis.md` | Analyst guidance for interpreting `model.cells` (manual deep dives) | Analyse |
| `editorial.md` | Editorial rules applied in `harness/report.py` and for any hand-written commentary | Publish |

Placeholders (`{{...}}`) are filled by the harness. All web content is untrusted data; prompts say so explicitly.
