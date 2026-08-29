"""Text normalisation primitives shared by every identity module.

Turkish is a first-class citizen here, not an afterthought. Python's own casing
rules are wrong for Turkish in both directions:

- ``"İ".lower()`` returns ``"i̇"`` (Latin i **plus** a combining dot above),
  so a naive lowercase leaves an invisible combining mark behind.
- ``"ı"`` (dotless i) has no Unicode decomposition at all, so NFKD alone never
  turns it into ``"i"``.

Both cases are handled explicitly by translating the Turkish letters *before*
decomposition, which is why ``Işıl`` folds to ``isil`` and ``İstanbul`` folds to
``istanbul`` rather than to mangled look-alikes.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Sequence

# Turkish (and a few neighbouring) letters that must be mapped by hand.
_FOLD_MAP = str.maketrans(
    {
        "ı": "i",
        "İ": "i",
        "I": "i",
        "ğ": "g",
        "Ğ": "g",
        "ş": "s",
        "Ş": "s",
        "ö": "o",
        "Ö": "o",
        "ü": "u",
        "Ü": "u",
        "ç": "c",
        "Ç": "c",
        "ß": "ss",
        "æ": "ae",
        "Æ": "ae",
        "ø": "o",
        "Ø": "o",
        "đ": "d",
        "Đ": "d",
        "ł": "l",
        "Ł": "l",
        "þ": "th",
        "Þ": "th",
        "'": "",
        "’": "",
    }
)

# Legal-entity suffixes dropped by :func:`normalize_org` so that "Getir A.Ş."
# and "Getir" compare equal.
_ORG_LEGAL: frozenset[str] = frozenset(
    {
        "inc",
        "llc",
        "ltd",
        "limited",
        "gmbh",
        "as",
        "anonim",
        "sirket",
        "sirketi",
        "sti",
        "corp",
        "corporation",
        "co",
        "company",
        "plc",
        "sa",
        "bv",
        "nv",
        "oy",
        "oyj",
        "ab",
        "ag",
        "spa",
        "srl",
        "pte",
        "pty",
        "gida",
    }
)

_ORG_STOPWORDS: frozenset[str] = frozenset({"the", "and", "ve", "of"})

_NON_TOKEN = re.compile(r"[^a-z0-9]+")
_DOTTED_ABBREV = re.compile(r"\b(?:[a-z]\.){2,}")


def fold_ascii(text: str) -> str:
    """Lowercase ASCII fold: Turkish letters first, then NFKD minus combining marks.

    Anything that still is not ASCII after decomposition is dropped rather than
    guessed at, so the output is always safe to feed to a URL or a regex.
    """
    if not text:
        return ""
    translated = text.translate(_FOLD_MAP)
    decomposed = unicodedata.normalize("NFKD", translated)
    without_marks = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
    return "".join(ch for ch in without_marks if ch.isascii()).lower()


def name_tokens(name: str) -> tuple[str, ...]:
    """Folded, punctuation-free tokens. Single characters dropped, order preserved."""
    seen: set[str] = set()
    out: list[str] = []
    for token in _NON_TOKEN.split(fold_ascii(name)):
        if len(token) < 2 or token in seen:
            continue
        seen.add(token)
        out.append(token)
    return tuple(out)


def normalize_handle(handle: str) -> str:
    """Fold, strip a leading ``@`` and any leading/trailing separator characters."""
    folded = fold_ascii(handle).strip()
    return folded.lstrip("@").strip("._-/ ")


def normalize_org(name: str) -> str:
    """Company/school comparison key: folded, legal suffixes and stopwords removed.

    Dotted abbreviations collapse first (``a.ş.`` -> ``as``) so the suffix filter
    sees one token rather than two stray single letters.
    """
    folded = _DOTTED_ABBREV.sub(lambda m: m.group(0).replace(".", ""), fold_ascii(name))
    tokens = [t for t in _NON_TOKEN.split(folded) if t]
    kept = [t for t in tokens if t not in _ORG_LEGAL and t not in _ORG_STOPWORDS and len(t) > 1]
    # Never let the filter erase an organisation whose whole name looks like a
    # suffix (e.g. a company literally called "Co"): fall back to the raw tokens.
    return " ".join(kept or tokens)


def token_overlap(a: Sequence[str], b: Sequence[str]) -> float:
    """Jaccard overlap of two token sequences, 0.0 when either side is empty."""
    set_a, set_b = set(a), set(b)
    if not set_a or not set_b:
        return 0.0
    union = set_a | set_b
    return round(len(set_a & set_b) / len(union), 4)


def levenshtein(a: str, b: str) -> int:
    """Edit distance, iterative two-row implementation. No dependencies."""
    if a == b:
        return 0
    if not a:
        return len(b)
    if not b:
        return len(a)
    previous = list(range(len(b) + 1))
    for i, ch_a in enumerate(a, start=1):
        current = [i]
        for j, ch_b in enumerate(b, start=1):
            cost = 0 if ch_a == ch_b else 1
            current.append(min(previous[j] + 1, current[j - 1] + 1, previous[j - 1] + cost))
        previous = current
    return previous[-1]


def is_similar_handle(a: str, b: str, *, max_distance: int = 2) -> bool:
    """Whether two handles are plausibly the same identity.

    The allowance scales with length: two letters of slack on a three-character
    handle would match half the internet, so short handles must match exactly.
    """
    left, right = normalize_handle(a), normalize_handle(b)
    if not left or not right:
        return False
    if left == right:
        return True
    allowance = min(max_distance, max(1, min(len(left), len(right)) // 3))
    return levenshtein(left, right) <= allowance


def split_name(name: str) -> tuple[str, tuple[str, ...], str]:
    """``(first, middles, last)``. A single-token name yields an empty last name."""
    tokens = name_tokens(name)
    if not tokens:
        return "", (), ""
    if len(tokens) == 1:
        return tokens[0], (), ""
    return tokens[0], tokens[1:-1], tokens[-1]
