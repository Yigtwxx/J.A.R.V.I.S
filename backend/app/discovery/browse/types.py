"""Value types for the interactive browse tier.

Dependency-free on purpose, exactly like ``discovery/types.py``: every other
module in this package imports from here, and the guard and the observation
renderer must stay pure enough to test without a browser or a model.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum


class ActionKind(StrEnum):
    """Everything the agent is allowed to want.

    Deliberately small. There is no ``evaluate``, no ``press``, no ``upload``:
    an action the model cannot name is an action it cannot take, and that is a
    cheaper defence than validating arbitrary input.
    """

    CLICK = "click"
    """Click the element at ``index``. Primary, because the coordinates come
    from the DOM and therefore cannot be hallucinated."""

    CLICK_AT = "click_at"
    """Click raw viewport coordinates. The fallback for targets with no DOM node
    — a canvas, a map, a region of an image. Grounded only by the model, so it
    is recorded distinctly and can be switched off."""

    TYPE = "type"
    SCROLL = "scroll"
    NAVIGATE = "navigate"
    WAIT = "wait"

    EXTRACT = "extract"
    """"The content is on screen now." It does not carry text: the harvest reads
    the DOM with the pipeline's existing extractors. This is the line that keeps
    the model from writing evidence."""

    DONE = "done"
    GIVE_UP = "give_up"


class BrowseOutcome(StrEnum):
    """How a browse task ended. Every one of these is a statement; none is silence."""

    EXTRACTED = "extracted"
    """Harvest produced something. The only outcome that may add a claim."""

    REACHED_EMPTY = "reached_empty"
    """The page loaded, no wall, and the DOM still held nothing about the target.
    Not an absence — the platform verdict is left exactly as it was."""

    NOT_FOUND = "not_found"
    """The main-frame navigation returned 404/410. The *only* route to this
    outcome: never an empty DOM, never an SPA route change, never the model."""

    LOGIN_WALL = "login_wall"
    CHALLENGE = "challenge"

    REFUSED = "refused"
    """Our own guard stopped the agent too many times in a row."""

    STALLED = "stalled"
    """The agent repeated itself. A loop that cannot notice itself burns the
    whole budget looking busy."""

    STEP_BUDGET = "step_budget"
    TIME_BUDGET = "time_budget"
    MODEL_UNAVAILABLE = "model_unavailable"
    ERROR = "error"
    UNAVAILABLE = "unavailable"
    """No browser in this environment (Docker's non-stealth stage, a failed
    launch, or the feature switched off)."""

    STOPPED = "stopped"
    """The user pressed Stop in the panel."""


#: Outcomes that may change what we report about a platform. Everything else
#: leaves the prior verdict untouched — browse may improve a status, never
#: degrade one, because it runs *after* the cheap tiers have already spoken.
CONCLUSIVE_OUTCOMES: frozenset[BrowseOutcome] = frozenset({BrowseOutcome.EXTRACTED, BrowseOutcome.NOT_FOUND})


class RefusalReason(StrEnum):
    """Why the guard said no. Shown to the user verbatim, so each one is a fact."""

    CREDENTIAL_FIELD = "credential_field"
    LOGIN_SUBMIT = "login_submit"
    UNSAFE_URL = "unsafe_url"
    UNKNOWN_INDEX = "unknown_index"
    DISABLED_ELEMENT = "disabled_element"
    PIXEL_DISABLED = "pixel_disabled"
    OFF_VIEWPORT = "off_viewport"
    TEXT_TOO_LONG = "text_too_long"
    MALFORMED = "malformed"


@dataclass(frozen=True, slots=True)
class Element:
    """One interactable the page offered, as the injected script saw it."""

    index: int
    tag: str
    role: str = ""
    name: str = ""
    href: str = ""
    input_type: str = ""
    autocomplete: str = ""
    disabled: bool = False
    in_password_form: bool = False
    """True when this node shares a ``<form>`` with a password field. The signal
    that turns an innocuous-looking "Continue" into a credential submit."""

    box: tuple[int, int, int, int] = (0, 0, 0, 0)
    """x, y, width, height in viewport coordinates."""


@dataclass(frozen=True, slots=True)
class BrowseAction:
    """One decision, from the model or from a deterministic rule."""

    kind: ActionKind
    index: int | None = None
    x: int | None = None
    y: int | None = None
    text: str = ""
    url: str = ""
    direction: str = "down"
    thought: str = ""
    by: str = "model"
    """``"rule"`` or ``"model"``. Surfaced in the panel so a user can see which
    steps cost an inference and which were simply the obvious thing."""


@dataclass(frozen=True, slots=True)
class Refusal:
    """A guard verdict. Carries its own sentence — the UI does not compose one."""

    reason: RefusalReason
    detail: str = ""


@dataclass(frozen=True, slots=True)
class Observation:
    """What the agent is told before it decides."""

    task: str
    url: str
    title: str
    text: str
    elements: tuple[Element, ...]
    step: int
    max_steps: int
    scroll_y: int = 0
    scroll_height: int = 0
    viewport_height: int = 0
    last: str = ""
    """One line describing the previous action and how it went, including a
    refusal. Feeding a refusal back is what stops the agent retrying it."""


@dataclass(frozen=True, slots=True)
class BrowseTask:
    """One target, one page, one budget."""

    task_id: str
    url: str
    platform: str
    username: str
    reason: str
    """Why this target earned a browser, in words the panel can show."""


@dataclass(slots=True)
class BrowseStep:
    """A record of one step, kept for the report and the panel."""

    step: int
    action: BrowseAction
    status: str
    """``ok`` | ``refused`` | ``failed``"""

    description: str
    refusal: Refusal | None = None
    frame_name: str = ""
    page_url: str = ""


@dataclass(slots=True)
class BrowseReport:
    """Everything a finished task has to say for itself."""

    task: BrowseTask
    outcome: BrowseOutcome
    steps: list[BrowseStep] = field(default_factory=list)
    duration_ms: int = 0
    final_url: str = ""
    http_status: int | None = None
    html: str = ""
    detail: str = ""
    model_calls: int = 0
    dropped_ungrounded: int = 0
    """Values the harvest refused because the DOM never contained them. Counted
    and reported rather than dropped quietly — a silent filter is unfalsifiable."""

    @property
    def steps_used(self) -> int:
        return len(self.steps)
