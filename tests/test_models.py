"""Tests for RAWG payload parsing and saved-game serialisation."""

from __future__ import annotations

import pytest
from conftest import detail_payload, game_payload, list_payload

from gamerec.models import (
    GameDetails,
    StoreLink,
    apply_store_urls,
    game_to_saved,
    parse_game,
    parse_games,
    parse_screenshots,
    parse_store_links,
    parse_store_urls,
    saved_to_game,
)


class TestParseGame:
    def test_parses_a_full_record(self):
        game = parse_game(game_payload())

        assert game.game_id == 3498
        assert game.name == "Grand Theft Auto V"
        assert game.rating == pytest.approx(4.47)
        assert game.metacritic == 92
        assert game.playtime == 74
        assert game.esrb == "Mature"
        assert game.release_date == "2013-09-17"
        assert game.genres == ["Action", "Adventure"]
        assert game.platforms == ["PlayStation 5", "PC"]
        assert game.tags == ["Singleplayer", "Steam Achievements"]
        assert game.screenshots == [
            "https://media.rawg.io/media/shot1.jpg",
            "https://media.rawg.io/media/shot2.jpg",
        ]

    def test_prefers_plain_description(self):
        game = parse_game(detail_payload())
        assert game.description == "Rockstar's open-world crime epic."

    def test_falls_back_to_stripping_html_description(self):
        payload = game_payload(description="<p>Hello <b>world</b></p>")
        assert parse_game(payload).description == "Hello world"

    def test_has_detail_reflects_enrichment(self):
        assert parse_game(game_payload()).has_detail is False
        assert parse_game(detail_payload()).has_detail is True


class TestParseGameResilience:
    """RAWG sends nulls and partial objects; parsing must never raise."""

    def test_empty_payload(self):
        game = parse_game({})
        assert game.game_id == 0
        assert game.name == "Unknown"
        assert game.genres == []
        assert game.rating == 0.0
        assert game.metacritic is None

    @pytest.mark.parametrize("payload", [None, [], "nonsense", 42])
    def test_non_dict_payloads(self, payload):
        assert parse_game(payload).name == "Unknown"

    def test_null_collections(self):
        payload = game_payload(
            genres=None, platforms=None, stores=None, tags=None, short_screenshots=None
        )
        game = parse_game(payload)
        assert game.genres == []
        assert game.platforms == []
        assert game.stores == []
        assert game.tags == []
        assert game.screenshots == []

    def test_malformed_nested_entries_are_skipped(self):
        payload = game_payload(
            genres=[{"name": "Action"}, {}, None, "junk", {"name": ""}],
            platforms=[{"platform": None}, {"platform": {"name": "PC"}}, {}],
        )
        game = parse_game(payload)
        assert game.genres == ["Action"]
        assert game.platforms == ["PC"]

    def test_null_esrb(self):
        assert parse_game(game_payload(esrb_rating=None)).esrb == ""

    def test_string_numbers_are_coerced(self):
        game = parse_game(game_payload(rating="4.2", metacritic="88", playtime="12"))
        assert game.rating == pytest.approx(4.2)
        assert game.metacritic == 88
        assert game.playtime == 12

    def test_unparseable_numbers_fall_back(self):
        game = parse_game(game_payload(rating="high", metacritic="n/a", playtime=None))
        assert game.rating == 0.0
        assert game.metacritic is None
        assert game.playtime == 0

    def test_duplicate_genres_collapse(self):
        payload = game_payload(genres=[{"name": "Action"}, {"name": "Action"}])
        assert parse_game(payload).genres == ["Action"]


class TestParseGames:
    def test_parses_results_array(self):
        games = parse_games(list_payload([game_payload(), game_payload(id=5, name="Portal")]))
        assert [g.name for g in games] == ["Grand Theft Auto V", "Portal"]

    def test_drops_records_without_an_id(self):
        games = parse_games(list_payload([game_payload(id=None), game_payload(id=7)]))
        assert [g.game_id for g in games] == [7]

    @pytest.mark.parametrize("payload", [None, {}, {"results": None}, "junk"])
    def test_missing_results(self, payload):
        assert parse_games(payload) == []

    def test_accepts_a_bare_list(self):
        assert len(parse_games([game_payload()])) == 1


class TestStores:
    def test_parses_embedded_store_names(self):
        links = parse_store_links(game_payload()["stores"])
        assert [link.name for link in links] == ["Steam", "PlayStation Store"]
        # RAWG leaves `url` empty on the embedded array.
        assert all(link.url is None for link in links)
        assert all(not link.actionable for link in links)

    def test_deduplicates_stores(self):
        raw = [
            {"store": {"id": 1, "name": "Steam"}},
            {"store": {"id": 1, "name": "Steam"}},
        ]
        assert len(parse_store_links(raw)) == 1

    def test_parses_store_urls_endpoint(self):
        payload = {
            "results": [
                {"id": 1, "game_id": 3498, "store_id": 1, "url": "https://store.steampowered.com/app/271590/"},
                {"id": 2, "game_id": 3498, "store_id": 3, "url": "https://store.playstation.com/x"},
            ]
        }
        assert parse_store_urls(payload) == {
            1: "https://store.steampowered.com/app/271590/",
            3: "https://store.playstation.com/x",
        }

    def test_rejects_non_http_and_empty_urls(self):
        payload = {
            "results": [
                {"store_id": 1, "url": ""},
                {"store_id": 2, "url": "javascript:alert(1)"},
                {"store_id": 3, "url": None},
                {"store_id": None, "url": "https://example.com"},
            ]
        }
        assert parse_store_urls(payload) == {}

    def test_apply_store_urls_only_fills_known_ids(self):
        game = parse_game(game_payload())
        apply_store_urls(game, {1: "https://store.steampowered.com/app/271590/"})

        steam = next(link for link in game.stores if link.store_id == 1)
        playstation = next(link for link in game.stores if link.store_id == 3)
        assert steam.actionable is True
        # No URL is ever invented for a store RAWG did not give one for.
        assert playstation.url is None
        assert playstation.actionable is False

    def test_apply_store_urls_does_not_overwrite(self):
        link = StoreLink(store_id=1, name="Steam", url="https://original/")
        game = GameDetails(game_id=1, stores=[link])
        apply_store_urls(game, {1: "https://replacement/"})
        assert link.url == "https://original/"


class TestScreenshots:
    def test_parses_dedicated_endpoint(self):
        payload = {"results": [{"image": "a.jpg"}, {"image": "b.jpg"}]}
        assert parse_screenshots(payload) == ["a.jpg", "b.jpg"]

    def test_deduplicates_and_skips_blanks(self):
        payload = {"results": [{"image": "a.jpg"}, {"image": ""}, {"image": "a.jpg"}, {}]}
        assert parse_screenshots(payload) == ["a.jpg"]

    def test_handles_missing_payload(self):
        assert parse_screenshots(None) == []


class TestSavedRoundTrip:
    def test_round_trips_the_persisted_fields(self):
        original = parse_game(detail_payload())
        restored = saved_to_game(game_to_saved(original))

        assert restored is not None
        assert restored.game_id == original.game_id
        assert restored.name == original.name
        assert restored.rating == original.rating
        assert restored.metacritic == original.metacritic
        assert restored.release_date == original.release_date
        assert restored.genres == original.genres
        assert restored.background_image == original.background_image

    def test_heavy_fields_are_not_persisted(self):
        saved = game_to_saved(parse_game(detail_payload()))
        assert "description" not in saved
        assert "screenshots" not in saved
        assert "tags" not in saved

    def test_saved_entries_are_json_serialisable(self):
        import json

        json.dumps(game_to_saved(parse_game(detail_payload())))

    @pytest.mark.parametrize("bad", [None, {}, {"name": "no id"}, {"game_id": 0}, "junk", []])
    def test_unusable_entries_return_none(self, bad):
        assert saved_to_game(bad) is None

    def test_partial_entry_gets_defaults(self):
        restored = saved_to_game({"game_id": 12})
        assert restored is not None
        assert restored.name == "Unknown"
        assert restored.rating == 0.0
        assert restored.genres == []

    def test_tolerates_wrong_types(self):
        restored = saved_to_game(
            {"game_id": "12", "name": 5, "rating": "bad", "genres": "Action"}
        )
        assert restored is not None
        assert restored.game_id == 12
        assert restored.rating == 0.0
        assert restored.genres == []
