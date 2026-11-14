"""Spec 004, plan item 11: the June section of `docs/VALIDATION.md` and the README, after the June run.

The June figures the two pages state are computed from the run's own summary, `results/june/v1_june.json`, and the
June list's manifest, so the pages cannot drift from the run (CLAUDE.md: every number comes from a real run). Words
for a rounded share, such as "about 4 complaints in 5", are checked by review, not here.
"""
import json
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
MINUS = "−"


def _summary():
    return json.loads((REPO / "results" / "june" / "v1_june.json").read_text(encoding="utf-8"))


def _text(*parts):
    return (REPO.joinpath(*parts)).read_text(encoding="utf-8")


def _pct(share):
    return f"{share * 100:.1f}%"


def _signed(share):
    return ("+" if share >= 0 else MINUS) + f"{abs(share) * 100:.1f}"


def _figures():
    s = _summary()
    primary, second = s["primary"], s["secondary"]
    return {
        "hybrid": _pct(primary["hybrid_reweighted"]),
        "llm": _pct(primary["llm_reweighted"]),
        "lead": f"{_signed(primary['difference'])} points",
        "interval": f"{_signed(primary['interval'][0])} to {_signed(primary['interval'][1])}",
        "tfidf_share": _pct(primary["tfidf_share"]),
        "second_llm": _pct(second["llm_reweighted"]),
        "second_tfidf": _pct(second["tfidf_reweighted"]),
        "second_lead": f"{_signed(second['difference'])} points",
        "second_interval": f"{_signed(second['interval'][0])} to {_signed(second['interval'][1])}",
        "complaints": f"{s['complaints']:,}",
        "quarantined": str(sum(s["quarantined"].values())),
        "cost_same": f"${s['cost_per_extra_correct_usd']['same_coverage']}",
        "cost_full": f"${s['cost_per_extra_correct_usd']['full_coverage']}",
        "live_cost": f"${float(s['live_cost_usd']):.3f}",
    }


def _june_only():
    """The figures only the validation page's June section states (review of #138, minor 7)."""
    s = _summary()
    manifest = json.loads((REPO / "splits" / "june" / "manifest.json").read_text(encoding="utf-8"))
    held, n = s["quarantined"], s["complaints"]
    credit = s["per_category"]["categories"]["Credit reporting or other personal consumer reports"]["llm"]
    debt = s["per_category"]["categories"]["Debt collection"]
    mix_cost = float(s["cost_per_1000_usd"]) * (1 - s["primary"]["tfidf_share"])
    return {
        "coverage": _pct(s["secondary"]["coverage"]),
        "cost_per_1000": f"${s['cost_per_1000_usd']}",
        "full_lead": f"{_signed(s['full_coverage']['difference'])} points",
        "held_share": _pct(sum(held.values()) / n),
        "quote_not_in_text": f"{held['quote_not_in_text']} with a quote not in the text",
        "invalid_label": f"{held['invalid_label']} that named no listed product",
        "unparseable": f"{held['unparseable']} unreadable answers",
        "quote_too_short": f"{held['quote_too_short']} quote too short",
        "credit_precision": f"{round(credit['precision'] * 100)}%",
        "debt_recall": f"{round(debt['llm']['recall'] * 100)}%",
        "debt_llm_f1": f"{debt['llm']['f1']:.2f}",
        "debt_tfidf_f1": f"{debt['tfidf']['f1']:.2f}",
        "mix_cost": f"about ${mix_cost:.2f} per 1,000",
        "stories": f"{manifest['june_rows']:,}",
        "pool": f"{manifest['pool']:,}",
        "july_copies": f"{manifest['july_copies']} copies of July's stories",
        "exact_copies": f"{manifest['exact_copies']} exact copies",
        "near_copies": f"{manifest['near_copies']} near copies",
    }


def test_J7_the_validation_page_states_the_june_figures_from_the_run_s_summary():
    page = _text("docs", "VALIDATION.md")
    assert "## June" in page
    june = page.split("## June")[1].split("\n## ")[0]
    assert "results/june/v1_june.json" in june and "**beats**" in june
    for name, figure in _figures().items():
        assert figure in june, name


def test_J7_the_readme_states_the_june_verdict_and_links_to_its_section():
    readme = _text("README.md")
    result = readme.split("## 📊 The result")[1].split("\n## ")[0]
    f = _figures()
    for name in ("hybrid", "llm", "lead", "interval", "complaints"):
        assert f[name] in result, name
    assert "docs/VALIDATION.md#june" in result


def test_J7_the_validation_page_states_the_june_section_s_other_figures_from_the_run():
    # Review of #138, minor 7: the section's other figures, from the summary and the June list's manifest.
    june = _text("docs", "VALIDATION.md").split("## June")[1].split("\n## ")[0]
    for name, figure in _june_only().items():
        assert figure in june, name


def test_J7_the_readme_gives_the_side_comparison_s_lead_and_range():
    # Review of #138, minor 1: the README names the range it says includes zero.
    result = _text("README.md").split("## 📊 The result")[1].split("\n## ")[0]
    f = _figures()
    assert f"{f['second_lead']}" in result and f["second_interval"] in result


def test_J7_the_training_data_limit_names_june():
    # Spec 004, Known limits: some June narratives may be in the model's training data. "June 2026" alone is the
    # cutoff's month, which the old line already named.
    for parts in (("README.md",), ("docs", "LIMITS.md")):
        line = next(line for line in _text(*parts).splitlines() if "training data" in line)
        assert "June narratives" in line, parts


def test_J11_the_spec_names_the_not_in_list_marker_in_the_results_files():
    from voc.pipeline import NOT_IN_LIST

    spec = _text("specs", "004-june-test-and-baselines", "spec.md")
    line = next(line for line in spec.splitlines() if "from the fixed label list" in line)
    assert f"`{NOT_IN_LIST}`" in line
