"""Console control tools — the panels, operated by the agent on the user's behalf.

Everything here has a hand-driven equivalent in the UI: `WatchPanel` starts and
stops watches, `MemoryPanel` writes memories, `SystemPanel` queues an OS action
and waits for an Approve click. The user asked to stop doing that by hand, so
each panel's actions are exposed as a tool and the agent performs them instead.

Two decisions shape the whole module:

**Grouped tools, not one tool per action.** The local model is a 9B; handing it
thirty-odd flat functions measurably degrades which one it picks. Six tools with
an ``action`` enum keep the registry small and keep related arguments together.

**Every action reports.** An unknown action, a missing argument and an empty
result are three different answers and each says so. A tool that quietly returns
nothing is indistinguishable from one that worked, and the model will narrate
the silence as success.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Iterable
from typing import Any

from sqlalchemy.orm import Session

from app.agents.tool_registry import Tool, ToolRegistry
from app.agents.tools import as_json, truncate_result
from app.database.connection import SessionLocal
from app.models.history import SearchHistory
from app.models.profile import Profile
from app.plugins import plugin_manager
from app.services.self_healing_service import self_healing_service
from app.services.system_service import system_service
from app.services.user_memory_service import UserMemoryService
from app.services.watch_service import watch_service

_memory = UserMemoryService()

WATCH_ACTIONS = ("list", "status", "start", "stop", "stop_all")
WATCH_DESTRUCTIVE = frozenset({"stop", "stop_all"})

MEMORY_ACTIONS = ("list", "search", "add", "delete", "delete_category")
MEMORY_DESTRUCTIVE = frozenset({"delete", "delete_category"})

PLUGIN_ACTIONS = ("list", "toggle")
PLUGIN_DESTRUCTIVE = frozenset({"toggle"})

PROFILE_ACTIONS = ("list", "get", "search", "export", "delete")
PROFILE_DESTRUCTIVE = frozenset({"delete"})

HISTORY_ACTIONS = ("list", "delete", "clear")
HISTORY_DESTRUCTIVE = frozenset({"delete", "clear"})

SYSTEM_ACTIONS = ("service_status", "health_log", "pending", "run_command", "open_app", "open_url")
SYSTEM_DESTRUCTIVE = frozenset({"run_command", "open_app", "open_url"})

EXPORT_FORMATS = ("pdf", "json", "csv")

# The profile row is wide (30+ columns); dumping all of it for every listing
# spends the model's context on nulls.
PROFILE_SUMMARY_FIELDS = ("id", "name", "description")

SUMMARY_LIMIT = 300
"""An approval card is one sentence the user has to read before clicking."""


# ------------------------------------------------------------------
# Shared answers
# ------------------------------------------------------------------


def _unknown_action(action: str, allowed: Iterable[str]) -> str:
    return f"Error: unknown action '{action}'. Valid actions: {', '.join(allowed)}."


def _missing(action: str, parameter: str) -> str:
    return f"Error: action '{action}' requires the '{parameter}' argument."


async def _db(work: Callable[[Session], Any]) -> Any:
    """Run blocking SQLAlchemy work off the event loop, in its own session.

    The tools run outside any request, so there is no ``Depends(get_db)`` session
    to borrow; this mirrors what that dependency does — commit on success, roll
    back on failure, always close.
    """

    def run() -> Any:
        db = SessionLocal()
        try:
            result = work(db)
            db.commit()
            return result
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    return await asyncio.to_thread(run)


# ------------------------------------------------------------------
# Watch
# ------------------------------------------------------------------


async def watch_control(
    action: str,
    query: str | None = None,
    interval_minutes: int = 60,
) -> str:
    """Start, stop and inspect the background monitoring the Watch panel drives."""
    if action == "list":
        watches = watch_service.active_watches
        if not watches:
            return "No watches are running."
        return as_json({"count": len(watches), "watches": watches})

    if action == "status":
        if not query:
            return _missing(action, "query")
        status = watch_service.get_watch_status(query)
        if status is None:
            return f"No watch is running for '{query}'."
        return as_json(status)

    if action == "start":
        if not query:
            return _missing(action, "query")
        # The same bounds the route declares (ge=5, le=1440). Enforced here too,
        # because a model that invents interval_minutes=1 would otherwise get a
        # watch that re-runs the whole discovery pipeline every minute.
        if not 5 <= interval_minutes <= 1440:
            return f"Error: interval_minutes must be between 5 and 1440, got {interval_minutes}."
        return as_json(watch_service.start_discovery_watch(query=query, interval_minutes=interval_minutes))

    if action == "stop":
        if not query:
            return _missing(action, "query")
        result = watch_service.stop_watch(query)
        if result.get("status") == "not_found":
            return f"No watch was running for '{query}'; nothing was stopped."
        return as_json(result)

    if action == "stop_all":
        count = watch_service.stop_all()
        return f"Stopped {count} watch(es)." if count else "There were no watches to stop."

    return _unknown_action(action, WATCH_ACTIONS)


# ------------------------------------------------------------------
# Memory
# ------------------------------------------------------------------


async def memory_control(
    action: str,
    category: str | None = None,
    key: str | None = None,
    value: str | None = None,
    query: str | None = None,
    memory_id: int | None = None,
    importance: int = 5,
) -> str:
    """Read and write the persistent user memory the Memory panel shows."""
    if action == "list":
        memories = await _db(lambda db: _memory.recall(db, category=category))
        if not memories:
            scope = f" in category '{category}'" if category else ""
            return f"No memories stored{scope}."
        return as_json({"count": len(memories), "memories": memories})

    if action == "search":
        if not query:
            return _missing(action, "query")
        matches = await _db(lambda db: _memory.search(db, query, n_results=5))
        if not matches:
            return f"No memory matches '{query}'."
        return as_json({"count": len(matches), "memories": matches})

    if action == "add":
        for name, supplied in (("category", category), ("key", key), ("value", value)):
            if not supplied:
                return _missing(action, name)
        if not 1 <= importance <= 10:
            return f"Error: importance must be between 1 and 10, got {importance}."
        stored = await _db(
            lambda db: (
                _memory.remember(
                    db,
                    category=category,
                    key=key,
                    value=value,
                    importance=importance,
                ).id
            )
        )
        return f"Stored memory #{stored}: [{category}] {key}."

    if action == "delete":
        if memory_id is None:
            return _missing(action, "memory_id")
        deleted = await _db(lambda db: _memory.forget(db, memory_id))
        return f"Deleted memory #{memory_id}." if deleted else f"No memory with id {memory_id}; nothing was deleted."

    if action == "delete_category":
        if not category:
            return _missing(action, "category")
        count = await _db(lambda db: _memory.forget_category(db, category))
        return f"Deleted {count} memory/memories from category '{category}'."

    return _unknown_action(action, MEMORY_ACTIONS)


# ------------------------------------------------------------------
# Plugins
# ------------------------------------------------------------------


async def plugin_control(action: str, name: str | None = None) -> str:
    """List plugins and switch them on or off, as the Plugin panel does."""
    if action == "list":
        plugins = plugin_manager.list_plugins()
        if not plugins:
            return "No plugins are installed."
        return as_json({"count": len(plugins), "plugins": plugins})

    if action == "toggle":
        if not name:
            return _missing(action, "name")
        try:
            enabled = plugin_manager.toggle(name)
        except KeyError:
            installed = ", ".join(p["name"] for p in plugin_manager.list_plugins()) or "none"
            return f"Error: plugin '{name}' is not installed. Installed plugins: {installed}."
        return f"Plugin '{name}' is now {'enabled' if enabled else 'disabled'}."

    return _unknown_action(action, PLUGIN_ACTIONS)


# ------------------------------------------------------------------
# Profiles
# ------------------------------------------------------------------


def _profile_summary(profile: Profile) -> dict[str, Any]:
    return {field: getattr(profile, field) for field in PROFILE_SUMMARY_FIELDS}


def _profile_detail(profile: Profile) -> dict[str, Any]:
    """Every populated column, so empty fields do not crowd out the real ones."""
    return {
        column.name: getattr(profile, column.name)
        for column in profile.__table__.columns
        if getattr(profile, column.name) not in (None, "", [], {})
    }


async def profile_control(
    action: str,
    profile_id: int | None = None,
    name: str | None = None,
    export_format: str = "pdf",
) -> str:
    """List, read, export and delete the saved dossiers."""
    if action == "list":
        profiles = await _db(lambda db: [_profile_summary(p) for p in db.query(Profile).limit(100).all()])
        if not profiles:
            return "No profiles are saved."
        return as_json({"count": len(profiles), "profiles": profiles})

    if action == "get":
        if profile_id is None:
            return _missing(action, "profile_id")

        def load(db: Session) -> dict[str, Any] | None:
            profile = db.query(Profile).filter(Profile.id == profile_id).first()
            return _profile_detail(profile) if profile else None

        detail = await _db(load)
        if detail is None:
            return f"No profile with id {profile_id}."
        return as_json(detail)

    if action == "search":
        if not name:
            return _missing(action, "name")
        matches = await _db(
            lambda db: [
                _profile_summary(p) for p in db.query(Profile).filter(Profile.name.ilike(f"%{name}%")).limit(50).all()
            ]
        )
        if not matches:
            return f"No saved profile matches '{name}'."
        return as_json({"count": len(matches), "profiles": matches})

    if action == "export":
        if profile_id is None:
            return _missing(action, "profile_id")
        if export_format not in EXPORT_FORMATS:
            return f"Error: unknown export_format '{export_format}'. Valid formats: {', '.join(EXPORT_FORMATS)}."
        exists = await _db(lambda db: db.query(Profile).filter(Profile.id == profile_id).first() is not None)
        if not exists:
            return f"No profile with id {profile_id}; nothing to export."
        # The dossier is a file download, not text — the tool confirms the target
        # and hands back the endpoint rather than pulling bytes into the context.
        return (
            f"Profile #{profile_id} can be downloaded as {export_format.upper()} "
            f"from /api/export/{export_format}/{profile_id}."
        )

    if action == "delete":
        if profile_id is None:
            return _missing(action, "profile_id")

        def drop(db: Session) -> str | None:
            profile = db.query(Profile).filter(Profile.id == profile_id).first()
            if not profile:
                return None
            deleted_name = profile.name
            db.delete(profile)
            return deleted_name

        deleted = await _db(drop)
        if deleted is None:
            return f"No profile with id {profile_id}; nothing was deleted."
        return f"Deleted profile #{profile_id} ({deleted})."

    return _unknown_action(action, PROFILE_ACTIONS)


# ------------------------------------------------------------------
# Search history
# ------------------------------------------------------------------


async def history_control(action: str, history_id: int | None = None) -> str:
    """Read and prune the search history the Logs panel lists."""
    if action == "list":
        records = await _db(
            lambda db: [
                {"id": r.id, "query_name": r.query_name, "searched_at": r.searched_at}
                for r in db.query(SearchHistory).order_by(SearchHistory.searched_at.desc()).limit(50).all()
            ]
        )
        if not records:
            return "The search history is empty."
        return as_json({"count": len(records), "history": records})

    if action == "delete":
        if history_id is None:
            return _missing(action, "history_id")

        def drop(db: Session) -> bool:
            record = db.query(SearchHistory).filter(SearchHistory.id == history_id).first()
            if not record:
                return False
            db.delete(record)
            return True

        return (
            f"Deleted history record #{history_id}."
            if await _db(drop)
            else f"No history record with id {history_id}; nothing was deleted."
        )

    if action == "clear":
        count = await _db(lambda db: db.query(SearchHistory).delete())
        return f"Cleared {count} history record(s)."

    return _unknown_action(action, HISTORY_ACTIONS)


# ------------------------------------------------------------------
# System
# ------------------------------------------------------------------


async def _run_system_action(action_type: str, description: str, parameters: dict[str, Any]) -> str:
    """Queue an OS action through ``system_service`` and run it.

    Queue *and* approve, because the approval already happened: this handler is
    only reached after the user answered the agent's own confirmation card.
    Asking twice for one decision trains people to click through both. Going via
    ``request_action`` keeps the command whitelist, URL normalisation, app
    resolution and the System panel's audit history — none of which is
    reimplemented here.
    """

    def run() -> str:
        queued = system_service.request_action(action_type, description, parameters)
        executed = system_service.approve_action(queued.action_id)
        return f"{executed.status.value}: {executed.result}"

    try:
        # approve_action executes inline, and a whitelisted command may run for
        # up to 60 seconds of blocking subprocess.run.
        return await asyncio.to_thread(run)
    except PermissionError as exc:
        return f"Refused: {exc}"
    except ValueError as exc:
        return f"Rejected: {exc}"


async def system_control(
    action: str,
    command: str | None = None,
    app_name: str | None = None,
    url: str | None = None,
    limit: int = 50,
) -> str:
    """Inspect service health and perform the OS actions the System panel offers."""
    if action == "service_status":
        return as_json(self_healing_service.get_status())

    if action == "health_log":
        entries = self_healing_service.get_health_log(limit)
        return as_json({"count": len(entries), "log": entries}) if entries else "The self-healing log is empty."

    if action == "pending":
        pending = system_service.list_pending()
        return as_json({"count": len(pending), "pending_actions": pending}) if pending else "No actions are pending."

    if action == "run_command":
        if not command:
            return _missing(action, "command")
        return await _run_system_action("run_command", f"Run command: {command}", {"command": command})

    if action == "open_app":
        if not app_name:
            return _missing(action, "app_name")
        return await _run_system_action("open_app", f"Open application: {app_name}", {"app_name": app_name})

    if action == "open_url":
        if not url:
            return _missing(action, "url")
        return await _run_system_action("open_url", f"Open URL: {url}", {"url": url})

    return _unknown_action(action, SYSTEM_ACTIONS)


# ------------------------------------------------------------------
# Confirmation predicates and summaries
# ------------------------------------------------------------------


def _gate(destructive: frozenset[str]) -> Callable[[dict[str, Any]], bool]:
    """Confirm only the actions in ``destructive`` — reads never stop the agent."""

    def needs(arguments: dict[str, Any]) -> bool:
        return str(arguments.get("action", "")) in destructive

    return needs


def _summary(template: Callable[[dict[str, Any]], str]) -> Callable[[dict[str, Any]], str]:
    def render(arguments: dict[str, Any]) -> str:
        return truncate_result(template(arguments), SUMMARY_LIMIT)

    return render


def _watch_summary(args: dict[str, Any]) -> str:
    if args.get("action") == "stop_all":
        return "Stop every running watch"
    return f"Stop watching '{args.get('query')}'"


def _memory_summary(args: dict[str, Any]) -> str:
    if args.get("action") == "delete_category":
        return f"Delete every memory in category '{args.get('category')}'"
    return f"Delete memory #{args.get('memory_id')}"


def _history_summary(args: dict[str, Any]) -> str:
    if args.get("action") == "clear":
        return "Clear the entire search history"
    return f"Delete history record #{args.get('history_id')}"


def _system_summary(args: dict[str, Any]) -> str:
    action = args.get("action")
    if action == "run_command":
        return f"Run the shell command: {args.get('command')}"
    if action == "open_app":
        return f"Open the application: {args.get('app_name')}"
    return f"Open in the browser: {args.get('url')}"


def _plugin_summary(args: dict[str, Any]) -> str:
    return f"Toggle the plugin '{args.get('name')}' on or off"


def _profile_summary_text(args: dict[str, Any]) -> str:
    return f"Delete saved profile #{args.get('profile_id')}"


# ------------------------------------------------------------------
# Registration
# ------------------------------------------------------------------


def register_console_tools(registry: ToolRegistry) -> ToolRegistry:
    """Add the console-control tools to ``registry`` and return it."""
    registry.register(
        Tool(
            name="watch_control",
            description=(
                "Control background monitoring of a target (the Watch panel). "
                "actions: list (all running watches), status (one watch), start (begin monitoring), "
                "stop (end one watch), stop_all (end every watch)."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "action": {"type": "string", "enum": list(WATCH_ACTIONS)},
                    "query": {"type": "string", "description": "Target to monitor, e.g. a name or name/username"},
                    "interval_minutes": {
                        "type": "integer",
                        "description": "Check interval for 'start', 5-1440 minutes (default 60)",
                    },
                },
                "required": ["action"],
            },
            handler=watch_control,
            requires_confirmation=_gate(WATCH_DESTRUCTIVE),
            confirm_summary=_summary(_watch_summary),
        )
    )

    registry.register(
        Tool(
            name="memory_control",
            description=(
                "Read and write what J.A.R.V.I.S. remembers about the user (the Memory panel). "
                "actions: list, search, add, delete (one memory by id), delete_category (a whole category). "
                "Categories in use: preference, fact, interaction, personality."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "action": {"type": "string", "enum": list(MEMORY_ACTIONS)},
                    "category": {"type": "string", "description": "Memory category"},
                    "key": {"type": "string", "description": "Memory key, for 'add'"},
                    "value": {"type": "string", "description": "Memory value, for 'add'"},
                    "query": {"type": "string", "description": "Text to search for, for 'search'"},
                    "memory_id": {"type": "integer", "description": "Memory id, for 'delete'"},
                    "importance": {"type": "integer", "description": "1-10, for 'add' (default 5)"},
                },
                "required": ["action"],
            },
            handler=memory_control,
            requires_confirmation=_gate(MEMORY_DESTRUCTIVE),
            confirm_summary=_summary(_memory_summary),
        )
    )

    registry.register(
        Tool(
            name="plugin_control",
            description=(
                "List the installed OSINT plugins and enable or disable them (the Plugin panel). "
                "actions: list, toggle. Use the run_plugin tool to actually run one."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "action": {"type": "string", "enum": list(PLUGIN_ACTIONS)},
                    "name": {"type": "string", "description": "Plugin name, for 'toggle'"},
                },
                "required": ["action"],
            },
            handler=plugin_control,
            requires_confirmation=_gate(PLUGIN_DESTRUCTIVE),
            confirm_summary=_summary(_plugin_summary),
        )
    )

    registry.register(
        Tool(
            name="profile_control",
            description=(
                "Work with the saved profile dossiers. actions: list, get (one by id), search (by name), "
                "export (returns the download endpoint for pdf/json/csv), delete."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "action": {"type": "string", "enum": list(PROFILE_ACTIONS)},
                    "profile_id": {"type": "integer", "description": "Profile id, for 'get', 'export', 'delete'"},
                    "name": {"type": "string", "description": "Name to search for, for 'search'"},
                    "export_format": {"type": "string", "enum": list(EXPORT_FORMATS)},
                },
                "required": ["action"],
            },
            handler=profile_control,
            requires_confirmation=_gate(PROFILE_DESTRUCTIVE),
            confirm_summary=_summary(_profile_summary_text),
        )
    )

    registry.register(
        Tool(
            name="history_control",
            description="Read and prune the search history (the Logs panel). actions: list, delete, clear.",
            parameters={
                "type": "object",
                "properties": {
                    "action": {"type": "string", "enum": list(HISTORY_ACTIONS)},
                    "history_id": {"type": "integer", "description": "History record id, for 'delete'"},
                },
                "required": ["action"],
            },
            handler=history_control,
            requires_confirmation=_gate(HISTORY_DESTRUCTIVE),
            confirm_summary=_summary(_history_summary),
        )
    )

    registry.register(
        Tool(
            name="system_control",
            description=(
                "Inspect service health and control this machine (the System panel). "
                "actions: service_status, health_log, pending, run_command (whitelisted executables only), "
                "open_app (an installed application), open_url (http/https only). "
                "The three control actions need the user's approval and are refused entirely "
                "unless computer control is enabled in the configuration."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "action": {"type": "string", "enum": list(SYSTEM_ACTIONS)},
                    "command": {"type": "string", "description": "Shell command, for 'run_command'"},
                    "app_name": {"type": "string", "description": "Application name, for 'open_app'"},
                    "url": {"type": "string", "description": "http/https URL, for 'open_url'"},
                    "limit": {"type": "integer", "description": "Row limit for 'health_log' (default 50)"},
                },
                "required": ["action"],
            },
            handler=system_control,
            requires_confirmation=_gate(SYSTEM_DESTRUCTIVE),
            confirm_summary=_summary(_system_summary),
        )
    )

    return registry
