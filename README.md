# Game Recommender

**An Android game discovery and recommendation app powered by RAWG.**

Finding your next game usually means bouncing between store pages, review sites
and wikis. Game Recommender puts that in one place: browse curated collections
spanning modern and retro platforms, search the whole RAWG catalogue, open any
game for its artwork, description, scores and storefronts, keep a wishlist and a
played list, and get suggestions for what to play next.

It ships as an Android APK built in CI, and also runs on desktop
(Windows, macOS, Linux) and under
[Pydroid 3](https://play.google.com/store/apps/details?id=ru.iiec.pydroid3).

Built with Python and [Kivy](https://kivy.org). Game data comes from the
[RAWG Video Games Database](https://rawg.io) — you supply your own free API key,
and it is never bundled into the app.

---

## Screenshots

No screenshots are committed yet. Placeholders are intentionally left blank
rather than filled with mock-ups, so nothing here misrepresents the app.

To add them: capture on a device, save into `docs/screenshots/`, and replace the
lines below.

| Slot | File | What to capture |
| --- | --- | --- |
| 1. Discovery | `docs/screenshots/home.png` | The Browse tab, scrolled so at least two collection rows and their cover art are visible |
| 2. Game detail | `docs/screenshots/detail.png` | A game with a description, rating, Metacritic score, genres, platform badges and store buttons |
| 3. Library | `docs/screenshots/library.png` | The My Games tab with saved wishlist and played entries |

```markdown
![Discovery](docs/screenshots/home.png)
![Game detail](docs/screenshots/detail.png)
![Library](docs/screenshots/library.png)
```

---

## Features

**Discovery**
- 36 curated collections across current, last-gen, retro and mobile platforms
- Horizontally swipeable rows of cover art
- Collections load lazily as you scroll rather than all at once
- Debounced search across the whole RAWG catalogue, with stale results discarded

**Game detail**
- Cover art, plain-text description and a screenshot gallery
- Rating, Metacritic score, average playtime and ESRB rating
- Developer, publisher and release date
- Platform badges and storefront links
- "You might also like" suggestions

**Your library** — stored on your device only
- **Want to play** wishlist and a **Played** list
- Stats: games saved, games opened, searches run, most-saved genres, and your
  average rating and Metacritic across played games

**Reliability**
- All network work happens off the UI thread
- In-memory response caching, bounded retries, rate-limit handling
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

### How discovery and recommendations work

Collections are RAWG queries — a platform filter, a genre filter, a Metacritic
range, or an ordering — defined in `gamerec/constants.py`. There is no
server-side model and no personalisation; the app does not upload anything about
you.

For a given game, "You might also like" tries three strategies in order and
stops at the first that returns results:

1. `/games/{id}/suggested` — RAWG's own recommendation engine
2. `/games/{id}/game-series` — other entries in the same series
3. Highest-rated games sharing the game's primary genre

Each step is independent, so a failure in one does not abort the chain — which
matters because `suggested` 404s for obscure titles. The game itself and any
duplicates are filtered out.

### RAWG integration

All data comes from `api.rawg.io`; artwork comes from `media.rawg.io`. Requests
go directly from your device — there is no backend in between.

The client (`gamerec/api.py`) uses one pooled `requests.Session`, centralises
authentication, caches successful responses in memory with a TTL, de-duplicates
identical concurrent requests, and retries with bounded backoff. `429` honours
`Retry-After`; `401`, `403` and `404` fail immediately rather than retrying.

### Image loading

Cover art is requested at a size appropriate to where it is drawn. RAWG serves
resized variants under `/media/resize/<width>/-/…`, and `gamerec/utils.py`
rewrites image URLs accordingly:

| Context | Requested width |
| --- | --- |
| Collection card | 420 px |
| Screenshot thumbnail | 800 px |
| Detail hero image | 1280 px |

Roughly 3× the drawn size, which suits a high-density phone screen. Previously
the app downloaded the full-size original — often 1920 px wide — for a 132 dp
card, which wasted bandwidth and looked soft because the GPU was point-sampling
a large downscale. Mipmapping is enabled on remote images so any remaining
downscale is filtered properly.

If a resized variant ever fails to load, the widget retries the original URL
once before falling back to a placeholder, so a CDN change degrades to "slower"
rather than "no artwork". Anything that is not a plain RAWG media URL is left
untouched.

Kivy's image loader caches decoded textures in memory, so scrolling back over a
row does not re-download. Twelve games are requested per collection row: each
card is a live widget holding a decoded texture, which makes this the main lever
on scroll smoothness and memory use on a phone.

### Saved games and persistence

Your wishlist, played list, stats and settings live in `library.json` in the
app's private data directory. Writes are atomic — content goes to a temporary
file and is moved into place — so an interrupted save cannot destroy the file.
Loading is total: a missing file, unreadable file, malformed JSON, corrupt rows
or an older schema all recover to usable data. An unparseable file is moved
aside as `library.json.corrupt-<timestamp>` rather than deleted.

Because the data lives in the app's private directory and the Android package ID
does not change between builds, **saved games and your API key survive an
ordinary APK update.**

### Android support

The app is packaged with Buildozer / python-for-android and built in CI for
`arm64-v8a` and `armeabi-v7a`. It is portrait-locked by design — the layout is
built for a phone in portrait and has not been verified in landscape.

Store links open through an Android `ACTION_VIEW` intent via pyjnius, falling
back to `webbrowser` on desktop.

---

## Architecture

```
main.py                     Entry point; configures Kivy, then hands off
gamerec/
├── constants.py            Collections, platform/store metadata, genre slugs
├── errors.py               Exception hierarchy with user-facing messages
├── utils.py                Pure helpers: formatting, coercion, image URL sizing
├── models.py               GameDetails/StoreLink + RAWG payload parsing
├── config.py               API-key resolution, credential storage, atomic writes
├── storage.py              Wishlist / played / stats / settings persistence
├── api.py                  RAWG client: session, cache, retries, rate limits
├── recommendations.py      Similar-game fallback chain
└── ui/                     Everything that imports Kivy
    ├── theme.py            Design tokens: colour, spacing, type scale, sizes
    ├── widgets.py          Cards, rows, badges, state views, buttons
    ├── tasks.py            Thread → Clock marshalling, stale-response guards
    ├── links.py            Platform-aware external URL opening
    ├── app.py              App shell, navigation, controller for the screens
    └── screens/            setup.py, home.py, detail.py
```

Every module outside `gamerec/ui/` is free of Kivy imports. That is what lets
the test suite run headless with no display server, and
`tests/test_layering.py` asserts it in a clean subprocess so it cannot quietly
regress. The screens hold no knowledge of HTTP or the filesystem — they call
methods on the app object.

### Tech stack

| | |
| --- | --- |
| Language | Python 3.9+ |
| UI | Kivy 2.2+ (2.3.0 in the APK) |
| HTTP | requests |
| Data source | RAWG Video Games Database API |
| Android packaging | Buildozer 1.5.0 + python-for-android `v2024.01.21` |
| Tests | pytest |
| Lint | Ruff |
| CI | GitHub Actions |

---

## Building and running locally

Requires **Python 3.9 or newer**.

```bash
git clone https://github.com/Dathaze20/Game-recommender-.git
cd Game-recommender-

python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate

pip install -r requirements.txt
python main.py
```

| Package | Why |
| --- | --- |
| `kivy>=2.2.0` | UI framework |
| `requests>=2.31.0` | HTTP client for the RAWG API |
| `python-dotenv>=1.0.0` | Optional `.env` support for the API key (desktop only) |

### Running tests

```bash
pip install -r requirements-dev.txt
pytest
ruff check .
```

`requirements-dev.txt` deliberately does **not** install Kivy — the suite runs
headless with no display server. All network calls are mocked; the tests never
contact RAWG.

Coverage includes RAWG response parsing, malformed and missing API fields,
saved-game serialisation and persistence, storage durability and migration,
rating and Metacritic formatting, image URL sizing, API-key resolution and
storage, client retry/rate-limit/cache/de-duplication behaviour, the
recommendation fallback chain, and the desktop/Android URL split.

---

## GitHub Actions

| Workflow | Trigger | Does |
| --- | --- | --- |
| `ci.yml` | push, pull request | `ruff check` on 3.12, `pytest` on Python 3.9 / 3.10 / 3.11 / 3.12 |
| `android.yml` | push to `main`, pull request, manual dispatch | Builds the debug APK and uploads it as an artifact |

Neither test job installs Kivy or starts a display server.

The Android workflow caches the Android SDK/NDK between runs, and audits the APK
before publishing it: it fails unless both ABIs are present, and fails if any
`.env`, `credentials.json`, `library.json` or 32-hex-character API key is found
inside the archive.

### Building the Android APK

In CI: run the **Android APK** workflow (it also runs on pull requests and on
pushes to `main`), then download the **`Game-Recommender-Android-debug`**
artifact.

Locally, on a Linux host with the Android SDK/NDK:

```bash
pip install buildozer cython==0.29.36
buildozer -v android debug        # produces bin/*.apk
```

The build pins `ubuntu-22.04`, python-for-android `v2024.01.21`, Cython 0.29.36
and `virtualenv<21`. Those pins are load-bearing, not cosmetic — the reasons are
documented inline in `buildozer.spec` and `.github/workflows/android.yml`.

### Installing the APK

1. Open the successful workflow run on GitHub and download the
   **`Game-Recommender-Android-debug`** artifact. It arrives as a `.zip`.
2. Extract it to get the `.apk`.
3. Tap the APK. Android will warn that installs from this source are blocked —
   allow your file manager or browser to install unknown apps, then install.
4. Launch **Game Recommender** and paste your RAWG key on the setup screen.

The APK is signed with a debug key. That is fine for side-loading onto your own
device; it is not suitable for Play Store distribution and no release signing is
configured.

Installing a newer build over an older one keeps your saved games and API key.

---

## RAWG API key

The app ships with **no API key**. You supply your own free one — it takes about
a minute, and RAWG's free tier allows 20,000 requests a month.

1. Go to <https://rawg.io/apikey>
2. Sign up **with an email address**
3. Copy the key shown on that page

> Sign up with email. Signing in through Steam or another game platform links a
> profile but does not issue an API key.

Three ways to supply it; the first one found wins.

**1. Environment variable** (recommended for development)

```bash
export GAME_API_KEY=your_key_here     # Windows: set GAME_API_KEY=your_key_here
python main.py
```

**2. `.env` file** — `python-dotenv` is in `requirements.txt`, so this works out
of the box on desktop:

```bash
cp .env.example .env
# edit .env and set GAME_API_KEY=your_key_here
```

`.env` is git-ignored, and a real environment variable takes precedence over it.

**3. In the app** — launch with no key configured and the setup screen opens.
Paste your key and tap **Save and continue**. The key is validated against RAWG
before being accepted, so you find out immediately if it is wrong. Use the
**Key** button in the header to change or remove it later.

If no key is configured the app shows the setup screen and makes **zero** API
requests.

The key is written to `credentials.json` in the platform user-data directory
with owner-only permissions — never to the repository, and never into the APK.
It is kept in its own file, separate from your game library, so `library.json`
can be copied or shared without leaking it. Android auto-backup is disabled for
the same reason.

---

## Privacy

Everything the app saves stays on your device. Nothing is uploaded anywhere and
there is no analytics or telemetry of any kind.

| File | Contents |
| --- | --- |
| `credentials.json` | Your RAWG API key (owner-only permissions) |
| `library.json` | Wishlist, played list, stats, settings |
| `game_app.log` | Rotating local log, capped at 512 KB |

Typical locations: `~/.local/share/game-recommender/` on Linux,
`~/Library/Application Support/game-recommender/` on macOS, `%APPDATA%` on
Windows, and the app's private storage on Android.

The only network destinations are `api.rawg.io` and `media.rawg.io`, plus
whatever storefront you explicitly tap through to.

---

## Known limitations

- **A RAWG account is required.** No key, no data; there is no offline catalogue.
- **RAWG's free tier is 20,000 requests/month.** Caching keeps normal use well
  under it, but heavy searching adds up.
- **Store links depend on RAWG's data.** Storefronts RAWG has no URL for are
  shown greyed out and labelled rather than given a guessed URL.
- **"Japanese Masterpieces" depends on RAWG developer slugs.** If RAWG renames or
  merges any of those studio slugs the row returns nothing and is hidden.
- **Search is title-based**, using RAWG's own search endpoint; it does not search
  descriptions or tags.
- **No offline mode.** The API response cache is in memory only and is lost when
  the app closes. Image textures are cached by Kivy for the session only.
- **Portrait only.** Landscape is not supported and has not been verified.
- **Device testing is limited.** The APK has been installed and used on a single
  Android phone. It is not tested across a range of devices, Android versions or
  screen sizes, and there are no automated UI tests.
- **No release signing.** Only debug APKs are produced; there is no Play Store
  pipeline.

---

## Licence

[MIT](LICENSE).

The licence covers the source code in this repository only. Game data, cover art
and screenshots come from RAWG and remain the property of RAWG and the
respective rights holders.

---

## Attribution

Game data, cover art and screenshots are supplied by the
[RAWG Video Games Database API](https://rawg.io/apidocs). RAWG's free tier
requires attribution and a link back to rawg.io, which this notice provides.

This project is an independent, unofficial client. It is **not** affiliated
with, endorsed by, or sponsored by RAWG. RAWG names and trademarks belong to
their owners and are used here only to identify the data source.
