"""Spec 004, plan item 11: the June section of `docs/VALIDATION.md` and the README, after the June run.

Every June figure the two pages state is read from the run's own summary, `results/june/v1_june.json`, so the pages
cannot drift from the run (CLAUDE.md: every number comes from a real run).
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
