"""Pure helpers shared across the app. No Kivy, no I/O, no globals."""

from __future__ import annotations

import re
import threading
from collections.abc import Iterable, Sequence
from typing import Any

_TAG_RE = re.compile(r"<[^>]+>")
_WHITESPACE_RE = re.compile(r"[ \t\r\f\v]+")
_BLANKLINES_RE = re.compile(r"\n{3,}")

_HTML_ENTITIES = {
    "&amp;": "&",
    "&lt;": "<",
    "&gt;": ">",
    "&quot;": '"',
    "&#39;": "'",
    "&apos;": "'",
    "&nbsp;": " ",
    "&mdash;": "—",
    "&ndash;": "–",
    "&hellip;": "…",
}

_MONTHS = (
    "Jan", "Feb", "Mar", "Apr", "May", "Jun",
    "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
)

MAX_STARS = 5


def clamp(value: float, low: float, high: float) -> float:
    """Constrain ``value`` to the inclusive ``[low, high]`` range."""
    return max(low, min(high, value))


def safe_float(value: Any, default: float = 0.0) -> float:
    """Coerce ``value`` to ``float``, falling back to ``default``."""
    try:
        if value is None or isinstance(value, bool):
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def safe_int(value: Any, default: int | None = None) -> int | None:
    """Coerce ``value`` to ``int``, falling back to ``default``."""
    try:
        if value is None or isinstance(value, bool):
            return default
        return int(value)
    except (TypeError, ValueError):
        return default


def safe_str(value: Any, default: str = "") -> str:
    """Coerce ``value`` to a stripped ``str``, falling back to ``default``."""
    if value is None or isinstance(value, (dict, list, tuple, set)):
        return default
    if isinstance(value, str):
        return value.strip()
    return str(value)


def as_list(value: Any) -> list:
    """Return ``value`` when it is a list/tuple, otherwise an empty list.

    RAWG occasionally sends ``null`` where a collection is documented; this
    keeps parsing total instead of raising ``TypeError``.
    """
    if isinstance(value, (list, tuple)):
        return list(value)
    return []


def as_dict(value: Any) -> dict:
    """Return ``value`` when it is a dict, otherwise an empty dict."""
    return value if isinstance(value, dict) else {}


def rating_text(rating: Any) -> str:
    """Render a 0-5 rating as ASCII stars plus the numeric value.

    ASCII is deliberate: the bundled fonts used by Pydroid 3 on Android do not
    render the ``★`` glyph, which previously showed up as empty boxes.
    """
    value = clamp(safe_float(rating), 0.0, float(MAX_STARS))
    filled = int(value)
    return "{}{} {:.1f}".format("*" * filled, "." * (MAX_STARS - filled), value)


def metacritic_band(score: Any) -> str | None:
    """Classify a Metacritic score as ``"great"``, ``"mixed"`` or ``"weak"``.

    Returns ``None`` when there is no usable score, so callers can hide the
    badge entirely rather than showing a misleading zero.
    """
    value = safe_int(score)
    if value is None or value <= 0:
        return None
    if value >= 75:
        return "great"
    if value >= 50:
        return "mixed"
    return "weak"


def strip_html(text: Any) -> str:
    """Turn RAWG's HTML descriptions into readable plain text."""
    raw = safe_str(text)
    if not raw:
        return ""
    raw = re.sub(r"<br\s*/?>", "\n", raw, flags=re.IGNORECASE)
    raw = re.sub(r"</p\s*>", "\n\n", raw, flags=re.IGNORECASE)
    raw = _TAG_RE.sub("", raw)
    for entity, char in _HTML_ENTITIES.items():
        raw = raw.replace(entity, char)
    raw = _WHITESPACE_RE.sub(" ", raw)
    raw = _BLANKLINES_RE.sub("\n\n", raw)
    return raw.strip()


def release_year(date_str: Any) -> str:
    """Extract a four-digit year from an ISO date, or ``""``."""
    raw = safe_str(date_str)
    return raw[:4] if len(raw) >= 4 and raw[:4].isdigit() else ""


def format_release(date_str: Any) -> str:
    """Format ``YYYY-MM-DD`` as ``"12 Mar 2011"``; degrade gracefully."""
    raw = safe_str(date_str)
    parts = raw.split("-")
    if len(parts) == 3 and all(p.isdigit() for p in parts):
        year, month, day = (int(p) for p in parts)
        if 1 <= month <= 12:
            return f"{day} {_MONTHS[month - 1]} {year}"
    return raw or "Unknown"


def join_names(names: Iterable[Any], separator: str = ", ", limit: int = 0) -> str:
    """Join a collection of names, skipping blanks and optionally capping it."""
    cleaned = [safe_str(n) for n in as_list(names)]
    cleaned = [n for n in cleaned if n]
    if limit > 0 and len(cleaned) > limit:
        cleaned = cleaned[:limit]
    return separator.join(cleaned)


def dedupe_by_id(games: Sequence[Any], exclude_id: int | None = None) -> list:
    """Drop duplicate and excluded entries, preserving first-seen order."""
    seen: set = set()
    if exclude_id is not None:
        seen.add(exclude_id)
    result = []
    for game in games:
        game_id = getattr(game, "game_id", None)
        if game_id in seen:
            continue
        seen.add(game_id)
        result.append(game)
    return result


def backoff_delay(attempt: int, base: float = 0.8, cap: float = 8.0) -> float:
    """Exponential backoff for retry ``attempt`` (1-based), capped at ``cap``."""
    if attempt < 1:
        return 0.0
    return min(cap, base * (2 ** (attempt - 1)))


class Generation:
    """Monotonic token used to discard stale async responses.

    A screen bumps the generation whenever it starts new work; a background
    thread captures the token it started with and drops its result if the
    token is no longer current. That is how an in-flight search for "hal" is
    prevented from overwriting the newer results for "half-life".
    """

    def __init__(self) -> None:
        self._value = 0
        self._lock = threading.Lock()

    @property
    def current(self) -> int:
        with self._lock:
            return self._value

    def next(self) -> int:
        """Invalidate every outstanding token and return the new one."""
        with self._lock:
            self._value += 1
            return self._value

    def is_current(self, token: int) -> bool:
        with self._lock:
            return token == self._value
