"""Identity layer of the discovery pipeline.

Four concerns, deliberately kept separate:

- :mod:`normalize` — Turkish-aware folding, tokens, edit distance. No I/O.
- :mod:`usernames` — handle candidates with provenance and priors.
- :mod:`anchor` — the one subject every candidate is judged against.
- :mod:`workedu` — employment/education extraction, grounded against its source.

Everything here is pure and offline: no network, no LLM, no database. That is
what makes identity decisions reproducible and testable.
"""

from __future__ import annotations

from app.discovery.identity.anchor import (
    CONFIRMED_GITHUB_API,
    CONFIRMED_RECIPROCAL_LINK,
    CONFIRMED_USER_ANSWER,
    Anchor,
    build_anchor,
    conflicts,
    strengthen,
)
from app.discovery.identity.normalize import (
    fold_ascii,
    is_similar_handle,
    levenshtein,
    name_tokens,
    normalize_handle,
    normalize_org,
    split_name,
    token_overlap,
)
from app.discovery.identity.usernames import (
    MAX_GENERATION,
    UsernameCandidate,
    UsernameSource,
    from_domain,
    from_email,
    from_full_name,
    from_seed_username,
    merge,
    normalize_for_platform,
    top_n,
)
from app.discovery.identity.workedu import (
    EducationRecord,
    WorkRecord,
    dedupe_education,
    dedupe_work,
    from_bio_text,
    from_github_profile,
    from_json_ld,
    from_linkedin_serp_title,
    is_grounded,
)

__all__ = [
    "CONFIRMED_GITHUB_API",
    "CONFIRMED_RECIPROCAL_LINK",
    "CONFIRMED_USER_ANSWER",
    "MAX_GENERATION",
    "Anchor",
    "EducationRecord",
    "UsernameCandidate",
    "UsernameSource",
    "WorkRecord",
    "build_anchor",
    "conflicts",
    "dedupe_education",
    "dedupe_work",
    "fold_ascii",
    "from_bio_text",
    "from_domain",
    "from_email",
    "from_full_name",
    "from_github_profile",
    "from_json_ld",
    "from_linkedin_serp_title",
    "from_seed_username",
    "is_grounded",
    "is_similar_handle",
    "levenshtein",
    "merge",
    "name_tokens",
    "normalize_for_platform",
    "normalize_handle",
    "normalize_org",
    "split_name",
    "strengthen",
    "token_overlap",
    "top_n",
]
