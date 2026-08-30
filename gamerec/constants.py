"""Static catalog metadata: curated collections, platforms and storefronts.

Nothing here talks to the network — it is the fixed vocabulary the rest of the
app is built from.
"""

from __future__ import annotations

from dataclasses import dataclass, field

APP_NAME = "Game Recommender"
BASE_URL = "https://api.rawg.io/api"
RAWG_SIGNUP_URL = "https://rawg.io/apikey"

#: How many collections are requested before the app waits for the user to
#: scroll. Keeping this small is what stops the app firing ~36 requests at
#: launch.
INITIAL_CATEGORY_CHUNK = 3
CATEGORY_CHUNK = 3

#: Results requested per collection row.
ROW_PAGE_SIZE = 20
SEARCH_PAGE_SIZE = 30
SIMILAR_PAGE_SIZE = 12
SCREENSHOT_PAGE_SIZE = 8


@dataclass(frozen=True)
class Category:
    """One curated collection row."""

    key: str
    title: str
    params: dict[str, object] = field(default_factory=dict)
    subtitle: str = ""

    def request_params(self) -> dict[str, object]:
        """A fresh copy so callers can mutate without corrupting the catalog."""
        params = dict(self.params)
        params.setdefault("page_size", ROW_PAGE_SIZE)
        return params


#: Ordered most-valuable-first: the first few are what a new user sees.
CATEGORIES: tuple[Category, ...] = (
    Category("trending", "Trending Now", {"ordering": "-added"},
             "What everyone is adding right now"),
    Category("top-rated", "Top Rated", {"ordering": "-rating", "metacritic": "80,100"},
             "Critically acclaimed and player approved"),
    Category("all-time", "All-Time Greatest", {"metacritic": "95,100", "ordering": "-metacritic"},
             "Metacritic 95 and above"),
    Category("perfect", "Perfect Scores", {"metacritic": "98,100", "ordering": "-metacritic"},
             "The rarest scores ever awarded"),
    Category("new", "New Releases", {"ordering": "-released"},
             "Fresh on the shelves"),
    Category("ps5", "PlayStation 5", {"platforms": 187, "ordering": "-added"}),
    Category("xbox-series", "Xbox Series X|S", {"platforms": 186, "ordering": "-added"}),
    Category("switch", "Nintendo Switch", {"platforms": 7, "ordering": "-added"}),
    Category("pc", "PC Games", {"platforms": 4, "ordering": "-rating"}),
    Category("best-rpg", "Highest Rated RPGs",
             {"genres": "role-playing-games-rpg", "metacritic": "85,100",
              "ordering": "-metacritic"},
             "Long campaigns, high scores"),
    Category(
        "japanese", "Japanese Masterpieces",
        {"developers": "nintendo,square-enix,capcom,konami,fromsoftware,atlus,"
                       "sega,bandai-namco-entertainment,platinum-games",
         "ordering": "-metacritic"},
        "Landmark releases from Japan's biggest studios",
    ),
    Category("action", "Best Action Games", {"genres": "action", "ordering": "-rating"}),
    Category("rpg", "RPG Adventures",
             {"genres": "role-playing-games-rpg", "ordering": "-rating"}),
    Category("shooter", "Shooters", {"genres": "shooter", "ordering": "-rating"}),
    Category("strategy", "Strategy & Tactics", {"genres": "strategy", "ordering": "-rating"}),
    Category("racing", "Racing Games", {"genres": "racing", "ordering": "-rating"}),
    Category("fighting", "Fighting Games", {"genres": "fighting", "ordering": "-rating"}),
    Category("platformer", "Platformers", {"genres": "platformer", "ordering": "-rating"}),
    Category("sports", "Sports Games", {"genres": "sports", "ordering": "-added"}),
    Category("indie", "Indie Gems", {"genres": "indie", "ordering": "-rating"}),
    Category("ps4", "PlayStation 4", {"platforms": 18, "ordering": "-rating"}),
    Category("xbox-one", "Xbox One", {"platforms": 1, "ordering": "-rating"}),
    Category("genesis", "Retro: Sega Genesis", {"platforms": 167, "ordering": "-rating"}),
    Category("neogeo", "Retro: Neo Geo", {"platforms": 12, "ordering": "-rating"}),
    Category("snes", "Retro: SNES", {"platforms": 79, "ordering": "-rating"}),
    Category("nes", "Retro: NES", {"platforms": 49, "ordering": "-rating"}),
    Category("n64", "Retro: Nintendo 64", {"platforms": 83, "ordering": "-rating"}),
    Category("dreamcast", "Retro: Dreamcast", {"platforms": 106, "ordering": "-rating"}),
    Category("ps1", "Retro: PlayStation 1", {"platforms": 27, "ordering": "-rating"}),
    Category("ps2", "Retro: PlayStation 2", {"platforms": 15, "ordering": "-rating"}),
    Category("gamecube", "Retro: GameCube", {"platforms": 105, "ordering": "-rating"}),
    Category("gba", "Retro: Game Boy Advance", {"platforms": 24, "ordering": "-rating"}),
    Category("atari", "Retro: Atari 2600", {"platforms": 31, "ordering": "-rating"}),
    Category("saturn", "Retro: Sega Saturn", {"platforms": 107, "ordering": "-rating"}),
    Category("ios", "Mobile: iOS", {"platforms": 3, "ordering": "-rating"}),
    Category("android", "Mobile: Android", {"platforms": 21, "ordering": "-rating"}),
)

CATEGORIES_BY_KEY: dict[str, Category] = {c.key: c for c in CATEGORIES}


@dataclass(frozen=True)
class PlatformStyle:
    """Short badge label plus brand colour for a platform."""

    label: str
    color: tuple[float, float, float]


#: Canonical RAWG platform name -> badge style.
PLATFORM_BADGES: dict[str, PlatformStyle] = {
    "PlayStation 5": PlatformStyle("PS5", (0.00, 0.32, 0.73)),
    "PlayStation 4": PlatformStyle("PS4", (0.00, 0.27, 0.63)),
    "PlayStation 3": PlatformStyle("PS3", (0.00, 0.22, 0.53)),
    "PlayStation 2": PlatformStyle("PS2", (0.15, 0.15, 0.55)),
    "PlayStation": PlatformStyle("PS1", (0.40, 0.40, 0.48)),
    "PS Vita": PlatformStyle("Vita", (0.00, 0.22, 0.53)),
    "PSP": PlatformStyle("PSP", (0.25, 0.25, 0.45)),
    "Xbox Series S/X": PlatformStyle("XSX", (0.07, 0.49, 0.04)),
    "Xbox One": PlatformStyle("XB1", (0.04, 0.38, 0.03)),
    "Xbox 360": PlatformStyle("360", (0.06, 0.42, 0.03)),
    "Xbox": PlatformStyle("Xbox", (0.04, 0.38, 0.03)),
    "Nintendo Switch": PlatformStyle("NSW", (0.85, 0.10, 0.12)),
    "Wii U": PlatformStyle("WiiU", (0.00, 0.47, 0.78)),
    "Wii": PlatformStyle("Wii", (0.45, 0.48, 0.55)),
    "GameCube": PlatformStyle("GCN", (0.38, 0.20, 0.55)),
    "Nintendo 64": PlatformStyle("N64", (0.20, 0.50, 0.20)),
    "Nintendo DS": PlatformStyle("NDS", (0.45, 0.45, 0.50)),
    "Nintendo DSi": PlatformStyle("DSi", (0.42, 0.42, 0.48)),
    "Nintendo 3DS": PlatformStyle("3DS", (0.75, 0.12, 0.14)),
    "Game Boy Advance": PlatformStyle("GBA", (0.40, 0.20, 0.60)),
    "Game Boy Color": PlatformStyle("GBC", (0.30, 0.30, 0.60)),
    "Game Boy": PlatformStyle("GB", (0.30, 0.45, 0.20)),
    "SNES": PlatformStyle("SNES", (0.30, 0.30, 0.70)),
    "NES": PlatformStyle("NES", (0.62, 0.20, 0.20)),
    "PC": PlatformStyle("PC", (0.35, 0.36, 0.46)),
    "macOS": PlatformStyle("Mac", (0.33, 0.33, 0.36)),
    "Linux": PlatformStyle("LNX", (0.78, 0.52, 0.10)),
    "iOS": PlatformStyle("iOS", (0.30, 0.30, 0.34)),
    "Android": PlatformStyle("AND", (0.24, 0.60, 0.18)),
    "Genesis": PlatformStyle("GEN", (0.12, 0.12, 0.58)),
    "SEGA Master System": PlatformStyle("SMS", (0.12, 0.12, 0.48)),
    "SEGA Saturn": PlatformStyle("SAT", (0.33, 0.33, 0.52)),
    "SEGA CD": PlatformStyle("SCD", (0.16, 0.16, 0.50)),
    "SEGA 32X": PlatformStyle("32X", (0.20, 0.20, 0.52)),
    "Game Gear": PlatformStyle("GG", (0.20, 0.24, 0.44)),
    "Dreamcast": PlatformStyle("DC", (0.30, 0.45, 0.70)),
    "Neo Geo": PlatformStyle("NGeo", (0.58, 0.15, 0.15)),
    "Atari 2600": PlatformStyle("2600", (0.55, 0.35, 0.10)),
    "Atari 7800": PlatformStyle("7800", (0.50, 0.30, 0.10)),
    "Atari 5200": PlatformStyle("5200", (0.48, 0.28, 0.10)),
    "Atari Lynx": PlatformStyle("Lynx", (0.45, 0.28, 0.10)),
    "3DO": PlatformStyle("3DO", (0.38, 0.38, 0.22)),
    "Jaguar": PlatformStyle("Jag", (0.42, 0.30, 0.12)),
    "Commodore / Amiga": PlatformStyle("Amiga", (0.35, 0.35, 0.40)),
    "Web": PlatformStyle("Web", (0.28, 0.34, 0.44)),
    "Nintendo Switch 2": PlatformStyle("NS2", (0.85, 0.10, 0.12)),
}

#: RAWG has used more than one spelling for some platforms over the years.
PLATFORM_ALIASES: dict[str, str] = {
    "Sega Genesis": "Genesis",
    "SEGA Genesis": "Genesis",
    "Sega Mega Drive": "Genesis",
    "Sega Saturn": "SEGA Saturn",
    "Sega CD": "SEGA CD",
    "Sega Master System": "SEGA Master System",
    "Sega 32X": "SEGA 32X",
    "Super Nintendo": "SNES",
    "Super Nintendo Entertainment System": "SNES",
    "Nintendo Entertainment System": "NES",
    "Xbox Series X": "Xbox Series S/X",
    "Xbox Series X/S": "Xbox Series S/X",
    "Xbox Series X|S": "Xbox Series S/X",
    "Apple Macintosh": "macOS",
    "Apple II": "macOS",
    "PlayStation Vita": "PS Vita",
}


def platform_style(name: str) -> PlatformStyle | None:
    """Resolve a RAWG platform name (or known alias) to its badge style."""
    if not name:
        return None
    canonical = PLATFORM_ALIASES.get(name, name)
    return PLATFORM_BADGES.get(canonical)


@dataclass(frozen=True)
class StoreStyle:
    """Display name and brand colour for a storefront."""

    name: str
    color: tuple[float, float, float]


#: RAWG store id -> style. Ids are stable and documented by RAWG.
STORE_STYLES: dict[int, StoreStyle] = {
    1: StoreStyle("Steam", (0.10, 0.14, 0.24)),
    2: StoreStyle("Xbox Store", (0.07, 0.45, 0.06)),
    3: StoreStyle("PlayStation Store", (0.00, 0.30, 0.70)),
    4: StoreStyle("App Store", (0.00, 0.42, 0.90)),
    5: StoreStyle("GOG", (0.45, 0.12, 0.58)),
    6: StoreStyle("Nintendo eShop", (0.78, 0.10, 0.12)),
    7: StoreStyle("Xbox 360 Store", (0.06, 0.38, 0.05)),
    8: StoreStyle("Google Play", (0.20, 0.52, 0.18)),
    9: StoreStyle("itch.io", (0.78, 0.24, 0.32)),
    11: StoreStyle("Epic Games", (0.16, 0.16, 0.18)),
}

DEFAULT_STORE_COLOR: tuple[float, float, float] = (0.22, 0.22, 0.30)


def store_style(store_id: int | None, fallback_name: str = "") -> StoreStyle:
    """Look up a storefront style, tolerating unknown ids."""
    known = STORE_STYLES.get(store_id) if store_id is not None else None
    if known is not None:
        return known
    return StoreStyle(fallback_name or "Store", DEFAULT_STORE_COLOR)


#: Human genre name -> RAWG slug, used by the similar-games genre fallback.
GENRE_SLUGS: dict[str, str] = {
    "Action": "action",
    "Adventure": "adventure",
    "RPG": "role-playing-games-rpg",
    "Strategy": "strategy",
    "Shooter": "shooter",
    "Puzzle": "puzzle",
    "Racing": "racing",
    "Sports": "sports",
    "Simulation": "simulation",
    "Platformer": "platformer",
    "Fighting": "fighting",
    "Indie": "indie",
    "Arcade": "arcade",
    "Casual": "casual",
    "Family": "family",
    "Board Games": "board-games",
    "Educational": "educational",
    "Card": "card",
    "Massively Multiplayer": "massively-multiplayer",
}
