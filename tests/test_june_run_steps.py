"""Spec 004, plan item 11: the owner's steps for the June run, `docs/JUNE_RUN_STEPS.md`.

The facts the steps carry are read from the repo's own files, so the steps cannot drift from the pin, the frozen
sample or the scripts.
"""
import json
import tomllib
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
STEPS = REPO / "docs" / "JUNE_RUN_STEPS.md"


def _text():
    return STEPS.read_text(encoding="utf-8")


def test_J8_the_june_run_steps_name_the_june_zip_and_the_sample_s_size():
    pin = tomllib.loads((REPO / "config" / "data_files.toml").read_text(encoding="utf-8"))["june_2026"]
    count = json.loads((REPO / "splits" / "june" / "manifest.json").read_text(encoding="utf-8"))["lists"]["june"]
    text = _text()
    assert pin["zip_file_name"] in text and pin["zip_sha256"][:8] in text
    assert f"{count['count']:,}" in text


def test_J8_the_june_run_steps_check_the_dry_run_s_clean_up_first_and_keep_main_still():
    text = _text()
    before = text.split("## The run")[0]
    assert "`incoming`" in before and "`voc_june`" in before and "syn_june_dry_run" in before
    assert "**Paused**" in before and "from the upload until Job B ends" in text


def test_J1_the_june_run_steps_say_which_figures_to_check_before_approving():
    text = _text()
    for name in ("complaints", "worst_case_tokens", "tokens_left_under_cap", "expected_cost_usd"):
        assert f"`{name}`" in text


def test_J11_the_june_run_steps_end_with_the_copy_by_claude():
    text = _text()
    assert "scripts/copy_june_results.py" in text and "`v1_june.csv`" in text and "`v1_june.json`" in text


def test_J10_the_june_run_steps_show_the_figures_as_the_approval_prints_them():
    from decimal import Decimal

    from voc.job_a import expected_cost

    count = json.loads((REPO / "splits" / "june" / "manifest.json").read_text(encoding="utf-8"))["lists"]["june"]
    per_1000 = json.loads((REPO / "results" / "eval" / "v1_test.json").read_text(encoding="utf-8"))["llm"]
    cap = tomllib.loads((REPO / "config" / "budget.toml").read_text(encoding="utf-8"))["june_cap_tokens"]
    step = _text().split("## The run")[1].split("\n7. ")[0]
    cost = expected_cost(Decimal(per_1000["cost_per_1000_usd"]), count["count"])
    for line in (f"complaints: {count['count']}", f"calls: {count['count']}", f"tokens_left_under_cap: {cap}",
                 f"expected_cost_usd: {cost}", "Job A run: ", "started: "):
        assert f"`{line}" in step


def test_J12_the_june_run_steps_check_the_console_key_and_the_spend_limit_before_the_run():
    before = _text().split("## The run")[0]
    assert "`voc-june-job-b`" in before and "**Active**" in before and "$5" in before


def test_J13_the_june_run_steps_check_each_credential_s_end_date_and_the_reader_first():
    before = _text().split("## The run")[0]
    for name in ("`voc-june-runner`", "`voc-receiver-dispatch`", "`voc-results-reader`", "--check-reader"):
        assert name in before


def test_J8_the_june_run_steps_say_what_never_to_click_after_a_refusal_or_a_stop():
    part = _text().split("## If something refuses or stops")[1].split("## After the run")[0]
    for name in ("**Re-run", "**Run now**", "**Repair", "upload", "attempt"):
        assert name in part
