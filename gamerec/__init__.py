"""Game Recommender — a Kivy game-discovery app powered by the RAWG API.

The package is split so that every module outside :mod:`gamerec.ui` is free of
Kivy imports. That keeps the application logic testable (and lintable in CI)
without needing a graphical environment.
"""

from __future__ import annotations

__version__ = "1.0.0"
__all__ = ["__version__"]
