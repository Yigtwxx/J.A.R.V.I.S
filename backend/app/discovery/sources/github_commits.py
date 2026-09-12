"""Public commit author addresses, which GitHub serves without a key.

The single highest-yield contact source for a developer, and the only one in the
pipeline that costs a request of its own — one per session, against an endpoint
that already carries this pipeline's traffic (``_API_HANDLERS["github"]`` reads
``users/{login}`` from the same host and the same rate limiter).

Two filters do all the work, and both exist because of what happens without them:

* ``*@users.noreply.github.com`` is GitHub's own privacy proxy. Publishing one
  would be publishing our inability to find an address, dressed as a finding.
* A ``PushEvent`` carries every commit on the pushed branch, including commits
  authored by somebody else. Without a name check the first result on a busy
  repository is a colleague's personal address — a stranger's contact detail
  attributed to the subject, which is the worst failure this module can have.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import TYPE_CHECKING, Any

from app.discovery.identity.contacts import ContactHit, normalize_email
from app.discovery.identity.normalize import fold_ascii
from app.discovery.types import EvidenceKind
from app.utils.logger import logger

if TYPE_CHECKING:  # pragma: no cover - import kept out of the runtime path
    from app.discovery.fetch.session import FetchSession

EVENTS_URL = "https://api.github.com/users/{username}/events/public"

MAX_ADDRESSES = 3
"""Enough for a personal and a work address. More is a repository's contributors."""

CONFIDENCE = 0.75
"""Below a `mailto:` the person wrote themselves: a commit address is a
configuration value, and a stale one outlives the account that set it."""


def _author_matches(author_name: str, name_tokens: Sequence[str]) -> bool:
    """True when the commit's author shares a name token with the anchor.

    Deliberately permissive — one shared token is enough, because a commit author
    name is as likely to be `yigtwx` as `Yigit Erdogan`. The check exists to
    exclude *other people*, not to prove identity.
    """
    if not name_tokens:
        return False
    folded = fold_ascii(author_name or "").casefold()
    if not folded:
        return False
    return any(token and fold_ascii(token).casefold() in folded for token in name_tokens)


def _commits_of(event: Any) -> list[dict[str, Any]]:
    if not isinstance(event, dict):
        return []
    payload = event.get("payload")
    commits = payload.get("commits") if isinstance(payload, dict) else None
    return [c for c in commits if isinstance(c, dict)] if isinstance(commits, list) else []


async def commit_emails(
    fetch: FetchSession,
    username: str,
    *,
    name_tokens: Sequence[str],
    limit: int = MAX_ADDRESSES,
) -> list[ContactHit]:
    """Addresses from ``username``'s public push events. One request, no key."""
    if not username:
        return []
    url = EVENTS_URL.format(username=username)
    profile_url = f"https://github.com/{username}"

    result, payload = await fetch.get_json(url)
    if payload is None:
        # Not silence: a rate-limited or refused API is a different thing from a
        # developer who has never pushed, and the log has to keep them apart.
        logger.log_warning(
            f"github commit e-mails unavailable for {username}: {result.status}",
            broadcast=False,
        )
        return []
    if not isinstance(payload, list):
        return []

    hits: list[ContactHit] = []
    seen: set[str] = set()
    for event in payload:
        for commit in _commits_of(event):
            author = commit.get("author")
            if not isinstance(author, dict):
                continue
            if not _author_matches(str(author.get("name") or ""), name_tokens):
                continue
            address = normalize_email(str(author.get("email") or ""))
            if address is None or address in seen:
                continue
            seen.add(address)
            hits.append(
                ContactHit(
                    kind=EvidenceKind.EMAIL,
                    value=address,
                    display=address,
                    source_url=profile_url,
                    extractor="github_commits",
                    confidence=CONFIDENCE,
                )
            )
            if len(hits) >= limit:
                return hits
    return hits
