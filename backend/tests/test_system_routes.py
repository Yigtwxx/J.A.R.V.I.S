"""HTTP contract of the System panel's application endpoints.

There were no route tests for `/api/system` at all, which is how two of these
went unnoticed: `/execute/app` translated only `PermissionError`, so an unknown
application name escaped as a 500 rather than the 400 that would have told the
user what was wrong, and there was no way for the panel to learn what is
installed — the user had to guess the exact name.

`conftest.py` deliberately leaves `ENABLE_COMPUTER_CONTROL` unset, so the flag is
False under pytest and every test that needs the feature turns it on explicitly.
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
def installed(monkeypatch: pytest.MonkeyPatch) -> tuple[AppEntry, ...]:
    """Computer control on, with a fixed catalogue standing in for this machine."""
    from app.routes import system as route_module
    from app.services import system_service as service_module

    monkeypatch.setattr(service_module.settings, "enable_computer_control", True, raising=False)
    monkeypatch.setattr(service_module, "discover_apps", lambda **_kwargs: CATALOGUE)

    async def _fake_discover(*, refresh: bool = False) -> tuple[AppEntry, ...]:
        return CATALOGUE

    monkeypatch.setattr(route_module, "discover_apps_async", _fake_discover)
    return CATALOGUE


def test_apps_endpoint_lists_what_is_installed(client, installed) -> None:
    response = client.get("/api/system/apps")

    assert response.status_code == 200, response.text
    names = [app["name"] for app in response.json()["apps"]]
    assert "Spotify" in names and "Discord" in names, f"the panel must be able to see both, got {names}"


def test_apps_endpoint_filters_by_query(client, installed) -> None:
    response = client.get("/api/system/apps", params={"q": "disc"})

    assert response.status_code == 200, response.text
    assert [app["name"] for app in response.json()["apps"]] == ["Discord"]


def test_apps_endpoint_explains_an_empty_machine(client, monkeypatch: pytest.MonkeyPatch) -> None:
    """A backend with no desktop session must say so, not return a bare empty list."""
    from app.routes import system as route_module

    async def _nothing(*, refresh: bool = False) -> tuple[AppEntry, ...]:
        return ()

    monkeypatch.setattr(route_module, "discover_apps_async", _nothing)

    payload = client.get("/api/system/apps").json()

    assert payload["apps"] == []
    assert payload["detail"], "an empty result must carry a reason the user can read"


def test_apps_endpoint_requires_the_api_key(unauthenticated_client) -> None:
    assert unauthenticated_client.get("/api/system/apps").status_code == 401


def test_open_app_queues_the_resolved_application(client, installed) -> None:
    response = client.post("/api/system/execute/app", json={"app_name": "spotify"})

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "pending_approval", body
    assert "Spotify" in body["description"], f"the approval card must name the resolved app, got {body}"


def test_open_app_rejects_an_unknown_application_with_400(client, installed) -> None:
    """The bug this pins: it used to escape the route as a 500."""
    response = client.post("/api/system/execute/app", json={"app_name": "photoshop"})

    assert response.status_code == 400, response.text
    assert "photoshop" in response.json()["detail"]


def test_open_app_rejects_an_ambiguous_name_with_the_candidates(client, installed) -> None:
    response = client.post("/api/system/execute/app", json={"app_name": "visual studio"})

    assert response.status_code == 400, response.text
    detail = response.json()["detail"]
    assert "Visual Studio Code" in detail and "Visual Studio 2022" in detail, (
        f"the user must be shown what to pick between, got {detail!r}"
    )


def test_open_app_is_refused_when_computer_control_is_off(client, monkeypatch: pytest.MonkeyPatch) -> None:
    from app.services import system_service as service_module

    monkeypatch.setattr(service_module.settings, "enable_computer_control", False, raising=False)

    response = client.post("/api/system/execute/app", json={"app_name": "spotify"})

    assert response.status_code == 403, response.text
