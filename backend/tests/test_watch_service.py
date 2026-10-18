"""Watch mode: does starting a watch actually re-scan the target?

These cover the contract the WatchPanel depends on — the route has to start an
engine that really runs, the status payload has to use the field names the
frontend reads, and a stopped watch has to leave the list.
"""

import asyncio

import pytest

from app.services.watch_service import WatchService, watch_service


class FakeResult:
    """Stand-in for ``DiscoveryResult`` — the loop only reads ``.profiles``."""

    def __init__(self, profiles):
        self.profiles = profiles


class FakeRunner:
    """Records every call and returns each queued round of profiles in turn."""

    def __init__(self, rounds):
        self.rounds = list(rounds)
        self.calls: list[str] = []
        self.scanned = asyncio.Event()

    async def run(self, *, session_id, raw_query, depth, interactive):
        assert interactive is False, "a timer-driven watch must never ask a question"
        self.calls.append(raw_query)
        profiles = self.rounds[min(len(self.calls) - 1, len(self.rounds) - 1)]
        self.scanned.set()
        return FakeResult(profiles)


def account(platform, username, **extra):
    return {
        "platform": platform,
        "username": username,
        "url": f"https://{platform}.com/{username}",
        "status": "found",
        "confidence": 90,
        **extra,
    }


@pytest.fixture(autouse=True)
def clean_watches():
    """The service is a module-level singleton; don't leak targets between tests."""
    watch_service.stop_all()
    watch_service._targets.clear()
    yield
    watch_service.stop_all()
    watch_service._targets.clear()


@pytest.mark.asyncio
async def test_watch_scans_immediately_instead_of_idling():
    """The bug: the started watch never scanned, so it sat at 0 changes forever."""
    runner = FakeRunner([[account("github", "alice")]])
    service = WatchService()

    service.start_discovery_watch("alice", interval_minutes=60, runner=runner)
    await asyncio.wait_for(runner.scanned.wait(), timeout=2)

    target = service._targets["alice"]
    assert runner.calls == ["alice"], "watch must re-scan without waiting a full interval"
    assert target.last_check is not None, "a completed scan must stamp last_check"


@pytest.mark.asyncio
async def test_watch_detects_a_new_account_between_scans():
    runner = FakeRunner([[account("github", "alice")]])
    service = WatchService()
    target = service._targets["alice"] = _target(service, "alice")

    await service._run_once(target, runner)  # baseline
    assert target.changes_detected == 0, "the first scan has nothing to compare against"

    runner.rounds.append([account("github", "alice"), account("x", "alice")])
    alerts = await service._run_once(target, runner)

    assert len(alerts) == 1
    assert alerts[0]["platform"] == "x"
    assert target.changes_detected == 1


@pytest.mark.asyncio
async def test_a_failed_scan_does_not_poison_the_baseline():
    class Boom(FakeRunner):
        async def run(self, **kwargs):
            raise RuntimeError("network down")

    service = WatchService()
    target = service._targets["alice"] = _target(service, "alice")
    await service._run_once(target, FakeRunner([[account("github", "alice")]]))
    baseline = dict(target.last_profile_snapshot)

    assert await service._run_once(target, Boom([])) == []
    assert target.last_profile_snapshot == baseline, "a failed scan must not clear the baseline"


def _target(service, query):
    from app.services.watch_service import WatchTarget

    return WatchTarget(query, interval_minutes=60)


@pytest.fixture
def offline_scan(monkeypatch):
    """Keep the route tests off the network: the started watch scans a stub."""

    async def _stub(query, runner=None, *, depth=5):
        return FakeResult([account("github", query)])

    monkeypatch.setattr(WatchService, "rescan", staticmethod(_stub))


def test_status_payload_uses_the_field_names_the_frontend_reads(client, offline_scan):
    """WatchPanel reads `last_checked` / `last_diff`; the API used to send `last_check`."""
    started = client.post("/api/watch/start", json={"query": "alice", "interval_minutes": 60})
    assert started.status_code == 200
    assert started.json()["status"] == "watching"

    listed = client.get("/api/watch/").json()
    assert listed["count"] == 1
    row = listed["watches"][0]
    assert set(row) >= {"query", "interval_minutes", "is_active", "last_checked", "changes_detected", "last_diff"}
    assert "last_check" not in row


def test_stopping_a_watch_removes_it_from_the_list(client, offline_scan):
    client.post("/api/watch/start", json={"query": "alice", "interval_minutes": 60})
    stopped = client.post("/api/watch/stop", json={"query": "alice"})

    assert stopped.status_code == 200
    assert stopped.json()["status"] == "stopped"
    assert client.get("/api/watch/").json()["count"] == 0
