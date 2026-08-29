"""Turning a page into something a model can answer about. Pure, no I/O.

The numbered element list is the *primary* observation and the screenshot is
corroborating context, not the other way round. That ordering is the design's
main defence against a hallucinated click: an index the model returns either
names a node the DOM actually offered — with coordinates the DOM supplied — or
it is refused by the guard. Pixels are the fallback precisely because nothing
checks them.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence

from app.discovery.browse.types import ActionKind, BrowseAction, Element, Observation

MAX_ELEMENTS = 40
"""More than this and the list stops being readable — for the model and for the
person watching the panel. The script already sorts by reading order, so the
cut keeps the top of the page rather than a random slice."""

MAX_NAME_CHARS = 60
MAX_TEXT_CHARS = 1200


def _clean(value: object, limit: int = MAX_NAME_CHARS) -> str:
    """Collapse whitespace and clip. Element names come from the page, so they
    can be a whole paragraph of alt text."""
    text = " ".join(str(value or "").split())
    return text[:limit].strip()


def number_elements(raw: Iterable[dict]) -> tuple[Element, ...]:
    """Normalise the injected script's output into indexed elements.

    Indices are assigned here rather than in JavaScript so that the numbering,
    the overlay labels and the guard all read from one source. A page that
    mutates between the screenshot and the decision would otherwise renumber
    underneath us.
    """
    elements: list[Element] = []
    for position, item in enumerate(raw):
        if not isinstance(item, dict):
            continue
        box = item.get("box") or [0, 0, 0, 0]
        try:
            coords = tuple(int(round(float(value))) for value in box[:4])
        except (TypeError, ValueError):
            coords = (0, 0, 0, 0)
        if len(coords) != 4:
            coords = (0, 0, 0, 0)

        # The injected script stamps each node with its own ordinal and returns
        # the list in that order, so the two agree. Preferring the script's
        # number keeps `[7]` pointing at the node the overlay labelled 7 even if
        # this loop ever stops being a straight enumerate.
        raw_idx = item.get("idx")
        index = raw_idx if isinstance(raw_idx, int) and raw_idx >= 0 else position

        elements.append(
            Element(
                index=index,
                tag=_clean(item.get("tag"), 12).lower(),
                role=_clean(item.get("role"), 20).lower(),
                name=_clean(item.get("name")),
                href=_clean(item.get("href"), 200),
                input_type=_clean(item.get("type"), 20).lower(),
                autocomplete=_clean(item.get("autocomplete"), 30).lower(),
                disabled=bool(item.get("disabled")),
                in_password_form=bool(item.get("in_password_form")),
                box=coords,  # type: ignore[arg-type]
            )
        )
        if len(elements) >= MAX_ELEMENTS:
            break
    return tuple(elements)


def _element_line(element: Element, *, refused: bool) -> str:
    label = element.role or element.tag
    parts = [f"[{element.index}]", f"{label:<8}", f'"{element.name}"' if element.name else '""']
    if element.input_type and element.input_type != "text":
        parts.append(f"type={element.input_type}")
    if element.href:
        parts.append(f"href={element.href}")
    if element.disabled:
        parts.append("(disabled)")
    if refused:
        # Listed and marked rather than hidden: hiding a control makes the model
        # hunt for it, while naming it as off-limits settles the question once.
        parts.append("— OFF LIMITS (sign-in)")
    return " ".join(parts)


def render_observation(
    observation: Observation,
    *,
    off_limits: Sequence[int] = (),
) -> str:
    """The text half of what the model sees, paired with one screenshot."""
    blocked = set(off_limits)
    lines = [
        f"TASK: {observation.task}",
        f"URL: {observation.url}",
        f"TITLE: {observation.title}",
        f"SCROLL: {observation.scroll_y} of {observation.scroll_height} px (viewport {observation.viewport_height})",
        f"STEP: {observation.step} of {observation.max_steps}",
    ]
    if observation.last:
        lines.append(f"LAST: {observation.last}")

    text = _clean(observation.text, MAX_TEXT_CHARS)
    lines += ["", f"VISIBLE TEXT ({len(text)} chars):", text or "(none)"]

    lines += ["", "ELEMENTS:"]
    if observation.elements:
        lines += [_element_line(element, refused=element.index in blocked) for element in observation.elements]
    else:
        lines.append("(none visible)")
    return "\n".join(lines)


def describe_action(action: BrowseAction, elements: Sequence[Element] = ()) -> str:
    """One human line for the panel and the step log.

    Names the target rather than the index alone, so a step reads as something
    a person did — and so a ``click_at`` is visibly different from a ``click``.
    """
    lookup = {element.index: element for element in elements}
    # `action.index or -1` would be a bug here: index 0 is falsy, so the very
    # first element on the page would never resolve to a name.
    target = lookup.get(action.index) if action.index is not None else None

    if action.kind is ActionKind.CLICK:
        label = f'"{target.name}"' if target and target.name else "an unnamed control"
        return f"Clicked [{action.index}] {label}"
    if action.kind is ActionKind.CLICK_AT:
        return f"Clicked at ({action.x}, {action.y}) — no element there to name"
    if action.kind is ActionKind.TYPE:
        label = f'"{target.name}"' if target and target.name else f"[{action.index}]"
        return f"Typed {action.text!r} into {label}"
    if action.kind is ActionKind.SCROLL:
        return f"Scrolled {action.direction}"
    if action.kind is ActionKind.NAVIGATE:
        return f"Opened {action.url}"
    if action.kind is ActionKind.WAIT:
        return "Waited for the page to settle"
    if action.kind is ActionKind.EXTRACT:
        return "Read the page"
    if action.kind is ActionKind.DONE:
        return f"Finished — {action.thought or 'done'}"
    return f"Gave up — {action.thought or 'no way through'}"
