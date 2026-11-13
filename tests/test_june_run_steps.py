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
