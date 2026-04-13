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

from app.config import get_settings
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
    "systeminfo", "hostname", "whoami", "ver", "date", "time",
    # File & directory listing (read-only)
    "dir", "ls", "type", "cat", "head", "tail", "find", "where", "tree",
    # Network diagnostics
    "ping", "ipconfig", "ifconfig", "nslookup", "tracert", "traceroute",
    "netstat", "curl", "wget",
    # Process / service info (read-only)
    "tasklist", "ps", "sc", "wmic",
    # Python & dev tools
    "python", "python3", "pip", "pip3", "node", "npm", "git",
    # Utilities
    "echo", "cls", "clear",
}

# Application aliases for cross-platform launching
APP_ALIASES: dict[str, list[str]] = {
    "notepad": ["notepad.exe"],
    "calculator": ["calc.exe"],
    "browser": ["start", "msedge"],
    "explorer": ["explorer.exe"],
    "vscode": ["code"],
    "spotify": ["spotify"],
}


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
            raise PermissionError(
                "Computer control is disabled. Set ENABLE_COMPUTER_CONTROL=true in .env to enable."
            )

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
            raise ValueError(
                f"Command not in whitelist. Allowed executables: {', '.join(sorted(COMMAND_WHITELIST))}"
            )

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
        result = self._execute(action)
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

    def _exec_open_app(self, params: dict) -> str:
        """Launch an application from the predefined alias list only."""
        app_name = params.get("app_name", "").lower()
        cmd_parts = APP_ALIASES.get(app_name)
        if not cmd_parts:
            return f"Unknown application: '{app_name}'. Allowed: {', '.join(sorted(APP_ALIASES))}"

        try:
            subprocess.Popen(cmd_parts, shell=False)
            return f"Launched: {app_name}"
        except FileNotFoundError:
            return f"Application not found: {app_name}"

    def _exec_open_url(self, params: dict) -> str:
        """Open a URL in the default browser."""
        url = params.get("url", "")
        webbrowser.open(url)
        return f"Opened in browser: {url}"


system_service = SystemService()
