"""A tool that changes the user's console must stop and ask first.

The load-bearing assertion in this file is the negative one: when the model asks
for a destructive tool, the handler must NOT have run by the time the loop
suspends. Emitting an approval card while the action has already happened is
worse than having no gate at all, because the card says the opposite of the truth.
"""

import asyncio

import pytest

from app.agents.agent_loop import AgentLoop
from app.agents.pending_actions import DENIED_RESULT, AgentActionQueue
from app.agents.tool_registry import Tool, ToolRegistry


def run(coro):
    return asyncio.run(coro)


class FakeOllama:
    """Replays a scripted sequence of `chat` responses, one per iteration."""

    def __init__(self, responses):
        self._responses = list(responses)
        self.calls: list[dict] = []

    async def chat(self, **kwargs):
        self.calls.append(kwargs)
        if kwargs.get("stream"):
            return self._token_stream("Done.")
        if not self._responses:
            return {"message": {"content": "Nothing left to do."}}
        return self._responses.pop(0)

    @staticmethod
    async def _token_stream(text):
        for token in text.split(" "):
            yield {"message": {"content": token + " "}}


def tool_call(name, arguments):
    return {"message": {"tool_calls": [{"function": {"name": name, "arguments": arguments}}]}}


@pytest.fixture
def performed():
    return []


@pytest.fixture
def registry(performed):
    async def dangerous(action: str, target: str = "") -> str:
        performed.append((action, target))
        return f"{action} performed on {target}"

    async def harmless(action: str) -> str:
        performed.append((action, None))
        return "listed"

    reg = ToolRegistry()
    reg.register(
        Tool(
            name="dangerous_control",
            description="test",
            parameters={"type": "object", "properties": {}},
            handler=dangerous,
            requires_confirmation=lambda args: args.get("action") == "destroy",
            confirm_summary=lambda args: f"Destroy {args.get('target')}",
        )
    )
    reg.register(
        Tool(
            name="harmless_control",
            description="test",
            parameters={"type": "object", "properties": {}},
            handler=harmless,
        )
    )
    return reg


@pytest.fixture
def queue():
    return AgentActionQueue()


def make_loop(registry, queue, responses):
    loop = AgentLoop(registry=registry, action_queue=queue, max_iterations=4)
    loop.client = FakeOllama(responses)
    return loop


async def collect(events):
    return [event async for event in events]


def test_a_destructive_call_suspends_the_turn_without_running(registry, queue, performed):
    loop = make_loop(registry, queue, [tool_call("dangerous_control", {"action": "destroy", "target": "watch:ada"})])

    events = run(collect(loop.run_events("delete the watch on ada")))

    assert [e["type"] for e in events] == ["confirm_required"]
    assert performed == [], "the handler must not have run before the user answered"
    assert events[0]["action"]["description"] == "Destroy watch:ada"
    assert len(queue.list_pending()) == 1


def test_a_read_only_call_runs_without_asking(registry, queue, performed):
    loop = make_loop(registry, queue, [tool_call("harmless_control", {"action": "list"})])

    events = run(collect(loop.run_events("what is running?")))
    kinds = [e["type"] for e in events]

    assert "confirm_required" not in kinds
    assert performed == [("list", None)], "a read must not be gated behind an approval"
    assert "tool_result" in kinds


def test_approving_runs_the_action_and_reports_it(registry, queue, performed):
    loop = make_loop(registry, queue, [tool_call("dangerous_control", {"action": "destroy", "target": "watch:ada"})])
    action_id = run(collect(loop.run_events("go")))[0]["action"]["action_id"]

    result = run(queue.resolve(action_id, approved=True, registry=registry))

    assert performed == [("destroy", "watch:ada")]
    assert "performed on watch:ada" in result
    assert queue.list_pending() == []


def test_denying_runs_nothing_and_says_so(registry, queue, performed):
    loop = make_loop(registry, queue, [tool_call("dangerous_control", {"action": "destroy", "target": "watch:ada"})])
    action_id = run(collect(loop.run_events("go")))[0]["action"]["action_id"]

    result = run(queue.resolve(action_id, approved=False, registry=registry))

    assert performed == []
    assert result == DENIED_RESULT


def test_an_action_cannot_be_answered_twice(registry, queue):
    loop = make_loop(registry, queue, [tool_call("dangerous_control", {"action": "destroy", "target": "x"})])
    action_id = run(collect(loop.run_events("go")))[0]["action"]["action_id"]
    run(queue.resolve(action_id, approved=False, registry=registry))

    with pytest.raises(KeyError):
        run(queue.resolve(action_id, approved=True, registry=registry))


def test_an_unknown_action_is_not_silently_ignored(registry, queue):
    with pytest.raises(KeyError):
        run(queue.resolve("no-such-action", approved=True, registry=registry))


def test_a_safe_call_in_the_same_round_still_runs_before_the_gate(registry, queue, performed):
    """Both calls arrive together; the read should not be held hostage by the gate."""
    loop = make_loop(
        registry,
        queue,
        [
            {
                "message": {
                    "tool_calls": [
                        {"function": {"name": "harmless_control", "arguments": {"action": "list"}}},
                        {
                            "function": {
                                "name": "dangerous_control",
                                "arguments": {"action": "destroy", "target": "t"},
                            }
                        },
                    ]
                }
            }
        ],
    )

    kinds = [e["type"] for e in run(collect(loop.run_events("list then delete")))]

    assert kinds == ["tool_call", "tool_result", "confirm_required"]
    assert performed == [("list", None)]


def test_resuming_carries_the_outcome_back_into_the_conversation(registry, queue):
    loop = make_loop(registry, queue, [{"message": {"content": ""}}])

    events = run(collect(loop.resume_events("dangerous_control", "destroy performed on watch:ada")))

    assert events[-1]["type"] == "done"
    sent = loop.client.calls[0]["messages"]
    assert sent[-2]["role"] == "tool"
    assert "dangerous_control -> destroy performed on watch:ada" in sent[-2]["content"]


def test_run_reports_a_suspended_turn_as_pending_not_as_an_answer(registry, queue):
    loop = make_loop(registry, queue, [tool_call("dangerous_control", {"action": "destroy", "target": "x"})])

    outcome = run(loop.run("delete x"))

    assert outcome["status"] == "pending_approval"
    assert "response" not in outcome, "a turn that stopped to ask has no answer yet"
