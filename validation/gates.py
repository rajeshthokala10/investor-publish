"""Publication gates. A daily report is published only if every hard gate passes.

Hard gates block publication (report goes to reports/daily/_blocked/). Soft gates
add visible warnings to the report.
"""
from __future__ import annotations

from datetime import timedelta

from harness.common import load_config, parse_date
from validation.verification import USABLE

DISQUALIFYING = {"unsupported_guarantee", "citation_failed", "recheck_failed"}


def run_gates(d: dict, window) -> dict:
    hard, soft = [], []
    # G1 evidence completeness for anything presented as usable evidence
    for c in d["claims"]:
        if c["verification_status"] in USABLE:
            missing = [f for f in ("url", "excerpt", "publisher", "retrieved_at") if not c.get(f)]
            if missing:
                hard.append(f"G1 {c['claim_id']} usable but missing {missing}")
            if not c["url"].startswith(("http://", "https://")):
                hard.append(f"G1 {c['claim_id']} non-http URL")
    # G2 disqualified claims must never be usable
    for c in d["claims"]:
        bad = DISQUALIFYING & set(c["flags"])
        if bad and c["verification_status"] in USABLE | {"verified_primary"}:
            hard.append(f"G2 {c['claim_id']} is {c['verification_status']} despite {sorted(bad)}")
    # G3 calculations recomputed without error
    for e in d.get("recheck", {}).get("calc_errors", []):
        hard.append(f"G3 {e}")
    # G4 ranking integrity
    sc = load_config("scoring")
    for cell in d["model"]["cells"]:
        n = len(cell["factors"])
        if cell["attractiveness"] is not None and n < sc["min_factors_for_rank"]:
            hard.append(f"G4 {cell['corridor']}/{cell['property_type']} ranked with {n} factors")
        if cell["scenarios"]["status"] == "estimated" and len(cell["scenarios"]["evidence_claim_ids"]) == 0:
            hard.append(f"G4 {cell['corridor']}/{cell['property_type']} scenario without evidence")
    # G5 window
    start, end = window
    if end - start != timedelta(hours=load_config("schedule")["window_hours"]):
        hard.append("G5 window is not the configured length")
    # G6 stage changes rest on usable claims with an evidenced stage
    by = {c["claim_id"]: c for c in d["claims"]}
    for s in d.get("stage_changes", []):
        c = by.get(s["claim_id"])
        if c and (c["verification_status"] not in USABLE or not c.get("evidenced_stage")):
            hard.append(f"G6 stage change {s['name']} rests on {c['verification_status']} claim")
    # soft gates
    if d.get("contradictions"):
        soft.append(f"{len(d['contradictions'])} unresolved contradiction(s) - see Risks section")
    unreachable = d.get("recheck", {}).get("links_unreachable", [])
    if unreachable:
        soft.append(f"{len(unreachable)} cited link(s) could not be reached during link check")
    failed_tasks = [k for k, v in d["coverage"].items() if not v["ok"]]
    if failed_tasks:
        soft.append(f"research tasks failed or skipped: {', '.join(failed_tasks)}")
    if d["feeds"]["failed"]:
        soft.append(f"{len(d['feeds']['failed'])} RSS feed(s) failed")
    for c in d["claims"]:
        p = parse_date(c["published_at"])
        if p and p > end.date():
            soft.append(f"{c['claim_id']} has a publication date after the window end ({p})")
    return {"passed": not hard, "hard_failures": hard, "warnings": soft}
