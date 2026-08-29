"""The safety allowlist for the browse tier. Pure, and the last word.

Two things this exists to guarantee, both of which are decisions the user made
rather than preferences of ours:

* **The browser never logs in.** Anonymous-only was chosen on 2026-08-22 and
  reaffirmed for this tier. Intent is not enough — a model looking at a page
  with a "Log in" button will eventually press it, so the refusal lives here,
  in code that runs before every action, rather than in a prompt.
* **The browser only ever reaches public http(s).** Host-level safety is
  delegated to ``sources.website.is_safe_url``, the SSRF gate the personal-site
  crawler already uses, instead of a second implementation that could drift
  from it.

A refusal is never silent: it is returned, published as a step, fed back to the
agent as its next observation, and it costs a step from the budget.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Sequence
from urllib.parse import urlsplit

from app.discovery.browse.types import (
    ActionKind,
    BrowseAction,
    Element,
    Refusal,
    RefusalReason,
)
from app.discovery.sources.website import is_safe_url

MAX_TYPE_CHARS = 120
"""Long enough for a username or a search phrase, short enough that the field
cannot be used to paste something the agent was never meant to compose."""

_CREDENTIAL_AUTOCOMPLETE: frozenset[str] = frozenset({"current-password", "new-password", "one-time-code"})

_CREDENTIAL_NAME = re.compile(r"pass\s?word|passwd|\bpwd\b|\botp\b|2fa|verification|security code", re.I)

_LOGIN_NAME = re.compile(
    r"\b(log\s?in|sign\s?in|sign\s?up|register|create account|continue with"
    r"|giri[sş] yap|kay[ıi]t ol)\b",
    re.I,
)
"""Turkish forms are here because the pipeline pins ``Accept-Language: en-US``
for parsing but sites still localise by IP, and this browser runs on a Turkish
residential address."""

_SAFE_SCHEMES: frozenset[str] = frozenset({"http", "https"})


def _element_by_index(elements: Sequence[Element], index: int | None) -> Element | None:
    if index is None:
        return None
    for element in elements:
        if element.index == index:
            return element
    return None


def is_credential_field(element: Element) -> bool:
    """A field that wants a secret, by any of the three signals a page offers."""
    if (element.input_type or "").lower() == "password":
        return True
    if (element.autocomplete or "").lower() in _CREDENTIAL_AUTOCOMPLETE:
        return True
    return bool(_CREDENTIAL_NAME.search(element.name or ""))


def is_login_control(element: Element) -> bool:
    """A control that starts or completes an authentication.

    ``in_password_form`` catches the unlabelled submit button that a name-based
    check alone would wave through — the dangerous case, because it is the one
    that actually posts credentials.
    """
    if element.in_password_form:
        return True
    return bool(_LOGIN_NAME.search(element.name or ""))


def _scheme_ok(url: str) -> bool:
    """Cheap, no-I/O half of the URL check: scheme and embedded credentials."""
    try:
        split = urlsplit((url or "").strip())
    except ValueError:
        return False
    if (split.scheme or "").lower() not in _SAFE_SCHEMES:
        return False
    return "@" not in (split.netloc or "")


def check(
    action: BrowseAction,
    *,
    elements: Sequence[Element],
    allow_pixel_clicks: bool = True,
    viewport: tuple[int, int] = (1280, 800),
    url_is_safe: Callable[[str], bool] = is_safe_url,
) -> Refusal | None:
    """Return the reason this action is refused, or ``None`` to allow it.

    ``url_is_safe`` is injected so the scheme rules can be tested without DNS;
    production always gets the real SSRF gate.
    """
    if action.kind in (ActionKind.CLICK, ActionKind.TYPE):
        element = _element_by_index(elements, action.index)
        if element is None:
            return Refusal(
                RefusalReason.UNKNOWN_INDEX,
                f"no element [{action.index}] in the current view",
            )
        if element.disabled:
            return Refusal(RefusalReason.DISABLED_ELEMENT, f"[{element.index}] is disabled")

        if action.kind is ActionKind.TYPE:
            if is_credential_field(element):
                return Refusal(
                    RefusalReason.CREDENTIAL_FIELD,
                    "this search never enters a password or a verification code",
                )
            if len(action.text or "") > MAX_TYPE_CHARS:
                return Refusal(
                    RefusalReason.TEXT_TOO_LONG,
                    f"{len(action.text)} characters, limit is {MAX_TYPE_CHARS}",
                )
        elif is_login_control(element):
            return Refusal(
                RefusalReason.LOGIN_SUBMIT,
                "this search stays logged out, so sign-in controls are off limits",
            )
        return None

    if action.kind is ActionKind.CLICK_AT:
        if not allow_pixel_clicks:
            return Refusal(RefusalReason.PIXEL_DISABLED, "pixel clicking is switched off")
        if action.x is None or action.y is None:
            return Refusal(RefusalReason.MALFORMED, "click_at needs both x and y")
        width, height = viewport
        if not (0 <= action.x < width and 0 <= action.y < height):
            return Refusal(
                RefusalReason.OFF_VIEWPORT,
                f"({action.x}, {action.y}) is outside the {width}x{height} viewport",
            )
        return None

    if action.kind is ActionKind.NAVIGATE:
        url = (action.url or "").strip()
        if not _scheme_ok(url) or not url_is_safe(url):
            return Refusal(
                RefusalReason.UNSAFE_URL,
                "only public http(s) addresses may be opened",
            )
        return None

    return None
