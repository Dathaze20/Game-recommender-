"""Game data models and RAWG payload parsing.

Parsing is deliberately total: RAWG sends ``null`` where lists are documented,
omits fields on list endpoints that exist on detail endpoints, and occasionally
returns partially-populated nested objects. Every helper here degrades to a
sensible default rather than raising, so one odd record cannot blank out a row.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .constants import store_style
from .utils import as_dict, as_list, safe_float, safe_int, safe_str, strip_html

#: Bumped when the saved-game dict shape changes so old data can be migrated.
SAVED_GAME_VERSION = 1


@dataclass
class StoreLink:
    """A storefront entry for a game.

    ``url`` is ``None`` unless RAWG actually gave us one — the UI uses that to
    tell an openable link apart from an informational badge. URLs are never
    synthesised from a store domain.
    """

    store_id: int | None
    name: str
    url: str | None = None

    @property
    def actionable(self) -> bool:
        return bool(self.url)

    @property
    def color(self):
        return store_style(self.store_id, self.name).color


@dataclass
class GameDetails:
    """Everything the UI needs about a single game."""

    game_id: int = 0
    name: str = "Unknown"
    description: str = ""
    release_date: str = ""
    background_image: str = ""
    rating: float = 0.0
    metacritic: int | None = None
    playtime: int = 0
    esrb: str = ""
    genres: list[str] = field(default_factory=list)
    platforms: list[str] = field(default_factory=list)
    stores: list[StoreLink] = field(default_factory=list)
    screenshots: list[str] = field(default_factory=list)
    developers: list[str] = field(default_factory=list)
    publishers: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)

    @property
    def has_detail(self) -> bool:
        """True once the full detail endpoint has enriched this record."""
        return bool(self.description or self.developers or self.publishers)


def _names(entries: Any, key: str = "name", limit: int = 0) -> list[str]:
    """Pull ``key`` out of a list of dicts, skipping malformed entries."""
    out: list[str] = []
    for entry in as_list(entries):
        name = safe_str(as_dict(entry).get(key))
        if name and name not in out:
            out.append(name)
        if limit and len(out) >= limit:
            break
    return out


def _platform_names(entries: Any) -> list[str]:
    """RAWG nests platforms as ``[{"platform": {"name": ...}}, ...]``."""
    out: list[str] = []
    for entry in as_list(entries):
        item = as_dict(entry)
        nested = as_dict(item.get("platform"))
        name = safe_str(nested.get("name")) or safe_str(item.get("name"))
        if name and name not in out:
            out.append(name)
    return out


def _description(payload: dict[str, Any]) -> str:
    """Prefer the plain-text description, else de-tag the HTML one."""
    raw = safe_str(payload.get("description_raw"))
    if raw:
        return raw
    return strip_html(payload.get("description"))


def parse_store_links(payload: Any) -> list[StoreLink]:
    """Parse the ``stores`` array embedded in a game payload.

    The embedded array reliably names the storefronts but usually carries an
    empty ``url``; :func:`parse_store_urls` fills those in from the dedicated
    ``/games/{id}/stores`` endpoint.
    """
    links: list[StoreLink] = []
    seen: set = set()
    for entry in as_list(payload):
        item = as_dict(entry)
        store = as_dict(item.get("store"))
        store_id = safe_int(store.get("id"))
        name = safe_str(store.get("name")) or store_style(store_id).name
        if store_id in seen:
            continue
        seen.add(store_id)
        url = safe_str(item.get("url")) or None
        links.append(StoreLink(store_id=store_id, name=name, url=url))
    return links


def parse_store_urls(payload: Any) -> dict[int, str]:
    """Map ``store_id -> url`` from the ``/games/{id}/stores`` response.

    Only URLs RAWG actually returned are included; nothing is fabricated.
    """
    results = as_list(as_dict(payload).get("results")) if isinstance(payload, dict) else []
    urls: dict[int, str] = {}
    for entry in results:
        item = as_dict(entry)
        store_id = safe_int(item.get("store_id"))
        url = safe_str(item.get("url"))
        if store_id is not None and url.startswith(("http://", "https://")):
            urls.setdefault(store_id, url)
    return urls


def apply_store_urls(game: GameDetails, urls: dict[int, str]) -> GameDetails:
    """Attach real storefront URLs to a game, in place."""
    for link in game.stores:
        if not link.url and link.store_id in urls:
            link.url = urls[link.store_id]
    return game


def parse_screenshots(payload: Any) -> list[str]:
    """Collect image URLs from either ``short_screenshots`` or ``/screenshots``."""
    if isinstance(payload, dict):
        entries = as_list(payload.get("results")) or as_list(payload.get("short_screenshots"))
    else:
        entries = as_list(payload)
    out: list[str] = []
    for entry in entries:
        url = safe_str(as_dict(entry).get("image"))
        if url and url not in out:
            out.append(url)
    return out


def parse_game(payload: Any) -> GameDetails:
    """Build a :class:`GameDetails` from any RAWG game object."""
    data = as_dict(payload)
    esrb = as_dict(data.get("esrb_rating"))
    screenshots = parse_screenshots(data.get("screenshots")) or parse_screenshots(
        data.get("short_screenshots")
    )
    return GameDetails(
        game_id=safe_int(data.get("id"), 0) or 0,
        name=safe_str(data.get("name")) or "Unknown",
        description=_description(data),
        release_date=safe_str(data.get("released")),
        background_image=safe_str(data.get("background_image")),
        rating=safe_float(data.get("rating")),
        metacritic=safe_int(data.get("metacritic")),
        playtime=safe_int(data.get("playtime"), 0) or 0,
        esrb=safe_str(esrb.get("name")),
        genres=_names(data.get("genres")),
        platforms=_platform_names(data.get("platforms")),
        stores=parse_store_links(data.get("stores")),
        screenshots=screenshots,
        developers=_names(data.get("developers")),
        publishers=_names(data.get("publishers")),
        tags=_names(data.get("tags"), limit=10),
    )


def parse_games(payload: Any) -> list[GameDetails]:
    """Parse a paginated ``{"results": [...]}`` list response.

    Records without a usable id are dropped: they cannot be opened or saved.
    """
    entries = as_list(payload.get("results")) if isinstance(payload, dict) else as_list(payload)
    games = [parse_game(entry) for entry in entries]
    return [g for g in games if g.game_id]


def game_to_saved(game: GameDetails) -> dict[str, Any]:
    """Serialise the subset of a game worth persisting locally.

    Descriptions, screenshots and tags are intentionally dropped — they are
    large, they go stale, and they are re-fetched on demand.
    """
    return {
        "version": SAVED_GAME_VERSION,
        "game_id": int(game.game_id),
        "name": game.name,
        "background_image": game.background_image or "",
        "rating": float(game.rating or 0.0),
        "release_date": game.release_date or "",
        "metacritic": game.metacritic,
        "genres": list(game.genres or []),
    }


def saved_to_game(data: Any) -> GameDetails | None:
    """Rebuild a :class:`GameDetails` from persisted data.

    Returns ``None`` for entries that are unusable (no id), which lets the
    storage layer quietly drop corrupt rows instead of crashing a screen.
    """
    item = as_dict(data)
    game_id = safe_int(item.get("game_id"), 0) or 0
    if not game_id:
        return None
    return GameDetails(
        game_id=game_id,
        name=safe_str(item.get("name")) or "Unknown",
        background_image=safe_str(item.get("background_image")),
        rating=safe_float(item.get("rating")),
        release_date=safe_str(item.get("release_date")),
        metacritic=safe_int(item.get("metacritic")),
        genres=[safe_str(g) for g in as_list(item.get("genres")) if safe_str(g)],
    )
