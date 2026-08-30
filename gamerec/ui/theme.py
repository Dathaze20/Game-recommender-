"""Design tokens.

One place for colour, spacing, type scale and radii so the screens stay
consistent instead of each widget inventing its own numbers. Sizes are
expressed with Kivy's ``dp``/``sp`` so they hold up across phone densities —
which is the whole reason the app is legible on a small Android screen.
"""

from __future__ import annotations

from kivy.metrics import dp, sp

from ..utils import metacritic_band

RGBA = tuple[float, float, float, float]


# ── Colour ────────────────────────────────────────────────────────────────
BACKGROUND: RGBA = (0.055, 0.058, 0.086, 1)
SURFACE: RGBA = (0.098, 0.102, 0.145, 1)
SURFACE_RAISED: RGBA = (0.133, 0.137, 0.192, 1)
SURFACE_SUNKEN: RGBA = (0.075, 0.078, 0.114, 1)
BORDER: RGBA = (0.196, 0.204, 0.267, 1)

PRIMARY: RGBA = (0.427, 0.357, 0.945, 1)
PRIMARY_PRESSED: RGBA = (0.353, 0.286, 0.831, 1)
PRIMARY_SOFT: RGBA = (0.180, 0.157, 0.353, 1)

ACCENT: RGBA = (1.0, 0.784, 0.259, 1)
SUCCESS: RGBA = (0.235, 0.729, 0.404, 1)
WARNING: RGBA = (0.949, 0.702, 0.243, 1)
DANGER: RGBA = (0.902, 0.353, 0.376, 1)

TEXT: RGBA = (0.957, 0.961, 0.980, 1)
TEXT_MUTED: RGBA = (0.639, 0.655, 0.729, 1)
TEXT_FAINT: RGBA = (0.427, 0.443, 0.522, 1)
TEXT_ON_PRIMARY: RGBA = (1, 1, 1, 1)

TRANSPARENT: RGBA = (0, 0, 0, 0)

_METACRITIC_COLORS = {
    "great": SUCCESS,
    "mixed": WARNING,
    "weak": DANGER,
}


def metacritic_color(score) -> RGBA:
    """Colour for a Metacritic badge; muted when there is no usable score."""
    return _METACRITIC_COLORS.get(metacritic_band(score) or "", TEXT_MUTED)


def rgb(color: tuple[float, float, float], alpha: float = 1.0) -> RGBA:
    """Promote an RGB triple (as used in :mod:`gamerec.constants`) to RGBA."""
    return (color[0], color[1], color[2], alpha)


# ── Spacing ───────────────────────────────────────────────────────────────
def space(n: float) -> float:
    """4dp spacing scale: ``space(1)`` = 4dp, ``space(4)`` = 16dp."""
    return dp(4 * n)


GUTTER = space(4)          # screen edge padding
GAP_TIGHT = space(1.5)
GAP = space(2)
GAP_LOOSE = space(3)
SECTION_GAP = space(5)


# ── Radii ─────────────────────────────────────────────────────────────────
RADIUS_SM = dp(6)
RADIUS_MD = dp(12)
RADIUS_LG = dp(18)
RADIUS_PILL = dp(999)


# ── Type scale ────────────────────────────────────────────────────────────
FONT_DISPLAY = sp(23)
FONT_TITLE = sp(19)
FONT_HEADING = sp(16)
FONT_SUBHEADING = sp(14)
FONT_BODY = sp(13)
FONT_CAPTION = sp(11)
FONT_MICRO = sp(10)


# ── Sizing ────────────────────────────────────────────────────────────────
#: Android's accessibility guidance puts the minimum touch target at 48dp.
TOUCH_TARGET = dp(48)
CONTROL_HEIGHT = dp(48)
HEADER_HEIGHT = dp(56)
NAV_HEIGHT = dp(56)

CARD_WIDTH = dp(132)
CARD_ART_RATIO = 1.32
CARD_META_HEIGHT = dp(58)
CARD_HEIGHT = CARD_WIDTH * CARD_ART_RATIO + CARD_META_HEIGHT

ROW_HEADER_HEIGHT = dp(54)
ROW_HEIGHT = ROW_HEADER_HEIGHT + CARD_HEIGHT + GAP_LOOSE

HERO_HEIGHT = dp(208)
SHOT_WIDTH = dp(248)
SHOT_HEIGHT = dp(140)

#: Movement beyond this during a touch counts as a swipe, not a tap.
TAP_SLOP = dp(14)

# ── Image request sizes ───────────────────────────────────────────────────
# Pixel widths requested from RAWG's resizing CDN. Roughly 3x the dp size the
# image is drawn at, which is the density of a modern phone, so the texture is
# sharp without downloading a 1920px cover for a 132dp card.
CARD_IMAGE_WIDTH = 420
HERO_IMAGE_WIDTH = 1280
SHOT_IMAGE_WIDTH = 800


def state_color(kind: str) -> RGBA:
    """Accent colour for a UX state view (``loading``/``empty``/``error``)."""
    return {
        "loading": TEXT_MUTED,
        "empty": TEXT_FAINT,
        "error": DANGER,
        "offline": WARNING,
    }.get(kind, TEXT_MUTED)


def state_glyph(kind: str) -> str:
    """ASCII-only glyph for a state view.

    Deliberately not emoji: the font Pydroid 3 ships on Android renders many
    pictographs as empty boxes, which is exactly the bug this app used to have
    with star characters.
    """
    return {
        "loading": "...",
        "empty": "( )",
        "error": "[!]",
        "offline": "[~]",
        "search": "[?]",
        "key": "[*]",
    }.get(kind, "[ ]")
