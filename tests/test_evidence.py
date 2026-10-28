"""B1 and B6: a label needs a quote that really appears in the complaint text.

All text here is synthetic.
"""
import pytest

from voc.evidence import check_quote

TEXT = (
    "On XX/XX/XXXX the bank charged me a {$35.00} fee.\n"
    "I called   XXXX twice and nobody helped.\n"
    "The bank’s letter said the fee was “final” — it was not."
)


def test_B1_a_quote_is_found_ignoring_spaces_and_line_breaks():
    result = check_quote(TEXT, "fee. I called XXXX twice and nobody helped")
    assert result.ok and result.reason is None


def test_B1_the_reported_start_and_end_point_into_the_original_text():
    quote = "I called XXXX twice and nobody helped"
    result = check_quote(TEXT, quote)
    assert TEXT[result.start:result.end] == "I called   XXXX twice and nobody helped"


def test_B1_capital_letters_matter():
    result = check_quote(TEXT, "the BANK charged me")
    assert not result.ok and result.reason == "quote_not_in_text"


def test_B1_a_quote_not_in_the_text_is_rejected_with_no_position():
    result = check_quote(TEXT, "the bank refunded my money")
    assert result.reason == "quote_not_in_text"
    assert result.start is None and result.end is None


@pytest.mark.parametrize("quote", ["", "   ", "\n\t"])
def test_B1_an_empty_or_blank_quote_is_rejected(quote):
    assert check_quote(TEXT, quote).reason == "quote_empty"


def test_B1_a_quote_needs_at_least_3_real_words():
    assert check_quote(TEXT, "nobody helped").reason == "quote_too_short"
    assert check_quote(TEXT, "and nobody helped").ok


def test_B6_redaction_marks_do_not_count_toward_the_3_words():
    assert check_quote(TEXT, "called XXXX twice").reason == "quote_too_short"


def test_B1_dates_amounts_and_numbers_are_not_real_words():
    text = "Paid {$500.00} on XX/XX/XXXX and 2026 again on XX/XX/XXXX."
    # Only "Paid" and "on" are real words here, so it is too short.
    assert check_quote(text, "Paid {$500.00} on XX/XX/XXXX 2026").reason == "quote_too_short"
    # "and" makes the third real word.
    assert check_quote(text, "Paid {$500.00} on XX/XX/XXXX and 2026").ok


@pytest.mark.parametrize("quote", ["he bank charged me", "the bank charged m", "ank charged me a"])
def test_B1_a_quote_that_starts_or_ends_inside_a_word_is_rejected(quote):
    assert check_quote(TEXT, quote).reason == "quote_not_in_text"


def test_B1_curly_and_straight_quote_marks_apostrophes_and_dashes_match():
    assert check_quote(TEXT, "The bank's letter said the fee was \"final\" - it was not").ok
    straight = "The bank's letter said the fee was \"final\" - it was not."
    assert check_quote(straight, "The bank’s letter said the fee was “final” — it was not").ok


def test_B6_xxxx_in_a_quote_matches_xxxx_in_the_text():
    assert check_quote(TEXT, "I called XXXX twice").ok


def test_B6_a_guess_in_place_of_xxxx_does_not_match():
    assert check_quote(TEXT, "I called Bank twice").reason == "quote_not_in_text"


@pytest.mark.parametrize("quote", ["XXXX", "XX/XX/XXXX XXXX", "{$XXXX} XXXX XX/XX/XXXX"])
def test_B6_a_quote_of_only_redaction_marks_is_not_evidence(quote):
    text = "Sent XXXX on XX/XX/XXXX for {$XXXX} XXXX XX/XX/XXXX to XXXX."
    assert check_quote(text, quote).reason == "quote_redaction_only"


def test_B1_the_first_occurrence_on_word_boundaries_is_reported():
    text = "the fee was high. Then the fee was high again"
    result = check_quote(text, "the fee was high")
    assert result.start == 0
    assert check_quote("Xthe fee was high and the fee was high", "the fee was high").start == 22
