"""Tool Registry — maps tool definitions to callable handlers for the agent loop."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any


@dataclass
class Tool:
    name: str
    description: str
    parameters: dict  # JSON Schema for the function parameters
    handler: Callable[..., Awaitable[str]]  # async function that returns a string result

    # A tool that changes the user's console state must not run on the model's
    # say-so alone. `True` gates every call; a predicate gates only some of them,
    # which is what the grouped console tools need — `watch_control(action="list")`
    # is a read and `action="stop"` is not.
    requires_confirmation: bool | Callable[[dict[str, Any]], bool] = False
    # Renders the sentence the approval card shows. Without one the card would
    # have to describe the call in raw JSON, which is not a question a person can
    # answer.
    confirm_summary: Callable[[dict[str, Any]], str] | None = None

    def needs_confirmation(self, arguments: dict[str, Any]) -> bool:
        if callable(self.requires_confirmation):
            return bool(self.requires_confirmation(arguments))
        return bool(self.requires_confirmation)

    def summarize(self, arguments: dict[str, Any]) -> str:
        if self.confirm_summary is not None:
            return self.confirm_summary(arguments)
        rendered = ", ".join(f"{key}={value!r}" for key, value in arguments.items())
        return f"{self.name}({rendered})"


class ToolRegistry:
    """Central registry for all tools the LLM agent can call."""

    def __init__(self) -> None:
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        self._tools[tool.name] = tool

    def get(self, name: str) -> Tool | None:
        return self._tools.get(name)

    def list_tools(self) -> list[str]:
        return list(self._tools.keys())

    def get_ollama_schemas(self) -> list[dict]:
        """Return all tools as Ollama-compatible function schemas."""
        schemas = []
        for tool in self._tools.values():
            schemas.append(
                {
                    "type": "function",
                    "function": {
                        "name": tool.name,
                        "description": tool.description,
                        "parameters": tool.parameters,
                    },
                }
            )
        return schemas

    def needs_confirmation(self, name: str, arguments: dict[str, Any]) -> bool:
        """Whether this exact call must be approved before it runs.

        An unknown tool never needs approval: it cannot do anything, and
        ``execute`` already answers it with the list of tools that exist.
        """
        tool = self._tools.get(name)
        return bool(tool and tool.needs_confirmation(arguments))

    def summarize(self, name: str, arguments: dict[str, Any]) -> str:
        """One sentence describing what the call would do, for the approval card."""
        tool = self._tools.get(name)
        if not tool:
            return f"Unknown tool '{name}'"
        return tool.summarize(arguments)

    async def execute(self, name: str, arguments: dict[str, Any]) -> str:
        """Execute a tool by name with the given arguments."""
        tool = self._tools.get(name)
        if not tool:
            return f"Error: Tool '{name}' not found. Available tools: {', '.join(self._tools.keys())}"
        try:
            return await tool.handler(**arguments)
        except Exception as exc:
            return f"Error executing {name}: {exc}"
