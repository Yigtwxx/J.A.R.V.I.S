"""The browse loop's stopping conditions.

Nothing here launches a browser or reaches a model: the page is a fake and the
policy is a script. That is the point of both being protocols — the conditions
that stop a runaway agent are exactly the ones you cannot prove against a live
browser, because a live browser is what they exist to bound.
"""

import asyncio

from app.discovery.browse.agent import REFUSAL_LIMIT, REPEAT_LIMIT, BrowseAgent, BrowseBudget
from app.discovery.browse.types import ActionKind, BrowseAction, BrowseOutcome, BrowseTask

TASK = BrowseTask(
    task_id="t1",
    url="https://www.instagram.com/janedoe/",
    platform="instagram",
    username="janedoe",
    reason="stealth tier was refused",
)

PROFILE_HTML = "<html><body><h1>Jane Doe</h1><p>photographer, Istanbul</p></body></html>"


def run(coro):
    return asyncio.run(coro)


class FakePage:
    """A page that serves fixed state and records what was done to it."""

    def __init__(
        self,
        *,
        status: int | None = 200,
        url: str = "https://www.instagram.com/janedoe/",
        redirect_to: str = "",
        html: str = PROFILE_HTML,
        elements: list[dict] | None = None,
        text: str = "Jane Doe photographer",
    ) -> None:
        self._status = status
        self.url = url
        self._redirect_to = redirect_to
        """Where a navigation actually lands. A login wall is a redirect, and a
        fake that ignored that could never reproduce one."""
        self._html = html
        self._elements = (
            elements
            if elements is not None
            else [
                {"idx": 0, "tag": "A", "name": "janedoe", "href": "/janedoe/"},
                {"idx": 1, "tag": "BUTTON", "name": "Followers"},
            ]
        )
        self._text = text
        self.actions: list[tuple] = []
        self.closed = False
        self.shots = 0

    @property
    def last_status(self):
        return self._status

    async def goto(self, url: str):
        self.actions.append(("goto", url))
        self.url = self._redirect_to or url
        return self._status

    async def context(self):
        return {
            "title": "Jane Doe (@janedoe)",
            "url": self.url,
            "scrollY": 0,
            "scrollHeight": 2000,
            "innerHeight": 800,
            "text": self._text,
        }

    async def collect(self):
        return list(self._elements)

    async def screenshot(self) -> bytes:
        self.shots += 1
        return b"\xff\xd8\xff" + b"0" * 32

    async def content(self) -> str:
        return self._html

    async def click_index(self, index: int) -> None:
        self.actions.append(("click", index))

    async def click_at(self, x: int, y: int) -> None:
        self.actions.append(("click_at", x, y))

    async def type_into(self, index: int, text: str) -> None:
        self.actions.append(("type", index, text))

    async def scroll(self, direction: str) -> None:
        self.actions.append(("scroll", direction))

    async def settle(self, ms: int = 800) -> None:
        return None

    async def close(self) -> None:
        self.closed = True


class ScriptedPolicy:
    """Returns a fixed sequence of actions, then repeats the last one."""

    def __init__(self, actions, *, raises: Exception | None = None) -> None:
        self._actions = list(actions)
        self._raises = raises
        self.calls = 0
        self.images: list[bytes] = []

    async def decide(self, observation, image):
        self.calls += 1
        self.images.append(image)
        if self._raises is not None:
            raise self._raises
        if not self._actions:
            return None
        if len(self._actions) == 1:
            return self._actions[0]
        return self._actions.pop(0)


def _agent(page, policy, *, budget=None, events=None, should_stop=None, use_rules=False):
    async def emit(event_type, payload):
        if events is not None:
            events.append((event_type, payload))

    return BrowseAgent(
        policy=policy,
        open_page=lambda: _resolved(page),
        budget=budget or BrowseBudget(max_steps=6, max_seconds=30.0),
        emit=emit,
        should_stop=should_stop,
        use_rules=use_rules,
    )


async def _resolved(value):
    return value


# -- invariant 1: an absence needs a status code -------------------------------


def test_a_404_navigation_is_the_only_route_to_not_found():
    page = FakePage(status=404)
    report = run(_agent(page, ScriptedPolicy([])).run(TASK))

    assert report.outcome is BrowseOutcome.NOT_FOUND, f"got {report.outcome}"
    assert report.steps_used == 0, "a 404 should settle the question before any step"


def test_an_empty_dom_is_never_reported_as_not_found():
    """The failure this whole tier exists to avoid: silence read as absence."""
    page = FakePage(status=200, html="<html><body></body></html>", elements=[], text="")
    policy = ScriptedPolicy([BrowseAction(kind=ActionKind.GIVE_UP, thought="nothing here")])

    report = run(_agent(page, policy).run(TASK))

    assert report.outcome is BrowseOutcome.REACHED_EMPTY, f"got {report.outcome}"
    assert report.outcome is not BrowseOutcome.NOT_FOUND, "an empty page was called an absence"


def test_a_login_wall_terminates_without_ever_asking_the_model():
    page = FakePage(redirect_to="https://www.instagram.com/accounts/login/?next=/janedoe/")
    policy = ScriptedPolicy([BrowseAction(kind=ActionKind.CLICK, index=0)])

    report = run(_agent(page, policy).run(TASK))

    assert report.outcome is BrowseOutcome.LOGIN_WALL, f"got {report.outcome}"
    assert policy.calls == 0, f"the model was asked {policy.calls} times about a settled wall"


def test_a_challenge_page_is_reported_as_a_challenge_not_an_absence():
    page = FakePage(html="<html><body>Checking your browser before accessing</body></html>")
    report = run(_agent(page, ScriptedPolicy([])).run(TASK))

    assert report.outcome in (BrowseOutcome.CHALLENGE, BrowseOutcome.LOGIN_WALL), f"got {report.outcome}"
    assert report.outcome is not BrowseOutcome.NOT_FOUND


# -- budgets and loops ---------------------------------------------------------


def test_the_loop_stops_at_the_step_budget():
    page = FakePage()
    # Alternating so the repeat detector cannot fire first.
    policy = ScriptedPolicy(
        [
            BrowseAction(kind=ActionKind.SCROLL, direction="down"),
            BrowseAction(kind=ActionKind.SCROLL, direction="up"),
        ]
        * 6
    )
    report = run(_agent(page, policy, budget=BrowseBudget(max_steps=4)).run(TASK))

    assert report.outcome is BrowseOutcome.STEP_BUDGET, f"got {report.outcome}"
    assert report.steps_used == 4, f"expected exactly the budget, got {report.steps_used}"


def test_the_same_action_three_times_running_is_a_stall():
    page = FakePage()
    policy = ScriptedPolicy([BrowseAction(kind=ActionKind.SCROLL, direction="down")])

    report = run(_agent(page, policy, budget=BrowseBudget(max_steps=20)).run(TASK))

    assert report.outcome is BrowseOutcome.STALLED, f"got {report.outcome}"
    assert report.steps_used == REPEAT_LIMIT, f"got {report.steps_used}"


def test_the_time_budget_ends_the_task_before_the_step_budget_does():
    page = FakePage()
    policy = ScriptedPolicy([BrowseAction(kind=ActionKind.SCROLL, direction="down")])
    budget = BrowseBudget(max_steps=50, max_seconds=0.0)

    report = run(_agent(page, policy, budget=budget).run(TASK))

    assert report.outcome is BrowseOutcome.TIME_BUDGET, f"got {report.outcome}"
    assert policy.calls == 0, "the clock should be checked before the model is asked"


def test_the_stop_signal_ends_the_task_and_says_so():
    page = FakePage()
    policy = ScriptedPolicy([BrowseAction(kind=ActionKind.SCROLL)])

    report = run(_agent(page, policy, should_stop=lambda: True).run(TASK))

    assert report.outcome is BrowseOutcome.STOPPED, f"got {report.outcome}"
    assert "console" in report.detail, f"got {report.detail!r}"


# -- refusals ------------------------------------------------------------------


def test_a_refused_action_costs_a_step_and_is_fed_back():
    page = FakePage(
        elements=[
            {"idx": 0, "tag": "BUTTON", "name": "Log in"},
            {"idx": 1, "tag": "A", "name": "janedoe"},
        ]
    )
    policy = ScriptedPolicy([BrowseAction(kind=ActionKind.CLICK, index=0)])
    events: list = []

    report = run(_agent(page, policy, budget=BrowseBudget(max_steps=10), events=events).run(TASK))

    assert report.outcome is BrowseOutcome.REFUSED, f"got {report.outcome}"
    assert report.steps_used == REFUSAL_LIMIT, f"got {report.steps_used}"
    assert ("click", 0) not in page.actions, "a refused click reached the page"
    refused = [p for _, p in events if p.get("status") == "refused"]
    assert refused, "the refusal was never published"
    assert refused[0]["refusal"] == "login_submit", f"got {refused[0]['refusal']!r}"


def test_a_hallucinated_index_is_refused_rather_than_clicked():
    page = FakePage()
    policy = ScriptedPolicy([BrowseAction(kind=ActionKind.CLICK, index=97)])

    report = run(_agent(page, policy).run(TASK))

    assert report.outcome is BrowseOutcome.REFUSED, f"got {report.outcome}"
    assert not [a for a in page.actions if a[0] == "click"], "a made-up index reached the page"


# -- the model's own answers ---------------------------------------------------


def test_extract_then_done_is_the_only_path_to_extracted():
    page = FakePage()
    policy = ScriptedPolicy(
        [
            BrowseAction(kind=ActionKind.EXTRACT),
            BrowseAction(kind=ActionKind.DONE, thought="profile read"),
        ]
    )

    report = run(_agent(page, policy).run(TASK))

    assert report.outcome is BrowseOutcome.EXTRACTED, f"got {report.outcome}"
    assert report.html == PROFILE_HTML, "the harvest needs the HTML captured at extract time"


def test_done_without_an_extract_does_not_claim_a_reading():
    page = FakePage()
    policy = ScriptedPolicy([BrowseAction(kind=ActionKind.DONE, thought="looks fine")])

    report = run(_agent(page, policy).run(TASK))

    assert report.outcome is BrowseOutcome.REACHED_EMPTY, f"got {report.outcome}"


def test_three_unusable_replies_in_a_row_end_the_task():
    page = FakePage()
    report = run(_agent(page, ScriptedPolicy([])).run(TASK))

    assert report.outcome is BrowseOutcome.MODEL_UNAVAILABLE, f"got {report.outcome}"


def test_a_policy_that_raises_does_not_leak_the_page():
    page = FakePage()
    policy = ScriptedPolicy([], raises=RuntimeError("model exploded"))

    report = run(_agent(page, policy).run(TASK))

    assert report.outcome is BrowseOutcome.ERROR, f"got {report.outcome}"
    assert page.closed, "the page was left open after a crash"


def test_the_page_is_closed_on_every_path():
    page = FakePage()
    policy = ScriptedPolicy([BrowseAction(kind=ActionKind.DONE)])

    run(_agent(page, policy).run(TASK))

    assert page.closed, "the page outlived the task"


def test_no_browser_at_all_is_reported_as_unavailable_not_as_an_error():
    async def refuse():
        raise RuntimeError("stealth tier unavailable")

    agent = BrowseAgent(policy=ScriptedPolicy([]), open_page=refuse)
    report = run(agent.run(TASK))

    assert report.outcome is BrowseOutcome.UNAVAILABLE, f"got {report.outcome}"
    assert "stealth tier unavailable" in report.detail, f"got {report.detail!r}"


# -- rules save inferences -----------------------------------------------------


def test_a_consent_banner_is_cleared_by_rule_without_a_model_call():
    """Every rule that fires is a 3.6 s inference and 6 GB of VRAM not spent."""
    page = FakePage(
        elements=[
            {"idx": 0, "tag": "BUTTON", "name": "Accept all cookies"},
            {"idx": 1, "tag": "A", "name": "janedoe"},
        ]
    )
    policy = ScriptedPolicy([BrowseAction(kind=ActionKind.DONE)])
    agent = _agent(page, policy, budget=BrowseBudget(max_steps=1), use_rules=True)

    run(agent.run(TASK))

    assert policy.calls == 0, f"the model was asked {policy.calls} times for a cookie banner"
    assert ("click", 0) in page.actions, f"the banner was not dismissed; actions={page.actions}"


def test_a_rule_driven_step_is_labelled_rule_in_the_event_stream():
    page = FakePage(elements=[{"idx": 0, "tag": "BUTTON", "name": "Accept all"}])
    events: list = []
    agent = _agent(
        page,
        ScriptedPolicy([BrowseAction(kind=ActionKind.DONE)]),
        budget=BrowseBudget(max_steps=1),
        events=events,
        use_rules=True,
    )

    run(agent.run(TASK))

    steps = [p for name, p in events if name == "browse_step"]
    assert steps, "no step was published"
    assert steps[0]["by"] == "rule", f"got by={steps[0]['by']!r}"


# -- telemetry -----------------------------------------------------------------


def test_every_step_is_published_with_its_description():
    page = FakePage()
    policy = ScriptedPolicy(
        [
            BrowseAction(kind=ActionKind.EXTRACT),
            BrowseAction(kind=ActionKind.DONE, thought="done"),
        ]
    )
    events: list = []

    run(_agent(page, policy, events=events).run(TASK))

    steps = [p for name, p in events if name == "browse_step"]
    assert len(steps) == 2, f"expected two published steps, got {len(steps)}"
    assert steps[0]["description"] == "Read the page", f"got {steps[0]['description']!r}"


def test_a_pixel_click_is_recorded_distinctly_from_an_indexed_one():
    """The user must be able to see which clicks the DOM grounded."""
    page = FakePage()
    policy = ScriptedPolicy(
        [
            BrowseAction(kind=ActionKind.CLICK_AT, x=430, y=210),
            BrowseAction(kind=ActionKind.DONE),
        ]
    )
    events: list = []

    run(_agent(page, policy, events=events).run(TASK))

    described = [p["description"] for _, p in events]
    assert any("430" in text and "no element" in text for text in described), described
    assert ("click_at", 430, 210) in page.actions, f"actions={page.actions}"


def test_the_model_is_never_handed_the_raw_screenshot():
    """A device-scale-2 frame is 178 KB base64 and ollama answers 400 to it.

    Measured 2026-08-29: three such refusals in a row retired the model, so the
    panel opened, showed a blank frame and never took a step. The shrink has to
    happen before the policy sees the bytes, not on the way to disk.
    """
    page = FakePage()
    policy = ScriptedPolicy([BrowseAction(kind=ActionKind.DONE)])
    agent = BrowseAgent(
        policy=policy,
        open_page=lambda: _resolved(page),
        budget=BrowseBudget(max_steps=1),
        shrink=lambda raw: b"SHRUNK",
        use_rules=False,
    )

    run(agent.run(TASK))

    assert policy.images == [b"SHRUNK"], f"the policy was handed {policy.images!r}"


def test_a_shrink_that_fails_still_lets_the_step_happen():
    """A worse frame is better than a stalled agent."""
    page = FakePage()
    policy = ScriptedPolicy([BrowseAction(kind=ActionKind.DONE)])

    def explode(_raw: bytes) -> bytes:
        raise RuntimeError("pillow is unhappy")

    agent = BrowseAgent(
        policy=policy,
        open_page=lambda: _resolved(page),
        budget=BrowseBudget(max_steps=1),
        shrink=explode,
        use_rules=False,
    )

    report = run(agent.run(TASK))

    assert policy.calls == 1, "the step was skipped because the shrink failed"
    assert report.outcome is not BrowseOutcome.ERROR, f"got {report.outcome}"
