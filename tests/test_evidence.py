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


# Review of pull request #10. Special characters are built from code points.

COMBINING_ACUTE = chr(0x0301)
E_ACUTE = chr(0x00E9)
NBSP = chr(0x00A0)
SOFT_HYPHEN = chr(0x00AD)
ZERO_WIDTH_SPACE = chr(0x200B)
MODIFIER_APOSTROPHE = chr(0x02BC)
FULLWIDTH_HYPHEN = chr(0xFF0D)
FULLWIDTH_X = chr(0xFF38)
CYRILLIC_HA = chr(0x0425)
LEFT_DOUBLE, RIGHT_DOUBLE = chr(0x201C), chr(0x201D)


@pytest.mark.parametrize("text, quote", [
    ("I paid {$35.00} fee and nobody helped", ".00} fee and nobody"),
    ("I don't want this charge at all", "t want this charge"),
    ("The non-payment was late again", "payment was late again"),
    ("I paid the bank's fee late", "paid the bank"),
])
def test_B1_a_quote_starting_or_ending_inside_a_word_after_punctuation_is_rejected(text, quote):
    assert check_quote(text, quote).reason == "quote_not_in_text"


def test_B1_a_combining_mark_is_part_of_the_word():
    text = "we ate at the cafe" + COMBINING_ACUTE + " today"
    assert check_quote(text, "ate at the cafe").reason == "quote_not_in_text"


def test_B1_the_same_text_in_composed_and_decomposed_form_matches():
    composed = "we ate at the caf" + E_ACUTE + " today"
    result = check_quote(composed, "ate at the cafe" + COMBINING_ACUTE)
    assert result.ok
    assert composed[result.start:result.end] == "ate at the caf" + E_ACUTE


@pytest.mark.parametrize("mark", [FULLWIDTH_X * 4, CYRILLIC_HA * 4])
def test_B6_lookalike_redaction_marks_are_not_real_words(mark):
    text = f"Sent {mark} {mark} {mark} to {mark}."
    assert not check_quote(text, f"{mark} {mark} {mark}").ok


def test_B6_redaction_marks_joined_by_a_dash_are_redaction_only():
    assert check_quote("Paid XXXX - XXXX today", "XXXX - XXXX").reason == "quote_redaction_only"


def test_B1_other_apostrophes_and_dashes_match_their_plain_forms():
    text = "The bank" + MODIFIER_APOSTROPHE + "s fee " + FULLWIDTH_HYPHEN + " it was wrong"
    assert check_quote(text, "The bank's fee - it was wrong").ok


def test_B1_soft_hyphens_and_zero_width_spaces_are_ignored_on_both_sides():
    text = "The pay" + SOFT_HYPHEN + "ment was " + ZERO_WIDTH_SPACE + "late again"
    assert check_quote(text, "The payment was late again").ok
    assert check_quote("The payment was late again", "The pay" + SOFT_HYPHEN + "ment was late").ok


def test_B1_a_non_breaking_space_counts_as_a_space():
    assert check_quote("the fee" + NBSP + "was too high", "the fee was too").ok


def test_B1_positions_are_right_after_quote_marks_are_made_plain():
    text = "He said " + LEFT_DOUBLE + "the fee is fine" + RIGHT_DOUBLE + " and left"
    result = check_quote(text, 'said "the fee is fine"')
    assert text[result.start:result.end] == "said " + LEFT_DOUBLE + "the fee is fine" + RIGHT_DOUBLE


def test_B1_a_match_that_ends_at_the_very_end_of_the_text():
    text = "nobody helped me at all"
    result = check_quote(text, "me at all")
    assert result.ok and result.end == len(text)


def test_B1_a_contiguous_quote_with_too_few_real_words_is_too_short():
    text = "Paid {$500.00} on XX/XX/XXXX 2026 again."
    assert check_quote(text, "Paid {$500.00} on XX/XX/XXXX 2026").reason == "quote_too_short"


def test_B1_the_first_occurrence_on_word_boundaries_is_reported():
    text = "the fee was high. Then the fee was high again"
    result = check_quote(text, "the fee was high")
    assert result.start == 0
    assert check_quote("Xthe fee was high and the fee was high", "the fee was high").start == 22
