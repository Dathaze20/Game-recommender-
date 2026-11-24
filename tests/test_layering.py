"""Guards the layering rule the test suite and CI depend on.

Everything under ``gamerec/`` except ``gamerec/ui/`` must be importable without
Kivy. If that ever stops being true, CI would need a graphical environment and
the logic below would stop being unit-testable — so it is asserted here rather
than left as a convention.
"""

from __future__ import annotations

import ast
import importlib
from pathlib import Path

import pytest

PACKAGE_ROOT = Path(__file__).resolve().parents[1] / "gamerec"

CORE_MODULES = [
    "gamerec",
    "gamerec.api",
    "gamerec.config",
    "gamerec.constants",
    "gamerec.errors",
    "gamerec.models",
    "gamerec.recommendations",
    "gamerec.storage",
    "gamerec.utils",
]


def core_source_files() -> list[Path]:
    """Every ``.py`` file outside the UI package."""
    return [
        path
        for path in PACKAGE_ROOT.rglob("*.py")
        if "ui" not in path.relative_to(PACKAGE_ROOT).parts
    ]


def imported_roots(path: Path) -> set[str]:
    """Top-level package names imported by ``path``."""
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    roots: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                roots.add(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            roots.add(node.module.split(".")[0])
    return roots


class TestCoreIsKivyFree:
    def test_no_core_module_imports_kivy(self):
        offenders = [
            str(path.relative_to(PACKAGE_ROOT))
            for path in core_source_files()
            if "kivy" in imported_roots(path)
        ]
        assert offenders == [], f"Kivy imported outside gamerec/ui: {offenders}"

    @pytest.mark.parametrize("module", CORE_MODULES)
    def test_core_modules_import_cleanly(self, module):
        assert importlib.import_module(module) is not None

    def test_core_modules_do_not_pull_kivy_in_transitively(self):
        """Run in a clean interpreter so test ordering cannot mask a leak."""
        import subprocess
        import sys

        script = (
            "import sys;"
            + "".join(f"__import__({m!r});" for m in CORE_MODULES)
            + "leaked=[n for n in sys.modules if n=='kivy' or n.startswith('kivy.')];"
            "print(','.join(sorted(leaked)))"
        )
        result = subprocess.run(
            [sys.executable, "-c", script],
            cwd=str(PACKAGE_ROOT.parent),
            capture_output=True,
            text=True,
            timeout=60,
        )
        assert result.returncode == 0, result.stderr
        assert result.stdout.strip() == "", f"Kivy imported transitively: {result.stdout}"


class TestUiLayerExists:
    """The UI modules should at least parse, even where Kivy is absent."""

    @pytest.mark.parametrize(
        "relative",
        [
            "ui/app.py",
            "ui/theme.py",
            "ui/widgets.py",
            "ui/tasks.py",
            "ui/screens/home.py",
            "ui/screens/detail.py",
            "ui/screens/setup.py",
        ],
    )
    def test_ui_module_is_syntactically_valid(self, relative):
        path = PACKAGE_ROOT / relative
        assert path.is_file(), f"missing {relative}"
        ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


class TestUiImports:
    """Only meaningful where Kivy is installed; skipped in the headless CI job."""

    def test_ui_package_imports(self):
        pytest.importorskip("kivy")
        import os

        if not (os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY")):
            pytest.skip("Kivy needs a display to import its window provider")
        assert importlib.import_module("gamerec.ui.app") is not None
