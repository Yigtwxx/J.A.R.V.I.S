"""Approval queue for agent tool calls that change the user's console state.

The console already had this shape once: ``SystemService`` queues an OS action,
the System panel shows it, and nothing runs until the user clicks Approve. That
model is the reason the agent can be trusted with the panels at all, so this
queue reuses its vocabulary (``PendingAction``, ``ActionStatus``) rather than
inventing a second one — a denied agent action and a denied system action mean
the same thing and should read the same in the audit log.

It is in-memory for the same reason ``SystemService``'s queue is: an approval is
only meaningful while the person who was asked is still there. A restart drops
pending approvals, and that is the safe direction to fail.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from app.agents.tool_registry import ToolRegistry
from app.services.system_service import ActionStatus, PendingAction
from app.utils.logger import logger

DENIED_RESULT = "The user denied this action. Nothing was changed."
"""Fed back to the model as the tool result, so it narrates the refusal instead
of assuming the action succeeded or silently retrying it."""


class AgentActionQueue:
    """Holds agent tool calls that are waiting for the user's approval."""

    def __init__(self, max_history: int = 100) -> None:
        self._pending: dict[str, PendingAction] = {}
        self._history: list[PendingAction] = []
        self._max_history = max_history

    def request(self, tool_name: str, arguments: dict[str, Any], summary: str) -> PendingAction:
        """Queue a call and return the action the user has to answer."""
        action = PendingAction(
            action_id=str(uuid.uuid4()),
            action_type=tool_name,
            description=summary,
            parameters=dict(arguments),
        )
        self._pending[action.action_id] = action
        logger.log_action(f"Agent action queued for approval: {tool_name}", target=summary[:80])
        return action

    def get(self, action_id: str) -> PendingAction | None:
        return self._pending.get(action_id)

    def list_pending(self) -> list[dict[str, Any]]:
        return [as_dict(a) for a in self._pending.values() if a.status == ActionStatus.PENDING]

    async def resolve(self, action_id: str, *, approved: bool, registry: ToolRegistry) -> str:
        """Run the queued call, or record the refusal. Returns the tool result.

        Raises ``KeyError`` when the action is unknown — which, because the queue
        is in-memory, is also what a restart between the question and the answer
        looks like — and ``ValueError`` when it has already been answered.
        """
        action = self._pending.get(action_id)
        if action is None:
            raise KeyError(f"Action '{action_id}' not found")
        if action.status != ActionStatus.PENDING:
            raise ValueError(f"Action is already {action.status.value}")

        if not approved:
            action.status = ActionStatus.DENIED
            action.executed_at = datetime.now(UTC).isoformat()
            action.result = DENIED_RESULT
            logger.log_warning(f"Agent action denied: {action.action_type} — {action.description[:60]}")
            self._retire(action)
            return DENIED_RESULT

        action.status = ActionStatus.APPROVED
        # `registry.execute` turns every failure into a string, so the result is
        # reported to the model either way; there is no exception to catch here.
        result = await registry.execute(action.action_type, action.parameters)
        action.status = ActionStatus.EXECUTED
        action.result = result
        action.executed_at = datetime.now(UTC).isoformat()
        logger.log_success(f"Agent action executed: {action.action_type}")
        self._retire(action)
        return result

    def _retire(self, action: PendingAction) -> None:
        self._pending.pop(action.action_id, None)
        self._history.append(action)
        if len(self._history) > self._max_history:
            del self._history[: -self._max_history]

    def get_history(self, limit: int = 50) -> list[dict[str, Any]]:
        return [as_dict(a) for a in self._history[-limit:]]


def as_dict(action: PendingAction) -> dict[str, Any]:
    """Wire shape of an action — the same keys the System panel already renders."""
    return {
        "action_id": action.action_id,
        "action_type": action.action_type,
        "description": action.description,
        "parameters": action.parameters,
        "status": action.status.value,
        "result": action.result,
        "created_at": action.created_at,
        "executed_at": action.executed_at,
    }


agent_action_queue = AgentActionQueue()
