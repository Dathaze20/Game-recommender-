"""RAWG API client: one session, centralised auth, caching and bounded retries.

Behaviour worth knowing about:

* every request goes through one :class:`requests.Session`, so connections are
  pooled instead of re-handshaking TLS for each of the ~36 collection rows;
* successful responses are cached in memory with a TTL, which is what makes
  switching tabs and re-opening a game free;
* identical concurrent requests are de-duplicated — the first caller performs
  the request, the rest wait and read the cached result;
* retries are bounded and only apply to failures that can plausibly succeed on
  a second attempt (network blips, 5xx, 429). A rejected key or a 404 fails
  immediately rather than hammering RAWG.
"""

from __future__ import annotations

import logging
import threading
import time
from typing import Any, Callable

import requests

from .constants import BASE_URL
from .errors import (
    InvalidApiKey,
    MissingApiKey,
    NetworkError,
    NotFound,
    RateLimited,
    RawgError,
    ServiceError,
)
from .utils import backoff_delay

log = logging.getLogger(__name__)

#: Default cache lifetime for list endpoints, in seconds.
DEFAULT_CACHE_TTL = 15 * 60
#: Game details change rarely, so they are held longer.
DETAIL_CACHE_TTL = 60 * 60

DEFAULT_TIMEOUT = 15.0
DEFAULT_MAX_RETRIES = 2

#: Waiting longer than this for a rate limit blocks a worker thread pointlessly;
#: past it we surface the limit to the user instead.
MAX_RETRY_AFTER = 10.0

CacheKey = tuple[str, tuple[tuple[str, str], ...]]


def build_session(user_agent: str = "GameRecommender/1.0") -> requests.Session:
    """A session with sensible connection pooling and a real User-Agent."""
    session = requests.Session()
    session.headers.update({"User-Agent": user_agent, "Accept": "application/json"})
    adapter = requests.adapters.HTTPAdapter(pool_connections=4, pool_maxsize=8)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    return session


class RawgClient:
    """Thin, defensive wrapper around the RAWG REST API."""

    def __init__(
        self,
        api_key: str | None = None,
        session: requests.Session | None = None,
        base_url: str = BASE_URL,
        cache_ttl: float = DEFAULT_CACHE_TTL,
        timeout: float = DEFAULT_TIMEOUT,
        max_retries: int = DEFAULT_MAX_RETRIES,
        sleeper: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.api_key = (api_key or "").strip() or None
        self.base_url = base_url.rstrip("/")
        self.cache_ttl = cache_ttl
        self.timeout = timeout
        self.max_retries = max(0, max_retries)
        self._session = session if session is not None else build_session()
        self._sleep = sleeper
        self._clock = clock
        self._cache: dict[CacheKey, tuple[float, Any]] = {}
        self._inflight: dict[CacheKey, threading.Event] = {}
        self._lock = threading.Lock()

    # ── configuration ───────────────────────────────────────────────────
    def set_api_key(self, api_key: str | None) -> None:
        """Swap the credential and drop every cached response for the old one."""
        cleaned = (api_key or "").strip() or None
        with self._lock:
            if cleaned != self.api_key:
                self._cache.clear()
            self.api_key = cleaned

    @property
    def has_key(self) -> bool:
        return bool(self.api_key)

    @property
    def session(self) -> requests.Session:
        """The shared session, so a probe client can reuse the pool."""
        return self._session

    def clear_cache(self) -> None:
        with self._lock:
            self._cache.clear()

    def close(self) -> None:
        try:
            self._session.close()
        except Exception:  # noqa: BLE001 - shutdown must never raise
            log.debug("Ignoring error while closing session", exc_info=True)

    # ── cache plumbing ──────────────────────────────────────────────────
    @staticmethod
    def _cache_key(path: str, params: dict[str, Any]) -> CacheKey:
        items = tuple(sorted((str(k), str(v)) for k, v in params.items() if k != "key"))
        return (path, items)

    def _cache_get(self, key: CacheKey, ttl: float) -> Any:
        if ttl <= 0:
            return None
        with self._lock:
            entry = self._cache.get(key)
        if entry is None:
            return None
        stored_at, payload = entry
        if self._clock() - stored_at > ttl:
            with self._lock:
                self._cache.pop(key, None)
            return None
        return payload

    def _cache_put(self, key: CacheKey, payload: Any) -> None:
        with self._lock:
            self._cache[key] = (self._clock(), payload)

    # ── requests ────────────────────────────────────────────────────────
    def get(
        self,
        path: str,
        params: dict[str, Any] | None = None,
        ttl: float | None = None,
    ) -> Any:
        """GET ``path`` and return the decoded JSON body.

        Raises a :class:`~gamerec.errors.RawgError` subclass on failure; every
        one of them carries a ``user_message`` fit for display.
        """
        if not self.api_key:
            raise MissingApiKey()

        request_params = dict(params or {})
        key = self._cache_key(path, request_params)
        effective_ttl = self.cache_ttl if ttl is None else ttl

        cached = self._cache_get(key, effective_ttl)
        if cached is not None:
            return cached

        with self._lock:
            waiter = self._inflight.get(key)
            leader = waiter is None
            if leader:
                waiter = threading.Event()
                self._inflight[key] = waiter

        if not leader and waiter is not None:
            # Another thread is already asking for exactly this. Wait for it
            # rather than sending a duplicate request.
            waiter.wait(timeout=self.timeout * (self.max_retries + 2))
            cached = self._cache_get(key, effective_ttl)
            if cached is not None:
                return cached
            # The leader failed or timed out; fall through and try ourselves.
            return self._request(path, request_params, key)

        try:
            return self._request(path, request_params, key)
        finally:
            with self._lock:
                self._inflight.pop(key, None)
            if waiter is not None:
                waiter.set()

    def _request(self, path: str, params: dict[str, Any], key: CacheKey) -> Any:
        url = f"{self.base_url}/{path.lstrip('/')}"
        query = dict(params)
        query["key"] = self.api_key
        attempt = 0
        last_error: RawgError = ServiceError()

        while True:
            retry_after: float | None = None
            try:
                response = self._session.get(url, params=query, timeout=self.timeout)
            except requests.Timeout as exc:
                last_error = NetworkError(f"Timed out calling {path}: {exc}")
            except requests.RequestException as exc:
                last_error = NetworkError(f"Network failure calling {path}: {exc}")
            else:
                try:
                    return self._handle_response(response, path, key)
                except _RetryRequested as signal:
                    last_error = signal.error
                    retry_after = signal.retry_after

            attempt += 1
            if attempt > self.max_retries:
                log.warning("Giving up on %s after %s attempt(s)", path, attempt)
                raise last_error
            delay = retry_after if retry_after is not None else backoff_delay(attempt)
            log.info("Retrying %s in %.1fs (attempt %s)", path, delay, attempt + 1)
            self._sleep(delay)

    def _handle_response(self, response: requests.Response, path: str, key: CacheKey) -> Any:
        """Decode a response, or raise — including :class:`_RetryRequested`."""
        status = response.status_code

        if status == 200:
            try:
                payload = response.json()
            except ValueError as exc:
                raise ServiceError(f"RAWG sent a non-JSON response for {path}: {exc}") from exc
            self._cache_put(key, payload)
            return payload

        if status in (401, 403):
            # Permanent for this credential — retrying cannot help.
            raise InvalidApiKey(f"RAWG rejected the API key (HTTP {status}) for {path}")

        if status == 404:
            raise NotFound(f"RAWG has no resource at {path}")

        if status == 429:
            retry_after = _parse_retry_after(response.headers.get("Retry-After"))
            error = RateLimited(f"RAWG rate limit on {path}", retry_after=retry_after)
            if retry_after is not None and retry_after > MAX_RETRY_AFTER:
                # Blocking a worker thread this long helps nobody; tell the user.
                raise error
            raise _RetryRequested(error, retry_after)

        if 500 <= status < 600:
            raise _RetryRequested(ServiceError(f"RAWG returned HTTP {status} for {path}"))

        raise ServiceError(f"Unexpected HTTP {status} from RAWG for {path}")

    # ── typed endpoints ─────────────────────────────────────────────────
    def games(self, params: dict[str, Any] | None = None, ttl: float | None = None) -> Any:
        return self.get("games", params, ttl=ttl)

    def game(self, game_id: int) -> Any:
        return self.get(f"games/{int(game_id)}", ttl=DETAIL_CACHE_TTL)

    def screenshots(self, game_id: int, page_size: int = 8) -> Any:
        return self.get(
            f"games/{int(game_id)}/screenshots",
            {"page_size": page_size},
            ttl=DETAIL_CACHE_TTL,
        )

    def stores(self, game_id: int) -> Any:
        return self.get(f"games/{int(game_id)}/stores", ttl=DETAIL_CACHE_TTL)

    def suggested(self, game_id: int, page_size: int = 12) -> Any:
        return self.get(f"games/{int(game_id)}/suggested", {"page_size": page_size})

    def game_series(self, game_id: int, page_size: int = 12) -> Any:
        return self.get(f"games/{int(game_id)}/game-series", {"page_size": page_size})

    def search(self, query: str, page_size: int = 30) -> Any:
        return self.get("games", {"search": query, "page_size": page_size})

    def validate_key(self) -> bool:
        """Confirm the configured key works with one tiny live request.

        Propagates :class:`~gamerec.errors.InvalidApiKey` for a rejected key and
        the relevant transport error otherwise, so the UI can tell "your key is
        wrong" apart from "your Wi-Fi is off".
        """
        self.get("games", {"page_size": 1}, ttl=0)
        return True


class _RetryRequested(Exception):
    """Internal signal: this response failed but another attempt may succeed.

    Carrying the retry state on the exception (rather than on the client) keeps
    concurrent requests from clobbering each other's backoff.
    """

    def __init__(self, error: RawgError, retry_after: float | None = None) -> None:
        super().__init__(str(error))
        self.error = error
        self.retry_after = retry_after


def _parse_retry_after(value: str | None) -> float | None:
    """Parse a ``Retry-After`` header expressed in seconds."""
    if not value:
        return None
    try:
        seconds = float(value.strip())
    except (TypeError, ValueError):
        # RAWG sends the numeric form; an HTTP-date is valid per spec but we
        # simply fall back to normal backoff rather than guessing.
        return None
    return max(0.0, seconds)
