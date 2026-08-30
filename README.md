# Game Recommender

A Python/Kivy game-discovery app powered by the [RAWG Video Games Database](https://rawg.io).
Browse curated collections across modern and retro platforms, search the catalogue,
read full game details, keep a wishlist and a played list, and see what to play next.

Runs on desktop (Windows, macOS, Linux) and on Android via
[Pydroid 3](https://play.google.com/store/apps/details?id=ru.iiec.pydroid3).

---

## Screenshots

No screenshots are committed to this repository yet. Add them to a `docs/screenshots/`
directory and link them here.

---

## Features

**Browsing**
- 36 curated collections, loaded lazily as you scroll rather than all at once
- Horizontally swipeable rows of cover art, Play-Store style
- Debounced search across the whole RAWG catalogue

**Game details**
- Cover art, description, screenshot gallery
- Rating, Metacritic score, average playtime, ESRB rating
- Developer, publisher and release date
- Platform badges and storefront links
- "You might also like" recommendations

**Your library** (stored on your device only)
- **Want to play** wishlist
- **Played** list
- Stats: games saved, games opened, searches run, most-saved genres, and your
  average rating / Metacritic across played games

**Reliability**
- Every network call happens off the UI thread
- In-memory response caching, bounded retries, and rate-limit handling
- Explicit loading, empty, error, offline and no-results states throughout

### Collections

| Group | Collections |
| --- | --- |
| Highlights | Trending Now, Top Rated, All-Time Greatest (Metacritic 95+), Perfect Scores (98+), New Releases |
| Current platforms | PlayStation 5, Xbox Series X\|S, Nintendo Switch, PC |
| Curated | Highest Rated RPGs, Japanese Masterpieces |
| Genres | Action, RPG, Shooter, Strategy, Racing, Fighting, Platformer, Sports, Indie |
| Last gen | PlayStation 4, Xbox One |
| Retro | Sega Genesis, Neo Geo, SNES, NES, Nintendo 64, Dreamcast, PlayStation 1, PlayStation 2, GameCube, Game Boy Advance, Atari 2600, Sega Saturn |
| Mobile | iOS, Android |

A collection that returns nothing from RAWG is hidden rather than shown empty.

### How recommendations work

For a given game, three strategies are tried in order, stopping at the first
that returns results:

1. `/games/{id}/suggested` — RAWG's own recommendation engine
2. `/games/{id}/game-series` — other entries in the same series
3. Highest-rated games sharing the game's primary genre

Each step is independent: a failure in one does not abort the chain, which
matters because `suggested` 404s for obscure titles. The game itself and any
duplicates are filtered out of the result.

---

## Installation

Requires **Python 3.9 or newer**.

```bash
git clone https://github.com/Dathaze20/Game-recommender-.git
cd Game-recommender-

python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate

pip install -r requirements.txt
```

### Dependencies

| Package | Why |
| --- | --- |
| `kivy>=2.2.0` | UI framework |
| `requests>=2.31.0` | HTTP client for the RAWG API |
| `python-dotenv>=1.0.0` | Optional `.env` support for the API key |

---

## RAWG API key

The app ships with **no API key**. You need your own free one — it takes about a
minute and RAWG's free tier allows 20,000 requests a month.

1. Go to <https://rawg.io/apikey>
2. Sign up **with an email address**
3. Copy the key shown on that page

> Sign up with email. Signing in through Steam or another game platform links a
> profile but does not issue an API key.

There are three ways to supply it. The first one found wins.

### 1. Environment variable (recommended for development)

```bash
export GAME_API_KEY=your_key_here     # Windows: set GAME_API_KEY=your_key_here
python main.py
```

### 2. `.env` file

`python-dotenv` is in `requirements.txt`, so this works out of the box:

```bash
cp .env.example .env
# edit .env and set GAME_API_KEY=your_key_here
python main.py
```

`.env` is git-ignored. A real environment variable always takes precedence over
the file.

### 3. In the app

Launch the app with no key configured and it opens a setup screen. Paste your
key and tap **Save and continue**. The key is checked against RAWG before it is
accepted, so you find out immediately if it is wrong.

The key is written to `credentials.json` in your platform's user-data directory
(`App.user_data_dir`) with owner-only permissions — never to the repository. Use
the **Key** button in the header to change or remove it later.

If no key is configured, the app shows the setup screen and makes **zero** API
requests.

---

## Running

```bash
python main.py
```

### On Android with Pydroid 3

1. Install Pydroid 3 from the Play Store
2. In Pydroid's pip manager, install `kivy`, `requests` and `python-dotenv`
3. Copy this repository to your device
4. Open `main.py` and run it
5. Paste your RAWG key into the setup screen on first launch

---

## Testing

```bash
pip install -r requirements-dev.txt
pytest
ruff check .
```

`requirements-dev.txt` deliberately does **not** install Kivy. Every module
under `gamerec/` except `gamerec/ui/` is free of Kivy imports, so the suite runs
headless with no display server. `tests/test_layering.py` asserts that
invariant in a clean subprocess so it cannot quietly regress.

All network calls in the tests are mocked; the suite never contacts RAWG.

Coverage includes RAWG response parsing, malformed and missing API fields,
saved-game serialisation, rating and Metacritic helpers, API-key resolution and
storage, client retry/rate-limit/caching/deduplication behaviour, storage
durability and migration, and the recommendation fallback chain.

---

## Continuous integration

`.github/workflows/ci.yml` runs on every push and pull request:

- **Lint** — `ruff check .` on Python 3.12
- **Tests** — `pytest` on Python 3.9, 3.10, 3.11 and 3.12

Neither job installs Kivy or starts a display server.

---

## Architecture

```
main.py                     Entry point; configures Kivy, then hands off
gamerec/
├── constants.py            Collections, platform/store metadata, genre slugs
├── errors.py               Exception hierarchy with user-facing messages
├── utils.py                Pure helpers (formatting, coercion, backoff, tokens)
├── models.py               GameDetails/StoreLink + RAWG payload parsing
├── config.py               API-key resolution, credential storage, atomic writes
├── storage.py              Wishlist / played / stats / settings persistence
├── api.py                  RAWG client: session, cache, retries, rate limits
├── recommendations.py      Similar-game fallback chain
└── ui/                     Everything that imports Kivy
    ├── theme.py            Design tokens (colour, spacing, type scale)
    ├── widgets.py          Cards, rows, badges, state views, buttons
    ├── tasks.py            Thread → Clock marshalling, stale-response guards
    ├── links.py            Platform-aware external URL opening
    ├── app.py              App shell, navigation, controller for the screens
    └── screens/            setup.py, home.py, detail.py
```

The screens hold no knowledge of HTTP or the filesystem — they call methods on
the app object. That keeps the Kivy code focused on presentation and leaves the
logic in plain Python where it can be tested.

---

## Local data and privacy

Everything the app saves stays on your device. Nothing is uploaded anywhere and
there is no analytics or telemetry of any kind.

Files live in your platform's user-data directory:

| File | Contents |
| --- | --- |
| `credentials.json` | Your RAWG API key (owner-only permissions) |
| `library.json` | Wishlist, played list, stats, settings |
| `game_app.log` | Rotating local log, capped at 512 KB |

Typical locations: `~/.local/share/gamerecommender/` on Linux,
`~/Library/Application Support/gamerecommender/` on macOS, `%APPDATA%` on
Windows, and the app's private storage on Android.

The credential is kept in its own file so `library.json` can be copied or shared
without leaking your key. Writes are atomic, so an interrupted save cannot
destroy your library, and an unreadable file is moved aside as
`library.json.corrupt-<timestamp>` rather than deleted.

Requests to RAWG go directly from your device to `api.rawg.io`; cover art is
loaded from `media.rawg.io`.

---

## Android packaging

A `buildozer.spec` is included and configured for this app — portrait
orientation, `INTERNET` and `ACCESS_NETWORK_STATE` permissions, and the
`openssl`/`certifi` requirements that HTTPS needs on Android. Store links use an
`ACTION_VIEW` intent through pyjnius when running as an APK, falling back to
`webbrowser` elsewhere.

```bash
pip install buildozer
buildozer -v android debug        # produces bin/*.apk
```

**This spec has not been build-tested.** It was written from the app's actual
requirements, but no APK has been produced from it in this repository, and
buildozer needs a Linux host with the Android SDK/NDK. Treat the first build as
something to debug rather than something guaranteed to work — the Android API
level, architecture list and the exact `charset-normalizer` recipe name are the
values most likely to need adjusting for your toolchain.

The verified way to run this on Android today is **Pydroid 3**, as described
above.

---

## Known limitations

- **RAWG account required.** No key, no data; there is no offline catalogue.
- **RAWG free tier is 20,000 requests/month.** Caching keeps normal use well
  under it, but heavy searching adds up.
- **Store links depend on RAWG's data.** Storefronts RAWG has no URL for are
  shown greyed out and marked "no link" rather than given a guessed URL.
- **"Japanese Masterpieces" depends on RAWG developer slugs.** If RAWG renames
  or merges any of those studio slugs the row will return nothing and be hidden.
  It has not been verified against the live API.
- **Buildozer spec is untested** — see above.
- **Search is title-based**, using RAWG's own search endpoint; it does not
  search descriptions or tags.
- **No offline mode.** The response cache is in memory only and is lost when the
  app closes.

---

## Licence

No licence has been chosen for this repository yet, which means default
copyright applies and others have no rights to use, modify or redistribute the
code. If you want it to be open source, add a `LICENSE` file — MIT is the usual
choice for a project like this.

---

## Attribution

Game data, cover art and screenshots come from the
[RAWG Video Games Database API](https://rawg.io/apidocs). RAWG's free tier
requires attribution and a link back to rawg.io, which this notice provides.

This project is not affiliated with or endorsed by RAWG.
