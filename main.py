"""Game Recommender — entry point.

Window configuration has to happen before Kivy's window provider is imported,
so it lives here rather than inside the package.
"""

from __future__ import annotations

import sys

from kivy.config import Config

# Desktop-only convenience: a phone-shaped window so the mobile layout can be
# checked without a device. Android ignores these and uses the real screen.
if sys.platform not in ("android",):
    Config.set("graphics", "width", "420")
    Config.set("graphics", "height", "820")
Config.set("kivy", "keyboard_mode", "system")

from gamerec.ui.app import run  # noqa: E402  (must follow Config.set)

if __name__ == "__main__":
    raise SystemExit(run(sys.argv[1:]))
