"""Deterministic pre-policy: the obvious move, for free.

Most of what stands between an anonymous browser and a public page is not a
puzzle. It is a cookie banner, an "app is better" interstitial, a "Show more"
expander, or an age gate — the same handful of controls, on every site, in two
languages. Asking a vision model to recognise them costs a full inference each
time and can get them wrong.

So this module runs first. When it recognises the situation the agent spends
zero inferences; when it does not, the model is asked. The panel labels each
step ``rule`` or ``model`` so a user can see which is which.

Pure: it takes an observation and returns an action or nothing. The guard still
runs on whatever it returns — a rule is a shortcut, never an exemption.
"""

from __future__ import annotations

import re

from app.discovery.browse.types import ActionKind, BrowseAction, Element, Observation

_CONSENT = re.compile(
    r"^(accept( all)?( cookies)?|allow all|agree|i agree|got it|ok(ay)?|understood"
    r"|t[üu]m[üu]n[üu] kabul et|kabul et|anlad[ıi]m|tamam)$",
    re.I,
)
"""Anchored, unlike the guard's patterns. A banner button says exactly this and
nothing else; a substring match would fire on a post whose text mentions
agreement."""

_DISMISS = re.compile(
    r"^(not now|maybe later|later|no thanks|dismiss|close|skip|continue as guest"
    r"|[şs]imdi de[ğg]il|daha sonra|hay[ıi]r te[şs]ekk[üu]rler|ge[çc])$",
    re.I,
)
"""The "Save your login info?" / "Open in app" family. Declining these is what
keeps an anonymous session anonymous without touching a credential."""

_EXPAND = re.compile(
    r"^(show|see|view|read|load)( more| all)?$|^more$|^(daha fazla|devam[ıi]n[ıi] g[öo]ster|t[üu]m[üu]n[üu] g[öo]r)$",
    re.I,
)

_AGE_GATE = re.compile(r"^(i am over \d+|yes,? i am( over \d+)?|continue|enter|18\+|evet)$", re.I)

_AGE_CONTEXT = re.compile(r"\bage\b|\b18\+|adult|ya[şs][ıi]n[ıi]z|ya[şs] s[ıi]n[ıi]r", re.I)


def _pick(elements: tuple[Element, ...], pattern: re.Pattern[str]) -> Element | None:
    """First enabled, non-login element whose accessible name matches.

    ``in_password_form`` is excluded here as well as in the guard. A rule that
    proposed a credential submit would be refused, but it would still cost a
    step and appear in the panel as something we tried.
    """
    for element in elements:
        if element.disabled or element.in_password_form:
            continue
        if element.input_type == "password":
            continue
        if pattern.match(element.name or ""):
            return element
    return None


def suggest(observation: Observation) -> BrowseAction | None:
    """The obvious action for this page, or ``None`` to ask the model.

    Order matters: consent and dismissal come first because they overlay the
    content, so nothing else on the page can be read until they are gone.
    """
    elements = observation.elements

    consent = _pick(elements, _CONSENT)
    if consent is not None:
        return BrowseAction(
            kind=ActionKind.CLICK,
            index=consent.index,
            thought="consent banner",
            by="rule",
        )

    dismiss = _pick(elements, _DISMISS)
    if dismiss is not None:
        return BrowseAction(
            kind=ActionKind.CLICK,
            index=dismiss.index,
            thought="dismissible interstitial",
            by="rule",
        )

    # Only when the page is *about* age — "Continue" and "Evet" are far too
    # common to click on their own account.
    if _AGE_CONTEXT.search(observation.text or ""):
        gate = _pick(elements, _AGE_GATE)
        if gate is not None:
            return BrowseAction(
                kind=ActionKind.CLICK,
                index=gate.index,
                thought="age gate",
                by="rule",
            )

    expand = _pick(elements, _EXPAND)
    if expand is not None:
        return BrowseAction(
            kind=ActionKind.CLICK,
            index=expand.index,
            thought="expander",
            by="rule",
        )

    return None
