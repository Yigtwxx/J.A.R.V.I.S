"""Queueing and running an "open this application" action.

Three behaviours are pinned here, each replacing something that was wrong:

1. **The application is resolved when the action is queued, not when it runs.**
   URLs already worked this way (`normalize_url` is applied in `request_action`
   so the approval card shows exactly what will happen). Applications did not, so
   a name that could never launch was discovered only *after* the user had
   approved it.
2. **A failure to launch is a failure.** `_exec_open_app` used to return strings
   like "Application not found" instead of raising, and `_execute` dutifully
   marked the action EXECUTED and logged a success. The history said the
   application had opened when nothing had.
3. **An ambiguous name is never guessed at.** Opening the wrong desktop
   application is worse than asking.
"""

from __future__ import annotations

import pytest

from app.services.app_launcher.models import AppEntry


def _entry(name: str, *, kind: str = "shortcut") -> AppEntry:
    return AppEntry.build(name=name, kind=kind, target=f"C:/fake/{name}.lnk", source="test")


CATALOGUE: tuple[AppEntry, ...] = (
    _entry("Spotify", kind="packaged"),
    _entry("Discord"),
    _entry("Visual Studio Code"),
    _entry("Visual Studio 2022"),
)


@pytest.fixture
def service(monkeypatch: pytest.MonkeyPatch):
    """A control service with computer control on and a fixed application list."""
    from app.services import system_service as module

    monkeypatch.setattr(module.settings, "enable_computer_control", True, raising=False)
    monkeypatch.setattr(module, "discover_apps", lambda **_kwargs: CATALOGUE)
    return module.SystemService()


def test_request_action_resolves_the_application_before_asking_for_approval(service) -> None:
    action = service.request_action("open_app", "Open app: spotify", {"app_name": "spotify"})

    assert action.parameters["app_name"] == "Spotify", (
        f"the queued action must name the resolved application, got {action.parameters['app_name']!r}"
    )
    assert "Spotify" in action.description, f"the approval card must show what will open, got {action.description!r}"


def test_request_action_rejects_an_application_that_is_not_installed(service) -> None:
    with pytest.raises(ValueError, match="not installed|No application"):
        service.request_action("open_app", "Open app: photoshop", {"app_name": "photoshop"})


def test_request_action_rejects_an_ambiguous_name_and_names_the_candidates(service) -> None:
    with pytest.raises(ValueError) as excinfo:
        service.request_action("open_app", "Open app: visual studio", {"app_name": "visual studio"})

    message = str(excinfo.value)
    assert "Visual Studio Code" in message and "Visual Studio 2022" in message, (
        f"the user must be told which applications matched, got {message!r}"
    )


def test_request_action_rejects_an_empty_application_name(service) -> None:
    with pytest.raises(ValueError):
        service.request_action("open_app", "Open app: ", {"app_name": "   "})


def test_a_launch_failure_marks_the_action_failed(service, monkeypatch: pytest.MonkeyPatch) -> None:
    """The bug this pins: a failed launch used to be recorded as a success."""
    from app.services import system_service as module
    from app.services.app_launcher.models import AppLaunchError

    def _explode(_entry: AppEntry) -> None:
        raise AppLaunchError("the shell refused")

    monkeypatch.setattr(module, "launch_app", _explode)
    action = service.request_action("open_app", "Open app: discord", {"app_name": "discord"})

    service.approve_action(action.action_id)

    assert action.status.value == "failed", (
        f"a launch that raised must not be recorded as executed, got {action.status}"
    )
    assert "refused" in (action.result or ""), f"the reason must survive into the history, got {action.result!r}"


def test_a_successful_launch_reports_the_application_name(service, monkeypatch: pytest.MonkeyPatch) -> None:
    from app.services import system_service as module

    launched: list[AppEntry] = []
    monkeypatch.setattr(module, "launch_app", launched.append)
    action = service.request_action("open_app", "Open app: discord", {"app_name": "discord"})

    service.approve_action(action.action_id)

    assert [entry.name for entry in launched] == ["Discord"], f"exactly Discord must be launched, got {launched}"
    assert "Discord" in (action.result or ""), f"the result must name what was opened, got {action.result!r}"
    assert action.status.value == "executed"


def test_an_application_uninstalled_between_approval_and_execution_fails_cleanly(
    service, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Re-resolved at execution, exactly as URLs are re-normalised there."""
    from app.services import system_service as module

    action = service.request_action("open_app", "Open app: discord", {"app_name": "discord"})
    monkeypatch.setattr(module, "discover_apps", lambda **_kwargs: ())

    service.approve_action(action.action_id)

    assert action.status.value == "failed", "an application that vanished must not report success"
