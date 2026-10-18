"""The spatial console's one backend endpoint.

Two things matter more than the happy path.

**A model outage must not read as a description.** `/api/vision/*` used to catch
a load failure and hand the exception text back in a 200 body, so a dead model
answered with prose that looked like an answer. This route inherits the split
that fixed it — 503 for "I could not look", 502 for "there was nothing to look
at" — and these tests hold it there.

**The browser's content type is not evidence.** The frame is sniffed, the same
way the reference-avatar upload sniffs, because a page served as `image/jpeg` is
exactly how junk would otherwise reach the model.
"""

import io
import time

import pytest
from starlette.websockets import WebSocketDisconnect

from app.routes import spatial as spatial_route
from app.services.vision_service import VisionImageError, VisionUnavailableError
from app.services.window_control import DesktopBounds, Outcome, WindowInfo

JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 64
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64
WEBP = b"RIFF" + b"\x00\x00\x00\x00" + b"WEBP" + b"\x00" * 64


def _frame(data: bytes, name: str = "frame.jpg", content_type: str = "image/jpeg"):
    return {"file": (name, io.BytesIO(data), content_type)}


@pytest.fixture
def described(monkeypatch):
    """Stub the vision model with something that records what it was asked."""
    calls: list[tuple[bytes, str, str | None]] = []

    async def fake(data: bytes, prompt: str = "", *, keep_alive: str | None = None) -> str:
        calls.append((data, prompt, keep_alive))
        return "You are at a desk; there is a grey couch and a bookshelf behind you."

    monkeypatch.setattr(spatial_route.vision_service, "analyze_image_bytes", fake)
    return calls


class TestDescribeScene:
    def test_describes_a_frame_with_the_local_model(self, client, described):
        response = client.post("/api/spatial/scene", files=_frame(JPEG))

        assert response.status_code == 200, response.text
        body = response.json()
        assert "couch" in body["description"], "the model's answer must reach the caller unchanged"
        assert body["model"] == spatial_route._SETTINGS.vision_model
        assert body["elapsed_ms"] >= 0

    def test_asks_the_model_to_describe_only_what_it_can_see(self, client, described):
        client.post("/api/spatial/scene", files=_frame(JPEG))

        _, prompt, _keep_alive = described[0]
        assert "do not speculate" in prompt.lower(), "the prompt must not invite guesses about who the person is"

    @pytest.mark.parametrize("data", [JPEG, PNG, WEBP], ids=["jpeg", "png", "webp"])
    def test_accepts_the_three_formats_a_camera_frame_arrives_in(self, client, described, data):
        assert client.post("/api/spatial/scene", files=_frame(data)).status_code == 200

    def test_rejects_a_file_that_is_not_an_image_whatever_it_claims_to_be(self, client, described):
        response = client.post("/api/spatial/scene", files=_frame(b"<html>not a frame</html>"))

        assert response.status_code == 415, response.text
        assert not described, "nothing should have reached the model"

    def test_rejects_an_empty_frame(self, client, described):
        assert client.post("/api/spatial/scene", files=_frame(b"")).status_code == 400

    def test_rejects_a_frame_over_the_size_ceiling(self, client, described):
        oversized = JPEG + b"\x00" * spatial_route.MAX_FRAME_BYTES
        response = client.post("/api/spatial/scene", files=_frame(oversized))

        assert response.status_code == 413, response.text
        assert not described

    def test_reports_a_model_outage_as_503_rather_than_a_description(self, client, monkeypatch):
        async def unavailable(data: bytes, prompt: str = "", *, keep_alive: str | None = None) -> str:
            raise VisionUnavailableError("Vision model 'qwen2.5vl:7b' could not answer: connection refused")

        monkeypatch.setattr(spatial_route.vision_service, "analyze_image_bytes", unavailable)
        response = client.post("/api/spatial/scene", files=_frame(JPEG))

        assert response.status_code == 503, response.text
        assert "could not answer" in response.json()["detail"]

    def test_reports_an_unreadable_frame_as_502(self, client, monkeypatch):
        async def bad_image(data: bytes, prompt: str = "", *, keep_alive: str | None = None) -> str:
            raise VisionImageError("that frame could not be decoded")

        monkeypatch.setattr(spatial_route.vision_service, "analyze_image_bytes", bad_image)

        assert client.post("/api/spatial/scene", files=_frame(JPEG)).status_code == 502

    def test_says_so_when_the_console_is_switched_off(self, client, described, monkeypatch):
        monkeypatch.setattr(spatial_route._SETTINGS, "spatial_enabled", False)
        response = client.post("/api/spatial/scene", files=_frame(JPEG))

        assert response.status_code == 503, response.text
        assert "SPATIAL_ENABLED" in response.json()["detail"], "the message has to name the flag that turns it back on"
        assert not described

    def test_releases_the_model_the_moment_it_has_answered(self, client, described):
        """Ollama's default is to hold the model for five more minutes.

        Measured on the reporting machine: 6958 MiB of an 8188 MiB card with this
        model alone resident, already spilling 13% of itself to CPU, while the
        console holds a live camera and a hand tracker on the same GPU. Those
        five minutes are five minutes of a stalled desktop — the browser's own
        compositor included — bought for a sentence that has already been read.
        """
        client.post("/api/spatial/scene", files=_frame(JPEG))

        _, _prompt, keep_alive = described[0]
        assert keep_alive == "0", "the scene model must not be left resident on the card"

    def test_prefers_the_dedicated_scene_model_when_one_is_configured(self, client, described, monkeypatch):
        monkeypatch.setattr(spatial_route._SETTINGS, "spatial_scene_model", "some-other-vl:7b")

        assert client.post("/api/spatial/scene", files=_frame(JPEG)).json()["model"] == "some-other-vl:7b"

    def test_requires_the_api_key(self, unauthenticated_client, described):
        response = unauthenticated_client.post("/api/spatial/scene", files=_frame(JPEG))

        assert response.status_code == 401, response.text
        assert not described


class FakeController:
    """A window controller with no operating system behind it."""

    platform = "fake"

    def __init__(self, *, supported=True, reason=None, outcomes=None):
        self._supported = supported
        self._reason = reason
        self.outcomes = outcomes or {}
        self.moves: list[tuple[str, int, int, int, int]] = []
        self.focused: list[str] = []

    def is_supported(self):
        return self._supported

    def unsupported_reason(self):
        return self._reason

    def desktop_bounds(self):
        return DesktopBounds(x=0, y=0, width=1920, height=1200)

    def list_windows(self):
        return [
            WindowInfo(
                id="4242",
                key="chrome.exe",
                title="J.A.R.V.I.S - Google Chrome",
                app="chrome.exe",
                x=100,
                y=200,
                width=800,
                height=600,
                minimized=False,
            )
        ]

    def move(self, window_id, x, y, width, height):
        self.moves.append((window_id, x, y, width, height))
        return self.outcomes.get(window_id, Outcome.OK)

    def focus(self, window_id):
        self.focused.append(window_id)
        return self.outcomes.get(window_id, Outcome.OK)


@pytest.fixture
def window_control(monkeypatch):
    """Switch window control on and put a fake operating system behind it."""
    monkeypatch.setattr(spatial_route._SETTINGS, "spatial_window_control", True)
    controller = FakeController()
    monkeypatch.setattr(spatial_route, "get_window_controller", lambda: controller)
    spatial_route._tickets.clear()
    return controller


class TestListWindows:
    def test_lists_what_is_open(self, client, window_control):
        response = client.get("/api/spatial/windows")

        assert response.status_code == 200, response.text
        body = response.json()
        assert body["supported"] is True
        assert body["desktop"] == {"x": 0, "y": 0, "width": 1920, "height": 1200}
        assert body["windows"][0]["key"] == "chrome.exe"

    def test_says_why_rather_than_answering_an_empty_list(self, client, monkeypatch):
        # An empty list is indistinguishable from a machine with nothing open,
        # and the console would show an empty room with nothing to say about it.
        monkeypatch.setattr(spatial_route._SETTINGS, "spatial_window_control", True)
        controller = FakeController(supported=False, reason="Grant Accessibility permission.")
        monkeypatch.setattr(spatial_route, "get_window_controller", lambda: controller)

        body = client.get("/api/spatial/windows").json()
        assert body["supported"] is False
        assert body["windows"] == []
        assert "Accessibility" in body["reason"]

    def test_refuses_while_the_flag_is_off(self, client, monkeypatch):
        # Set explicitly, never inherited: conftest does not isolate this one
        # from backend/.env, so a developer with window control switched on
        # would otherwise watch this test decide its own outcome.
        monkeypatch.setattr(spatial_route._SETTINGS, "spatial_window_control", False)
        response = client.get("/api/spatial/windows")

        assert response.status_code == 403, response.text
        assert "SPATIAL_WINDOW_CONTROL" in response.json()["detail"], (
            "the message has to name the flag that turns it on"
        )

    def test_requires_the_api_key(self, unauthenticated_client, window_control):
        assert unauthenticated_client.get("/api/spatial/windows").status_code == 401


class TestFocusWindow:
    def test_brings_a_window_forward(self, client, window_control):
        response = client.post("/api/spatial/windows/4242/focus")

        assert response.status_code == 200, response.text
        assert response.json() == {"id": "4242", "outcome": "ok"}
        assert window_control.focused == ["4242"]

    def test_reports_a_refusal_rather_than_claiming_success(self, client, window_control):
        window_control.outcomes["4242"] = Outcome.BLOCKED

        assert client.post("/api/spatial/windows/4242/focus").json()["outcome"] == "blocked"

    def test_reports_a_window_that_closed_as_gone(self, client, window_control):
        window_control.outcomes["4242"] = Outcome.GONE

        assert client.post("/api/spatial/windows/4242/focus").json()["outcome"] == "gone"


class TestTicket:
    def test_issues_a_ticket_with_a_lifetime(self, client, window_control):
        body = client.post("/api/spatial/ticket").json()

        assert len(body["ticket"]) >= 32, "a socket credential has to be unguessable"
        assert body["expires_in"] == spatial_route.TICKET_TTL_SECONDS

    def test_issues_a_different_ticket_every_time(self, client, window_control):
        first = client.post("/api/spatial/ticket").json()["ticket"]
        second = client.post("/api/spatial/ticket").json()["ticket"]

        assert first != second

    def test_refuses_while_the_flag_is_off(self, client, monkeypatch):
        monkeypatch.setattr(spatial_route._SETTINGS, "spatial_window_control", False)
        assert client.post("/api/spatial/ticket").status_code == 403

    def test_requires_the_api_key(self, unauthenticated_client, window_control):
        assert unauthenticated_client.post("/api/spatial/ticket").status_code == 401

    def test_spends_a_ticket_exactly_once(self, client, window_control):
        ticket = client.post("/api/spatial/ticket").json()["ticket"]

        assert spatial_route._spend_ticket(ticket) is True
        assert spatial_route._spend_ticket(ticket) is False, "a replayed ticket is not a credential"

    def test_refuses_a_ticket_that_has_expired(self, client, window_control, monkeypatch):
        ticket = client.post("/api/spatial/ticket").json()["ticket"]
        later = time.monotonic() + spatial_route.TICKET_TTL_SECONDS + 1
        monkeypatch.setattr(spatial_route.time, "monotonic", lambda: later)

        assert spatial_route._spend_ticket(ticket) is False

    def test_refuses_a_ticket_nobody_issued(self, client, window_control):
        assert spatial_route._spend_ticket("made-up") is False
        assert spatial_route._spend_ticket(None) is False

    def test_forgets_expired_tickets_instead_of_growing_forever(self, client, window_control, monkeypatch):
        client.post("/api/spatial/ticket")
        later = time.monotonic() + spatial_route.TICKET_TTL_SECONDS + 1
        monkeypatch.setattr(spatial_route.time, "monotonic", lambda: later)

        client.post("/api/spatial/ticket")
        assert len(spatial_route._tickets) == 1


class TestWindowSocket:
    def test_moves_a_batch_and_reports_each_window(self, client, window_control):
        window_control.outcomes["9"] = Outcome.BLOCKED
        ticket = client.post("/api/spatial/ticket").json()["ticket"]

        with client.websocket_connect(f"/api/spatial/ws?ticket={ticket}") as socket:
            socket.send_json(
                {
                    "op": "move",
                    "items": [
                        {"id": "4242", "x": 10, "y": 20, "w": 300, "h": 400},
                        {"id": "9", "x": 0, "y": 0, "w": 100, "h": 100},
                    ],
                }
            )
            reply = socket.receive_json()

        # An elevated window says so; it never quietly stays put while the card
        # carries on without it.
        assert reply == {"op": "moved", "results": {"4242": "ok", "9": "blocked"}}
        assert window_control.moves[0] == ("4242", 10, 20, 300, 400)

    def test_focuses_a_window(self, client, window_control):
        ticket = client.post("/api/spatial/ticket").json()["ticket"]

        with client.websocket_connect(f"/api/spatial/ws?ticket={ticket}") as socket:
            socket.send_json({"op": "focus", "id": "4242"})
            assert socket.receive_json() == {"op": "focused", "id": "4242", "outcome": "ok"}

    def test_refuses_a_connection_with_no_ticket(self, client, window_control):
        with pytest.raises(WebSocketDisconnect), client.websocket_connect("/api/spatial/ws") as socket:
            socket.receive_json()

    def test_refuses_a_replayed_ticket(self, client, window_control):
        ticket = client.post("/api/spatial/ticket").json()["ticket"]
        with client.websocket_connect(f"/api/spatial/ws?ticket={ticket}"):
            pass

        with (
            pytest.raises(WebSocketDisconnect),
            client.websocket_connect(f"/api/spatial/ws?ticket={ticket}") as socket,
        ):
            socket.receive_json()

    def test_refuses_every_connection_while_the_flag_is_off(self, client, monkeypatch):
        monkeypatch.setattr(spatial_route._SETTINGS, "spatial_window_control", False)

        with (
            pytest.raises(WebSocketDisconnect),
            client.websocket_connect("/api/spatial/ws?ticket=anything") as socket,
        ):
            socket.receive_json()

    def test_says_so_on_a_platform_it_cannot_drive(self, client, monkeypatch):
        monkeypatch.setattr(spatial_route._SETTINGS, "spatial_window_control", True)
        controller = FakeController(supported=False, reason="No adapter for freebsd.")
        monkeypatch.setattr(spatial_route, "get_window_controller", lambda: controller)
        spatial_route._tickets.clear()
        ticket = client.post("/api/spatial/ticket").json()["ticket"]

        with client.websocket_connect(f"/api/spatial/ws?ticket={ticket}") as socket:
            reply = socket.receive_json()

        assert reply["op"] == "unsupported"
        assert "freebsd" in reply["reason"]

    def test_rejects_a_batch_larger_than_the_ceiling(self, client, window_control):
        ticket = client.post("/api/spatial/ticket").json()["ticket"]
        oversized = [{"id": str(n), "x": 0, "y": 0, "w": 1, "h": 1} for n in range(spatial_route.MAX_BATCH + 1)]

        with client.websocket_connect(f"/api/spatial/ws?ticket={ticket}") as socket:
            socket.send_json({"op": "move", "items": oversized})
            reply = socket.receive_json()

        assert reply["op"] == "error"
        assert window_control.moves == [], "nothing may be moved when the batch is refused"

    def test_answers_a_message_it_does_not_understand(self, client, window_control):
        ticket = client.post("/api/spatial/ticket").json()["ticket"]

        with client.websocket_connect(f"/api/spatial/ws?ticket={ticket}") as socket:
            socket.send_json({"op": "teleport"})
            assert socket.receive_json()["op"] == "error"

    def test_skips_a_malformed_item_without_dropping_the_batch(self, client, window_control):
        ticket = client.post("/api/spatial/ticket").json()["ticket"]

        with client.websocket_connect(f"/api/spatial/ws?ticket={ticket}") as socket:
            socket.send_json({"op": "move", "items": ["nonsense", {"id": "4242", "x": 1, "y": 2, "w": 3, "h": 4}]})
            reply = socket.receive_json()

        assert reply["results"] == {"4242": "ok"}
