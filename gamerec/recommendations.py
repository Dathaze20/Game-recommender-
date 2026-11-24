"""Similar-game lookup.

The original three-step fallback is preserved, because it degrades in the right
order — from "RAWG thinks these are alike" down to "at least it's the same
genre":

1. ``/games/{id}/suggested`` — RAWG's own recommendation engine;
2. ``/games/{id}/game-series`` — other entries in the same series;
3. top-rated games sharing the subject's primary genre.

Each step is attempted independently: a failure in one does not abort the
chain, so a 404 on ``suggested`` (common for obscure titles) still yields
series or genre results.
"""

from __future__ import annotations

import logging
from typing import Any, Protocol

from .constants import GENRE_SLUGS, SIMILAR_PAGE_SIZE
from .errors import InvalidApiKey, MissingApiKey, RawgError
from .models import GameDetails, parse_games
from .utils import dedupe_by_id

log = logging.getLogger(__name__)


class SupportsSimilar(Protocol):
    """The slice of :class:`~gamerec.api.RawgClient` this module needs."""

    def suggested(self, game_id: int, page_size: int = ...) -> Any: ...

    def game_series(self, game_id: int, page_size: int = ...) -> Any: ...

    def games(self, params: dict | None = ..., ttl: float | None = ...) -> Any: ...


def genre_slug(genre_name: str) -> str | None:
    """Map a display genre name to the slug RAWG's filter expects."""
    if not genre_name:
        return None
    known = GENRE_SLUGS.get(genre_name)
    if known:
        return known
    # Unknown genres are slugified rather than dropped; RAWG's slugs are
    # lowercase-hyphenated, so this is right far more often than it is wrong.
    return genre_name.strip().lower().replace(" ", "-") or None


def similar_games(
    client: SupportsSimilar,
    game: GameDetails,
    limit: int = 10,
) -> list[GameDetails]:
    """Return games similar to ``game``, newest strategy first.

    Never raises for ordinary API trouble — an empty list means "we tried and
    found nothing", which the UI renders as an empty state. A missing or
    rejected key does propagate, because that is a configuration problem the
    user has to fix rather than a per-game miss.
    """
    if not game or not game.game_id:
        return []

    for strategy in (_from_suggested, _from_series, _from_genre):
        try:
            results = strategy(client, game)
        except (MissingApiKey, InvalidApiKey):
            raise
        except RawgError as exc:
            log.info("Similar-games step %s failed: %s", strategy.__name__, exc)
            continue
        cleaned = dedupe_by_id(results, exclude_id=game.game_id)
        if cleaned:
            return cleaned[:limit]
    return []


def _from_suggested(client: SupportsSimilar, game: GameDetails) -> list[GameDetails]:
    return parse_games(client.suggested(game.game_id, page_size=SIMILAR_PAGE_SIZE))


def _from_series(client: SupportsSimilar, game: GameDetails) -> list[GameDetails]:
    return parse_games(client.game_series(game.game_id, page_size=SIMILAR_PAGE_SIZE))


def _from_genre(client: SupportsSimilar, game: GameDetails) -> list[GameDetails]:
    if not game.genres:
        return []
    slug = genre_slug(game.genres[0])
    if not slug:
        return []
    payload = client.games(
        {"genres": slug, "page_size": SIMILAR_PAGE_SIZE, "ordering": "-rating"}
    )
    return parse_games(payload)
