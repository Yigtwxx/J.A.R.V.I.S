"""Observation rendering and the deterministic pre-policy. Both pure.

The pre-policy matters more than it looks: every situation it recognises is a
vision inference not spent, and on an 8 GB card inferences are the budget.
"""

import pytest

from app.discovery.browse import rules
from app.discovery.browse.observe import (
    MAX_ELEMENTS,
    describe_action,
    number_elements,
    render_observation,
)
from app.discovery.browse.types import ActionKind, BrowseAction, Element, Observation


def _observation(elements, *, text: str = "", step: int = 1) -> Observation:
    return Observation(
        task="reach the public profile text of instagram.com/janedoe",
        url="https://www.instagram.com/janedoe/",
        title="Jane Doe (@janedoe)",
        text=text,
        elements=tuple(elements),
        step=step,
        max_steps=12,
        scroll_y=0,
        scroll_height=3400,
        viewport_height=800,
    )


def _named(*names: str) -> tuple[Element, ...]:
    return tuple(Element(index=i, tag="button", role="button", name=name) for i, name in enumerate(names))


# -- number_elements ---------------------------------------------------------


def test_indices_are_assigned_in_order_so_the_overlay_and_the_guard_agree():
    elements = number_elements([{"tag": "A", "name": "one"}, {"tag": "BUTTON", "name": "two"}])

    assert [e.index for e in elements] == [0, 1], f"got {[e.index for e in elements]}"
    assert elements[0].tag == "a", f"tags should be folded to lowercase, got {elements[0].tag!r}"


def test_a_malformed_box_degrades_to_zeroes_rather_than_raising():
    """The script runs in a page we do not control; it can return anything."""
    elements = number_elements([{"tag": "a", "name": "x", "box": ["nope", None]}])

    assert elements[0].box == (0, 0, 0, 0), f"got {elements[0].box!r}"


def test_non_dict_entries_are_skipped():
    elements = number_elements([{"tag": "a", "name": "keep"}, "junk", None])

    assert len(elements) == 1, f"expected the junk to be dropped, got {len(elements)} elements"


def test_the_element_list_is_capped_so_the_observation_stays_readable():
    elements = number_elements([{"tag": "a", "name": f"n{i}"} for i in range(MAX_ELEMENTS + 25)])

    assert len(elements) == MAX_ELEMENTS, f"got {len(elements)}"


def test_a_paragraph_of_alt_text_is_clipped_not_carried_whole():
    elements = number_elements([{"tag": "img", "name": "word " * 200}])

    assert len(elements[0].name) <= 60, f"name was {len(elements[0].name)} chars"


# -- render_observation ------------------------------------------------------


def test_the_rendered_observation_carries_the_task_url_and_every_element():
    text = render_observation(_observation(_named("Accept all", "janedoe")))

    assert "TASK: reach the public profile" in text, text
    assert "[0]" in text and "[1]" in text, text
    assert "Accept all" in text and "janedoe" in text, text


def test_off_limits_elements_are_marked_rather_than_hidden():
    """Hiding a control makes the model hunt for it; naming it settles it."""
    text = render_observation(_observation(_named("Log in", "janedoe")), off_limits=[0])

    assert "OFF LIMITS" in text, "the sign-in control was not marked"
    assert "[0]" in text, "the sign-in control was hidden instead of marked"


def test_a_page_with_no_interactables_says_so_instead_of_rendering_nothing():
    text = render_observation(_observation([]))

    assert "(none visible)" in text, text


def test_the_previous_step_including_a_refusal_is_fed_back():
    observation = Observation(
        task="t",
        url="u",
        title="",
        text="",
        elements=(),
        step=3,
        max_steps=12,
        last='click [0] "Log in" -> refused (login_submit)',
    )

    assert "LAST: click [0]" in render_observation(observation)
    assert "refused" in render_observation(observation)


# -- describe_action ---------------------------------------------------------


def test_a_pixel_click_reads_differently_from_an_indexed_click():
    """A user must be able to see which clicks were grounded in the DOM."""
    elements = _named("Show more")

    indexed = describe_action(BrowseAction(kind=ActionKind.CLICK, index=0), elements)
    pixel = describe_action(BrowseAction(kind=ActionKind.CLICK_AT, x=430, y=210), elements)

    assert "Show more" in indexed, f"got {indexed!r}"
    assert "430" in pixel and "no element" in pixel, f"got {pixel!r}"


def test_an_unknown_index_still_describes_rather_than_raising():
    line = describe_action(BrowseAction(kind=ActionKind.CLICK, index=99), _named("a"))

    assert "[99]" in line, f"got {line!r}"


# -- rules -------------------------------------------------------------------


@pytest.mark.parametrize("label", ["Accept all", "Tümünü kabul et", "I agree", "Got it"])
def test_a_consent_banner_is_handled_by_rule_without_a_model_call(label):
    action = rules.suggest(_observation(_named(label, "janedoe")))

    assert action is not None, f"{label!r} was not recognised as consent"
    assert action.by == "rule", f"got by={action.by!r}"
    assert action.index == 0, f"got index={action.index}"


@pytest.mark.parametrize("label", ["Not now", "Şimdi değil", "No thanks"])
def test_a_dismissible_interstitial_is_declined_by_rule(label):
    action = rules.suggest(_observation(_named(label)))

    assert action is not None, f"{label!r} was not recognised as dismissible"
    assert action.kind is ActionKind.CLICK, f"got {action.kind!r}"


def test_consent_is_handled_before_an_expander_because_it_covers_the_page():
    action = rules.suggest(_observation(_named("Show more", "Accept all")))

    assert action is not None and action.index == 1, f"got {action!r}"


def test_an_expander_is_clicked_when_nothing_overlays_the_page():
    action = rules.suggest(_observation(_named("janedoe", "Show more")))

    assert action is not None and action.index == 1, f"got {action!r}"


def test_a_sign_in_control_is_never_suggested_by_a_rule():
    """A rule that proposed one would be refused, but it would still cost a step."""
    elements = (
        Element(index=0, tag="button", role="button", name="Continue", in_password_form=True),
        Element(index=1, tag="input", role="textbox", name="Accept", input_type="password"),
    )

    assert rules.suggest(_observation(elements, text="age 18+")) is None, "a rule proposed a login control"


def test_an_age_gate_is_only_clicked_when_the_page_is_about_age():
    """ "Continue" is far too common a word to click on its own account."""
    elements = _named("Continue")

    assert rules.suggest(_observation(elements, text="latest posts")) is None, (
        "'Continue' was clicked on a page with nothing to do with age"
    )
    assert rules.suggest(_observation(elements, text="Please confirm your age")) is not None, (
        "an age gate went unrecognised"
    )


def test_an_ordinary_page_falls_through_to_the_model():
    action = rules.suggest(_observation(_named("janedoe", "Followers", "Posts")))

    assert action is None, f"a rule fired where the model should decide: {action!r}"


def test_a_disabled_control_is_never_suggested():
    elements = (Element(index=0, tag="button", role="button", name="Accept all", disabled=True),)

    assert rules.suggest(_observation(elements)) is None, "a disabled banner button was suggested"


def test_the_scripts_own_ordinal_wins_over_list_position():
    """`[7]` must point at the node the overlay labelled 7, not at a re-count."""
    elements = number_elements([{"tag": "a", "name": "first", "idx": 5}])

    assert elements[0].index == 5, f"got {elements[0].index}"


def test_a_nonsense_ordinal_falls_back_to_position():
    elements = number_elements([{"tag": "a", "name": "first", "idx": "seven"}])

    assert elements[0].index == 0, f"got {elements[0].index}"
