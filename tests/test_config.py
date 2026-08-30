"""Tests for API-key resolution, storage and the no-bundled-key guarantee."""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from gamerec import config
from gamerec.config import (
    ENV_VAR,
    SOURCE_ENV,
    SOURCE_SAVED,
    ApiKeyStore,
    atomic_write,
    default_data_dir,
    looks_like_api_key,
    resolve_api_key,
)

VALID_KEY = "0123456789abcdef0123456789abcdef"


class TestNoBundledKey:
    """The repository must never ship a working credential."""

    def test_resolution_returns_nothing_when_unconfigured(self, data_dir):
        resolved = resolve_api_key(data_dir=data_dir, env={})
        assert resolved.key is None
        assert resolved.source is None
        assert bool(resolved) is False

    def test_config_module_defines_no_default_key(self):
        for name, value in vars(config).items():
            if isinstance(value, str) and looks_like_api_key(value):
                raise AssertionError(f"config.{name} looks like a bundled API key")

    def test_source_files_contain_no_32_char_hex_literals(self):
        import re

        root = Path(__file__).resolve().parents[1]
        pattern = re.compile(r"['\"][0-9a-f]{32}['\"]")
        offenders = []
        for path in root.rglob("*.py"):
            if any(part in {".venv", "venv", "build", "tests"} for part in path.parts):
                continue
            if pattern.search(path.read_text(encoding="utf-8")):
                offenders.append(str(path.relative_to(root)))
        assert offenders == [], f"possible hard-coded key in: {offenders}"


class TestResolutionOrder:
    def test_environment_wins(self, data_dir):
        ApiKeyStore(data_dir).write("s" * 32)
        resolved = resolve_api_key(data_dir=data_dir, env={ENV_VAR: VALID_KEY})
        assert resolved.key == VALID_KEY
        assert resolved.source == SOURCE_ENV

    def test_saved_key_is_used_when_no_environment(self, data_dir):
        ApiKeyStore(data_dir).write(VALID_KEY)
        resolved = resolve_api_key(data_dir=data_dir, env={})
        assert resolved.key == VALID_KEY
        assert resolved.source == SOURCE_SAVED

    def test_blank_environment_value_is_ignored(self, data_dir):
        ApiKeyStore(data_dir).write(VALID_KEY)
        resolved = resolve_api_key(data_dir=data_dir, env={ENV_VAR: "   "})
        assert resolved.source == SOURCE_SAVED

    def test_environment_value_is_stripped(self, data_dir):
        resolved = resolve_api_key(data_dir=data_dir, env={ENV_VAR: f"  {VALID_KEY}\n"})
        assert resolved.key == VALID_KEY

    def test_env_supplied_keys_are_not_editable_in_app(self, data_dir):
        resolved = resolve_api_key(data_dir=data_dir, env={ENV_VAR: VALID_KEY})
        assert resolved.is_editable is False
        assert resolve_api_key(data_dir=data_dir, env={}).is_editable is True


class TestApiKeyStore:
    def test_round_trip(self, data_dir):
        store = ApiKeyStore(data_dir)
        assert store.read() is None
        store.write(VALID_KEY)
        assert store.read() == VALID_KEY

    def test_clear_removes_the_key(self, data_dir):
        store = ApiKeyStore(data_dir)
        store.write(VALID_KEY)
        store.clear()
        assert store.read() is None

    def test_clear_is_safe_when_absent(self, data_dir):
        ApiKeyStore(data_dir).clear()  # must not raise

    def test_refuses_to_store_blank(self, data_dir):
        with pytest.raises(ValueError):
            ApiKeyStore(data_dir).write("   ")

    def test_value_is_stripped(self, data_dir):
        store = ApiKeyStore(data_dir)
        store.write(f"  {VALID_KEY}  ")
        assert store.read() == VALID_KEY

    def test_lives_apart_from_the_library_file(self, data_dir):
        store = ApiKeyStore(data_dir)
        store.write(VALID_KEY)
        assert os.path.basename(store.path) == "credentials.json"

    @pytest.mark.skipif(os.name == "nt", reason="POSIX permissions only")
    def test_file_is_not_world_readable(self, data_dir):
        store = ApiKeyStore(data_dir)
        store.write(VALID_KEY)
        assert oct(os.stat(store.path).st_mode & 0o777) == "0o600"

    @pytest.mark.parametrize("content", ["not json", "[]", "null", '{"api_key": ""}', "{}"])
    def test_unreadable_or_empty_files_yield_none(self, data_dir, content):
        path = os.path.join(data_dir, "credentials.json")
        Path(path).write_text(content)
        assert ApiKeyStore(data_dir).read() is None

    def test_missing_directory_is_created(self, tmp_path):
        target = str(tmp_path / "nested" / "deeper")
        store = ApiKeyStore(target)
        store.write(VALID_KEY)
        assert store.read() == VALID_KEY


class TestAtomicWrite:
    def test_replaces_content_completely(self, tmp_path):
        path = str(tmp_path / "f.json")
        atomic_write(path, json.dumps({"a": 1}))
        atomic_write(path, json.dumps({"b": 2}))
        assert json.loads(Path(path).read_text()) == {"b": 2}

    def test_original_survives_a_failed_write(self, tmp_path, monkeypatch):
        path = tmp_path / "f.json"
        atomic_write(str(path), '{"good": true}')

        def _boom(*_args, **_kwargs):
            raise OSError("interrupted")

        monkeypatch.setattr(os, "replace", _boom)
        with pytest.raises(OSError):
            atomic_write(str(path), '{"partial"')

        assert json.loads(path.read_text()) == {"good": True}
        assert [n for n in os.listdir(tmp_path) if n.startswith(".tmp-")] == []


class TestLooksLikeApiKey:
    @pytest.mark.parametrize("valid", [VALID_KEY, VALID_KEY.upper(), f" {VALID_KEY} "])
    def test_accepts_rawg_shaped_keys(self, valid):
        assert looks_like_api_key(valid) is True

    @pytest.mark.parametrize(
        "invalid",
        ["", "   ", "short", VALID_KEY[:-1], VALID_KEY + "0", "z" * 32, None],
    )
    def test_rejects_everything_else(self, invalid):
        assert looks_like_api_key(invalid) is False


class TestDotenv:
    def test_missing_file_is_a_no_op(self, tmp_path):
        assert config.load_dotenv(str(tmp_path / "nope.env")) is False

    def test_reads_a_real_env_file(self, tmp_path, monkeypatch):
        pytest.importorskip("dotenv")
        env_path = tmp_path / ".env"
        env_path.write_text(f"{ENV_VAR}={VALID_KEY}\n")
        monkeypatch.delenv(ENV_VAR, raising=False)

        assert config.load_dotenv(str(env_path)) is True
        assert os.environ[ENV_VAR] == VALID_KEY

    def test_does_not_override_a_real_environment_variable(self, tmp_path, monkeypatch):
        pytest.importorskip("dotenv")
        env_path = tmp_path / ".env"
        env_path.write_text(f"{ENV_VAR}=from-file\n")
        monkeypatch.setenv(ENV_VAR, VALID_KEY)

        config.load_dotenv(str(env_path))
        assert os.environ[ENV_VAR] == VALID_KEY


class TestDefaultDataDir:
    def test_is_absolute_and_named(self):
        directory = default_data_dir()
        assert os.path.isabs(directory)
        assert directory.endswith("game-recommender")

    def test_is_not_the_working_directory(self):
        assert os.path.abspath(default_data_dir()) != os.path.abspath(os.getcwd())
