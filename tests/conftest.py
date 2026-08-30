"""Shared fixtures.

Nothing here imports Kivy — that is the point. The whole suite exercises
``gamerec.*`` outside ``gamerec.ui``, so it runs headless in CI.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


@pytest.fixture
def data_dir(tmp_path: Path) -> str:
    """An isolated user-data directory."""
    directory = tmp_path / "userdata"
    directory.mkdir()
    return str(directory)


@pytest.fixture
def storage(data_dir: str):
    from gamerec.storage import Storage

    return Storage(data_dir)


def game_payload(**overrides: Any) -> dict[str, Any]:
    """A realistic RAWG list-endpoint game object."""
    payload: dict[str, Any] = {
        "id": 3498,
        "name": "Grand Theft Auto V",
        "released": "2013-09-17",
        "background_image": "https://media.rawg.io/media/gta5.jpg",
        "rating": 4.47,
        "metacritic": 92,
        "playtime": 74,
        "esrb_rating": {"id": 4, "name": "Mature", "slug": "mature"},
        "genres": [{"id": 4, "name": "Action"}, {"id": 3, "name": "Adventure"}],
        "platforms": [
            {"platform": {"id": 187, "name": "PlayStation 5", "slug": "playstation5"}},
            {"platform": {"id": 4, "name": "PC", "slug": "pc"}},
        ],
        "stores": [
            {"id": 290375, "url": "", "store": {"id": 1, "name": "Steam", "slug": "steam"}},
            {
                "id": 290376,
                "url": "",
                "store": {"id": 3, "name": "PlayStation Store", "slug": "playstation-store"},
            },
        ],
        "short_screenshots": [
            {"id": -1, "image": "https://media.rawg.io/media/shot1.jpg"},
            {"id": 1, "image": "https://media.rawg.io/media/shot2.jpg"},
        ],
        "tags": [{"id": 31, "name": "Singleplayer"}, {"id": 40847, "name": "Steam Achievements"}],
    }
    payload.update(overrides)
    return payload


def detail_payload(**overrides: Any) -> dict[str, Any]:
    """A RAWG detail-endpoint game object (adds description/dev/publisher)."""
    payload = game_payload()
    payload.update(
        {
            "description_raw": "Rockstar's open-world crime epic.",
            "developers": [{"id": 3524, "name": "Rockstar North"}],
            "publishers": [{"id": 2155, "name": "Rockstar Games"}],
        }
    )
    payload.update(overrides)
    return payload


def list_payload(games: list[dict[str, Any]] | None = None, **overrides: Any):
    body = {"count": len(games or []), "next": None, "previous": None, "results": games or []}
    body.update(overrides)
    return body


class FakeResponse:
    """Minimal stand-in for ``requests.Response``."""

    def __init__(
        self,
        status_code: int = 200,
        json_body: Any = None,
        headers: dict[str, str] | None = None,
        raise_on_json: bool = False,
    ) -> None:
        self.status_code = status_code
        self._json_body = json_body if json_body is not None else {}
        self.headers = headers or {}
        self._raise_on_json = raise_on_json

    def json(self) -> Any:
        if self._raise_on_json:
            raise ValueError("no json")
        return self._json_body


class FakeSession:
    """Records requests and replays a scripted sequence of responses."""

    def __init__(self, responses: Any = None) -> None:
        # Either a single response reused forever, or a list consumed in order.
        self._responses = responses
        self.calls: list[dict[str, Any]] = []
        self.headers: dict[str, str] = {}
        self.closed = False

    def get(self, url: str, params: dict | None = None, timeout: Any = None):
        self.calls.append({"url": url, "params": dict(params or {}), "timeout": timeout})
        response = self._next()
        if isinstance(response, Exception):
            raise response
        return response

    def _next(self):
        if isinstance(self._responses, list):
            if not self._responses:
                raise AssertionError("FakeSession ran out of scripted responses")
            return self._responses.pop(0)
        return self._responses

    def mount(self, *_args, **_kwargs) -> None:  # pragma: no cover - interface shim
        pass

    def close(self) -> None:
        self.closed = True


@pytest.fixture
def make_client():
    """Build a :class:`RawgClient` wired to a fake session and a fake clock."""
    from gamerec.api import RawgClient

    def _factory(responses=None, api_key: str | None = "k" * 32, **kwargs):
        session = FakeSession(responses)
        slept: list[float] = []
        now = {"t": 0.0}

        client = RawgClient(
            api_key=api_key,
            session=session,
            sleeper=lambda seconds: slept.append(seconds),
            clock=lambda: now["t"],
            **kwargs,
        )
        client.test_session = session
        client.test_slept = slept
        client.test_now = now
        return client

    return _factory
