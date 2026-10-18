"""The file mirror is opt-in, and when it is off nothing touches the disk.

`logs/` used to be recreated on every import of `app.utils.logger`, so deleting
it accomplished nothing. These tests pin both halves of the switch: off means no
handler *and* no directory, on means a real rotating file that actually receives
a line.
"""

from __future__ import annotations

import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

import pytest

import app.utils.logger  # noqa: F401  (registers the module in sys.modules)

# `from app.utils import logger` yields the JarvisLogger *instance* that
# `app/utils/__init__.py` re-exports, not this module. Go through sys.modules.
logger_module = sys.modules["app.utils.logger"]


@pytest.fixture(autouse=True)
def _isolated_jarvis_logger(monkeypatch: pytest.MonkeyPatch):
    """Detach the process-wide "jarvis" logger so each test builds it fresh."""
    named = logging.getLogger("jarvis")
    original = list(named.handlers)
    named.handlers.clear()
    monkeypatch.delenv("JARVIS_FILE_LOGGING", raising=False)
    yield named
    for handler in named.handlers:
        handler.close()
    named.handlers.clear()
    named.handlers.extend(original)


@pytest.mark.parametrize("value", ["", "0", "false", "no", "off", "maybe"])
def test_file_logging_is_off_unless_explicitly_enabled(monkeypatch: pytest.MonkeyPatch, value: str) -> None:
    monkeypatch.setenv("JARVIS_FILE_LOGGING", value)

    assert logger_module.file_logging_enabled() is False


@pytest.mark.parametrize("value", ["1", "true", "TRUE", "yes", "on"])
def test_file_logging_is_on_for_the_truthy_spellings(monkeypatch: pytest.MonkeyPatch, value: str) -> None:
    monkeypatch.setenv("JARVIS_FILE_LOGGING", value)

    assert logger_module.file_logging_enabled() is True


def test_disabled_attaches_a_null_handler_and_creates_no_directory(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The whole point: with the switch off, `logs/` must not come back."""
    fake_module = tmp_path / "pkg" / "app" / "utils" / "logger.py"
    fake_module.parent.mkdir(parents=True)
    monkeypatch.setattr(logger_module, "__file__", str(fake_module))

    built = logger_module._build_file_logger()

    assert [type(h) for h in built.handlers] == [logging.NullHandler]
    assert not (tmp_path / "pkg" / "logs").exists()


def test_enabled_writes_through_a_rotating_file_handler(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    fake_module = tmp_path / "pkg" / "app" / "utils" / "logger.py"
    fake_module.parent.mkdir(parents=True)
    monkeypatch.setattr(logger_module, "__file__", str(fake_module))
    monkeypatch.setenv("JARVIS_FILE_LOGGING", "1")

    built = logger_module._build_file_logger()
    built.info("hello from the file channel")
    for handler in built.handlers:
        handler.flush()

    log_file = tmp_path / "pkg" / "logs" / "jarvis.log"
    assert [type(h) for h in built.handlers] == [RotatingFileHandler]
    assert "hello from the file channel" in log_file.read_text(encoding="utf-8")
