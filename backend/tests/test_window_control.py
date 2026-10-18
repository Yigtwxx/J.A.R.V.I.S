"""The window-control layer, and the promises it makes about failure.

The whole package exists so that a window which did not move says so. Every test
here is some version of that: an unsupported platform names a reason instead of
answering an empty list, a refused move comes back ``blocked`` rather than
``ok``, and a window that closed comes back ``gone`` rather than ``blocked`` —
because one of those is worth retrying and the other never will be.

The two live adapters cannot both be exercised here. ``WindowsController`` is
probed for real when the suite runs on Windows; ``DarwinController`` is driven
against a fake Quartz and Accessibility layer, and is marked as not
live-verified.
"""

import sys

import pytest

from app.services.window_control import (
    Outcome,
    WindowControlUnsupported,
    get_window_controller,
    stable_key,
)
from app.services.window_control.base import UnsupportedController


class TestStableKey:
    """The identity a layout is stored against.

    It is deliberately not built from the window title. That was the first
    design, and it is worse than it looks: a browser's title is its current page
    and an editor's is its current file, so keying on it loses the card's place
    in the room every time the user changes tab.
    """

    def test_is_the_same_key_however_the_title_changes(self):
        assert stable_key("chrome.exe") == stable_key("chrome.exe")

    def test_separates_two_applications(self):
        assert stable_key("chrome.exe") != stable_key("code.exe")

    def test_separates_a_second_window_of_the_same_application(self):
        assert stable_key("chrome.exe", 1) != stable_key("chrome.exe", 2)

    def test_ignores_case(self):
        assert stable_key("Chrome.exe") == stable_key("chrome.exe")

    def test_holds_no_title_material_at_all(self):
        # The key is stored in the browser's local storage, and a window title
        # can hold a document name, a URL or a customer's name.
        assert stable_key("winword.exe") == "winword.exe"

    def test_survives_an_application_name_that_is_not_a_filename(self):
        assert stable_key("Visual Studio Code") == "visual-studio-code"

    def test_never_produces_an_empty_key(self):
        assert stable_key("") == "unknown"
        assert stable_key("///") == "unknown"


class TestDispatch:
    def test_returns_a_controller_for_this_platform(self):
        controller = get_window_controller()
        assert controller.platform == sys.platform or isinstance(controller, UnsupportedController)

    def test_is_cached_because_adapters_are_stateless(self):
        assert get_window_controller() is get_window_controller()


class TestUnsupportedController:
    """The answer on a platform with no adapter."""

    @pytest.fixture
    def controller(self):
        return UnsupportedController("freebsd", "No adapter for freebsd.")

    def test_says_it_is_unsupported_and_why(self, controller):
        assert controller.is_supported() is False
        assert "freebsd" in (controller.unsupported_reason() or "")

    @pytest.mark.parametrize(
        "call",
        [
            lambda c: c.list_windows(),
            lambda c: c.desktop_bounds(),
            lambda c: c.move("1", 0, 0, 100, 100),
            lambda c: c.focus("1"),
        ],
        ids=["list", "desktop", "move", "focus"],
    )
    def test_raises_rather_than_answering_nothing(self, controller, call):
        # An empty window list is indistinguishable from a working machine with
        # nothing open, and the console would show an empty room with no reason.
        with pytest.raises(WindowControlUnsupported):
            call(controller)


@pytest.mark.skipif(sys.platform != "win32", reason="the Windows adapter needs Windows")
class TestWindowsControllerLive:
    """Probed against the real desktop, because a mocked user32 proves nothing."""

    @pytest.fixture
    def controller(self):
        from app.services.window_control.windows import WindowsController

        return WindowsController()

    def test_reports_itself_supported(self, controller):
        assert controller.is_supported() is True
        assert controller.unsupported_reason() is None

    def test_measures_the_desktop_in_the_same_units_as_the_windows(self, controller):
        # The DPI trap: without declaring awareness, GetSystemMetrics reports
        # scaled pixels while DWM reports real ones, and every window lands
        # further off the further right it goes.
        desktop = controller.desktop_bounds()
        assert desktop.width > 0 and desktop.height > 0

        windows = controller.list_windows()
        if not windows:
            pytest.skip("no top-level windows open to compare against")
        widest = max(window.width for window in windows)
        assert widest <= desktop.width * 1.5, (
            f"a window is {widest} wide on a desktop reported as {desktop.width} — "
            "the two are being measured in different coordinate spaces"
        )

    def test_lists_only_windows_a_user_would_recognise(self, controller):
        for window in controller.list_windows():
            assert window.title.strip(), "an untitled window is not one the user has open"
            assert window.width > 0 and window.height > 0
            assert window.id.isdigit(), "the id is the OS handle"
            assert window.key, "every window needs an identity a layout can be stored against"

    def test_reports_a_handle_that_is_not_a_window_as_gone(self, controller):
        assert controller.move("999999999", 0, 0, 100, 100) is Outcome.GONE
        assert controller.focus("999999999") is Outcome.GONE

    def test_reports_a_malformed_handle_as_gone_rather_than_raising(self, controller):
        assert controller.move("not-a-handle", 0, 0, 100, 100) is Outcome.GONE


class FakeAX:
    """Just enough Accessibility API to drive the macOS adapter."""

    kAXErrorSuccess = 0
    kAXErrorInvalidUIElement = -25202
    kAXErrorCannotComplete = -25204
    kAXValueCGPointType = 1
    kAXValueCGSizeType = 2
    kAXPositionAttribute = "AXPosition"
    kAXSizeAttribute = "AXSize"
    kAXWindowsAttribute = "AXWindows"
    kAXTitleAttribute = "AXTitle"
    kAXRaiseAction = "AXRaise"

    def __init__(self, *, trusted=True, windows=None, set_result=0, raise_result=0):
        self.trusted = trusted
        self.windows = windows if windows is not None else [{"AXTitle": "Notes"}]
        self.set_result = set_result
        self.raise_result = raise_result
        self.written: list[tuple[str, object]] = []
        self.raised: list[object] = []

    def AXIsProcessTrusted(self):
        return self.trusted

    def AXUIElementCreateApplication(self, pid):
        return {"pid": pid}

    def AXUIElementCopyAttributeValue(self, element, attribute, _none):
        if attribute == self.kAXWindowsAttribute:
            return self.kAXErrorSuccess, self.windows
        if attribute == self.kAXTitleAttribute:
            return self.kAXErrorSuccess, element.get("AXTitle")
        if attribute == self.kAXPositionAttribute:
            return self.kAXErrorSuccess, element.get("AXPosition")
        return self.kAXErrorCannotComplete, None

    def AXUIElementSetAttributeValue(self, element, attribute, value):
        self.written.append((attribute, value))
        return self.set_result

    def AXUIElementPerformAction(self, element, action):
        self.raised.append((element, action))
        return self.raise_result

    def AXValueCreate(self, kind, value):
        return (kind, value)

    def AXValueGetValue(self, value, _kind, _none):
        return True, value


class FakeQuartz:
    kCGWindowListOptionOnScreenOnly = 1
    kCGWindowListExcludeDesktopElements = 16
    kCGNullWindowID = 0

    def __init__(self, entries):
        self.entries = entries

    def CGWindowListCopyWindowInfo(self, _options, _relative):
        return self.entries

    @staticmethod
    def CGPoint(x, y):
        return {"x": x, "y": y}

    @staticmethod
    def CGSize(width, height):
        return {"width": width, "height": height}


ENTRY = {
    "kCGWindowLayer": 0,
    "kCGWindowNumber": 42,
    "kCGWindowOwnerPID": 501,
    "kCGWindowOwnerName": "Notes",
    "kCGWindowName": "Notes",
    "kCGWindowBounds": {"X": 100, "Y": 200, "Width": 800, "Height": 600},
}


class TestDarwinController:
    """Driven against a fake window server. Not verified on real macOS."""

    @pytest.fixture
    def adapter(self, monkeypatch):
        from app.services.window_control import darwin

        monkeypatch.setattr(darwin, "_IS_DARWIN", True)

        def install(*, entries=(ENTRY,), **ax_kwargs):
            ax = FakeAX(**ax_kwargs)
            quartz = FakeQuartz(list(entries))
            monkeypatch.setattr(darwin, "_load_ax", lambda: ax)
            monkeypatch.setattr(darwin, "_load_quartz", lambda: quartz)
            return darwin.DarwinController(), ax

        return install

    def test_lists_the_windows_quartz_reports(self, adapter):
        controller, _ax = adapter()
        [window] = controller.list_windows()

        assert window.id == "501:42"
        assert window.app == "Notes"
        assert (window.x, window.y, window.width, window.height) == (100, 200, 800, 600)

    def test_ignores_the_menu_bar_and_the_dock(self, adapter):
        chrome = {**ENTRY, "kCGWindowLayer": 25, "kCGWindowNumber": 43}
        controller, _ax = adapter(entries=(ENTRY, chrome))

        assert [window.id for window in controller.list_windows()] == ["501:42"]

    def test_ignores_surfaces_too_small_to_be_windows(self, adapter):
        shadow = {**ENTRY, "kCGWindowNumber": 44, "kCGWindowBounds": {"X": 0, "Y": 0, "Width": 8, "Height": 8}}
        controller, _ax = adapter(entries=(ENTRY, shadow))

        assert len(controller.list_windows()) == 1

    def test_moves_a_window_by_setting_its_size_and_position(self, adapter):
        controller, ax = adapter()

        assert controller.move("501:42", 10, 20, 300, 400) is Outcome.OK
        attributes = [attribute for attribute, _value in ax.written]
        # Size first: a window clamped to a minimum would otherwise be recentred
        # by the window server after the move.
        assert attributes == [FakeAX.kAXSizeAttribute, FakeAX.kAXPositionAttribute]

    def test_reports_a_refused_move_as_blocked(self, adapter):
        controller, _ax = adapter(set_result=FakeAX.kAXErrorCannotComplete)

        assert controller.move("501:42", 10, 20, 300, 400) is Outcome.BLOCKED

    def test_reports_a_window_that_went_away_as_gone(self, adapter):
        controller, _ax = adapter(set_result=FakeAX.kAXErrorInvalidUIElement)

        assert controller.move("501:42", 10, 20, 300, 400) is Outcome.GONE

    def test_reports_an_unknown_window_as_gone(self, adapter):
        controller, _ax = adapter()

        assert controller.move("501:999", 0, 0, 10, 10) is Outcome.GONE

    def test_says_what_to_do_when_accessibility_has_not_been_granted(self, adapter):
        controller, _ax = adapter(trusted=False)

        reason = controller.unsupported_reason() or ""
        assert controller.is_supported() is False
        assert "Accessibility" in reason and "System Settings" in reason, (
            "the message has to name the one place the user can fix this"
        )

    def test_refuses_to_move_anything_without_that_permission(self, adapter):
        controller, ax = adapter(trusted=False)

        with pytest.raises(WindowControlUnsupported):
            controller.move("501:42", 0, 0, 10, 10)
        assert ax.written == [], "nothing may be attempted before the permission is there"


class FakeUser32:
    """The three calls the snap check makes, and a record of what it asked."""

    def __init__(self, *, zoomed=False, iconic=False):
        self.zoomed = zoomed
        self.iconic = iconic
        self.shown: list[tuple[int, int]] = []

    def IsZoomed(self, hwnd):
        return 1 if self.zoomed else 0

    def IsIconic(self, hwnd):
        return 1 if self.iconic else 0

    def ShowWindow(self, hwnd, command):
        self.shown.append((hwnd, command))
        return 1


class TestRestoreBeforeMoving:
    """The regression that live probing caught, pinned.

    Moving a real window and asking the operating system where it ended up
    showed a maximized window reporting ``ok`` from a move that had not moved
    it: ``SetWindowPos`` returns TRUE and the window manager snaps the window
    straight back. Reporting success for a window that did not move is the one
    thing this package promises never to do.
    """

    @pytest.fixture
    def controller(self, monkeypatch):
        from app.services.window_control import windows as windows_module

        def install(**kwargs):
            fake = FakeUser32(**kwargs)
            monkeypatch.setattr(windows_module, "_user32", fake)
            return windows_module.WindowsController(), fake

        return install

    def test_restores_a_maximized_window_before_placing_it(self, controller):
        adapter, fake = controller(zoomed=True)

        from app.services.window_control.windows import SW_RESTORE

        assert adapter._restore_if_snapped(1234) is True
        assert fake.shown == [(1234, SW_RESTORE)], "a maximized window has to be restored or the move does nothing"

    def test_restores_a_minimized_window_too(self, controller):
        adapter, fake = controller(iconic=True)

        assert adapter._restore_if_snapped(1234) is True
        assert len(fake.shown) == 1

    def test_leaves_an_ordinary_window_alone(self, controller):
        adapter, fake = controller()

        # Restoring an already-restored window would flicker it on every frame
        # of a drag.
        assert adapter._restore_if_snapped(1234) is False
        assert fake.shown == []
