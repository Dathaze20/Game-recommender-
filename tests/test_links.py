"""Tests for external URL opening across desktop and Android.

``gamerec.ui.links`` lives under the UI package but deliberately keeps Kivy and
pyjnius behind function-local guarded imports, so it is importable — and
testable — on a machine with neither. That property is what the whole
desktop/Android split relies on, so it is asserted here.
"""

from __future__ import annotations

import sys

import pytest

from gamerec.ui import links


class TestImportIsStandalone:
    def test_module_does_not_import_kivy_at_module_level(self):
        """Importing the module must not drag in Kivy or pyjnius."""
        import subprocess

        result = subprocess.run(
            [
                sys.executable,
                "-c",
                "import sys, gamerec.ui.links;"
                "print([n for n in sys.modules if n in ('kivy', 'jnius')])",
            ],
            capture_output=True,
            text=True,
            timeout=60,
        )
        assert result.returncode == 0, result.stderr
        assert result.stdout.strip() == "[]", result.stdout


class TestSchemeGuard:
    """Only real web URLs are ever handed to a browser or an intent."""

    @pytest.mark.parametrize(
        "url",
        [
            "",
            None,
            "javascript:alert(1)",
            "file:///etc/passwd",
            "intent://evil",
            "store.steampowered.com/app/1/",
            "ftp://example.com",
        ],
    )
    def test_rejects_non_web_urls(self, url, monkeypatch):
        called = []
        monkeypatch.setattr(links.webbrowser, "open", lambda u: called.append(u) or True)

        assert links.open_url(url) is False
        assert called == [], "a non-web URL reached the browser"

    @pytest.mark.parametrize(
        "url",
        ["http://example.com", "https://store.steampowered.com/app/271590/"],
    )
    def test_accepts_web_urls(self, url, monkeypatch):
        monkeypatch.setattr(links.webbrowser, "open", lambda _u: True)
        assert links.open_url(url) is True


class TestDesktopFallback:
    def test_uses_webbrowser_when_not_android(self, monkeypatch):
        opened = []
        monkeypatch.setattr(links, "_is_android", lambda: False)
        monkeypatch.setattr(links.webbrowser, "open", lambda u: opened.append(u) or True)

        assert links.open_url("https://rawg.io/apikey") is True
        assert opened == ["https://rawg.io/apikey"]

    def test_reports_failure_when_no_browser_exists(self, monkeypatch):
        monkeypatch.setattr(links, "_is_android", lambda: False)
        monkeypatch.setattr(links.webbrowser, "open", lambda _u: False)
        assert links.open_url("https://rawg.io") is False

    def test_browser_exception_does_not_propagate(self, monkeypatch):
        def _boom(_url):
            raise RuntimeError("no display")

        monkeypatch.setattr(links, "_is_android", lambda: False)
        monkeypatch.setattr(links.webbrowser, "open", _boom)
        assert links.open_url("https://rawg.io") is False


class TestAndroidPath:
    def test_android_intent_short_circuits_the_browser(self, monkeypatch):
        opened = []
        monkeypatch.setattr(links, "_is_android", lambda: True)
        monkeypatch.setattr(links, "_open_android", lambda _u: True)
        monkeypatch.setattr(links.webbrowser, "open", lambda u: opened.append(u) or True)

        assert links.open_url("https://rawg.io") is True
        assert opened == [], "the browser was used even though the intent succeeded"

    def test_falls_back_to_browser_when_the_intent_fails(self, monkeypatch):
        opened = []
        monkeypatch.setattr(links, "_is_android", lambda: True)
        monkeypatch.setattr(links, "_open_android", lambda _u: False)
        monkeypatch.setattr(links.webbrowser, "open", lambda u: opened.append(u) or True)

        assert links.open_url("https://rawg.io") is True
        assert opened == ["https://rawg.io"]

    def test_open_android_returns_false_without_pyjnius(self):
        """pyjnius is absent off-device; this must degrade, not raise."""
        assert "jnius" not in sys.modules
        assert links._open_android("https://rawg.io") is False


class TestPlatformDetection:
    def test_missing_kivy_is_not_android(self, monkeypatch):
        """CI has no Kivy at all; detection must answer rather than explode."""
        monkeypatch.setitem(sys.modules, "kivy.utils", None)
        assert links._is_android() is False

    def test_detects_android_from_kivy_platform(self, monkeypatch):
        module = type(sys)("kivy.utils")
        module.platform = "android"
        monkeypatch.setitem(sys.modules, "kivy", type(sys)("kivy"))
        monkeypatch.setitem(sys.modules, "kivy.utils", module)
        assert links._is_android() is True

    def test_desktop_platform_is_not_android(self, monkeypatch):
        module = type(sys)("kivy.utils")
        module.platform = "linux"
        monkeypatch.setitem(sys.modules, "kivy", type(sys)("kivy"))
        monkeypatch.setitem(sys.modules, "kivy.utils", module)
        assert links._is_android() is False
