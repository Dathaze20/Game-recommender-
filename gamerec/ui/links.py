"""Opening external URLs across the platforms this app actually runs on.

Python's :mod:`webbrowser` works on desktop but does nothing useful inside an
Android APK, where opening a link means firing an ``ACTION_VIEW`` intent. This
picks the right mechanism and reports honestly whether it managed it, so the UI
never pretends a tap did something it did not.
"""

from __future__ import annotations

import logging
import webbrowser

log = logging.getLogger(__name__)


def _is_android() -> bool:
    try:
        from kivy.utils import platform
    except Exception:  # noqa: BLE001 - detection must never break the caller
        return False
    return platform == "android"


def _open_android(url: str) -> bool:
    """Hand the URL to Android via an ACTION_VIEW intent.

    Requires pyjnius, which python-for-android bundles in an APK build. When it
    is unavailable (for example under Pydroid 3) this returns ``False`` and the
    caller falls back.
    """
    try:
        from jnius import autoclass, cast
    except Exception:  # noqa: BLE001 - not an APK build
        return False
    try:
        intent = autoclass("android.content.Intent")
        uri = autoclass("android.net.Uri")
        activity = autoclass("org.kivy.android.PythonActivity").mActivity
        view = intent(intent.ACTION_VIEW, uri.parse(url))
        view.setFlags(intent.FLAG_ACTIVITY_NEW_TASK)
        cast("android.app.Activity", activity).startActivity(view)
        return True
    except Exception:  # noqa: BLE001 - a failed handoff is not fatal
        log.info("Android intent could not open %s", url, exc_info=True)
        return False


def open_url(url: str) -> bool:
    """Open ``url`` externally. Returns ``True`` only if a handler took it."""
    if not url or not url.startswith(("http://", "https://")):
        return False

    if _is_android() and _open_android(url):
        return True

    try:
        return bool(webbrowser.open(url))
    except Exception:  # noqa: BLE001 - no browser available
        log.info("No browser available for %s", url, exc_info=True)
        return False
