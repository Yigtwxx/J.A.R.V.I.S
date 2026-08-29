"""Reading a stated gender out of text, in Turkish and English.

Two different jobs live here and they have different tolerances:

* :func:`parse_gender_word` reads what the **user** typed ("Eylul Akduman, kız").
  The user is authoritative, so the vocabulary can be generous.
* :func:`gender_from_bio` reads what a **profile** says about itself. That feeds a
  scoring signal, so it is deliberately mean: only explicit markers count, a bio
  carrying markers of both genders returns ``UNKNOWN``, and a *given name* is
  never evidence — Turkish is full of unisex names (Deniz, Evren, Yağmur, Özgür,
  Umut, Şevval) and guessing from them would fabricate a contradiction for the
  one person the search is actually looking for.

Everything is matched on whole folded tokens, never as substrings: ``her`` is
inside ``there`` and ``his`` is inside ``history``, and a substring match would
have declared half the web female.
"""

from __future__ import annotations

from app.discovery.identity.normalize import name_tokens
from app.discovery.types import Gender

# What a user may type to state the target's gender. Turkish first, then English.
_USER_FEMALE: frozenset[str] = frozenset(
    {"kiz", "kadin", "bayan", "hanim", "disi", "female", "woman", "girl", "she", "her", "f", "k"}
)
_USER_MALE: frozenset[str] = frozenset(
    {"erkek", "oglan", "adam", "bay", "bey", "male", "man", "boy", "he", "him", "m", "e"}
)

# What counts as a marker *on a profile*. Narrower on purpose, and with the
# common Turkish inflections spelled out rather than matched by prefix, which
# would have made "babacan" (a surname) read as "baba" (father).
_BIO_FEMALE: frozenset[str] = frozenset(
    {
        "she",
        "her",
        "hers",
        "herself",
        "woman",
        "female",
        "mrs",
        "ms",
        "miss",
        "kadin",
        "kadinim",
        "bayan",
        "hanim",
        "hanimefendi",
        "anne",
        "annesi",
        "anneyim",
        "kizi",
        "kizim",
    }
)
_BIO_MALE: frozenset[str] = frozenset(
    {
        "he",
        "him",
        "his",
        "himself",
        "man",
        "male",
        "mr",
        "erkek",
        "erkegim",
        "bay",
        "beyefendi",
        "baba",
        "babasi",
        "babayim",
        "oglu",
        "oglum",
    }
)


def _decide(tokens: frozenset[str], female: frozenset[str], male: frozenset[str]) -> Gender:
    """Return a gender only when exactly one side of the vocabulary fired.

    A text carrying both ("he/him" in a bio that also thanks "her") tells us
    nothing, and answering anyway is how a wrong exclusion gets manufactured.
    """
    hit_female = bool(tokens & female)
    hit_male = bool(tokens & male)
    if hit_female == hit_male:
        return Gender.UNKNOWN
    return Gender.FEMALE if hit_female else Gender.MALE


# Word-level matching runs over a *name*, so anything that doubles as a personal
# name is dropped: "Adam Smith" must not be read as "a man called Smith", and the
# single letters would eat the "K." out of "Ahmet K. Yilmaz".
_TOKEN_FEMALE: frozenset[str] = frozenset({"kiz", "kadin", "bayan", "hanim", "disi", "female", "woman", "girl"})
_TOKEN_MALE: frozenset[str] = frozenset({"erkek", "oglan", "male", "man", "boy"})


def parse_gender_token(word: str) -> Gender:
    """Strict single-word reading, for scanning a segment that also holds a name."""
    tokens = frozenset(name_tokens(word))
    if len(tokens) != 1:
        return Gender.UNKNOWN
    return _decide(tokens, _TOKEN_FEMALE, _TOKEN_MALE)


def parse_gender_word(text: str) -> Gender:
    """Read a gender the user stated. ``UNKNOWN`` when the text says nothing.

    Single letters are accepted here ("k", "e", "f", "m") because a user writing
    a compact brief uses them; ``name_tokens`` drops one-character tokens, so
    they are checked against the raw folded segment separately.
    """
    stripped = (text or "").strip()
    if not stripped:
        return Gender.UNKNOWN
    tokens = set(name_tokens(stripped))
    # `name_tokens` drops single characters, so a bare "k" would vanish entirely.
    if len(stripped) == 1:
        tokens.add(stripped.casefold())
    return _decide(frozenset(tokens), _USER_FEMALE, _USER_MALE)


def gender_from_bio(bio: str) -> Gender:
    """Read an explicit gender marker off a profile bio. ``UNKNOWN`` by default.

    Returning ``UNKNOWN`` is the overwhelmingly common answer and the right one:
    most bios simply do not state a gender, and silence must never be read as
    disagreement.
    """
    if not bio or not bio.strip():
        return Gender.UNKNOWN
    return _decide(frozenset(name_tokens(bio)), _BIO_FEMALE, _BIO_MALE)
