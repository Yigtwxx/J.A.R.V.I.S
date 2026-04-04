from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class BasePlugin(ABC):
    """Abstract base class for all J.A.R.V.I.S OSINT plugins."""

    name: str = ""
    display_name: str = ""
    version: str = "1.0.0"
    description: str = ""

    @abstractmethod
    async def search(self, query: str, **kwargs: Any) -> dict[str, Any]:
        """Execute the plugin's search/scan logic.

        Returns a dict with at least:
            - source: str  (plugin name)
            - results: list[dict]
        """
        ...

    @property
    def tool_schema(self) -> dict:
        """Return an Ollama-compatible function/tool schema for LLM calling."""
        return {
            "type": "function",
            "function": {
                "name": f"plugin_{self.name}",
                "description": self.description,
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "The search query (name, username, IP, domain, etc.)",
                        },
                    },
                    "required": ["query"],
                },
            },
        }

    def info(self) -> dict[str, str]:
        return {
            "name": self.name,
            "display_name": self.display_name,
            "version": self.version,
            "description": self.description,
        }
