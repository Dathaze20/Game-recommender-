"""Local persistence for the wishlist, played list, stats and settings.

Design notes:

* the file lives in the platform user-data directory, never the working
  directory — Android in particular does not give an app a writable CWD;
* writes are atomic, so an interrupted save cannot leave a half-written file
  that destroys the whole library;
* loads are total: a missing file, unreadable file, malformed JSON or an older
  schema all resolve to usable data rather than an exception.
"""

from __future__ import annotations

import json
import logging
import os
import threading
import time
from typing import Any

from .config import atomic_write, with_suppressed_error
from .models import GameDetails, game_to_saved, saved_to_game
from .utils import as_dict, as_list, safe_int, safe_str

log = logging.getLogger(__name__)

LIBRARY_FILENAME = "library.json"
SCHEMA_VERSION = 2

#: Pre-1.0 builds wrote this into the working directory.
LEGACY_FILENAME = "game_recommender_config.json"

STAT_GAMES_VIEWED = "games_viewed"
STAT_SEARCHES = "searches"


def _empty_library() -> dict[str, Any]:
    return {
        "version": SCHEMA_VERSION,
        "wishlist": [],
        "played": [],
        "stats": {},
        "settings": {},
    }


def _normalise_entries(entries: Any) -> list[dict[str, Any]]:
    """Keep only entries that round-trip through the model layer."""
    cleaned: list[dict[str, Any]] = []
    seen: set = set()
    for entry in as_list(entries):
        game = saved_to_game(entry)
        if game is None or game.game_id in seen:
            continue
        seen.add(game.game_id)
        cleaned.append(game_to_saved(game))
    return cleaned


def _normalise_stats(stats: Any) -> dict[str, int]:
    cleaned: dict[str, int] = {}
    for key, value in as_dict(stats).items():
        count = safe_int(value)
        if isinstance(key, str) and count is not None and count >= 0:
            cleaned[key] = count
    return cleaned


def migrate(payload: Any) -> dict[str, Any]:
    """Bring any historical payload shape up to the current schema.

    Version 1 (and the unversioned original) stored the wishlist, played list
    and stats at the top level alongside an ``api_key``. The key is dropped
    here on purpose — credentials moved to their own restricted file.
    """
    data = as_dict(payload)
    library = _empty_library()
    library["wishlist"] = _normalise_entries(data.get("wishlist"))
    library["played"] = _normalise_entries(data.get("played"))
    library["stats"] = _normalise_stats(data.get("stats"))
    settings = as_dict(data.get("settings"))
    library["settings"] = {k: v for k, v in settings.items() if isinstance(k, str)}
    return library


class Storage:
    """Thread-safe accessor for the on-disk library.

    The whole file is small (a few hundred entries at most), so it is kept in
    memory and rewritten wholesale. That keeps the concurrency story simple:
    one lock, one atomic replace.
    """

    def __init__(self, data_dir: str, filename: str = LIBRARY_FILENAME) -> None:
        self.data_dir = data_dir
        self.path = os.path.join(data_dir, filename)
        self._lock = threading.RLock()
        self._data: dict[str, Any] = _empty_library()
        self._loaded = False

    # ── loading / saving ────────────────────────────────────────────────
    def load(self, force: bool = False) -> dict[str, Any]:
        """Read the library from disk, repairing anything unusable."""
        with self._lock:
            if self._loaded and not force:
                return self._data
            self._data = self._read_from_disk()
            self._loaded = True
            return self._data

    def _read_from_disk(self) -> dict[str, Any]:
        try:
            with open(self.path, encoding="utf-8") as fh:
                payload = json.load(fh)
        except FileNotFoundError:
            return _empty_library()
        except ValueError as exc:
            log.warning("Library file is not valid JSON (%s); starting fresh.", exc)
            self._quarantine()
            return _empty_library()
        except OSError as exc:
            log.warning("Could not read library file: %s", exc)
            return _empty_library()

        # `migrate` is total and idempotent, so it doubles as the validator for
        # current-version files: unknown keys are dropped, bad rows discarded.
        return migrate(payload)

    def _quarantine(self) -> None:
        """Move an unparseable file aside so the user does not lose it."""
        backup = f"{self.path}.corrupt-{int(time.time())}"
        try:
            os.replace(self.path, backup)
            log.warning("Kept the unreadable library file at %s", backup)
        except OSError:
            with_suppressed_error(os.unlink, self.path)

    def save(self) -> bool:
        """Persist the in-memory library. Returns ``False`` if the write failed."""
        with self._lock:
            payload = json.dumps(self._data, indent=2, ensure_ascii=False)
        try:
            atomic_write(self.path, payload, mode=0o644)
            return True
        except OSError as exc:
            log.error("Could not save library: %s", exc)
            return False

    # ── collections ─────────────────────────────────────────────────────
    def _collection(self, name: str) -> list[dict[str, Any]]:
        data = self.load()
        items = data.get(name)
        if not isinstance(items, list):
            items = []
            data[name] = items
        return items

    def entries(self, name: str) -> list[dict[str, Any]]:
        """Raw saved dicts for ``"wishlist"`` or ``"played"``."""
        with self._lock:
            return list(self._collection(name))

    def games(self, name: str) -> list[GameDetails]:
        """Saved entries rebuilt as models, newest first."""
        games = [saved_to_game(entry) for entry in self.entries(name)]
        return [g for g in reversed(games) if g is not None]

    def contains(self, name: str, game_id: int) -> bool:
        with self._lock:
            return any(
                safe_int(e.get("game_id")) == game_id for e in self._collection(name)
            )

    def toggle(self, name: str, game: GameDetails) -> bool:
        """Add or remove ``game``. Returns ``True`` when it is now saved."""
        with self._lock:
            items = self._collection(name)
            index = next(
                (i for i, e in enumerate(items) if safe_int(e.get("game_id")) == game.game_id),
                None,
            )
            if index is None:
                items.append(game_to_saved(game))
                present = True
            else:
                items.pop(index)
                present = False
        self.save()
        return present

    def remove(self, name: str, game_id: int) -> bool:
        with self._lock:
            items = self._collection(name)
            before = len(items)
            items[:] = [e for e in items if safe_int(e.get("game_id")) != game_id]
            changed = len(items) != before
        if changed:
            self.save()
        return changed

    # ── stats ───────────────────────────────────────────────────────────
    def stats(self) -> dict[str, int]:
        with self._lock:
            data = self.load()
            stats = data.get("stats")
            if not isinstance(stats, dict):
                stats = {}
                data["stats"] = stats
            return dict(stats)

    def bump_stat(self, key: str, amount: int = 1) -> int:
        with self._lock:
            data = self.load()
            stats = data.get("stats")
            if not isinstance(stats, dict):
                stats = {}
                data["stats"] = stats
            value = (safe_int(stats.get(key), 0) or 0) + amount
            stats[key] = value
        self.save()
        return value

    # ── settings ────────────────────────────────────────────────────────
    def get_setting(self, key: str, default: Any = None) -> Any:
        with self._lock:
            settings = self.load().get("settings")
            return as_dict(settings).get(key, default)

    def set_setting(self, key: str, value: Any) -> None:
        with self._lock:
            data = self.load()
            settings = data.get("settings")
            if not isinstance(settings, dict):
                settings = {}
                data["settings"] = settings
            settings[key] = value
        self.save()

    # ── legacy import ───────────────────────────────────────────────────
    def import_legacy(self, legacy_path: str) -> str | None:
        """Fold a pre-1.0 working-directory config into the library.

        Returns any API key found in the legacy file so the caller can move it
        into the credential store, or ``None``. Runs at most once — a flag in
        ``settings`` records that the import happened.
        """
        if self.get_setting("legacy_imported"):
            return None
        if not os.path.isfile(legacy_path):
            return None
        try:
            with open(legacy_path, encoding="utf-8") as fh:
                payload = json.load(fh)
        except (OSError, ValueError) as exc:
            log.warning("Could not import legacy config: %s", exc)
            return None

        legacy = migrate(payload)
        with self._lock:
            data = self.load()
            for name in ("wishlist", "played"):
                existing = {safe_int(e.get("game_id")) for e in self._collection(name)}
                for entry in legacy[name]:
                    if safe_int(entry.get("game_id")) not in existing:
                        data[name].append(entry)
            stats = data.setdefault("stats", {})
            for key, value in legacy["stats"].items():
                stats[key] = (safe_int(stats.get(key), 0) or 0) + value
            data.setdefault("settings", {})["legacy_imported"] = True
        self.save()
        log.info("Imported legacy library from %s", legacy_path)
        return safe_str(as_dict(payload).get("api_key")) or None


def summarise(storage: Storage) -> dict[str, Any]:
    """Derive the numbers shown on the Stats tab.

    Kept as a free function of pure data so it can be unit-tested without any
    UI or filesystem involvement beyond the storage object itself.
    """
    wishlist = storage.entries("wishlist")
    played = storage.entries("played")
    stats = storage.stats()

    genre_counts: dict[str, int] = {}
    for entry in wishlist + played:
        for genre in as_list(entry.get("genres")):
            name = safe_str(genre)
            if name:
                genre_counts[name] = genre_counts.get(name, 0) + 1
    top_genres = sorted(genre_counts.items(), key=lambda kv: (-kv[1], kv[0]))[:3]

    ratings = [
        float(entry["rating"])
        for entry in played
        if isinstance(entry.get("rating"), (int, float)) and entry["rating"] > 0
    ]
    metacritics = [
        int(entry["metacritic"])
        for entry in played
        if isinstance(entry.get("metacritic"), int) and entry["metacritic"] > 0
    ]

    return {
        "wishlist_count": len(wishlist),
        "played_count": len(played),
        "games_viewed": stats.get(STAT_GAMES_VIEWED, 0),
        "searches": stats.get(STAT_SEARCHES, 0),
        "top_genres": [name for name, _ in top_genres],
        "average_rating": round(sum(ratings) / len(ratings), 2) if ratings else None,
        "average_metacritic": (
            round(sum(metacritics) / len(metacritics)) if metacritics else None
        ),
    }
