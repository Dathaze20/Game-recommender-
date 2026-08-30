"""RAWG API-key resolution and storage.

Resolution order (first hit wins):

1. the ``GAME_API_KEY`` environment variable — the development path;
2. a ``.env`` file in the project directory, when ``python-dotenv`` is
   installed (it ships in ``requirements.txt``);
3. a key the user typed into the app, saved under the platform user-data
   directory.

There is deliberately **no** bundled fallback key. When none of the above
yields a key the app shows its setup screen and makes zero API requests.
"""

from __future__ import annotations

import contextlib
import json
import logging
import os
import sys
import tempfile
from collections.abc import Mapping
from dataclasses import dataclass

log = logging.getLogger(__name__)

ENV_VAR = "GAME_API_KEY"
CREDENTIALS_FILENAME = "credentials.json"

#: Sources reported by :func:`resolve_api_key`, in precedence order.
SOURCE_ENV = "environment"
SOURCE_DOTENV = "dotenv"
SOURCE_SAVED = "saved"


def load_dotenv(path: str = ".env") -> bool:
    """Load ``path`` into ``os.environ`` if python-dotenv is available.

    Returns ``True`` only when a file was actually read. Existing environment
    variables always win, so an exported ``GAME_API_KEY`` overrides ``.env``.
    """
    if not os.path.isfile(path):
        return False
    try:
        from dotenv import load_dotenv as _load
    except ImportError:
        log.info("Found %s but python-dotenv is not installed; ignoring it.", path)
        return False
    try:
        return bool(_load(path, override=False))
    except OSError as exc:
        log.warning("Could not read %s: %s", path, exc)
        return False


def default_data_dir(app_dirname: str = "game-recommender") -> str:
    """A platform-appropriate per-user data directory.

    The Kivy app passes ``App.user_data_dir`` instead; this exists so the
    non-UI code (and the tests) has a sane answer without importing Kivy.
    """
    if sys.platform == "win32":
        base = os.environ.get("APPDATA") or os.path.expanduser("~")
    elif sys.platform == "darwin":
        base = os.path.join(os.path.expanduser("~"), "Library", "Application Support")
    else:
        base = os.environ.get("XDG_DATA_HOME") or os.path.join(
            os.path.expanduser("~"), ".local", "share"
        )
    return os.path.join(base, app_dirname)


def atomic_write(path: str, payload: str, mode: int = 0o600) -> None:
    """Write ``payload`` to ``path`` without risking a truncated file.

    The content lands in a temp file in the same directory and is then moved
    into place with :func:`os.replace`, which is atomic on POSIX and Windows.
    """
    directory = os.path.dirname(os.path.abspath(path)) or "."
    os.makedirs(directory, exist_ok=True)
    handle, tmp_path = tempfile.mkstemp(dir=directory, prefix=".tmp-", suffix=".json")
    try:
        with os.fdopen(handle, "w", encoding="utf-8") as fh:
            fh.write(payload)
            fh.flush()
            os.fsync(fh.fileno())
        # Filesystems such as FAT (common on Android SD cards) ignore
        # permission bits. Not fatal — carry on without them.
        with contextlib.suppress(OSError):
            os.chmod(tmp_path, mode)
        os.replace(tmp_path, path)
    except BaseException:
        with_suppressed_error(os.unlink, tmp_path)
        raise


def with_suppressed_error(func, *args) -> None:
    """Best-effort cleanup helper: run ``func`` and swallow OS errors."""
    with contextlib.suppress(OSError):
        func(*args)


class ApiKeyStore:
    """Reads and writes the user-supplied key in its own restricted file.

    The credential lives apart from the game library so a user can copy or
    share ``library.json`` without leaking their key.
    """

    def __init__(self, data_dir: str, filename: str = CREDENTIALS_FILENAME) -> None:
        self.data_dir = data_dir
        self.path = os.path.join(data_dir, filename)

    def read(self) -> str | None:
        try:
            with open(self.path, encoding="utf-8") as fh:
                payload = json.load(fh)
        except FileNotFoundError:
            return None
        except (OSError, ValueError) as exc:
            log.warning("Could not read stored credentials: %s", exc)
            return None
        if not isinstance(payload, dict):
            return None
        key = payload.get("api_key")
        return key.strip() if isinstance(key, str) and key.strip() else None

    def write(self, api_key: str) -> None:
        cleaned = (api_key or "").strip()
        if not cleaned:
            raise ValueError("Refusing to store an empty API key")
        atomic_write(self.path, json.dumps({"api_key": cleaned}, indent=2))

    def clear(self) -> None:
        with_suppressed_error(os.unlink, self.path)


@dataclass(frozen=True)
class ResolvedKey:
    """The outcome of :func:`resolve_api_key`."""

    key: str | None
    source: str | None

    def __bool__(self) -> bool:
        return bool(self.key)

    @property
    def is_editable(self) -> bool:
        """Environment-provided keys are owned by the shell, not the app."""
        return self.source in (None, SOURCE_SAVED)


def resolve_api_key(
    data_dir: str | None = None,
    env: Mapping[str, str] | None = None,
    dotenv_path: str = ".env",
    use_dotenv: bool = True,
) -> ResolvedKey:
    """Find a usable RAWG key, reporting where it came from."""
    environ = os.environ if env is None else env

    direct = (environ.get(ENV_VAR) or "").strip()
    if direct:
        return ResolvedKey(direct, SOURCE_ENV)

    if use_dotenv and env is None and load_dotenv(dotenv_path):
        from_dotenv = (os.environ.get(ENV_VAR) or "").strip()
        if from_dotenv:
            return ResolvedKey(from_dotenv, SOURCE_DOTENV)

    directory = data_dir or default_data_dir()
    saved = ApiKeyStore(directory).read()
    if saved:
        return ResolvedKey(saved, SOURCE_SAVED)

    return ResolvedKey(None, None)


def looks_like_api_key(candidate: str) -> bool:
    """Cheap client-side sanity check before spending a network round-trip.

    RAWG keys are 32-character lowercase hex strings. This only rejects
    obvious typos; the authoritative check is a live request.
    """
    cleaned = (candidate or "").strip()
    return len(cleaned) == 32 and all(c in "0123456789abcdef" for c in cleaned.lower())
