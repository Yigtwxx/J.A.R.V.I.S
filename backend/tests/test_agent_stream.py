"""The agent endpoint streams events, not prose.

Two properties are pinned here. The wire format has to be the SSE framing the
console's own `parseSseFrames` already reads — a frame per event, the type on
both the `event:` line and inside the body. And the stream has to be wrapped in
the keep-alive: a tool-calling round produces no tokens for as long as the tools
take, and Node's undici cuts a body that stays silent for 300 s. That is the
failure already observed live on the two search streams.
"""

import inspect
import json

import pytest

from app.agents.pending_actions import agent_action_queue
from app.agents.tool_registry import Tool, ToolRegistry
from app.dependencies import get_agent_loop
from app.main import app
from app.routes import agent as agent_route


def frames(body: str) -> list[dict]:
    """Parse an SSE body the way the frontend does, dropping keep-alive comments."""
    parsed = []
    for block in body.replace("\r\n", "\n").split("\n\n"):
        data = [ln[len("data:") :].strip() for ln in block.split("\n") if ln.startswith("data:")]
        if data:
            parsed.append(json.loads("\n".join(data)))
    return parsed


class StubAgent:
    """Stands in for AgentLoop: the route's job is framing, not inference."""

    def __init__(self, events, registry=None):
        self._events = events
        self.registry = registry or ToolRegistry()
        self.resumed: list[tuple[str, str]] = []

    async def _emit(self, events):
        for event in events:
            yield event

    def run_events(self, user_message, conversation_history=None):
        return self._emit(self._events)

    def resume_events(self, tool_name, tool_result, conversation_history=None):
        self.resumed.append((tool_name, tool_result))
        return self._emit([{"type": "done", "content": "Stopped it."}])

    async def run(self, user_message, conversation_history=None):
        return {"status": "done", "response": "plain answer"}


@pytest.fixture
def stub_agent():
    agents: list[StubAgent] = []

    def install(events, registry=None):
        agent = StubAgent(events, registry)
        agents.append(agent)
        app.dependency_overrides[get_agent_loop] = lambda: agent
        return agent

    yield install
    app.dependency_overrides.pop(get_agent_loop, None)


def test_chat_streams_one_sse_frame_per_event(client, stub_agent):
    stub_agent(
        [
            {"type": "tool_call", "tool": "watch_control", "arguments": {"action": "list"}},
            {"type": "tool_result", "tool": "watch_control", "content": "No watches are running."},
            {"type": "done", "content": "Nothing is being watched."},
        ]
    )

    response = client.post("/api/agent/chat", json={"message": "what am I watching?"})

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert [f["type"] for f in frames(response.text)] == ["tool_call", "tool_result", "done"]


def test_every_frame_names_its_type_on_the_event_line_too(client, stub_agent):
    stub_agent([{"type": "done", "content": "ok"}])

    body = client.post("/api/agent/chat", json={"message": "hi"}).text

    assert "event: done" in body


def test_a_suspended_turn_reaches_the_client_as_a_confirmation(client, stub_agent):
    stub_agent(
        [
            {
                "type": "confirm_required",
                "action": {"action_id": "abc", "action_type": "watch_control", "description": "Stop watching 'ada'"},
            }
        ]
    )

    parsed = frames(client.post("/api/agent/chat", json={"message": "stop watching ada"}).text)

    assert parsed[-1]["type"] == "confirm_required"
    assert parsed[-1]["action"]["description"] == "Stop watching 'ada'"


def test_the_stream_is_wrapped_in_the_keep_alive(client, stub_agent):
    """Pinned structurally: a 300 s idle test cannot run in a suite."""
    stub_agent([{"type": "done", "content": "ok"}])
    response = client.post("/api/agent/chat", json={"message": "hi"})

    assert response.status_code == 200
    source = inspect.getsource(agent_route._sse)
    assert "with_heartbeat" in source, "a silent tool phase is what undici cuts at 300 s"


def test_non_streaming_chat_still_answers_as_json(client, stub_agent):
    stub_agent([])

    body = client.post("/api/agent/chat", json={"message": "hi", "stream": False}).json()

    assert body == {"status": "done", "response": "plain answer"}


# ---------------------------------------------------------------------------
# Resolving an approval
# ---------------------------------------------------------------------------


def _registry_with(name, handler, ran):
    async def wrapped(**kwargs):
        ran.append(kwargs)
        return handler

    registry = ToolRegistry()
    registry.register(
        Tool(name=name, description="t", parameters={"type": "object", "properties": {}}, handler=wrapped)
    )
    return registry


def test_approving_executes_then_continues_the_same_turn(client, stub_agent):
    ran: list[dict] = []
    registry = _registry_with("watch_control", "stopped", ran)
    agent = stub_agent([], registry)
    action = agent_action_queue.request("watch_control", {"action": "stop", "query": "ada"}, "Stop watching 'ada'")

    parsed = frames(client.post(f"/api/agent/actions/{action.action_id}/resolve", json={"decision": "approve"}).text)

    assert ran == [{"action": "stop", "query": "ada"}], "approve must actually run the queued call"
    assert [f["type"] for f in parsed] == ["tool_result", "done"]
    assert agent.resumed == [("watch_control", "stopped")]


def test_denying_reports_the_refusal_and_runs_nothing(client, stub_agent):
    ran: list[dict] = []
    stub_agent([], _registry_with("watch_control", "stopped", ran))
    action = agent_action_queue.request("watch_control", {"action": "stop", "query": "ada"}, "Stop watching 'ada'")

    parsed = frames(client.post(f"/api/agent/actions/{action.action_id}/resolve", json={"decision": "deny"}).text)

    assert ran == []
    assert "denied" in parsed[0]["content"].lower()


def test_resolving_an_action_that_is_gone_is_a_404_not_a_silent_success(client, stub_agent):
    stub_agent([])

    response = client.post("/api/agent/actions/does-not-exist/resolve", json={"decision": "approve"})

    assert response.status_code == 404
    assert "nothing was performed" in response.json()["detail"]


def test_pending_actions_are_listable(client, stub_agent):
    """After a reload the console has to be able to find what it was asked."""
    ran: list[dict] = []
    stub_agent([], _registry_with("watch_control", "stopped", ran))
    action = agent_action_queue.request("watch_control", {"action": "stop_all"}, "Stop every running watch")

    body = client.get("/api/agent/actions").json()
    assert action.action_id in [a["action_id"] for a in body["pending_actions"]]

    # The queue is a process-wide singleton; leaving the action pending would
    # leak into the next test's listing.
    client.post(f"/api/agent/actions/{action.action_id}/resolve", json={"decision": "deny"})
    assert action.action_id not in [a["action_id"] for a in client.get("/api/agent/actions").json()["pending_actions"]]
