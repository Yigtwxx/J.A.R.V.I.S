"""Agentic Loop — LLM decides which tools to call, executes them, and iterates until done.

The loop emits **events**, not a flat string. Two things need that. Tool calls
are half of what the agent does and used to be invisible to the client, which
only ever saw the final prose. And a tool that changes the user's console state
must stop and ask before it runs — a question the client cannot render if all it
receives is text.
"""

from __future__ import annotations

import asyncio
import re
from collections.abc import AsyncIterator
from typing import Any

from app.agents.pending_actions import AgentActionQueue, agent_action_queue, as_dict
from app.agents.tool_registry import ToolRegistry
from app.config import get_settings
from app.services.ollama_client import build_ollama_client
from app.utils.logger import logger

settings = get_settings()

AgentEvent = dict[str, Any]
"""One of: token, tool_call, tool_result, confirm_required, error, done."""


class AgentLoop:
    """Core agentic loop: message -> LLM (with tools) -> tool_calls -> execute -> loop."""

    def __init__(
        self,
        registry: ToolRegistry,
        model: str | None = None,
        max_iterations: int = 10,
        action_queue: AgentActionQueue | None = None,
    ) -> None:
        self.registry = registry
        self.model = model or settings.ollama_model
        self.client = build_ollama_client()
        self.max_iterations = max_iterations
        self.action_queue = action_queue or agent_action_queue

    @staticmethod
    def _strip_thinking(text: str) -> str:
        return re.sub(r"<think>[\s\S]*?</think>", "", text).strip()

    # ------------------------------------------------------------------
    # Entry points
    # ------------------------------------------------------------------

    def run_events(
        self,
        user_message: str,
        system_prompt: str | None = None,
        conversation_history: list[dict] | None = None,
    ) -> AsyncIterator[AgentEvent]:
        """Stream the events of one turn."""
        messages = self._opening_messages(system_prompt, conversation_history)
        messages.append({"role": "user", "content": user_message})
        return self._stream(messages)

    def resume_events(
        self,
        tool_name: str,
        tool_result: str,
        system_prompt: str | None = None,
        conversation_history: list[dict] | None = None,
    ) -> AsyncIterator[AgentEvent]:
        """Continue a turn that was suspended on an approval, with its outcome.

        The assistant turn that *requested* the tool is not replayed: the client
        only ever held the rendered conversation, and re-deriving it would mean
        persisting model-internal state across an HTTP round trip for no gain.
        Naming the tool inside the result keeps the message self-describing, which
        is all the model needs to narrate what happened.
        """
        messages = self._opening_messages(system_prompt, conversation_history)
        messages.append({"role": "tool", "content": f"{tool_name} -> {tool_result}"})
        return self._stream(messages)

    async def run(
        self,
        user_message: str,
        system_prompt: str | None = None,
        conversation_history: list[dict] | None = None,
    ) -> dict[str, Any]:
        """Non-streaming turn.

        Returns ``{"status": "done", "response": ...}``, or
        ``{"status": "pending_approval", "action": {...}}`` when the turn stopped
        to ask. The caller has to distinguish the two: reporting a suspended turn
        as a finished one would tell the user an action ran that did not.
        """
        text_parts: list[str] = []
        async for event in self.run_events(user_message, system_prompt, conversation_history):
            kind = event.get("type")
            if kind == "confirm_required":
                return {"status": "pending_approval", "action": event["action"]}
            if kind == "done":
                return {"status": "done", "response": event.get("content", "")}
            if kind == "error":
                return {"status": "error", "response": event.get("message", "")}
            if kind == "token":
                text_parts.append(event.get("content", ""))
        return {"status": "done", "response": "".join(text_parts)}

    # ------------------------------------------------------------------
    # The loop
    # ------------------------------------------------------------------

    def _opening_messages(
        self,
        system_prompt: str | None,
        conversation_history: list[dict] | None,
    ) -> list[dict[str, Any]]:
        messages: list[dict[str, Any]] = [{"role": "system", "content": system_prompt or self._default_system_prompt()}]
        if conversation_history:
            messages.extend(conversation_history)
        return messages

    async def _stream(self, messages: list[dict[str, Any]]) -> AsyncIterator[AgentEvent]:
        tools = self.registry.get_ollama_schemas()

        for iteration in range(self.max_iterations):
            is_last = iteration == self.max_iterations - 1
            logger.log_thought(f"Agent iteration {iteration + 1}/{self.max_iterations}")

            try:
                response = await self.client.chat(
                    model=self.model,
                    messages=messages,
                    # No tools on the last iteration, so the loop always ends on prose.
                    tools=tools if not is_last else [],
                    options={"temperature": 0.3, "top_p": 0.7},
                )
            except Exception as exc:
                logger.log_error(f"Agent LLM call failed: {exc}")
                yield {"type": "error", "message": str(exc)}
                return

            msg = response.get("message", {})
            tool_calls = msg.get("tool_calls")

            if not tool_calls:
                async for event in self._final_answer(messages, used_tools=iteration > 0):
                    yield event
                return

            messages.append(msg)
            immediate, gated = self._partition(tool_calls)

            for name, arguments in immediate:
                logger.log_action(f"Agent calling tool: {name}", target=str(arguments)[:100])
                yield {"type": "tool_call", "tool": name, "arguments": arguments}

            if immediate:
                results = await asyncio.gather(*(self.registry.execute(n, a) for n, a in immediate))
                for (name, _arguments), result in zip(immediate, results, strict=True):
                    messages.append({"role": "tool", "content": f"{name} -> {result}"})
                    yield {"type": "tool_result", "tool": name, "content": result}

            if gated:
                # One question at a time. Two approval cards at once is a dialog
                # the console has no place for, and the second action's arguments
                # may well depend on what the first one returns.
                name, arguments = gated[0]
                action = self.action_queue.request(name, arguments, self.registry.summarize(name, arguments))
                yield {"type": "confirm_required", "action": as_dict(action)}
                return

        yield {"type": "error", "message": "Agent reached maximum iterations without a final response."}

    def _partition(
        self, tool_calls: list[dict]
    ) -> tuple[list[tuple[str, dict[str, Any]]], list[tuple[str, dict[str, Any]]]]:
        """Split one round of tool calls into the ones that may run and the ones that must ask."""
        immediate: list[tuple[str, dict[str, Any]]] = []
        gated: list[tuple[str, dict[str, Any]]] = []
        for call in tool_calls:
            func = call.get("function", {})
            name = func.get("name", "")
            arguments = func.get("arguments") or {}
            if self.registry.needs_confirmation(name, arguments):
                gated.append((name, arguments))
            else:
                immediate.append((name, arguments))
        return immediate, gated

    async def _final_answer(self, messages: list[dict[str, Any]], *, used_tools: bool) -> AsyncIterator[AgentEvent]:
        """Stream the closing prose, with a reflection pass once tools have run."""
        reflection = ""
        if used_tools:
            reflection = (
                "\n\nBefore answering, briefly reflect: Are there gaps in the gathered data? "
                "Any contradictions? Rate your confidence."
            )
        messages.append({"role": "user", "content": f"Now provide your final comprehensive response.{reflection}"})

        try:
            stream = await self.client.chat(
                model=self.model,
                messages=messages,
                stream=True,
                options={"temperature": 0.3, "top_p": 0.7},
            )
        except Exception as exc:
            logger.log_error(f"Agent final response failed: {exc}")
            yield {"type": "error", "message": str(exc)}
            return

        in_thinking = False
        collected: list[str] = []
        async for chunk in stream:
            token = chunk.get("message", {}).get("content", "")
            if not token:
                continue
            if "<think>" in token:
                in_thinking = True
            if not in_thinking:
                collected.append(token)
                yield {"type": "token", "content": token}
            if "</think>" in token:
                in_thinking = False

        yield {"type": "done", "content": self._strip_thinking("".join(collected))}

    @staticmethod
    def _default_system_prompt() -> str:
        return """You are J.A.R.V.I.S., an advanced OSINT (Open Source Intelligence) AI agent.

You have access to two kinds of tools: intelligence-gathering tools, and console-control tools that operate the user's own J.A.R.V.I.S. console (watches, memory, plugins, saved profiles, search history, and this machine).

RULES:
1. Think carefully about which tools are most relevant before calling them.
2. Do NOT call tools unnecessarily — only use what is needed to answer the query.
3. The user asks you to operate the console so they do not have to do it by hand. When they ask for something a panel does, perform it with the matching tool instead of explaining where the button is.
4. Say what you are about to change before you change it, and report exactly what happened afterwards — including when nothing did.
5. Actions that destroy or alter state pause for the user's approval. When that happens, stop and wait; never claim an action succeeded before its result comes back.
6. If a tool returns an error or no data, note it and move on — do not retry excessively.
7. Be objective, analytical, and precise. Format intelligence findings as a structured report with clear sections."""
