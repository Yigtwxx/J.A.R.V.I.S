"""Username candidate generation with provenance and priors.

Ported from ``ScraperService.generate_username_variations`` /
``generate_name_username_variations``. The permutation logic itself was already
good — Turkish diacritic folding, vowel dropping, separator swaps — so it is
kept, converted to pure functions, and given two things it lacked:

- **provenance**: where a candidate came from (:class:`UsernameSource`) and which
  candidate it was derived from, so a false positive can be traced back.
- **a prior**: how much budget a candidate deserves in a round. A prior is *not*
  a probability of correctness — ``ygmrzgn`` at 0.25 is not "25% right", it is
  "only worth checking once the better shapes are exhausted".

Output order is fully deterministic (``-prior``, then generation, then value),
so the same input always produces the same list.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass, replace
from enum import StrEnum

from app.discovery.identity.normalize import fold_ascii, normalize_handle, split_name
from app.discovery.platforms.registry import get_registry
from app.discovery.platforms.urlmatch import is_generic_handle

MAX_GENERATION = 3
"""Candidates beyond this generation are never expanded again — that is how a
permutation-of-a-permutation explosion is prevented."""

MIN_LENGTH = 2

PRIOR_GIVEN = 1.00
PRIOR_OBSERVED = 0.95
PRIOR_EMAIL_LOCAL = 0.90
PRIOR_FIRSTLAST = 0.70
PRIOR_SEPARATED = 0.50
PRIOR_REORDERED = 0.35
PRIOR_VOWEL_DROP = 0.25
PRIOR_DIGIT_SUFFIX = 0.20

_VOWELS = frozenset("aeiou")
_DIGIT_SUFFIXES = ("1", "2", "99", "_")
_HANDLE_SUFFIXES = ("_official", "_real", "_tv", "_yt", "_ig", "official", "real")
_REPEAT_TAIL = re.compile(r"(.)\1+$")
_TRAILING_DIGITS = re.compile(r"\d+$")
_MULTI_TLD = ("com.tr", "co.uk", "com.au", "co.jp", "com.br", "org.tr", "net.tr", "edu.tr", "gov.tr")


class UsernameSource(StrEnum):
    """Where a candidate came from. Drives both the prior and the audit trail."""

    GIVEN = "given"
    OBSERVED = "observed"
    ANSWER = "answer"
    EMAIL_LOCAL = "email_local"
    NAME_PERMUTATION = "name_permutation"
    DOMAIN = "domain"


@dataclass(frozen=True, slots=True)
class UsernameCandidate:
    """One handle worth checking, plus why we think it is worth checking."""

    value: str
    source: UsernameSource
    generation: int = 0
    """0 = seed. Candidates above :data:`MAX_GENERATION` are never expanded."""

    parent: str | None = None
    prior: float = 0.5
    """0..1 budget weight, NOT a probability of correctness."""


def _sort_key(candidate: UsernameCandidate) -> tuple[float, int, str]:
    return -candidate.prior, candidate.generation, candidate.value


class _Collector:
    """Accumulates candidates, keeping the best prior per distinct value."""

    def __init__(self, source: UsernameSource, generation: int, parent: str | None) -> None:
        self._items: dict[str, UsernameCandidate] = {}
        self._source = source
        self._generation = generation
        self._parent = parent

    def add(self, value: str, prior: float) -> None:
        cleaned = value.strip().lower()
        if len(cleaned) < MIN_LENGTH or is_generic_handle(cleaned):
            return
        current = self._items.get(cleaned)
        if current is not None and current.prior >= prior:
            return
        self._items[cleaned] = UsernameCandidate(
            value=cleaned,
            source=self._source,
            generation=self._generation,
            parent=self._parent,
            prior=prior,
        )

    def result(self, limit: int) -> list[UsernameCandidate]:
        return sorted(self._items.values(), key=_sort_key)[: max(0, limit)]


def _drop_vowels(text: str) -> str:
    return "".join(ch for ch in text if ch not in _VOWELS)


def from_full_name(name: str, *, limit: int = 40) -> list[UsernameCandidate]:
    """Permutations of a real name: concatenations, separators, initials, vowel drops."""
    first, middles, last = split_name(name)
    if not first:
        return []
    out = _Collector(UsernameSource.NAME_PERMUTATION, 0, None)

    if not last:
        out.add(first, PRIOR_FIRSTLAST)
        for digit in _DIGIT_SUFFIXES:
            out.add(first + digit, PRIOR_DIGIT_SUFFIX)
        return out.result(limit)

    out.add(first + last, PRIOR_FIRSTLAST)
    out.add(f"{first}.{last}", PRIOR_FIRSTLAST)
    out.add(f"{first}_{last}", PRIOR_SEPARATED)
    out.add(f"{first}-{last}", PRIOR_SEPARATED)
    out.add(first[0] + last, PRIOR_SEPARATED)
    out.add(first + last[0], PRIOR_SEPARATED)
    out.add(last + first, PRIOR_REORDERED)
    out.add(f"{last}.{first}", PRIOR_REORDERED)
    out.add(f"{last}_{first}", PRIOR_REORDERED)
    out.add(first, PRIOR_REORDERED)
    out.add(last, PRIOR_REORDERED)

    if len(first) > 4:
        out.add(first[:4] + last, PRIOR_REORDERED)
    if len(last) > 3:
        out.add(first + last[:3], PRIOR_REORDERED)

    initials = first[0] + "".join(m[0] for m in middles)
    out.add(initials + last[0], PRIOR_REORDERED)
    out.add("".join(f"{ch}." for ch in initials + last[0]), PRIOR_REORDERED)
    out.add(initials + last, PRIOR_SEPARATED)

    if middles:
        out.add(first + "".join(middles) + last, PRIOR_FIRSTLAST)
        out.add(".".join([first, *middles, last]), PRIOR_SEPARATED)
        out.add("_".join([first, *middles, last]), PRIOR_SEPARATED)

    consonant_first, consonant_last = _drop_vowels(first), _drop_vowels(last)
    if len(consonant_first + consonant_last) >= 4:
        out.add(consonant_first + consonant_last, PRIOR_VOWEL_DROP)
        out.add(f"{consonant_first}_{consonant_last}", PRIOR_VOWEL_DROP)

    for digit in _DIGIT_SUFFIXES:
        out.add(first + last + digit, PRIOR_DIGIT_SUFFIX)

    return out.result(limit)


def from_seed_username(seed: str, *, limit: int = 25, generation: int = 1) -> list[UsernameCandidate]:
    """Variations of a handle we have actually observed somewhere.

    Returns the empty list past :data:`MAX_GENERATION` so an expansion chain
    terminates instead of drifting further from the real identity each round.
    """
    if generation > MAX_GENERATION:
        return []
    base = normalize_handle(seed)
    if len(base) < 3:
        return []
    out = _Collector(UsernameSource.NAME_PERMUTATION, generation, base)

    raw = seed.strip().lower()
    if base != raw:
        out.add(base, PRIOR_FIRSTLAST)

    stripped = _REPEAT_TAIL.sub(r"\1", base)
    out.add(stripped, PRIOR_REORDERED)
    out.add(base + base[-1], PRIOR_REORDERED)

    no_digits = _TRAILING_DIGITS.sub("", base)
    if no_digits != base:
        out.add(no_digits, PRIOR_SEPARATED)

    for separator in (".", "_", "-"):
        if separator not in base:
            continue
        parts = base.split(separator)
        for replacement in (".", "_", "-"):
            if replacement != separator:
                out.add(replacement.join(parts), PRIOR_SEPARATED)
        out.add("".join(parts), PRIOR_SEPARATED)

    for suffix in _HANDLE_SUFFIXES:
        if base.endswith(suffix) and len(base) - len(suffix) >= 3:
            out.add(base[: -len(suffix)], PRIOR_REORDERED)

    for digit in _DIGIT_SUFFIXES:
        out.add(base + digit, PRIOR_DIGIT_SUFFIX)

    return [c for c in out.result(limit + 1) if c.value != base][:limit]


def from_email(email: str) -> list[UsernameCandidate]:
    """The local part of an email is one of the strongest keyless handle signals."""
    local = fold_ascii((email or "").split("@", 1)[0])
    local = local.strip(" .")
    if len(local) < MIN_LENGTH:
        return []
    out = _Collector(UsernameSource.EMAIL_LOCAL, 0, None)
    out.add(local, PRIOR_EMAIL_LOCAL)
    untagged = local.split("+", 1)[0].strip(".")
    out.add(untagged, PRIOR_EMAIL_LOCAL)
    out.add(re.sub(r"[._\-]+", "", untagged), PRIOR_SEPARATED)
    out.add(_TRAILING_DIGITS.sub("", untagged), PRIOR_SEPARATED)
    return out.result(8)


def from_domain(domain: str) -> list[UsernameCandidate]:
    """A personal domain (``yagmurozgan.com``) usually restates the handle."""
    host = fold_ascii(domain).strip().strip("/")
    host = host.split("//")[-1].split("/", 1)[0].split(":", 1)[0]
    for prefix in ("www.", "blog.", "m."):
        if host.startswith(prefix):
            host = host[len(prefix) :]
    for tld in _MULTI_TLD:
        if host.endswith("." + tld):
            host = host[: -(len(tld) + 1)]
            break
    else:
        host = host.rsplit(".", 1)[0] if "." in host else host
    label = host.replace(".", "")
    if len(label) < 3:
        return []
    out = _Collector(UsernameSource.DOMAIN, 0, None)
    out.add(label, PRIOR_SEPARATED)
    out.add(_TRAILING_DIGITS.sub("", label), PRIOR_REORDERED)
    return out.result(4)


# How brands actually name their accounts. Person-shaped permutations do not
# apply: no company is `@trendyol99`, and swapping the word order of "Peak Games"
# into `@gamespeak` invents a handle nobody registered. Observed live — a company
# search generated exactly those and found only two of Trendyol's many accounts.
_COMPANY_SUFFIXES: tuple[str, ...] = ("", "official", "app", "group", "global", "hq", "co", "com", "tr", "inc")
_COMPANY_PREFIXES: tuple[str, ...] = ("", "we", "team", "hello", "join")
_COMPANY_STOPWORDS: frozenset[str] = frozenset({"the", "and", "ve", "inc", "llc", "ltd", "co", "corp", "as", "sa"})


def from_company_name(name: str, *, limit: int = 30) -> list[UsernameCandidate]:
    """Handle candidates for a brand rather than a person.

    Emits the exact name, its concatenated and separated multi-word forms, and the
    common brand decorations (`…official`, `…app`, `…tr`, `we…`). Deliberately
    omits digit suffixes, word-order swaps and vowel-dropping — all of which are
    person-name heuristics that produce handles no company would register.
    """
    tokens = [t for t in fold_ascii(name).lower().split() if t and t not in _COMPANY_STOPWORDS]
    if not tokens:
        return []

    base = "".join(tokens)
    if len(base) < 2:
        return []

    out = _Collector(UsernameSource.NAME_PERMUTATION, 0, None)
    out.add(base, PRIOR_GIVEN)

    if len(tokens) > 1:
        for separator in (".", "_", "-"):
            out.add(separator.join(tokens), PRIOR_SEPARATED)
        # An acronym is only distinctive enough to be worth a request at 3+ letters.
        acronym = "".join(token[0] for token in tokens)
        if len(acronym) >= 3:
            out.add(acronym, PRIOR_REORDERED)

    for suffix in _COMPANY_SUFFIXES:
        if not suffix:
            continue
        out.add(f"{base}{suffix}", PRIOR_SEPARATED)
        out.add(f"{base}_{suffix}", PRIOR_REORDERED)
    for prefix in _COMPANY_PREFIXES:
        if prefix:
            out.add(f"{prefix}{base}", PRIOR_REORDERED)

    return out.result(limit)


def normalize_for_platform(value: str, platform: str) -> str | None:
    """Adapt a candidate to one platform's rules, or ``None`` when it is illegal there.

    Candidates are never silently rewritten into a different handle: X forbids
    ``.``, so ``foo.bar`` is *dropped* rather than turned into ``foobar``, which
    would be a handle nobody ever claimed. Only trims that cannot change identity
    (GitHub's leading/trailing hyphen, Snapchat's leading symbol) are applied.
    """
    spec = get_registry().get(platform)
    if spec is None:
        return None
    handle = (value or "").strip().lower()
    if not handle or is_generic_handle(handle):
        return None

    if platform == "x" and "." in handle:
        return None
    if platform == "github":
        handle = handle.strip("-")
    if platform == "snapchat":
        handle = handle.lstrip("._-")
    if platform in {"instagram", "threads", "tiktok"}:
        handle = handle.strip(".")

    if not handle or not spec.accepts_username(handle):
        return None
    return handle


def merge(existing: dict[str, UsernameCandidate], new: Iterable[UsernameCandidate]) -> list[UsernameCandidate]:
    """Fold ``new`` into ``existing`` in place, then return the sorted candidate list.

    A value seen twice keeps the **highest** prior (the strongest reason to check
    it) and the **lowest** generation (the shortest derivation chain).
    """
    for candidate in new:
        current = existing.get(candidate.value)
        if current is None:
            existing[candidate.value] = candidate
            continue
        best = candidate if candidate.prior > current.prior else current
        shortest = candidate if candidate.generation < current.generation else current
        existing[candidate.value] = replace(
            best,
            generation=shortest.generation,
            parent=shortest.parent,
            prior=max(current.prior, candidate.prior),
        )
    return sorted(existing.values(), key=_sort_key)


def top_n(candidates: Iterable[UsernameCandidate], n: int) -> list[UsernameCandidate]:
    """The ``n`` highest-priority candidates, deterministically ordered."""
    return sorted(candidates, key=_sort_key)[: max(0, n)]
