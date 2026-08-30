"""Tests for local persistence: durability, resilience and migration."""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest
from conftest import detail_payload, game_payload

from gamerec.models import parse_game
from gamerec.storage import (
    SCHEMA_VERSION,
    STAT_GAMES_VIEWED,
    Storage,
    migrate,
    summarise,
)


@pytest.fixture
def game():
    return parse_game(detail_payload())


class TestCollections:
    def test_toggle_adds_then_removes(self, storage, game):
        assert storage.toggle("wishlist", game) is True
        assert storage.contains("wishlist", game.game_id) is True

        assert storage.toggle("wishlist", game) is False
        assert storage.contains("wishlist", game.game_id) is False

    def test_wishlist_and_played_are_independent(self, storage, game):
        storage.toggle("wishlist", game)
        assert storage.contains("played", game.game_id) is False

    def test_games_returns_models_newest_first(self, storage):
        first = parse_game(game_payload(id=1, name="First"))
        second = parse_game(game_payload(id=2, name="Second"))
        storage.toggle("played", first)
        storage.toggle("played", second)
        assert [g.name for g in storage.games("played")] == ["Second", "First"]

    def test_remove_by_id(self, storage, game):
        storage.toggle("wishlist", game)
        assert storage.remove("wishlist", game.game_id) is True
        assert storage.remove("wishlist", game.game_id) is False

    def test_missing_collection_is_empty(self, storage):
        assert storage.entries("wishlist") == []
        assert storage.games("played") == []


class TestPersistence:
    def test_data_survives_a_reload(self, data_dir, game):
        first = Storage(data_dir)
        first.toggle("wishlist", game)
        first.bump_stat(STAT_GAMES_VIEWED, 3)

        second = Storage(data_dir)
        assert second.contains("wishlist", game.game_id) is True
        assert second.stats()[STAT_GAMES_VIEWED] == 3

    def test_file_lives_in_the_data_dir_not_the_cwd(self, data_dir, game, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        storage = Storage(data_dir)
        storage.toggle("wishlist", game)

        assert os.path.isfile(os.path.join(data_dir, "library.json"))
        assert not os.path.exists(tmp_path / "library.json")

    def test_written_file_is_valid_json_with_a_version(self, data_dir, game):
        storage = Storage(data_dir)
        storage.toggle("played", game)
        payload = json.loads(Path(storage.path).read_text())
        assert payload["version"] == SCHEMA_VERSION
        assert len(payload["played"]) == 1

    def test_write_leaves_no_temp_files_behind(self, data_dir, game):
        storage = Storage(data_dir)
        storage.toggle("played", game)
        leftovers = [n for n in os.listdir(data_dir) if n.startswith(".tmp-")]
        assert leftovers == []

    def test_save_reports_failure_instead_of_raising(self, data_dir, game, monkeypatch):
        storage = Storage(data_dir)
        monkeypatch.setattr(
            "gamerec.storage.atomic_write",
            lambda *_a, **_k: (_ for _ in ()).throw(OSError("disk full")),
        )
        # Toggling still updates memory; only the persistence fails.
        storage.toggle("wishlist", game)
        assert storage.save() is False


class TestResilience:
    def test_missing_file_yields_empty_library(self, data_dir):
        storage = Storage(os.path.join(data_dir, "does-not-exist"))
        assert storage.entries("wishlist") == []

    def test_malformed_json_is_quarantined_not_lost(self, data_dir):
        path = os.path.join(data_dir, "library.json")
        Path(path).write_text("{not json at all")

        storage = Storage(data_dir)
        assert storage.entries("wishlist") == []

        backups = [n for n in os.listdir(data_dir) if ".corrupt-" in n]
        assert len(backups) == 1
        assert "{not json at all" in Path(os.path.join(data_dir, backups[0])).read_text()

    def test_recovers_and_can_save_after_corruption(self, data_dir, game):
        Path(os.path.join(data_dir, "library.json")).write_text("garbage")
        storage = Storage(data_dir)
        storage.toggle("wishlist", game)
        assert Storage(data_dir).contains("wishlist", game.game_id) is True

    @pytest.mark.parametrize("payload", ["null", "[]", '"a string"', "42"])
    def test_non_object_json_yields_empty_library(self, data_dir, payload):
        Path(os.path.join(data_dir, "library.json")).write_text(payload)
        assert Storage(data_dir).entries("wishlist") == []

    def test_corrupt_rows_are_dropped_not_fatal(self, data_dir):
        Path(os.path.join(data_dir, "library.json")).write_text(
            json.dumps(
                {
                    "version": SCHEMA_VERSION,
                    "wishlist": [{"game_id": 1, "name": "Good"}, {"no": "id"}, None, "junk"],
                    "played": "not a list",
                    "stats": {"games_viewed": "many", "searches": 4},
                }
            )
        )
        storage = Storage(data_dir)
        assert [e["game_id"] for e in storage.entries("wishlist")] == [1]
        assert storage.entries("played") == []
        assert storage.stats() == {"searches": 4}

    def test_duplicate_entries_collapse_on_load(self, data_dir):
        Path(os.path.join(data_dir, "library.json")).write_text(
            json.dumps({"wishlist": [{"game_id": 5}, {"game_id": 5}]})
        )
        assert len(Storage(data_dir).entries("wishlist")) == 1


class TestMigration:
    def test_migrate_normalises_a_v1_payload(self):
        legacy = {
            "wishlist": [{"game_id": 1, "name": "A", "rating": 4.0}],
            "played": [{"game_id": 2, "name": "B"}],
            "stats": {"games_viewed": 9},
            "api_key": "should-not-survive",
        }
        result = migrate(legacy)
        assert result["version"] == SCHEMA_VERSION
        assert len(result["wishlist"]) == 1
        assert result["stats"] == {"games_viewed": 9}
        # Credentials never live in the library file.
        assert "api_key" not in result

    def test_migrate_is_total(self):
        for payload in (None, {}, [], "junk", 5):
            result = migrate(payload)
            assert result["wishlist"] == []
            assert result["version"] == SCHEMA_VERSION

    def test_import_legacy_merges_and_returns_the_key(self, data_dir, tmp_path):
        legacy_path = tmp_path / "game_recommender_config.json"
        legacy_path.write_text(
            json.dumps(
                {
                    "wishlist": [{"game_id": 11, "name": "Old Favourite"}],
                    "played": [{"game_id": 12, "name": "Old Played"}],
                    "stats": {"games_viewed": 5},
                    "api_key": "a" * 32,
                }
            )
        )
        storage = Storage(data_dir)
        found = storage.import_legacy(str(legacy_path))

        assert found == "a" * 32
        assert storage.contains("wishlist", 11) is True
        assert storage.contains("played", 12) is True
        assert storage.stats()["games_viewed"] == 5

    def test_import_legacy_runs_only_once(self, data_dir, tmp_path):
        legacy_path = tmp_path / "legacy.json"
        legacy_path.write_text(json.dumps({"stats": {"searches": 2}}))

        storage = Storage(data_dir)
        storage.import_legacy(str(legacy_path))
        storage.import_legacy(str(legacy_path))
        assert storage.stats()["searches"] == 2

    def test_import_legacy_ignores_a_missing_file(self, storage):
        assert storage.import_legacy("/definitely/not/here.json") is None

    def test_import_legacy_survives_a_corrupt_file(self, data_dir, tmp_path):
        legacy_path = tmp_path / "legacy.json"
        legacy_path.write_text("{{{")
        assert Storage(data_dir).import_legacy(str(legacy_path)) is None

    def test_import_legacy_does_not_duplicate_existing_games(self, data_dir, tmp_path, game):
        storage = Storage(data_dir)
        storage.toggle("wishlist", game)

        legacy_path = tmp_path / "legacy.json"
        legacy_path.write_text(json.dumps({"wishlist": [{"game_id": game.game_id, "name": "x"}]}))
        storage.import_legacy(str(legacy_path))

        assert len(storage.entries("wishlist")) == 1


class TestStats:
    def test_bump_stat_accumulates(self, storage):
        assert storage.bump_stat("searches") == 1
        assert storage.bump_stat("searches", 4) == 5

    def test_settings_round_trip(self, data_dir):
        storage = Storage(data_dir)
        storage.set_setting("theme", "dark")
        assert Storage(data_dir).get_setting("theme") == "dark"
        assert storage.get_setting("missing", "fallback") == "fallback"


class TestSummarise:
    def test_empty_library(self, storage):
        summary = summarise(storage)
        assert summary["wishlist_count"] == 0
        assert summary["played_count"] == 0
        assert summary["average_rating"] is None
        assert summary["average_metacritic"] is None
        assert summary["top_genres"] == []

    def test_counts_and_averages(self, storage):
        storage.toggle("played", parse_game(game_payload(id=1, rating=4.0, metacritic=90)))
        storage.toggle("played", parse_game(game_payload(id=2, rating=5.0, metacritic=80)))
        storage.toggle("wishlist", parse_game(game_payload(id=3, rating=3.0)))
        storage.bump_stat(STAT_GAMES_VIEWED, 7)

        summary = summarise(storage)
        assert summary["played_count"] == 2
        assert summary["wishlist_count"] == 1
        assert summary["games_viewed"] == 7
        assert summary["average_rating"] == 4.5
        assert summary["average_metacritic"] == 85

    def test_top_genres_are_ranked(self, storage):
        storage.toggle(
            "played", parse_game(game_payload(id=1, genres=[{"name": "RPG"}, {"name": "Indie"}]))
        )
        storage.toggle("played", parse_game(game_payload(id=2, genres=[{"name": "RPG"}])))
        assert summarise(storage)["top_genres"][0] == "RPG"

    def test_ignores_zero_ratings_when_averaging(self, storage):
        storage.toggle("played", parse_game(game_payload(id=1, rating=4.0)))
        storage.toggle("played", parse_game(game_payload(id=2, rating=0)))
        assert summarise(storage)["average_rating"] == 4.0

    def test_no_metacritic_means_none(self, storage):
        storage.toggle("played", parse_game(game_payload(id=1, metacritic=None)))
        assert summarise(storage)["average_metacritic"] is None
