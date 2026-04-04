"""J.A.R.V.I.S Plugin Manager — auto-discovers and manages OSINT plugins."""

from __future__ import annotations

import importlib
import inspect
import json
import os
import sys
from pathlib import Path
from typing import Any

from app.utils.logger import logger

from .base_plugin import BasePlugin


class PluginManager:
    """Discovers, loads, and manages BasePlugin subclasses from the plugins directory."""

    def __init__(self, plugins_dir: str | None = None) -> None:
        self._plugins: dict[str, BasePlugin] = {}
        self._config_path = Path("data/plugin_config.json")
        self._enabled: dict[str, bool] = {}
        self._plugins_dir = plugins_dir or str(Path(__file__).parent)
        self._load_config()

    # ------------------------------------------------------------------
    # Config persistence
    # ------------------------------------------------------------------
    def _load_config(self) -> None:
        if self._config_path.exists():
            try:
                with open(self._config_path, encoding="utf-8") as f:
                    self._enabled = json.load(f)
            except Exception:
                self._enabled = {}

    def _save_config(self) -> None:
        self._config_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self._config_path, "w", encoding="utf-8") as f:
            json.dump(self._enabled, f, indent=2)

    # ------------------------------------------------------------------
    # Discovery
    # ------------------------------------------------------------------
    def discover(self) -> None:
        """Scan the plugins directory for BasePlugin subclasses and register them."""
        plugins_path = Path(self._plugins_dir)
        if not plugins_path.exists():
            logger.log_warning(f"Plugins directory not found: {plugins_path}")
            return

        # Ensure the plugins directory is on sys.path
        parent = str(plugins_path.parent)
        if parent not in sys.path:
            sys.path.insert(0, parent)

        for file in plugins_path.glob("*.py"):
            if file.name.startswith("_") or file.name == "base_plugin.py":
                continue
            module_name = f"app.plugins.{file.stem}"
            try:
                module = importlib.import_module(module_name)
                for _name, obj in inspect.getmembers(module, inspect.isclass):
                    if issubclass(obj, BasePlugin) and obj is not BasePlugin and obj.name:
                        instance = obj()
                        self._plugins[instance.name] = instance
                        # Default to enabled if not in config
                        if instance.name not in self._enabled:
                            self._enabled[instance.name] = True
                        logger.log_action(f"Plugin loaded: {instance.display_name} v{instance.version}")
            except Exception as exc:
                logger.log_warning(f"Failed to load plugin {file.name}: {exc}")

        self._save_config()
        logger.log_action(f"Plugin discovery complete: {len(self._plugins)} plugin(s) found")

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def list_plugins(self) -> list[dict[str, Any]]:
        return [
            {**plugin.info(), "enabled": self._enabled.get(plugin.name, True)}
            for plugin in self._plugins.values()
        ]

    def get_plugin(self, name: str) -> BasePlugin | None:
        return self._plugins.get(name)

    def is_enabled(self, name: str) -> bool:
        return self._enabled.get(name, False)

    def toggle(self, name: str) -> bool:
        """Toggle a plugin's enabled state. Returns the new state."""
        if name not in self._plugins:
            raise KeyError(f"Plugin '{name}' not found")
        self._enabled[name] = not self._enabled.get(name, True)
        self._save_config()
        return self._enabled[name]

    def set_enabled(self, name: str, enabled: bool) -> None:
        if name not in self._plugins:
            raise KeyError(f"Plugin '{name}' not found")
        self._enabled[name] = enabled
        self._save_config()

    async def run_plugin(self, name: str, query: str, **kwargs: Any) -> dict[str, Any]:
        plugin = self._plugins.get(name)
        if not plugin:
            return {"error": f"Plugin '{name}' not found", "results": []}
        if not self._enabled.get(name, False):
            return {"error": f"Plugin '{name}' is disabled", "results": []}
        return await plugin.search(query, **kwargs)

    async def run_all_enabled(self, query: str, **kwargs: Any) -> list[dict[str, Any]]:
        """Run all enabled plugins and collect results."""
        import asyncio

        tasks = []
        for name, plugin in self._plugins.items():
            if self._enabled.get(name, False):
                tasks.append(plugin.search(query, **kwargs))

        if not tasks:
            return []

        results = await asyncio.gather(*tasks, return_exceptions=True)
        output = []
        for r in results:
            if isinstance(r, Exception):
                output.append({"error": str(r), "results": []})
            else:
                output.append(r)
        return output

    def get_tool_schemas(self) -> list[dict]:
        """Return Ollama-compatible tool schemas for all enabled plugins."""
        return [
            plugin.tool_schema
            for name, plugin in self._plugins.items()
            if self._enabled.get(name, False)
        ]


# Module-level singleton
plugin_manager = PluginManager()
