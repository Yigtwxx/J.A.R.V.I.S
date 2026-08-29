"""Turn what the user typed into a :class:`SearchBrief`.

The parser is deliberately **deterministic and conservative**. It recognises the
shapes that carry real identity information and cannot be mistaken for a name —
a profile URL, an ``@handle``, an email address, a ``key: value`` pair, an
unambiguous gender word — and it leaves everything else alone. Whatever it could
not place lands in :attr:`SearchBrief.unparsed`, which the UI shows back, rather
than being guessed into a field that would silently narrow the search.

Order matters and is fixed:

1. A standalone one-word segment that is a gender word is read with the
   generous vocabulary — but only when the user actually separated the fields.
   A query of a single segment is a name and nothing else.
2. ``key: value`` on the whole segment.
3. Word-level extraction inside the segment — URL, email, ``@handle``, bare
   domain, unambiguous gender word. Claimed words are removed.
4. The first still-unclaimed segment becomes the name; the rest become
   ``unparsed``.

A URL is only ever recognised through
:func:`app.discovery.platforms.urlmatch.match_profile_url` — host equality plus an
anchored path pattern. Regexing the URL string is what once turned
``roblox.com/users/1`` into an X profile.
"""

from __future__ import annotations

import re

from app.discovery.brief.gender import parse_gender_token, parse_gender_word
from app.discovery.brief.model import KnownProfile, SearchBrief
from app.discovery.platforms.urlmatch import match_profile_url
from app.discovery.types import EntityType, Gender

_SEGMENT_SPLIT = re.compile(r"[,;\n\r|]+")
_EMAIL = re.compile(r"^[^\s@]+@[^\s@]+\.[A-Za-z]{2,}$")
# A bare host: at least one dot, no path. `match_profile_url` has already had
# first refusal, so anything reaching here is not a known platform — it is the
# target's own site, which `personal_site_backlink` (+25) can corroborate.
_BARE_DOMAIN = re.compile(r"^(?:https?://)?(?:www\.)?([A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+)/?$")
_HANDLE = re.compile(r"^@([A-Za-z0-9._-]{2,40})$")
_WRAPPERS = "\"'“”‘’()[]<>"

# `key: value` labels, folded to lowercase ASCII before lookup so "Şehir" and
# "sehir" both land. Unknown keys are left in the text rather than dropped.
_FIELD_KEYS: dict[str, str] = {
    "isim": "name",
    "ad": "name",
    "adi": "name",
    "name": "name",
    "cinsiyet": "gender",
    "gender": "gender",
    "sehir": "location",
    "konum": "location",
    "il": "location",
    "memleket": "location",
    "yer": "location",
    "city": "location",
    "location": "location",
    "lives": "location",
    "okul": "school",
    "universite": "school",
    "lise": "school",
    "bolum": "school",
    "school": "school",
    "university": "school",
    "college": "school",
    "is": "employer",
    "isyeri": "employer",
    "firma": "employer",
    "sirket": "employer",
    "kurum": "employer",
    "work": "employer",
    "works": "employer",
    "employer": "employer",
    "company": "employer",
    "job": "employer",
    "mail": "email",
    "eposta": "email",
    "email": "email",
    "site": "domain",
    "web": "domain",
    "website": "domain",
    "domain": "domain",
    "kullanici": "username",
    "kullaniciadi": "username",
    "handle": "username",
    "nick": "username",
    "username": "username",
}

_KEY_FOLD = str.maketrans(
    {
        "ı": "i",
        "İ": "i",
        "ş": "s",
        "Ş": "s",
        "ğ": "g",
        "Ğ": "g",
        "ü": "u",
        "Ü": "u",
        "ö": "o",
        "Ö": "o",
        "ç": "c",
        "Ç": "c",
    }
)

MAX_KNOWN_PROFILES = 10
MAX_USERNAMES = 10
MAX_UNPARSED = 10


class _Accumulator:
    """Mutable working set, frozen into a :class:`SearchBrief` at the end."""

    def __init__(self) -> None:
        self.name: str = ""
        self.gender: Gender = Gender.UNKNOWN
        self.known: list[KnownProfile] = []
        self.usernames: list[str] = []
        self.location: str | None = None
        self.employer: str | None = None
        self.school: str | None = None
        self.email: str | None = None
        self.domain: str | None = None
        self.unparsed: list[str] = []

    def add_profile(self, profile: KnownProfile) -> None:
        """First URL for a platform wins; a second one is surfaced, not silently dropped.

        Two accounts on one platform is a question, not a fact. Keeping the last
        one would answer it without asking, and dropping it would hide that the
        user said something we did not use.
        """
        if len(self.known) >= MAX_KNOWN_PROFILES:
            self.unparsed.append(profile.raw_url or profile.canonical_url)
            return
        if profile.platform in {p.platform for p in self.known}:
            self.unparsed.append(profile.raw_url or profile.canonical_url)
            return
        self.known.append(profile)

    def add_username(self, value: str) -> None:
        cleaned = value.strip().lstrip("@")
        if not cleaned or len(self.usernames) >= MAX_USERNAMES:
            return
        if cleaned.casefold() in {u.casefold() for u in self.usernames}:
            return
        self.usernames.append(cleaned)

    def set_field(self, field: str, value: str) -> None:
        """Assign a text field. The first value wins — a later one is not a correction."""
        cleaned = " ".join((value or "").split())
        if not cleaned:
            return
        if field == "gender":
            if self.gender is Gender.UNKNOWN:
                self.gender = parse_gender_word(cleaned)
            return
        if field == "name":
            self.name = self.name or cleaned
            return
        if field == "username":
            self.add_username(cleaned)
            return
        if getattr(self, field, None) is None:
            setattr(self, field, cleaned)


def _fold_key(text: str) -> str:
    return text.translate(_KEY_FOLD).casefold().replace(" ", "").replace("_", "")


def _claim_words(segment: str, acc: _Accumulator) -> str:
    """Pull the unmistakable shapes out of one segment, returning what is left."""
    remaining: list[str] = []
    for word in segment.split():
        stripped = word.strip(_WRAPPERS)
        if not stripped:
            continue

        match = match_profile_url(stripped)
        if match is not None:
            acc.add_profile(KnownProfile.from_match(match))
            continue

        if _EMAIL.match(stripped):
            acc.set_field("email", stripped.lower())
            continue

        handle = _HANDLE.match(stripped)
        if handle is not None:
            acc.add_username(handle.group(1))
            continue

        domain = _BARE_DOMAIN.match(stripped)
        if domain is not None:
            acc.set_field("domain", domain.group(1).lower())
            continue

        spoken = parse_gender_token(stripped)
        if spoken is not Gender.UNKNOWN:
            if acc.gender is Gender.UNKNOWN:
                acc.gender = spoken
            continue

        remaining.append(stripped)
    return " ".join(remaining)


def _claim_key_value(segment: str, acc: _Accumulator) -> str:
    """Consume a leading ``key: value`` label. Returns "" when it was consumed."""
    if ":" not in segment:
        return segment
    label, _, value = segment.partition(":")
    field = _FIELD_KEYS.get(_fold_key(label))
    if field is None or not value.strip():
        return segment
    acc.set_field(field, value)
    return ""


def parse_brief(text: str, *, entity: EntityType = EntityType.PERSON) -> SearchBrief:
    """Read a free-text query into a brief. Never raises, never invents a field."""
    raw = (text or "").strip()
    acc = _Accumulator()
    leftovers: list[str] = []

    segments = [" ".join(chunk.split()) for chunk in _SEGMENT_SPLIT.split(raw)]
    segments = [segment for segment in segments if segment]
    # A query that is one segment is a name and nothing else. Without this,
    # searching for "Adam Smith" read "adam" as "a man" and the name lost a word;
    # the generous vocabulary is only safe once the user has separated the fields.
    generous_gender = len(segments) > 1

    for segment in segments:
        # A standalone one-word segment ("kız", "k", "she/her") is read with the
        # generous vocabulary. Inside a longer segment only the unambiguous words
        # count, so "Adam Smith, erkek" keeps its first name and its gender.
        if generous_gender and len(segment.split()) == 1:
            spoken = parse_gender_word(segment)
            if spoken is not Gender.UNKNOWN:
                if acc.gender is Gender.UNKNOWN:
                    acc.gender = spoken
                continue

        residual = _claim_key_value(segment, acc)
        if not residual:
            continue
        residual = _claim_words(residual, acc).strip()
        if residual:
            leftovers.append(residual)

    if not acc.name and leftovers:
        acc.name = leftovers.pop(0)
    acc.unparsed.extend(leftovers)

    return SearchBrief(
        # An empty name would make the whole search meaningless, so a query that
        # parsed away to nothing keeps its original text.
        name=acc.name or raw,
        entity=entity,
        gender=acc.gender,
        known_profiles=tuple(acc.known),
        usernames=tuple(acc.usernames),
        location=acc.location,
        employer=acc.employer,
        school=acc.school,
        email=acc.email,
        domain=acc.domain,
        unparsed=tuple(acc.unparsed[:MAX_UNPARSED]),
    )
