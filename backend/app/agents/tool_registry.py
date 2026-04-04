"""Tool Registry — maps tool definitions to callable handlers for the agent loop."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any


@dataclass
class Tool:
    name: str
    description: str
    parameters: dict  # JSON Schema for the function parameters
    handler: Callable[..., Awaitable[str]]  # async function that returns a string result


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
            schemas.append({
                "type": "function",
                "function": {
                    "name": tool.name,
                    "description": tool.description,
                    "parameters": tool.parameters,
                },
            })
        return schemas

    async def execute(self, name: str, arguments: dict[str, Any]) -> str:
        """Execute a tool by name with the given arguments."""
        tool = self._tools.get(name)
        if not tool:
            return f"Error: Tool '{name}' not found. Available tools: {', '.join(self._tools.keys())}"
        try:
            return await tool.handler(**arguments)
        except Exception as exc:
            return f"Error executing {name}: {exc}"
