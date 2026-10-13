"""System Service — OS-level command execution, application launching, and browser control.

Security model:
  - Feature is disabled by default (enable_computer_control = False in config)
  - All actions go through an approval queue — nothing executes without explicit user approval
  - Command whitelist/blacklist prevents dangerous operations
  - Every action is logged for audit trail
"""

from __future__ import annotations

import os
import shlex
import subprocess
import uuid
import webbrowser
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any
from urllib.parse import urlparse, urlunparse

from app.config import get_settings
from app.services.app_launcher import (
    AppEntry,
    discover_apps,
    launch_app,
    resolve_app,
    unavailable_reason,
)
from app.utils.logger import logger

settings = get_settings()


class ActionStatus(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    DENIED = "denied"
    EXECUTED = "executed"
    FAILED = "failed"


@dataclass
class PendingAction:
    action_id: str
    action_type: str  # run_command, open_app, open_url, send_email
    description: str
    parameters: dict[str, Any]
    status: ActionStatus = ActionStatus.PENDING
    result: str | None = None
    created_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    executed_at: str | None = None


# Whitelist of allowed executables — only these can be run via the command endpoint.
# Add entries here as needed; everything else is rejected.
COMMAND_WHITELIST: set[str] = {
    # System info
    "systeminfo",
    "hostname",
    "whoami",
    "ver",
    "date",
    "time",
    # File & directory listing (read-only)
    "dir",
    "ls",
    "type",
    "cat",
    "head",
    "tail",
    "find",
    "where",
    "tree",
    # Network diagnostics
    "ping",
    "ipconfig",
    "ifconfig",
    "nslookup",
    "tracert",
    "traceroute",
    "netstat",
    "curl",
    "wget",
    # Process / service info (read-only)
    "tasklist",
    "ps",
    "sc",
    "wmic",
    # Python & dev tools
    "python",
    "python3",
    "pip",
    "pip3",
    "node",
    "npm",
    "git",
    # Utilities
    "echo",
    "cls",
    "clear",
}

# Only web URLs may be handed to the browser. `webbrowser.open` happily accepts
# `file://`, `data:` and OS-specific handler schemes, which would turn an
# approved "open a link" action into arbitrary local file / handler access.
ALLOWED_URL_SCHEMES: frozenset[str] = frozenset({"http", "https"})


def normalize_url(raw: str) -> str:
    """Validate a user-supplied URL and return a form the browser can open.

    A scheme-less host such as ``youtube.com`` is what people actually type, but
    ``webbrowser.open`` resolves it as a relative *path* and silently opens
    nothing, so it is promoted to ``https://`` here rather than rejected.
    """
    url = (raw or "").strip()
    if not url:
        raise ValueError("URL is empty.")

    parsed = urlparse(url)
    had_scheme = bool(parsed.scheme)
    if not had_scheme:
        parsed = urlparse(f"https://{url}")
    elif parsed.scheme.lower() not in ALLOWED_URL_SCHEMES:
        raise ValueError(
            f"Unsupported URL scheme '{parsed.scheme}'. Only "
            f"{' and '.join(sorted(ALLOWED_URL_SCHEMES))} URLs can be opened."
        )

    host = parsed.hostname or ""
    if not host or any(c.isspace() for c in host):
        raise ValueError(f"Not a valid URL: '{raw}'")

    # A typed-in host with no scheme and no dot ("notaurl") is far more likely to
    # be a typo than a hostname, so it is rejected. An explicit scheme means the
    # user meant it, which keeps dev targets like http://localhost:3000 working.
    if not had_scheme and "." not in host.strip(".") and host != "localhost":
        raise ValueError(f"Not a valid URL: '{raw}'")

    return urlunparse(parsed._replace(scheme=parsed.scheme.lower()))


class SystemService:
    """Manages OS-level actions with an approval queue."""

    def __init__(self) -> None:
        self._pending: dict[str, PendingAction] = {}
        self._history: list[PendingAction] = []

    @property
    def is_enabled(self) -> bool:
        return settings.enable_computer_control

    def _check_enabled(self) -> None:
        if not self.is_enabled:
            raise PermissionError("Computer control is disabled. Set ENABLE_COMPUTER_CONTROL=true in .env to enable.")

    def _is_allowed(self, command: str) -> bool:
        """Check if the command's executable is in the whitelist."""
        try:
            parts = shlex.split(command)
        except ValueError:
            return False
        if not parts:
            return False
        executable = os.path.basename(parts[0]).lower().removesuffix(".exe")
        return executable in COMMAND_WHITELIST

    # ------------------------------------------------------------------
    # Action queue management
    # ------------------------------------------------------------------

    def request_action(self, action_type: str, description: str, parameters: dict[str, Any]) -> PendingAction:
        """Create a pending action that requires user approval."""
        self._check_enabled()

        if action_type == "run_command" and not self._is_allowed(parameters.get("command", "")):
            raise ValueError(f"Command not in whitelist. Allowed executables: {', '.join(sorted(COMMAND_WHITELIST))}")

        if action_type == "open_app":
            # Resolved here, not at execution, for the same reason URLs are:
            # the approval card must show what will actually open, and a name
            # that can never launch should fail now rather than after the user
            # has already approved it.
            entry = self._resolve_app(parameters.get("app_name", ""))
            parameters = {**parameters, "app_name": entry.name}
            description = f"Open application: {entry.name}"

        if action_type == "open_url":
            # Normalise before queueing so the approval card shows the exact URL
            # that will be opened, and a bad one fails now instead of after the
            # user has already approved it.
            parameters = {**parameters, "url": normalize_url(parameters.get("url", ""))}
            description = f"Open URL: {parameters['url']}"

        action = PendingAction(
            action_id=str(uuid.uuid4()),
            action_type=action_type,
            description=description,
            parameters=parameters,
        )
        self._pending[action.action_id] = action
        logger.log_action(f"Action queued for approval: {action_type}", target=description[:80])
        return action

    def approve_action(self, action_id: str) -> PendingAction:
        """Approve and execute a pending action."""
        action = self._pending.get(action_id)
        if not action:
            raise KeyError(f"Action '{action_id}' not found")
        if action.status != ActionStatus.PENDING:
            raise ValueError(f"Action is already {action.status.value}")

        action.status = ActionStatus.APPROVED
        self._execute(action)
        return action

    def deny_action(self, action_id: str) -> PendingAction:
        """Deny a pending action."""
        action = self._pending.get(action_id)
        if not action:
            raise KeyError(f"Action '{action_id}' not found")
        action.status = ActionStatus.DENIED
        self._history.append(action)
        del self._pending[action_id]
        logger.log_warning(f"Action denied: {action.action_type} — {action.description[:60]}")
        return action

    def list_pending(self) -> list[dict]:
        return [
            {
                "action_id": a.action_id,
                "action_type": a.action_type,
                "description": a.description,
                "parameters": a.parameters,
                "created_at": a.created_at,
            }
            for a in self._pending.values()
            if a.status == ActionStatus.PENDING
        ]

    def get_history(self, limit: int = 50) -> list[dict]:
        return [
            {
                "action_id": a.action_id,
                "action_type": a.action_type,
                "description": a.description,
                "status": a.status.value,
                "result": a.result,
                "created_at": a.created_at,
                "executed_at": a.executed_at,
            }
            for a in self._history[-limit:]
        ]

    # ------------------------------------------------------------------
    # Execution
    # ------------------------------------------------------------------

    def _execute(self, action: PendingAction) -> str:
        """Execute an approved action."""
        try:
            handler = {
                "run_command": self._exec_command,
                "open_app": self._exec_open_app,
                "open_url": self._exec_open_url,
            }.get(action.action_type)

            if not handler:
                raise ValueError(f"Unknown action type: {action.action_type}")

            result = handler(action.parameters)
            action.status = ActionStatus.EXECUTED
            action.result = result
            action.executed_at = datetime.utcnow().isoformat()
            logger.log_success(f"Action executed: {action.action_type}")

        except Exception as exc:
            action.status = ActionStatus.FAILED
            action.result = str(exc)
            action.executed_at = datetime.utcnow().isoformat()
            logger.log_error(f"Action failed: {exc}")
            result = f"Error: {exc}"

        self._history.append(action)
        if action.action_id in self._pending:
            del self._pending[action.action_id]

        return result

    def _exec_command(self, params: dict) -> str:
        """Execute a command without a shell — prevents injection attacks."""
        command = params.get("command", "")
        if not self._is_allowed(command):
            raise PermissionError(
                f"Command not in whitelist. Allowed executables: {', '.join(sorted(COMMAND_WHITELIST))}"
            )

        try:
            cmd_parts = shlex.split(command)
        except ValueError as e:
            raise PermissionError(f"Invalid command syntax: {e}") from e

        timeout = min(params.get("timeout", 30), 60)  # Max 60 seconds
        proc = subprocess.run(
            cmd_parts,
            shell=False,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        output = proc.stdout or ""
        if proc.stderr:
            output += f"\n[STDERR]: {proc.stderr}"
        if proc.returncode != 0:
            output += f"\n[EXIT CODE]: {proc.returncode}"
        return output.strip() or "(no output)"

    @staticmethod
    def _resolve_app(app_name: str) -> AppEntry:
        """The one installed application ``app_name`` names, or a clear refusal.

        Never picks between comparable matches: opening the wrong desktop
        application is a much worse failure than one more question.
        """
        query = (app_name or "").strip()
        if not query:
            raise ValueError("No application name was given.")

        # The catalogue is fetched once and passed in, so queueing and execution
        # can never disagree about what was installed at that moment.
        installed = discover_apps()
        match = resolve_app(query, entries=installed)
        if match.entry is not None:
            return match.entry
        if match.candidates:
            names = ", ".join(candidate.name for candidate in match.candidates)
            raise ValueError(f"'{query}' matches several applications. Did you mean: {names}?")
        if not installed:
            raise ValueError(unavailable_reason())
        raise ValueError(f"'{query}' is not installed, or was not found among {len(installed)} applications.")

    def _exec_open_app(self, params: dict) -> str:
        """Launch an application discovered on this machine.

        Re-resolved here as well: the queue is in-memory and the application may
        have been uninstalled since approval. Execution is the only place a
        target is handed to the OS, and that target is always one discovery
        produced — the user's text only ever selected it.
        """
        entry = self._resolve_app(params.get("app_name", ""))
        launch_app(entry)
        return f"Launched: {entry.name}"

    def _exec_open_url(self, params: dict) -> str:
        """Open a URL in the default browser."""
        # Re-validated here as well: the queue is in-memory, but execution is the
        # only place that actually hands the string to the OS.
        url = normalize_url(params.get("url", ""))
        if not webbrowser.open(url):
            raise RuntimeError(
                f"No browser could be launched for {url}. "
                "The backend may be running without a desktop session (e.g. in Docker)."
            )
        return f"Opened in browser: {url}"


system_service = SystemService()
