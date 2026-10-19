"""The browse guard — the code that keeps "anonymous only" true in practice.

Every rule here is a user decision rather than a preference of ours, so each
test names the decision it protects. Nothing below touches the network: the
host-level SSRF gate is injected, and the scheme rules need no resolution.
"""

import pytest

from app.discovery.browse import guard
from app.discovery.browse.types import (
    ActionKind,
    BrowseAction,
    Element,
    RefusalReason,
)

VIEWPORT = (1280, 800)


def _elements() -> list[Element]:
    """A login page that also carries the public content we actually want."""
    return [
        Element(index=0, tag="a", role="link", name="Log in", href="/accounts/login/"),
        Element(index=1, tag="button", role="button", name="Accept all cookies"),
        Element(index=2, tag="a", role="link", name="janedoe", href="/janedoe/"),
        Element(
            index=3,
            tag="input",
            role="textbox",
            name="Password",
            input_type="password",
            autocomplete="current-password",
            in_password_form=True,
        ),
        Element(index=4, tag="input", role="searchbox", name="Search", input_type="text"),
        Element(index=5, tag="button", role="button", name="Continue", in_password_form=True),
        Element(index=6, tag="button", role="button", name="Show more", disabled=True),
        Element(
            index=7,
            tag="input",
            role="textbox",
            name="Verification code",
            input_type="text",
            autocomplete="one-time-code",
        ),
    ]


def _check(action: BrowseAction, **kwargs):
    kwargs.setdefault("url_is_safe", lambda _url: True)
    return guard.check(action, elements=_elements(), viewport=VIEWPORT, **kwargs)


@pytest.mark.parametrize("index", [3, 7])
def test_typing_into_a_credential_field_is_refused(index):
    """Password and one-time-code fields, by input type and by autocomplete."""
    refusal = _check(BrowseAction(kind=ActionKind.TYPE, index=index, text="hunter2"))

    assert refusal is not None, f"element [{index}] accepted typed input"
    assert refusal.reason is RefusalReason.CREDENTIAL_FIELD, f"got {refusal.reason!r}"


def test_clicking_an_unlabelled_submit_inside_a_password_form_is_refused():
    """[5] is only called "Continue" — the password form it sits in is the signal."""
    refusal = _check(BrowseAction(kind=ActionKind.CLICK, index=5))

    assert refusal is not None, "a submit inside a password form was allowed"
    assert refusal.reason is RefusalReason.LOGIN_SUBMIT, f"got {refusal.reason!r}"


def test_clicking_a_sign_in_link_outside_any_form_is_refused():
    refusal = _check(BrowseAction(kind=ActionKind.CLICK, index=0))

    assert refusal is not None, "a bare 'Log in' link was allowed"
    assert refusal.reason is RefusalReason.LOGIN_SUBMIT, f"got {refusal.reason!r}"


def test_an_ordinary_link_and_a_consent_button_are_allowed():
    """The guard must not be so broad that it blocks the work itself."""
    assert _check(BrowseAction(kind=ActionKind.CLICK, index=2)) is None, "a profile link was refused"
    assert _check(BrowseAction(kind=ActionKind.CLICK, index=1)) is None, "a cookie banner was refused"


def test_typing_a_handle_into_a_search_box_is_allowed():
    action = BrowseAction(kind=ActionKind.TYPE, index=4, text="yigtwx")

    assert _check(action) is None, "typing a handle into a search field was refused"


def test_a_disabled_element_is_refused_rather_than_clicked_uselessly():
    refusal = _check(BrowseAction(kind=ActionKind.CLICK, index=6))

    assert refusal is not None, "a disabled control was accepted"
    assert refusal.reason is RefusalReason.DISABLED_ELEMENT, f"got {refusal.reason!r}"


def test_an_index_absent_from_the_observation_is_refused():
    """A hallucinated index must cost a refusal, not an exception."""
    refusal = _check(BrowseAction(kind=ActionKind.CLICK, index=99))

    assert refusal is not None, "an unknown index was accepted"
    assert refusal.reason is RefusalReason.UNKNOWN_INDEX, f"got {refusal.reason!r}"


def test_typed_text_beyond_the_limit_is_refused():
    action = BrowseAction(kind=ActionKind.TYPE, index=4, text="x" * (guard.MAX_TYPE_CHARS + 1))
    refusal = _check(action)

    assert refusal is not None, "over-long input was accepted"
    assert refusal.reason is RefusalReason.TEXT_TOO_LONG, f"got {refusal.reason!r}"


@pytest.mark.parametrize(
    "url",
    [
        "file:///C:/Windows/win.ini",
        "javascript:alert(1)",
        "data:text/html,<h1>x</h1>",
        "chrome://settings",
        "https://user:pass@example.com/",
        "",
    ],
)
def test_navigation_off_public_http_is_refused(url):
    """Scheme and embedded-credential rules, none of which need DNS."""
    refusal = _check(BrowseAction(kind=ActionKind.NAVIGATE, url=url))

    assert refusal is not None, f"{url!r} was accepted for navigation"
    assert refusal.reason is RefusalReason.UNSAFE_URL, f"got {refusal.reason!r}"


def test_a_host_the_ssrf_gate_rejects_is_refused():
    """Host-level safety is delegated, so the guard must honour that verdict."""
    action = BrowseAction(kind=ActionKind.NAVIGATE, url="http://169.254.169.254/latest/meta-data/")
    refusal = _check(action, url_is_safe=lambda _url: False)

    assert refusal is not None, "the SSRF gate's rejection was ignored"
    assert refusal.reason is RefusalReason.UNSAFE_URL, f"got {refusal.reason!r}"


def test_any_public_https_url_is_allowed():
    """The user chose "any public http(s) URL" over a platform allowlist."""
    action = BrowseAction(kind=ActionKind.NAVIGATE, url="https://some-blog.example.org/about")

    assert _check(action) is None, "a public page was refused"


def test_pixel_clicks_are_refused_when_switched_off_and_allowed_when_on():
    action = BrowseAction(kind=ActionKind.CLICK_AT, x=430, y=210)

    refusal = _check(action, allow_pixel_clicks=False)
    assert refusal is not None, "pixel clicking ran while disabled"
    assert refusal.reason is RefusalReason.PIXEL_DISABLED, f"got {refusal.reason!r}"

    assert _check(action, allow_pixel_clicks=True) is None, "pixel clicking was refused while enabled"


@pytest.mark.parametrize("point", [(-1, 10), (10, -1), (1280, 10), (10, 800)])
def test_a_pixel_click_outside_the_viewport_is_refused(point):
    x, y = point
    refusal = _check(BrowseAction(kind=ActionKind.CLICK_AT, x=x, y=y))

    assert refusal is not None, f"({x}, {y}) was accepted outside {VIEWPORT}"
    assert refusal.reason is RefusalReason.OFF_VIEWPORT, f"got {refusal.reason!r}"


def test_a_pixel_click_missing_a_coordinate_is_refused_as_malformed():
    refusal = _check(BrowseAction(kind=ActionKind.CLICK_AT, x=100))

    assert refusal is not None, "click_at without y was accepted"
    assert refusal.reason is RefusalReason.MALFORMED, f"got {refusal.reason!r}"


@pytest.mark.parametrize(
    "kind", [ActionKind.SCROLL, ActionKind.WAIT, ActionKind.EXTRACT, ActionKind.DONE, ActionKind.GIVE_UP]
)
def test_actions_that_touch_nothing_are_always_allowed(kind):
    assert _check(BrowseAction(kind=kind)) is None, f"{kind} was refused"
