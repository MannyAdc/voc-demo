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


# Review of #51. These read the page files too. The browser smoke test (a later pull request) checks the behaviour.

def _function(name):
    script = _script()
    start = re.search(rf"(async )?function {name}\(", script).start()
    return script[start:script.index("\n}\n", start)]


def _colours():
    css = (WEB / "style.css").read_text(encoding="utf-8")
    light = dict(re.findall(r"--([\w-]+):\s*(#[0-9a-fA-F]{6})", css[:css.index("@media")]))
    dark_block = re.search(r"prefers-color-scheme: dark\)\s*\{\s*:root\s*\{([^}]*)\}", css).group(1)
    return {"light": light, "dark": {**light, **dict(re.findall(r"--([\w-]+):\s*(#[0-9a-fA-F]{6})", dark_block))}}


def _contrast(a, b):
    def lum(colour):
        c = [int(colour[i:i + 2], 16) / 255 for i in (1, 3, 5)]
        c = [x / 12.92 if x <= 0.04045 else ((x + 0.055) / 1.055) ** 2.4 for x in c]
        return 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2]
    hi, lo = sorted((lum(a), lum(b)), reverse=True)
    return (hi + 0.05) / (lo + 0.05)


def test_A7_every_text_colour_passes_4_5_to_1_in_both_themes():
    # Each text colour can sit on the page, on a card or on a grey tag. Buttons put --on-llm on --llm.
    for theme, c in _colours().items():
        pairs = [(fg, bg) for fg in ("ink", "muted", "llm", "tf", "good", "warn") for bg in ("bg", "card", "tag")]
        for fg, bg in pairs + [("on-llm", "llm")]:
            assert _contrast(c[fg], c[bg]) >= 4.5, (theme, fg, bg, round(_contrast(c[fg], c[bg]), 2))


def test_A7_the_tiles_sit_in_the_overview_and_hold_no_figure_before_a_run_is_loaded():
    page = _page()
    overview = page[page.index('id="tab-overview"'):page.index('id="tab-browse"')]
    for tile in ("tile-complaints", "tile-accuracy", "tile-waiting", "tile-cost"):
        assert re.search(rf'id="{tile}">n/a<', overview), tile
        assert f'put("{tile}"' in _script(), tile
    for tile in ("tile-complaints", "tile-accuracy", "tile-cost"):
        assert tile in _function("noVerdict"), tile


def test_A7_the_accuracy_tile_says_it_counts_all_test_complaints():
    tile = re.search(r'id="tile-accuracy".*?</div>', _page(), re.S).group(0)
    assert "of all test complaints" in tile


def test_A7_every_tab_link_names_its_tab():
    page = _page()
    links = re.findall(r'<a href="(#/[^"]*)" data-tab="(\w+)"', page)
    assert len(links) == 4
    for href, tab in links:
        assert f'id="tab-{tab}"' in page, tab
        assert href == ("#/" if tab == "overview" else f"#/{tab}"), href
    assert "a.dataset.tab === name" in _function("showTab")


def test_A7_each_term_button_opens_its_note():
    assert 'querySelectorAll("button.term")' in _function("wire")
    assert "toggleTerm(button)" in _function("wire")


def test_A10_an_answer_that_arrives_late_is_ignored():
    # Two quick clicks: the pane must not put one complaint's facts under another's heading.
    for name in ("complaintView", "listView", "reviewView"):
        assert re.search(r"const (\w+) = \+\+([\w.]+);.*?await fetchJson.*?if \(\1 !== \2\) return;",
                         _function(name), re.S), name


def test_A10_browse_with_no_product_asks_for_one():
    assert "Choose a product" in _function("listView")
    assert "listView(listState.product)" not in _script(), "paging must keep the address and the screen in step"


def test_A10_the_old_complaint_address_opens_the_review_queue():
    assert 'location.replace("#/review/"' in _function("route")


def test_A12_a_saved_decision_refreshes_the_queue_and_the_count():
    form = _function("decisionForm")
    assert "reviewCount()" in form and "reviewView(" in form


def test_A13_the_form_appears_only_where_a_review_can_be_saved():
    assert re.search(r"c\.can_review\)\s*decisionForm\(c\)", _function("complaintView"))


# A14 and the owner's review of the live page (30 October): a "Data as of" strip, larger text, and the narrow layout
# only on narrow screens.

def _css():
    return (WEB / "style.css").read_text(encoding="utf-8")


def _rem(value):
    number = re.fullmatch(r"([0-9.]+)rem", value.strip())
    return float(number.group(1)) if number else None


def test_A14_the_overview_has_a_data_as_of_strip_filled_from_the_api():
    page = _page()
    overview = page[page.index('id="tab-overview"'):page.index('id="tab-browse"')]
    assert 'id="freshness"' in overview
    assert '"/api/freshness"' in _script()


def test_A7_normal_text_is_as_large_as_the_verdict_line():
    # Owner decision: nothing smaller than the verdict line, except footnotes, captions and small marks.
    # Changed in the green commit: the floor is the verdict line's size when the owner set the rule (1.15rem). The
    # verdict line itself grew, so it still stands out, and the red version compared against its new size.
    css = _css()
    verdict = 1.15
    body = re.search(r"body \{[^}]*font-size: ([^;]+);", css)
    assert body and _rem(body.group(1)) == verdict
    small_ok = (".note", ".small", ".legend", "footer", ".tag", "svg text", "button.term", ".bar-count", ".grid2 span")
    for selector, size in re.findall(r"([^{}]+)\{[^}]*font-size: ([0-9.]+rem)", css):
        if _rem(size) < verdict:
            assert any(ok in selector for ok in small_ok), selector.strip()


def test_A7_the_narrow_layout_starts_below_720_pixels():
    css = _css()
    assert "max-width: 900px" not in css
    assert "max-width: 720px" in css


# Review of #54.

def _font_sizes():
    return re.findall(r"([^{}]+)\{[^}]*font-size: ([0-9.]+)(rem|px|em)", _css())


def test_A7_only_footnotes_captions_and_marks_are_smaller_than_normal_text():
    # Normal paragraphs (class "note") are normal text. The allowed list is matched by whole selector.
    small_ok = {"footer", ".legend", ".small", ".tag", "svg text", "button.term", ".bar-count", ".grid2 span"}
    for selector, size, unit in _font_sizes():
        too_small = (unit == "rem" and float(size) < 1.15) or unit == "em" and float(size) < 1
        if too_small:
            assert selector.strip() in small_ok, selector.strip()


def test_A7_the_verdict_line_stays_larger_than_normal_text():
    verdict = re.search(r"\.verdict\.big \{[^}]*font-size: ([0-9.]+)rem", _css())
    assert verdict and float(verdict.group(1)) > 1.15


def test_A7_the_wide_screen_rules_come_before_the_narrow_ones():
    # In CSS the later rule wins, so the 1000 px rules must come first, or they undo the phone layout.
    css = _css()
    assert css.index("max-width: 1000px") < min(m.start() for m in re.finditer(r"max-width: 720px", css))


def test_A14_the_strip_says_when_the_run_was_logged_and_in_which_time_zone():
    body = _function("freshness")
    assert "scored once" not in body
    assert "logged" in body and "Australian Eastern Daylight Time (AEDT)" in body


def test_A14_the_strip_explains_both_narrative_counts():
    body = _function("freshness")
    assert "copies" in body and "pool" in body


def test_A14_the_strip_spells_out_dbt_and_names_the_workflow_as_github_does():
    workflow = (REPO / ".github" / "workflows" / "scheduled.yml").read_text(encoding="utf-8")
    name = re.search(r"^name: (.+)$", workflow, re.M).group(1).strip()
    page = _page()
    assert "dbt (data build tool)" in page
    assert f'"{name}"' in page
