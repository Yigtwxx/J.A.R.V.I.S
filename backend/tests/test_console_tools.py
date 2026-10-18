"""The console tools are the panels, driven by the agent instead of by hand.

The thing worth pinning is not that the happy path works — it is that every
other path *says something*. A tool that returns an empty string for a missing
argument, an unknown action or a target that was not there is indistinguishable
from one that worked, and the model will narrate the silence as success.
"""

import asyncio

import pytest
from sqlalchemy.orm import sessionmaker

from app.agents.tools import console_tools
from app.agents.tools.console_tools import (
    history_control,
    memory_control,
    plugin_control,
    profile_control,
    system_control,
    watch_control,
)
from app.models.discovery import SearchSession
from app.models.profile import Profile


def run(coro):
    return asyncio.run(coro)


@pytest.fixture
def console_db(db_engine, monkeypatch):
    """Point the tools' own session factory at the in-memory test database.

    The tools run outside any request, so they open their own sessions rather
    than borrowing the ``get_db`` dependency the routes use.
    """
    monkeypatch.setattr(console_tools, "SessionLocal", sessionmaker(bind=db_engine))
    return db_engine


class FakeWatchService:
    """Enough of ``watch_service`` to prove the tool calls the right method."""

    def __init__(self):
        self.started: list[tuple[str, int]] = []
        self.stopped: list[str] = []
        self.watches: list[dict] = []
        self.stop_all_calls = 0

    @property
    def active_watches(self):
        return self.watches

    def get_watch_status(self, query):
        return next((w for w in self.watches if w["query"] == query), None)

    def start_discovery_watch(self, query, interval_minutes):
        self.started.append((query, interval_minutes))
        self.watches.append({"query": query, "interval_minutes": interval_minutes})
        return {"status": "watching", "query": query, "interval_minutes": interval_minutes}

    def stop_watch(self, query):
        if not any(w["query"] == query for w in self.watches):
            return {"status": "not_found", "query": query}
        self.stopped.append(query)
        self.watches = [w for w in self.watches if w["query"] != query]
        return {"status": "stopped", "query": query, "total_changes": 0}

    def stop_all(self):
        self.stop_all_calls += 1
        count = len(self.watches)
        self.watches = []
        return count


@pytest.fixture
def fake_watch(monkeypatch):
    fake = FakeWatchService()
    monkeypatch.setattr(console_tools, "watch_service", fake)
    return fake


# ---------------------------------------------------------------------------
# Watch
# ---------------------------------------------------------------------------


def test_watch_list_says_so_when_nothing_is_running(fake_watch):
    assert run(watch_control(action="list")) == "No watches are running."


def test_watch_start_reaches_the_service(fake_watch):
    result = run(watch_control(action="start", query="Ada Lovelace", interval_minutes=30))

    assert fake_watch.started == [("Ada Lovelace", 30)], "the tool must actually start the watch, not just report it"
    assert "watching" in result


def test_watch_start_refuses_an_interval_the_route_would_reject(fake_watch):
    result = run(watch_control(action="start", query="Ada", interval_minutes=1))

    assert "between 5 and 1440" in result
    assert fake_watch.started == [], "an out-of-range interval must not start a watch that rescans every minute"


def test_watch_stop_distinguishes_a_missing_target_from_a_stopped_one(fake_watch):
    result = run(watch_control(action="stop", query="nobody"))

    assert "No watch was running" in result
    assert fake_watch.stopped == []


def test_watch_stop_all_reports_the_count(fake_watch):
    run(watch_control(action="start", query="a", interval_minutes=60))
    run(watch_control(action="start", query="b", interval_minutes=60))

    assert run(watch_control(action="stop_all")) == "Stopped 2 watch(es)."


def test_watch_rejects_an_unknown_action_by_name(fake_watch):
    result = run(watch_control(action="obliterate"))

    assert "unknown action 'obliterate'" in result
    assert "stop_all" in result, "the refusal has to list what the model may use instead"


def test_watch_names_the_argument_it_is_missing(fake_watch):
    assert "requires the 'query'" in run(watch_control(action="stop"))


# ---------------------------------------------------------------------------
# Memory
# ---------------------------------------------------------------------------


def test_memory_add_then_list_round_trips(console_db):
    added = run(memory_control(action="add", category="preference", key="editor", value="neovim"))
    assert "Stored memory" in added

    listed = run(memory_control(action="list"))
    assert "neovim" in listed


def test_memory_delete_of_a_missing_row_does_not_claim_success(console_db):
    result = run(memory_control(action="delete", memory_id=4242))

    assert "nothing was deleted" in result


def test_memory_add_refuses_an_out_of_range_importance(console_db):
    result = run(memory_control(action="add", category="fact", key="k", value="v", importance=99))

    assert "between 1 and 10" in result
    assert "No memories stored" in run(memory_control(action="list"))


def test_memory_search_reports_a_miss(console_db):
    assert "No memory matches" in run(memory_control(action="search", query="nothing here"))


# ---------------------------------------------------------------------------
# Plugins
# ---------------------------------------------------------------------------


def test_plugin_toggle_of_an_unknown_plugin_lists_the_real_ones(monkeypatch):
    class FakeManager:
        def list_plugins(self):
            return [{"name": "shodan", "enabled": True}]

        def toggle(self, name):
            raise KeyError(name)

    monkeypatch.setattr(console_tools, "plugin_manager", FakeManager())

    result = run(plugin_control(action="toggle", name="nope"))

    assert "is not installed" in result
    assert "shodan" in result


# ---------------------------------------------------------------------------
# Profiles and history
# ---------------------------------------------------------------------------


def test_profile_delete_removes_the_row(console_db):
    Session = sessionmaker(bind=console_db)
    session = Session()
    session.add(Profile(name="Grace Hopper"))
    session.commit()
    profile_id = session.query(Profile).one().id
    session.close()

    result = run(profile_control(action="delete", profile_id=profile_id))

    assert f"Deleted profile #{profile_id}" in result
    assert run(profile_control(action="list")) == "No profiles are saved."


def test_profile_export_hands_back_an_endpoint_not_bytes(console_db):
    Session = sessionmaker(bind=console_db)
    session = Session()
    session.add(Profile(name="Grace Hopper"))
    session.commit()
    profile_id = session.query(Profile).one().id
    session.close()

    result = run(profile_control(action="export", profile_id=profile_id, export_format="csv"))

    assert f"/api/export/csv/{profile_id}" in result


def test_profile_export_rejects_an_invented_format(console_db):
    assert "unknown export_format" in run(profile_control(action="export", profile_id=1, export_format="docx"))


def test_history_clear_reports_zero_rather_than_nothing(console_db):
    assert run(history_control(action="clear")) == "Cleared 0 conversation(s)."


def _seed_conversation(console_db) -> None:
    Session = sessionmaker(bind=console_db)
    session = Session()
    session.add(
        SearchSession(
            id="s1",
            target_key="ada-lovelace:person",
            raw_query="ada lovelace",
            status="completed",
        )
    )
    session.commit()
    session.close()


def test_history_lists_the_same_conversations_the_panel_shows(console_db):
    _seed_conversation(console_db)

    listed = run(history_control(action="list"))

    assert "ada lovelace" in listed
    assert "s1" in listed, "the agent needs the session id it must pass back to delete"


def test_history_delete_takes_a_session_id(console_db):
    _seed_conversation(console_db)

    assert "Deleted conversation s1" in run(history_control(action="delete", session_id="s1"))
    assert run(history_control(action="list")) == "The search history is empty."


# ---------------------------------------------------------------------------
# System
# ---------------------------------------------------------------------------


@pytest.fixture
def computer_control(monkeypatch):
    """Set the OS-control flag explicitly.

    The suite does not isolate ``ENABLE_COMPUTER_CONTROL`` from the developer's
    ``.env``, so a test that reads it decides its own outcome from whatever the
    machine happens to be configured for — and, when it is on, actually runs the
    command.
    """

    def _set(enabled: bool) -> None:
        monkeypatch.setattr(type(console_tools.system_service), "is_enabled", property(lambda _self: enabled))

    return _set


def test_system_control_refuses_when_computer_control_is_disabled(computer_control):
    """Disabled is an answer, not an empty result — the refusal names the flag."""
    computer_control(False)

    result = run(system_control(action="run_command", command="whoami"))

    assert result.startswith("Refused:")
    assert "ENABLE_COMPUTER_CONTROL" in result


def test_system_control_keeps_the_command_whitelist(computer_control):
    """Approval is not a bypass: the agent's route is the panel's route."""
    computer_control(True)

    result = run(system_control(action="run_command", command="format C:"))

    assert result.startswith("Rejected:")
    assert "whitelist" in result


def test_system_control_still_reports_read_only_state_when_disabled(computer_control):
    computer_control(False)

    assert "pending" in run(system_control(action="pending")).lower()
