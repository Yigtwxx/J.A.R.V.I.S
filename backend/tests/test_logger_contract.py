"""Every ``logger.<name>`` the app writes must exist on ``JarvisLogger``.

A missing logger method is invisible until the line runs. ``DiscoveryRunner.run``
called ``logger.log_info`` on the brief-seeding path — a method that never
existed — so every search where the user supplied a known profile died with
``AttributeError`` before round 0, and the session manager reported the whole
discovery task as crashed. Nothing in the suite touched that line, so 1012 green
tests said the pipeline was fine.

``JarvisLogger`` has a deliberately small, semantic vocabulary (action, success,
error, thought, warning, step, scan, detail, phase). This test is the compiler
the vocabulary otherwise lacks: it resolves every call site statically, so a
typo or an invented verb fails here instead of in production.
"""

from __future__ import annotations

import ast
from pathlib import Path

from app.utils.logger import JarvisLogger, logger

APP_ROOT = Path(__file__).resolve().parents[1] / "app"


def collect_logger_attributes() -> dict[str, list[str]]:
    """Map each ``logger.<name>`` used under ``app/`` to the sites that use it.

    Inside ``app/`` the bare name ``logger`` is always the ``JarvisLogger``
    singleton — every module gets it via ``from app.utils.logger import logger``,
    and the one module that binds the stdlib logger names it ``file_logger``.
    """
    found: dict[str, list[str]] = {}

    for path in sorted(APP_ROOT.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Attribute) or not isinstance(node.value, ast.Name):
                continue
            if node.value.id != "logger":
                continue
            site = f"{path.relative_to(APP_ROOT.parent).as_posix()}:{node.lineno}"
            found.setdefault(node.attr, []).append(site)

    return found


def test_the_app_never_calls_a_logger_method_that_does_not_exist() -> None:
    available = set(dir(logger)) | set(vars(JarvisLogger))
    used = collect_logger_attributes()

    assert used, f"no logger call sites found under {APP_ROOT} — the AST walk is broken, not the code"

    missing = {name: sites for name, sites in used.items() if name not in available}

    assert not missing, "logger attributes that do not exist on JarvisLogger:\n" + "\n".join(
        f"  logger.{name} -> {', '.join(sites)}" for name, sites in sorted(missing.items())
    )
