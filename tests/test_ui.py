"""The UI rework of 30 October (docs/WIREFRAMES.md, version 2): tabs for the analyst's tasks, the overview,
terms with explanations, and keyboard focus. These read the page files. The browser smoke test comes later.
"""
import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
WEB = REPO / "src" / "voc" / "web"


def _page():
    return (WEB / "index.html").read_text(encoding="utf-8")


def _script():
    return (WEB / "app.js").read_text(encoding="utf-8")


def test_A7_the_page_has_a_tab_for_each_task_and_one_for_the_method():
    nav = re.search(r'<nav[^>]*aria-label="Sections"[^>]*>(.*?)</nav>', _page(), re.S)
    assert nav, "no tab bar"
    links = re.findall(r'<a[^>]*href="(#/[^"]*)"[^>]*>([^<]+)</a>', nav.group(1))
    assert [href for href, _ in links] == ["#/", "#/browse", "#/review", "#/measured"]
    assert [text.strip() for _, text in links][0] == "Overview"


def test_A7_the_current_tab_is_marked_for_screen_readers():
    assert 'aria-current' in _script() and '"page"' in _script()


def test_A7_the_overview_has_figure_tiles_and_a_bar_per_product():
    page = _page()
    for tile in ("tile-complaints", "tile-accuracy", "tile-waiting", "tile-cost"):
        assert f'id="{tile}"' in page, tile
    assert 'id="product-bars"' in page
    assert "product-bars" in _script()


def test_A7_the_development_figures_are_in_the_method_tab():
    page = _page()
    method = page[page.index('id="tab-measured"'):]
    for section in ("h2h", "speed", "safety", "scale", "versions"):
        assert f'id="{section}"' in method, section
    overview = page[page.index('id="tab-overview"'):page.index('id="tab-measured"')]
    assert 'id="h2h"' not in overview


def test_A7_each_core_term_has_an_explanation_that_opens_in_place():
    page = _page()
    for term in ("llm", "tfidf", "f1", "accuracy", "coverage"):
        button = re.search(rf'<button[^>]*aria-controls="term-{term}"[^>]*>', page)
        assert button and 'aria-expanded="false"' in button.group(0), term
        assert re.search(rf'id="term-{term}"[^>]*hidden', page), term
    assert "aria-expanded" in _script()


def test_A7_the_glossary_lists_the_core_terms():
    glossary = re.search(r'<dl[^>]*id="glossary"[^>]*>(.*?)</dl>', _page(), re.S)
    assert glossary
    for term in ("LLM", "TF-IDF", "F1", "Re-weighted strict accuracy", "Coverage"):
        assert term in glossary.group(1), term


def test_A7_every_control_shows_keyboard_focus():
    css = (WEB / "style.css").read_text(encoding="utf-8")
    rule = re.search(r"([^{}]*):focus-visible[^{}]*\{", css)
    assert rule
    focus = " ".join(re.findall(r"([^{}]*)\{[^}]*outline", css))
    for element in ("a:focus-visible", "button:focus-visible", "select:focus-visible", "input:focus-visible",
                    "summary:focus-visible"):
        assert element in focus, element


def test_A7_the_title_names_the_contest():
    assert "LLM against TF-IDF" in _page()
