"""Tests for the similar-games fallback chain."""

from __future__ import annotations

import pytest
from conftest import game_payload, list_payload

from gamerec.errors import InvalidApiKey, MissingApiKey, NotFound, ServiceError
from gamerec.models import GameDetails, parse_game
from gamerec.recommendations import genre_slug, similar_games


class FakeClient:
    """Scripted stand-in for :class:`~gamerec.api.RawgClient`.

    Each attribute is either a payload to return or an exception to raise.
    """

    def __init__(self, suggested=None, series=None, genre=None):
        self._suggested = suggested
        self._series = series
        self._genre = genre
        self.calls = []

    def suggested(self, game_id, page_size=12):
        self.calls.append(("suggested", game_id))
        return self._resolve(self._suggested)

    def game_series(self, game_id, page_size=12):
        self.calls.append(("game_series", game_id))
        return self._resolve(self._series)

    def games(self, params=None, ttl=None):
        self.calls.append(("games", dict(params or {})))
        return self._resolve(self._genre)

    @staticmethod
    def _resolve(value):
        if isinstance(value, Exception):
            raise value
        return value if value is not None else list_payload([])


@pytest.fixture
def subject():
    return parse_game(game_payload(id=100, name="Subject", genres=[{"name": "RPG"}]))


class TestStrategyOrder:
    def test_prefers_suggested(self, subject):
        client = FakeClient(suggested=list_payload([game_payload(id=1, name="Suggested")]))
        results = similar_games(client, subject)

        assert [g.name for g in results] == ["Suggested"]
        assert [c[0] for c in client.calls] == ["suggested"]

    def test_falls_back_to_the_series(self, subject):
        client = FakeClient(
            suggested=list_payload([]),
            series=list_payload([game_payload(id=2, name="Sequel")]),
        )
        results = similar_games(client, subject)

        assert [g.name for g in results] == ["Sequel"]
        assert [c[0] for c in client.calls] == ["suggested", "game_series"]

    def test_falls_back_to_the_genre(self, subject):
        client = FakeClient(
            suggested=list_payload([]),
            series=list_payload([]),
            genre=list_payload([game_payload(id=3, name="Same Genre")]),
        )
        results = similar_games(client, subject)

        assert [g.name for g in results] == ["Same Genre"]
        assert [c[0] for c in client.calls] == ["suggested", "game_series", "games"]

    def test_genre_query_uses_the_rawg_slug(self, subject):
        client = FakeClient(
            suggested=list_payload([]),
            series=list_payload([]),
            genre=list_payload([game_payload(id=3)]),
        )
        similar_games(client, subject)

        params = client.calls[-1][1]
        assert params["genres"] == "role-playing-games-rpg"
        assert params["ordering"] == "-rating"

    def test_returns_empty_when_everything_is_empty(self, subject):
        client = FakeClient()
        assert similar_games(client, subject) == []


class TestFailureHandling:
    def test_a_failing_step_does_not_abort_the_chain(self, subject):
        client = FakeClient(
            suggested=NotFound("no suggestions"),
            series=list_payload([game_payload(id=2, name="Sequel")]),
        )
        assert [g.name for g in similar_games(client, subject)] == ["Sequel"]

    def test_all_steps_failing_returns_empty(self, subject):
        client = FakeClient(
            suggested=ServiceError("500"),
            series=ServiceError("500"),
            genre=ServiceError("500"),
        )
        assert similar_games(client, subject) == []

    @pytest.mark.parametrize("fatal", [MissingApiKey(), InvalidApiKey()])
    def test_credential_problems_propagate(self, subject, fatal):
        client = FakeClient(suggested=fatal)
        with pytest.raises(type(fatal)):
            similar_games(client, subject)


class TestFiltering:
    def test_excludes_the_subject_itself(self, subject):
        client = FakeClient(
            suggested=list_payload([game_payload(id=100), game_payload(id=5, name="Other")])
        )
        results = similar_games(client, subject)
        assert [g.game_id for g in results] == [5]

    def test_deduplicates(self, subject):
        client = FakeClient(
            suggested=list_payload(
                [game_payload(id=5), game_payload(id=5), game_payload(id=6)]
            )
        )
        assert [g.game_id for g in similar_games(client, subject)] == [5, 6]

    def test_honours_the_limit(self, subject):
        payload = list_payload([game_payload(id=i) for i in range(1, 12)])
        client = FakeClient(suggested=payload)
        assert len(similar_games(client, subject, limit=4)) == 4

    def test_a_step_yielding_only_the_subject_moves_on(self, subject):
        client = FakeClient(
            suggested=list_payload([game_payload(id=100)]),
            series=list_payload([game_payload(id=9, name="Sequel")]),
        )
        assert [g.name for g in similar_games(client, subject)] == ["Sequel"]


class TestEdgeCases:
    def test_game_without_an_id_makes_no_calls(self):
        client = FakeClient(suggested=list_payload([game_payload(id=1)]))
        assert similar_games(client, GameDetails(game_id=0)) == []
        assert client.calls == []

    def test_no_genres_skips_the_genre_request(self):
        """With no genre to filter on there is nothing to ask RAWG for."""
        game = parse_game(game_payload(id=100, genres=[]))
        client = FakeClient(suggested=list_payload([]), series=list_payload([]))
        assert similar_games(client, game) == []
        assert [c[0] for c in client.calls] == ["suggested", "game_series"]

    def test_none_game_is_handled(self):
        assert similar_games(FakeClient(), None) == []


class TestGenreSlug:
    @pytest.mark.parametrize(
        ("name", "slug"),
        [
            ("RPG", "role-playing-games-rpg"),
            ("Action", "action"),
            ("Massively Multiplayer", "massively-multiplayer"),
        ],
    )
    def test_known_genres(self, name, slug):
        assert genre_slug(name) == slug

    def test_unknown_genre_is_slugified(self):
        assert genre_slug("Point And Click") == "point-and-click"

    def test_blank_genre(self):
        assert genre_slug("") is None
