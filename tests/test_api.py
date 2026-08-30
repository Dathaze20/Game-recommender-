"""Tests for the RAWG client. Every request is mocked — no live API calls."""

from __future__ import annotations

import threading

import pytest
import requests
from conftest import FakeResponse, FakeSession, game_payload, list_payload

from gamerec.api import RawgClient
from gamerec.errors import (
    InvalidApiKey,
    MissingApiKey,
    NetworkError,
    NotFound,
    RateLimited,
    ServiceError,
)


class TestAuth:
    def test_missing_key_raises_before_any_request(self, make_client):
        client = make_client(FakeResponse(200, list_payload()), api_key=None)
        with pytest.raises(MissingApiKey):
            client.games()
        # The important part: nothing was sent.
        assert client.test_session.calls == []

    def test_blank_key_is_treated_as_missing(self, make_client):
        client = make_client(FakeResponse(200, list_payload()), api_key="   ")
        assert client.has_key is False
        with pytest.raises(MissingApiKey):
            client.games()

    def test_key_is_attached_to_every_request(self, make_client):
        client = make_client(FakeResponse(200, list_payload()))
        client.games({"page_size": 5})
        params = client.test_session.calls[0]["params"]
        assert params["key"] == "k" * 32
        assert params["page_size"] == 5

    def test_401_raises_invalid_key_without_retrying(self, make_client):
        client = make_client(FakeResponse(401))
        with pytest.raises(InvalidApiKey):
            client.games()
        assert len(client.test_session.calls) == 1
        assert client.test_slept == []

    def test_403_is_also_an_invalid_key(self, make_client):
        client = make_client(FakeResponse(403))
        with pytest.raises(InvalidApiKey):
            client.games()

    def test_validate_key_succeeds(self, make_client):
        client = make_client(FakeResponse(200, list_payload([game_payload()])))
        assert client.validate_key() is True

    def test_validate_key_propagates_rejection(self, make_client):
        client = make_client(FakeResponse(401))
        with pytest.raises(InvalidApiKey):
            client.validate_key()

    def test_validate_key_distinguishes_network_failure(self, make_client):
        client = make_client(requests.ConnectionError("offline"), max_retries=0)
        with pytest.raises(NetworkError):
            client.validate_key()

    def test_changing_the_key_clears_the_cache(self, make_client):
        client = make_client([FakeResponse(200, {"a": 1}), FakeResponse(200, {"a": 2})])
        assert client.games() == {"a": 1}
        client.set_api_key("z" * 32)
        assert client.games() == {"a": 2}
        assert len(client.test_session.calls) == 2


class TestErrorMapping:
    def test_404_is_not_found(self, make_client):
        client = make_client(FakeResponse(404))
        with pytest.raises(NotFound):
            client.game(1)
        assert len(client.test_session.calls) == 1

    def test_unexpected_status_is_a_service_error(self, make_client):
        client = make_client(FakeResponse(418))
        with pytest.raises(ServiceError):
            client.games()

    def test_non_json_body_is_a_service_error(self, make_client):
        client = make_client(FakeResponse(200, raise_on_json=True))
        with pytest.raises(ServiceError):
            client.games()

    def test_timeout_becomes_network_error(self, make_client):
        client = make_client(requests.Timeout("slow"), max_retries=0)
        with pytest.raises(NetworkError):
            client.games()

    def test_every_error_carries_user_facing_copy(self, make_client):
        client = make_client(FakeResponse(401))
        with pytest.raises(InvalidApiKey) as excinfo:
            client.games()
        message = excinfo.value.user_message
        assert message and "Traceback" not in message


class TestRetries:
    def test_retries_server_errors_then_succeeds(self, make_client):
        client = make_client(
            [FakeResponse(500), FakeResponse(503), FakeResponse(200, {"ok": True})]
        )
        assert client.games() == {"ok": True}
        assert len(client.test_session.calls) == 3
        assert len(client.test_slept) == 2

    def test_gives_up_after_max_retries(self, make_client):
        client = make_client([FakeResponse(500)] * 5, max_retries=2)
        with pytest.raises(ServiceError):
            client.games()
        assert len(client.test_session.calls) == 3  # 1 attempt + 2 retries

    def test_backoff_grows(self, make_client):
        client = make_client([FakeResponse(500)] * 5, max_retries=2)
        with pytest.raises(ServiceError):
            client.games()
        assert client.test_slept == sorted(client.test_slept)
        assert client.test_slept[0] < client.test_slept[1]

    def test_network_errors_are_retried(self, make_client):
        client = make_client(
            [requests.ConnectionError("boom"), FakeResponse(200, {"ok": True})]
        )
        assert client.games() == {"ok": True}

    def test_permanent_errors_are_never_retried(self, make_client):
        for response in (FakeResponse(401), FakeResponse(404)):
            client = make_client([response] * 5)
            with pytest.raises((InvalidApiKey, NotFound)):
                client.games()
            assert len(client.test_session.calls) == 1

    def test_zero_retries_is_honoured(self, make_client):
        client = make_client([FakeResponse(500)] * 3, max_retries=0)
        with pytest.raises(ServiceError):
            client.games()
        assert len(client.test_session.calls) == 1


class TestRateLimiting:
    def test_429_is_retried_and_can_recover(self, make_client):
        client = make_client([FakeResponse(429), FakeResponse(200, {"ok": True})])
        assert client.games() == {"ok": True}

    def test_retry_after_header_is_respected(self, make_client):
        client = make_client(
            [FakeResponse(429, headers={"Retry-After": "3"}), FakeResponse(200, {})]
        )
        client.games()
        assert client.test_slept == [3.0]

    def test_long_retry_after_surfaces_immediately(self, make_client):
        client = make_client(FakeResponse(429, headers={"Retry-After": "600"}))
        with pytest.raises(RateLimited) as excinfo:
            client.games()
        assert excinfo.value.retry_after == 600.0
        # We do not block a worker thread for ten minutes.
        assert client.test_slept == []

    def test_unparseable_retry_after_falls_back_to_backoff(self, make_client):
        client = make_client(
            [FakeResponse(429, headers={"Retry-After": "Wed, 21 Oct 2015 07:28:00 GMT"}),
             FakeResponse(200, {})]
        )
        client.games()
        assert client.test_slept and client.test_slept[0] > 0

    def test_exhausted_rate_limit_raises_rate_limited(self, make_client):
        client = make_client([FakeResponse(429)] * 5, max_retries=1)
        with pytest.raises(RateLimited):
            client.games()


class TestCaching:
    def test_identical_requests_hit_the_cache(self, make_client):
        client = make_client([FakeResponse(200, {"n": 1}), FakeResponse(200, {"n": 2})])
        assert client.games({"page_size": 3}) == {"n": 1}
        assert client.games({"page_size": 3}) == {"n": 1}
        assert len(client.test_session.calls) == 1

    def test_different_params_are_separate_entries(self, make_client):
        client = make_client([FakeResponse(200, {"n": 1}), FakeResponse(200, {"n": 2})])
        assert client.games({"page_size": 3}) == {"n": 1}
        assert client.games({"page_size": 4}) == {"n": 2}

    def test_cache_expires(self, make_client):
        client = make_client(
            [FakeResponse(200, {"n": 1}), FakeResponse(200, {"n": 2})], cache_ttl=10
        )
        assert client.games() == {"n": 1}
        client.test_now["t"] = 11
        assert client.games() == {"n": 2}

    def test_ttl_zero_bypasses_the_cache(self, make_client):
        client = make_client([FakeResponse(200, {"n": 1}), FakeResponse(200, {"n": 2})])
        assert client.get("games", ttl=0) == {"n": 1}
        assert client.get("games", ttl=0) == {"n": 2}

    def test_clear_cache(self, make_client):
        client = make_client([FakeResponse(200, {"n": 1}), FakeResponse(200, {"n": 2})])
        client.games()
        client.clear_cache()
        assert client.games() == {"n": 2}

    def test_the_api_key_is_not_part_of_the_cache_key(self, make_client):
        client = make_client(FakeResponse(200, {"n": 1}))
        key_a = client._cache_key("games", {"page_size": 1, "key": "aaa"})
        key_b = client._cache_key("games", {"page_size": 1, "key": "bbb"})
        assert key_a == key_b


class TestDeduplication:
    def test_concurrent_identical_requests_send_one_call(self):
        """Two threads asking for the same row must not both hit RAWG."""
        started = threading.Event()
        release = threading.Event()

        class BlockingSession(FakeSession):
            def get(self, url, params=None, timeout=None):
                self.calls.append({"url": url, "params": dict(params or {})})
                started.set()
                release.wait(timeout=5)
                return FakeResponse(200, {"ok": True})

        session = BlockingSession()
        client = RawgClient(api_key="k" * 32, session=session)
        results = []

        def _call():
            results.append(client.games({"page_size": 1}))

        first = threading.Thread(target=_call)
        first.start()
        assert started.wait(timeout=5)

        second = threading.Thread(target=_call)
        second.start()
        # Give the follower a moment to reach the wait.
        second.join(timeout=0.2)

        release.set()
        first.join(timeout=5)
        second.join(timeout=5)

        assert results == [{"ok": True}, {"ok": True}]
        assert len(session.calls) == 1


class TestEndpoints:
    @pytest.mark.parametrize(
        ("call", "expected_path"),
        [
            (lambda c: c.game(42), "games/42"),
            (lambda c: c.screenshots(42), "games/42/screenshots"),
            (lambda c: c.stores(42), "games/42/stores"),
            (lambda c: c.suggested(42), "games/42/suggested"),
            (lambda c: c.game_series(42), "games/42/game-series"),
        ],
    )
    def test_endpoint_urls(self, make_client, call, expected_path):
        client = make_client(FakeResponse(200, {}))
        call(client)
        assert client.test_session.calls[0]["url"].endswith(expected_path)

    def test_search_passes_the_query(self, make_client):
        client = make_client(FakeResponse(200, list_payload()))
        client.search("halo", page_size=7)
        params = client.test_session.calls[0]["params"]
        assert params["search"] == "halo"
        assert params["page_size"] == 7

    def test_close_closes_the_session(self, make_client):
        client = make_client(FakeResponse(200, {}))
        client.close()
        assert client.test_session.closed is True
