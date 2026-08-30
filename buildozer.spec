[app]

title = Game Recommender
package.name = gamerecommender
package.domain = io.github.dathaze20

version = 1.0.0

source.dir = .
# Only these extensions are packaged at all. Note what this excludes by
# construction: `.env` has no extension and `credentials.json` / `library.json`
# are `.json`, so neither can reach the APK even before the patterns below.
source.include_exts = py

source.exclude_dirs = tests,.github,.git,.ruff_cache,.pytest_cache,__pycache__,bin,.buildozer,.venv,venv
source.exclude_patterns = .env,.env.*,*.log,*.json,buildozer.spec,pyproject.toml,requirements*.txt

# ── Runtime requirements ──────────────────────────────────────────────────
#
# `kivy` is deliberately unpinned: python-for-android resolves it through its
# own bundled recipe, and pinning a version it has no recipe for is the most
# common way these builds fail.
#
# `openssl` + `certifi` are what make HTTPS work for `requests` on Android;
# without them every RAWG call fails certificate verification at runtime.
#
# `chardet` rather than `charset-normalizer`: `requests` accepts either, and
# p4a has a long-standing recipe for chardet whereas charset-normalizer has a
# compiled speedup that has to fall back to pure Python on Android.
#
# `pyjnius` is required by gamerec/ui/links.py for the ACTION_VIEW intent used
# to open store links. The SDL2 bootstrap pulls it in anyway; listing it makes
# the dependency explicit rather than incidental.
#
# `python-dotenv` is intentionally absent. It only supports reading a local
# `.env` during desktop development, no `.env` is ever packaged, and the import
# in gamerec/config.py is already guarded. Shipping it would add build risk for
# no runtime benefit.
requirements = python3,kivy,openssl,certifi,urllib3,idna,chardet,requests,pyjnius,android

# ── Presentation ──────────────────────────────────────────────────────────
# The layout is designed for a phone in portrait; locking it avoids reflowing
# a dense card UI into landscape where it was never verified.
orientation = portrait
fullscreen = 0
# Matches the app background so launch does not flash white.
android.presplash_color = #0E0F17

# ── Permissions ───────────────────────────────────────────────────────────
# INTERNET reaches the RAWG API and its cover art CDN. ACCESS_NETWORK_STATE
# lets the platform report connectivity. Nothing else is requested: the app
# writes only to its own private directory and reads no device data.
android.permissions = android.permission.INTERNET,android.permission.ACCESS_NETWORK_STATE

# ── Android platform ──────────────────────────────────────────────────────
# python-for-android is pinned to a release rather than tracking `master`,
# which buildozer would otherwise clone. This is not conservatism for its own
# sake — master currently targets Python 3.14 and builds `charset_normalizer`
# (a `requests` dependency) as a native Android wheel, which pip 26 then
# refuses to install:
#
#   ERROR: charset_normalizer-3.5.1-cp314-cp314-android_24_arm64_v8a.whl
#          is not a supported wheel on this platform.
#
# v2024.01.21 ships Python 3.11.5 and Kivy 2.3.0, and has no recipe for
# requests/urllib3/idna/certifi/chardet — they install as ordinary pure-Python
# wheels, so that whole failure mode disappears. It also fixes the toolchain:
# buildozer reads RECOMMENDED_NDK_VERSION (25b) from this checkout, and Kivy
# 2.3.0 is what the pinned Cython 0.29.36 expects.
p4a.branch = v2024.01.21

# 33 is this p4a release's RECOMMENDED_TARGET_API. Raising it only earns a
# warning, but there is no reason to build against an API this version was
# never tested on for a side-loaded debug APK.
android.api = 33
android.minapi = 24
# `android.ndk` is deliberately NOT pinned. Buildozer reads the NDK version
# that python-for-android recommends out of the p4a checkout, and hard-coding
# a different one is a reliable way to get a toolchain its recipes were never
# tested against.
android.archs = arm64-v8a,armeabi-v7a
android.accept_sdk_license = True
android.enable_androidx = True

# The app stores a RAWG API key in credentials.json inside its private data
# directory. Android auto-backup would copy that to the user's Google Drive,
# so it stays off: the key is a credential, not app state worth syncing.
android.allow_backup = False

# Entry point matches the class gamerec/ui/links.py reaches through pyjnius.
android.entrypoint = org.kivy.android.PythonActivity

[buildozer]
log_level = 2
warn_on_root = 1
