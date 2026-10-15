"""End-to-end replay of the full pipeline on the synthetic fixture, in an isolated root."""
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
FIXTURE = REPO / "tests" / "fixtures" / "findings_sample.json"


@pytest.fixture(scope="module")
def root(tmp_path_factory):
    r = tmp_path_factory.mktemp("brei")
    for d in ("config", "content_engineering", "prompts", "validation"):
        (r / d).symlink_to(REPO / d)
    return r


def run(root, edition, *extra):
    env = dict(os.environ, BREI_ROOT=str(root))
    p = subprocess.run([sys.executable, "-m", "harness.cli", "run", "--edition", edition, "--offline", str(FIXTURE), *extra],
                       cwd=REPO, env=env, capture_output=True, text=True, timeout=300)
    assert p.returncode == 0, p.stdout[-3000:] + p.stderr[-3000:]
    return json.loads((root / "reports" / "daily" / f"{edition}.json").read_text())


@pytest.fixture(scope="module")
def day1(root):
    return run(root, "2026-10-15")


def by_stmt(ds, text):
    return [c for c in ds["claims"] if text in c["statement"]]


def test_outputs_from_one_dataset(root, day1):
    for ext in ("md", "html", "json", "pdf"):
        assert (root / "reports" / "daily" / f"2026-10-15.{ext}").exists()
    md = (root / "reports" / "daily" / "2026-10-15.md").read_text()
    for h in ["Today’s Bengaluru Property Brief", "East Bengaluru Deep Dive", "North, South and West",
              "Plots vs Villas", "Government Moves", "Growth Scenarios", "Opportunities to Investigate",
              "Risks, Contradictions", "What Changed Since Yesterday", "Sources and Coverage Gaps"]:
        assert h in md
    assert day1["meta"]["gates"]["passed"]


def test_pdf_is_exactly_five_pages(root, day1):
    from harness.pdf_edition import PAGES, count_pages
    assert count_pages(root / "reports" / "daily" / "2026-10-15.pdf") == PAGES == 5


def test_guarantee_claim_not_verified(day1):
    (c,) = by_stmt(day1, "guaranteed to double")
    assert c["verification_status"] == "unverified" and "unsupported_guarantee" in c["flags"]


def test_syndicated_launch_counts_two_groups_not_three(day1):
    launch = by_stmt(day1, "launches 300 villa plots")
    assert {c["verification_status"] for c in launch} == {"corroborated"}
    assert launch[0]["corroborating_groups"] == ["the_hindu_group", "times_group"]


def test_sqyd_price_normalised(day1):
    (c,) = by_stmt(day1, "45,000 per sq yd")
    assert c["psf_inr"] == 5000 and c["comparability"].startswith("land_rate")


def test_unevidenced_stage_and_old_news(day1):
    (prr,) = by_stmt(day1, "Peripheral Ring Road has been awarded")
    assert prr["verification_status"] == "unverified" and prr["evidenced_stage"] is None
    (old,) = by_stmt(day1, "Purple Line extension")
    assert "republished_old_event" in old["flags"]
    assert old["claim_id"] not in day1["brief_claim_ids"]


def test_contradiction_visible(day1, root):
    assert day1["contradictions"]
    md = (root / "reports" / "daily" / "2026-10-15.md").read_text()
    assert "Unresolved contradictions" in md


def test_scenario_math_and_labels(day1):
    cells = [c for c in day1["model"]["cells"] if c["scenarios"]["status"] == "estimated"]
    assert [(c["corridor"], c["property_type"]) for c in cells] == [("whitefield", "apartment")]
    s = cells[0]["scenarios"]["scenarios"]
    assert s["conservative"]["annual_pct"] < s["base"]["annual_pct"] < s["optimistic"]["annual_pct"]
    g = s["base"]["annual_pct"]
    assert s["base"]["cumulative_pct"]["10"] == round(((1 + g / 100) ** 10 - 1) * 100)
    others = [c for c in day1["model"]["cells"] if c["scenarios"]["status"] != "estimated"]
    assert all(c["scenarios"]["status"] == "Insufficient evidence to estimate" for c in others)


def test_rerun_is_idempotent(root, day1):
    again = run(root, "2026-10-15", "--force")
    assert sorted(c["claim_id"] for c in again["claims"]) == sorted(c["claim_id"] for c in day1["claims"])
    assert again["brief_claim_ids"] == day1["brief_claim_ids"]


def test_next_day_same_news_is_repeat(root, day1):
    day2 = run(root, "2026-10-16")
    assert all(c["novelty"] == "repeat" for c in day2["claims"])
    assert day2["meta"]["status"] == "no_new_updates"
    assert day2["brief_claim_ids"] == []
