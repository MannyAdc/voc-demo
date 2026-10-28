"""B1 and B6: check that a quote really appears in the complaint text.

Both sides get the same small normalisation before matching: runs of spaces
and line breaks become one space, and curly quote marks, apostrophes and
dashes become their plain forms. Capital letters still matter. The match
must start and end on word boundaries, and the quote needs at least 3 real
words. A word is real only if it holds a letter other than a capital X, so
redaction marks such as XXXX, XX/XX/XXXX and {$XXXX} are not real words.
"XXXX" is never changed (B6).
"""
from dataclasses import dataclass

# Curly single quotes and apostrophes, curly double quotes, and dashes, by code point.
SINGLE_QUOTES = (0x2018, 0x2019, 0x201A, 0x201B)
DOUBLE_QUOTES = (0x201C, 0x201D, 0x201E, 0x201F)
DASHES = (0x2010, 0x2011, 0x2012, 0x2013, 0x2014, 0x2015, 0x2212)
PLAIN = str.maketrans(
    {**dict.fromkeys(SINGLE_QUOTES, "'"), **dict.fromkeys(DOUBLE_QUOTES, '"'), **dict.fromkeys(DASHES, "-")})
MIN_REAL_WORDS = 3


@dataclass(frozen=True)
class Evidence:
    """The result of a quote check. `start` and `end` point into the original text."""
    ok: bool
    reason: str | None = None
    start: int | None = None
    end: int | None = None


def _normalise(text):
    """The normalised text, and for each of its characters the index in the original."""
    chars, origin = [], []
    for i, ch in enumerate(text):
        if ch.isspace():
            if chars and chars[-1] == " ":
                continue
            chars.append(" ")
        else:
            chars.append(ch.translate(PLAIN))
        origin.append(i)
    return "".join(chars), origin


def _is_real_word(word):
    return any(ch.isalpha() and ch != "X" for ch in word)


def _is_redaction_mark(word):
    return "X" in word and not _is_real_word(word)


def _word_char(ch):
    return ch.isalnum()


def check_quote(text, quote):
    """Check a quote against the complaint text. The first failure names the reason (B3)."""
    needle = _normalise(quote)[0].strip()
    if not needle:
        return Evidence(False, "quote_empty")
    words = needle.split(" ")
    if not any(_is_real_word(w) for w in words) and all(_is_redaction_mark(w) for w in words):
        return Evidence(False, "quote_redaction_only")
    if sum(_is_real_word(w) for w in words) < MIN_REAL_WORDS:
        return Evidence(False, "quote_too_short")
    haystack, origin = _normalise(text)
    at = haystack.find(needle)
    while at != -1:
        end = at + len(needle)
        starts_clean = at == 0 or not (_word_char(haystack[at - 1]) and _word_char(needle[0]))
        ends_clean = end == len(haystack) or not (_word_char(haystack[end]) and _word_char(needle[-1]))
        if starts_clean and ends_clean:
            return Evidence(True, None, origin[at], origin[end - 1] + 1)
        at = haystack.find(needle, at + 1)
    return Evidence(False, "quote_not_in_text")
