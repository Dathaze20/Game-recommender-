[app]

title = Game Recommender
package.name = gamerecommender
package.domain = io.github.dathaze20

source.dir = .
source.include_exts = py,png,jpg,jpeg,kv,atlas,ttf
# Keep the repo's tooling and tests out of the APK.
source.exclude_dirs = tests,.github,.git,.ruff_cache,.pytest_cache,__pycache__,bin,.buildozer
source.exclude_patterns = .env,.env.*,*.log,buildozer.spec,pyproject.toml,requirements-dev.txt

version = 1.0.0

# `openssl` and `certifi` are what let `requests` do HTTPS on Android; without
# them every RAWG call fails certificate verification at runtime.
requirements = python3,kivy==2.3.0,openssl,certifi,urllib3,idna,charset-normalizer,requests,python-dotenv

orientation = portrait
fullscreen = 0

# INTERNET is required for the RAWG API and cover art. ACCESS_NETWORK_STATE
# lets the platform report connectivity. Nothing else is requested — the app
# stores its data in its own private directory.
android.permissions = android.permission.INTERNET,android.permission.ACCESS_NETWORK_STATE

android.api = 34
android.minapi = 24
android.archs = arm64-v8a,armeabi-v7a
android.allow_backup = True

# Cover art is fetched over HTTPS only, so cleartext traffic stays disabled.
android.enable_androidx = True

[buildozer]
log_level = 2
warn_on_root = 1
