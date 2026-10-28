"""B1 and B6: check that a quote really appears in the complaint text.

Both sides get the same small normalisation before matching:
- Unicode NFC, so composed and decomposed letters match
- soft hyphens and zero-width characters are dropped
- runs of spaces and line breaks become one space
- curly and other quote marks, apostrophes and dashes become their plain forms

Capital letters still matter. The match must start and end on word
boundaries: the text may not continue the word on either side, also not
across an apostrophe or hyphen ("t want" in "don't want" is rejected). The
quote needs at least 3 real words. A word is real only if it holds a letter
that is not a capital X or a lookalike of one, so redaction marks such as
XXXX, XX/XX/XXXX and {$XXXX} are not real words. "XXXX" is never changed (B6).
"""
import unicodedata
from dataclasses import dataclass

# Characters written as code points, so this file stays plain ASCII.
SINGLE_QUOTES = (0x2018, 0x2019, 0x201A, 0x201B, 0x02BC, 0xFF07)
DOUBLE_QUOTES = (0x201C, 0x201D, 0x201E, 0x201F, 0xFF02)
DASHES = (0x2010, 0x2011, 0x2012, 0x2013, 0x2014, 0x2015, 0x2212, 0xFE58, 0xFE63, 0xFF0D)
DROPPED = (0x00AD, 0x200B, 0x200C, 0x200D, 0x2060, 0xFEFF)  # soft hyphen and zero-width characters
X_LOOKALIKES = (0x0425, 0x03A7)  # Cyrillic Ha and Greek Chi, which NFKC does not turn into X
PLAIN = str.maketrans({
    **dict.fromkeys(SINGLE_QUOTES, "'"), **dict.fromkeys(DOUBLE_QUOTES, '"'),
    **dict.fromkeys(DASHES, "-"), **dict.fromkeys(DROPPED, None),
})
JOINERS = "'-"
MIN_REAL_WORDS = 3


@dataclass(frozen=True)
class Evidence:
    """The result of a quote check. `start` and `end` point into the original text."""
    ok: bool
    reason: str | None = None
    start: int | None = None
    end: int | None = None


def _clusters(text):
    """Each base character with the combining marks after it, and where it starts and ends."""
    start = 0
    for i in range(1, len(text) + 1):
        if i == len(text) or not unicodedata.combining(text[i]):
            yield text[start:i], start, i
            start = i


def _normalise(text):
    """The normalised text, and for each of its characters the span it came from in the original."""
    chars, spans = [], []
    for cluster, start, end in _clusters(text):
        for ch in unicodedata.normalize("NFC", cluster).translate(PLAIN):
            if ch.isspace():
                if chars and chars[-1] == " ":
                    spans[-1] = (spans[-1][0], end)
                    continue
                ch = " "
            chars.append(ch)
            spans.append((start, end))
    return "".join(chars), spans


def _is_word_char(ch):
    return ch.isalnum() or unicodedata.category(ch).startswith("M")


def _is_x(ch):
    return unicodedata.normalize("NFKC", ch) == "X" or ord(ch) in X_LOOKALIKES


def _is_real_word(word):
    return any(ch.isalpha() and not _is_x(ch) for ch in word)


def _is_redaction_mark(word):
    return any(_is_x(ch) for ch in word) and not _is_real_word(word)


def _joined(text, i, step):
    """True if position i in the text continues a word, directly or across an apostrophe or hyphen."""
    if not 0 <= i < len(text):
        return False
    if _is_word_char(text[i]):
        return True
    beyond = i + step
    return text[i] in JOINERS and 0 <= beyond < len(text) and _is_word_char(text[beyond])


def check_quote(text, quote):
    """Check a quote against the complaint text. The first failure names the reason (B3)."""
    needle = _normalise(quote)[0].strip()
    if not needle:
        return Evidence(False, "quote_empty")
    words = needle.split(" ")
    marked = [w for w in words if any(ch.isalnum() for ch in w)]
    if marked and not any(_is_real_word(w) for w in words) and all(_is_redaction_mark(w) for w in marked):
        return Evidence(False, "quote_redaction_only")
    if sum(_is_real_word(w) for w in words) < MIN_REAL_WORDS:
        return Evidence(False, "quote_too_short")
    haystack, spans = _normalise(text)
    at = haystack.find(needle)
    while at != -1:
        end = at + len(needle)
        if not _joined(haystack, at - 1, -1) and not _joined(haystack, end, 1):
            return Evidence(True, None, spans[at][0], spans[end - 1][1])
        at = haystack.find(needle, at + 1)
    return Evidence(False, "quote_not_in_text")
