"""Reusable presentation components.

The pieces here solve the problems that made the previous single-file UI feel
rough:

* :class:`TappableMixin` distinguishes a tap from a swipe, so dragging a
  horizontal row no longer opens whichever card your finger started on;
* :class:`WrapLabel` measures its own text instead of being given a fixed
  height, so descriptions stop being clipped mid-sentence;
* :class:`RemoteImage` has a real failure state rather than a blank rectangle;
* :class:`StateView` gives every screen a consistent loading / empty / error /
  retry treatment.
"""

from __future__ import annotations

import contextlib
from collections.abc import Sequence
from typing import Callable

from kivy.clock import Clock
from kivy.graphics import Color, Line, Rectangle, RoundedRectangle
from kivy.metrics import dp
from kivy.uix.behaviors import ButtonBehavior
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.image import AsyncImage
from kivy.uix.label import Label
from kivy.uix.scrollview import ScrollView
from kivy.uix.widget import Widget

from ..constants import platform_style, store_style
from ..models import GameDetails, StoreLink
from ..utils import rating_compact, release_year, safe_str, sized_image_url
from . import theme
from .links import open_url


def paint_background(widget: Widget, color=theme.BACKGROUND) -> Rectangle:
    """Give ``widget`` an opaque background that tracks its geometry.

    The previous build drew a one-shot rectangle at ``Window.size``, so the
    backdrop stopped covering the screen the moment the device was rotated.
    """
    with widget.canvas.before:
        Color(*color)
        rect = Rectangle(pos=widget.pos, size=widget.size)
    widget.bind(
        pos=lambda _w, value: setattr(rect, "pos", value),
        size=lambda _w, value: setattr(rect, "size", value),
    )
    return rect


# ── primitives ────────────────────────────────────────────────────────────
class RoundedBox(BoxLayout):
    """A ``BoxLayout`` with a rounded, optionally outlined background."""

    def __init__(
        self,
        bg_color=theme.SURFACE,
        radius: float = theme.RADIUS_MD,
        border_color=None,
        border_width: float = dp(1),
        **kwargs,
    ) -> None:
        super().__init__(**kwargs)
        self._radius = radius
        with self.canvas.before:
            self._color_instruction = Color(*bg_color)
            self._rect = RoundedRectangle(pos=self.pos, size=self.size, radius=[radius])
            if border_color is not None:
                self._border_color = Color(*border_color)
                self._border = Line(width=border_width)
            else:
                self._border = None
        self.bind(pos=self._sync_canvas, size=self._sync_canvas)

    def _sync_canvas(self, *_args) -> None:
        self._rect.pos = self.pos
        self._rect.size = self.size
        if self._border is not None:
            self._border.rounded_rectangle = (
                self.x, self.y, self.width, self.height, self._radius,
            )

    def set_bg_color(self, color) -> None:
        self._color_instruction.rgba = color


class WrapLabel(Label):
    """A label that wraps to its own width and grows to fit its text."""

    def __init__(self, **kwargs) -> None:
        kwargs.setdefault("halign", "left")
        kwargs.setdefault("valign", "top")
        kwargs.setdefault("size_hint_y", None)
        kwargs.setdefault("color", theme.TEXT)
        kwargs.setdefault("font_size", theme.FONT_BODY)
        super().__init__(**kwargs)
        self.bind(width=self._sync_text_size, texture_size=self._sync_height)
        self._sync_text_size()

    def _sync_text_size(self, *_args) -> None:
        self.text_size = (self.width, None)

    def _sync_height(self, *_args) -> None:
        self.height = self.texture_size[1]


class LineLabel(Label):
    """A single-line label that ellipsises rather than overflowing."""

    def __init__(self, **kwargs) -> None:
        kwargs.setdefault("halign", "left")
        kwargs.setdefault("valign", "middle")
        kwargs.setdefault("shorten", True)
        kwargs.setdefault("shorten_from", "right")
        kwargs.setdefault("color", theme.TEXT)
        kwargs.setdefault("font_size", theme.FONT_BODY)
        super().__init__(**kwargs)
        self.bind(size=self._sync_text_size)
        self._sync_text_size()

    def _sync_text_size(self, *_args) -> None:
        self.text_size = self.size


class TappableMixin:
    """Fires ``on_tap`` for a press-and-release that did not travel.

    A plain ``on_touch_down`` binding — what this app used to do — treats the
    first frame of a horizontal scroll as a click, so swiping a row opened a
    game. Tracking the touch's origin and rejecting anything that moves more
    than :data:`theme.TAP_SLOP` makes scrolling and tapping coexist.
    """

    tap_slop = theme.TAP_SLOP

    def _tap_key(self) -> str:
        return f"tap_origin_{id(self)}"

    def on_touch_down(self, touch):  # noqa: D102 - Kivy protocol
        if self.collide_point(*touch.pos) and not getattr(self, "disabled", False):
            touch.ud[self._tap_key()] = touch.pos
        return super().on_touch_down(touch)

    def on_touch_up(self, touch):  # noqa: D102 - Kivy protocol
        origin = touch.ud.pop(self._tap_key(), None)
        if origin is not None and self.collide_point(*touch.pos):
            moved_x = abs(touch.pos[0] - origin[0])
            moved_y = abs(touch.pos[1] - origin[1])
            if moved_x <= self.tap_slop and moved_y <= self.tap_slop:
                self.dispatch_tap()
                return True
        return super().on_touch_up(touch)

    def dispatch_tap(self) -> None:
        callback = getattr(self, "on_tap", None)
        if callable(callback):
            callback()


class PillButton(ButtonBehavior, RoundedBox):
    """A flat, rounded button with a proper pressed state and touch target."""

    def __init__(
        self,
        text: str,
        on_press_callback: Callable[[], None] | None = None,
        bg_color=theme.PRIMARY,
        text_color=theme.TEXT_ON_PRIMARY,
        font_size: float = theme.FONT_SUBHEADING,
        bold: bool = True,
        radius: float = theme.RADIUS_SM,
        **kwargs,
    ) -> None:
        kwargs.setdefault("size_hint_y", None)
        kwargs.setdefault("height", theme.CONTROL_HEIGHT)
        kwargs.setdefault("padding", [theme.GAP, 0])
        super().__init__(bg_color=bg_color, radius=radius, **kwargs)
        self._base_color = bg_color
        self._callback = on_press_callback
        self.label = Label(
            text=text,
            font_size=font_size,
            bold=bold,
            color=text_color,
            halign="center",
            valign="middle",
        )
        self.label.bind(size=lambda w, s: setattr(w, "text_size", s))
        self.add_widget(self.label)
        self.bind(on_release=self._fire, state=self._sync_state)

    def _sync_state(self, _widget, state) -> None:
        if state == "down":
            dimmed = tuple(c * 0.78 for c in self._base_color[:3]) + (self._base_color[3],)
            self.set_bg_color(dimmed)
        else:
            self.set_bg_color(self._base_color)

    def _fire(self, *_args) -> None:
        if self._callback is not None:
            self._callback()

    def set_text(self, text: str) -> None:
        self.label.text = text

    def set_colors(self, bg_color, text_color=None) -> None:
        self._base_color = bg_color
        self.set_bg_color(bg_color)
        if text_color is not None:
            self.label.color = text_color


class Badge(RoundedBox):
    """A small, non-interactive coloured chip (platforms, ratings, genres)."""

    def __init__(
        self,
        text: str,
        bg_color=theme.SURFACE_RAISED,
        text_color=theme.TEXT,
        font_size: float = theme.FONT_MICRO,
        width: float | None = None,
        height: float = dp(24),
        **kwargs,
    ) -> None:
        kwargs.setdefault("size_hint", (None, None))
        kwargs.setdefault("padding", [dp(8), 0])
        super().__init__(bg_color=bg_color, radius=theme.RADIUS_SM, **kwargs)
        self.height = height
        label = Label(
            text=text,
            font_size=font_size,
            bold=True,
            color=text_color,
            halign="center",
            valign="middle",
        )
        label.bind(size=lambda w, s: setattr(w, "text_size", s))
        self.add_widget(label)
        self.width = width if width is not None else max(dp(40), dp(9) * len(text) + dp(16))


class RemoteImage(RoundedBox):
    """An async image with placeholder and failure states.

    Kivy's ``AsyncImage`` leaves a blank rectangle when a download fails; on a
    flaky mobile connection that is most of a screen. This shows the game's
    initials instead, so a row still reads as a list of games.
    """

    def __init__(
        self,
        source: str,
        fallback_text: str = "",
        radius: float = theme.RADIUS_SM,
        request_width: int = 0,
        **kwargs,
    ) -> None:
        kwargs.setdefault("padding", [0, 0])
        super().__init__(bg_color=theme.SURFACE_SUNKEN, radius=radius, **kwargs)
        self._fallback_text = _initials(fallback_text)
        self._image: AsyncImage | None = None
        self._original_source = safe_str(source)
        self._tried_original = False

        display = (
            sized_image_url(self._original_source, request_width)
            if request_width
            else self._original_source
        )
        self._display_source = display
        if display:
            self._show_image(display)
        else:
            self._show_placeholder()

    def _show_image(self, source: str) -> None:
        image = AsyncImage(
            source=source,
            allow_stretch=True,
            keep_ratio=False,
            nocache=False,
            # Cover art still arrives larger than the card. Without mipmaps the
            # GPU point-samples the downscale, which is what makes the art look
            # soft and shimmer while a row is scrolling.
            mipmap=True,
        )
        # `on_error` exists on Kivy >= 2.0; on anything older we simply do
        # without the failure state rather than refusing to render.
        with contextlib.suppress(Exception):
            image.bind(on_error=self._on_error)
        self._image = image
        self.add_widget(image)

    def _on_error(self, *_args) -> None:
        Clock.schedule_once(lambda _dt: self._handle_error(), 0)

    def _handle_error(self) -> None:
        """Retry at full size before giving up on the image entirely.

        If RAWG ever stops serving the resized variant, this degrades to the
        original URL rather than turning every cover into a placeholder.
        """
        if (
            not self._tried_original
            and self._original_source
            and self._display_source != self._original_source
        ):
            self._tried_original = True
            self._display_source = self._original_source
            self.clear_widgets()
            self._show_image(self._original_source)
            return
        self._show_placeholder()

    def _show_placeholder(self) -> None:
        self.clear_widgets()
        self._image = None
        label = Label(
            text=self._fallback_text or "—",
            font_size=theme.FONT_TITLE,
            bold=True,
            color=theme.TEXT_FAINT,
            halign="center",
            valign="middle",
        )
        label.bind(size=lambda w, s: setattr(w, "text_size", s))
        self.add_widget(label)


def _initials(name: str) -> str:
    """Up to two initials from a game title, for the image placeholder."""
    words = [w for w in safe_str(name).split() if w and w[0].isalnum()]
    if not words:
        return ""
    if len(words) == 1:
        return words[0][:2].upper()
    return (words[0][0] + words[1][0]).upper()


# ── states ────────────────────────────────────────────────────────────────
class StateView(BoxLayout):
    """A consistent loading / empty / error / offline panel with optional retry."""

    def __init__(
        self,
        kind: str,
        title: str,
        message: str = "",
        action_text: str = "",
        on_action: Callable[[], None] | None = None,
        compact: bool = False,
        **kwargs,
    ) -> None:
        kwargs.setdefault("orientation", "vertical")
        kwargs.setdefault("size_hint_y", None)
        kwargs.setdefault("spacing", theme.GAP)
        kwargs.setdefault("padding", [theme.GUTTER, theme.GAP_LOOSE])
        super().__init__(**kwargs)

        glyph = Label(
            text=theme.state_glyph(kind),
            font_size=theme.FONT_TITLE if compact else theme.FONT_DISPLAY,
            bold=True,
            color=theme.state_color(kind),
            size_hint_y=None,
            height=dp(28) if compact else dp(36),
        )
        self.add_widget(glyph)

        heading = Label(
            text=title,
            font_size=theme.FONT_SUBHEADING if compact else theme.FONT_HEADING,
            bold=True,
            color=theme.TEXT,
            size_hint_y=None,
            height=dp(24),
            halign="center",
            valign="middle",
        )
        heading.bind(size=lambda w, s: setattr(w, "text_size", s))
        self.add_widget(heading)

        height = dp(28) + (dp(24) if compact else dp(36))
        if message:
            body = WrapLabel(
                text=message,
                font_size=theme.FONT_CAPTION if compact else theme.FONT_BODY,
                color=theme.TEXT_MUTED,
                halign="center",
            )
            self.add_widget(body)
            height += dp(46)

        if action_text and on_action is not None:
            actions = BoxLayout(size_hint_y=None, height=theme.CONTROL_HEIGHT)
            actions.add_widget(Widget())
            actions.add_widget(
                PillButton(
                    action_text,
                    on_press_callback=on_action,
                    bg_color=theme.PRIMARY,
                    size_hint_x=None,
                    width=dp(150),
                )
            )
            actions.add_widget(Widget())
            self.add_widget(actions)
            height += theme.CONTROL_HEIGHT + theme.GAP

        self.height = height + theme.GAP_LOOSE * 2


class SkeletonCard(RoundedBox):
    """A neutral placeholder occupying exactly one card's footprint."""

    def __init__(self, **kwargs) -> None:
        kwargs.setdefault("orientation", "vertical")
        kwargs.setdefault("size_hint", (None, None))
        kwargs.setdefault("spacing", theme.GAP_TIGHT)
        kwargs.setdefault("padding", [dp(6), dp(6)])
        super().__init__(bg_color=theme.SURFACE, radius=theme.RADIUS_MD, **kwargs)
        self.size = (theme.CARD_WIDTH, theme.CARD_HEIGHT)
        art = RoundedBox(
            bg_color=theme.SURFACE_SUNKEN,
            radius=theme.RADIUS_SM,
            size_hint_y=None,
            height=theme.CARD_WIDTH * theme.CARD_ART_RATIO - dp(12),
        )
        self.add_widget(art)
        for width_factor, height in ((0.85, dp(11)), (0.5, dp(9))):
            bar = RoundedBox(
                bg_color=theme.SURFACE_SUNKEN,
                radius=dp(3),
                size_hint=(width_factor, None),
                height=height,
            )
            self.add_widget(bar)
        self.add_widget(Widget())


# ── game presentation ─────────────────────────────────────────────────────
class GameCard(TappableMixin, RoundedBox):
    """Cover art, title, rating and year — the unit every row is built from."""

    def __init__(
        self,
        game: GameDetails,
        on_select: Callable[[GameDetails], None] | None = None,
        width: float = theme.CARD_WIDTH,
        **kwargs,
    ) -> None:
        kwargs.setdefault("orientation", "vertical")
        kwargs.setdefault("size_hint", (None, None))
        kwargs.setdefault("spacing", theme.GAP_TIGHT)
        kwargs.setdefault("padding", [dp(6), dp(6)])
        super().__init__(bg_color=theme.SURFACE, radius=theme.RADIUS_MD, **kwargs)
        self.game = game
        self._on_select = on_select
        self.size = (width, width * theme.CARD_ART_RATIO + theme.CARD_META_HEIGHT)

        art_height = width * theme.CARD_ART_RATIO - dp(12)
        self.add_widget(
            RemoteImage(
                source=game.background_image,
                fallback_text=game.name,
                request_width=theme.CARD_IMAGE_WIDTH,
                size_hint_y=None,
                height=art_height,
            )
        )

        self.add_widget(
            LineLabel(
                text=game.name,
                font_size=theme.FONT_CAPTION,
                bold=True,
                size_hint_y=None,
                height=dp(20),
            )
        )

        meta = BoxLayout(size_hint_y=None, height=dp(18), spacing=theme.GAP_TIGHT)
        meta.add_widget(
            LineLabel(
                text=rating_compact(game.rating),
                font_size=theme.FONT_CAPTION,
                bold=True,
                color=theme.ACCENT,
                size_hint_x=0.5,
            )
        )
        meta.add_widget(
            LineLabel(
                text=release_year(game.release_date),
                font_size=theme.FONT_CAPTION,
                color=theme.TEXT_FAINT,
                halign="right",
                size_hint_x=0.5,
            )
        )
        self.add_widget(meta)

    def on_tap(self) -> None:
        if self._on_select is not None:
            self._on_select(self.game)


class HorizontalCards(ScrollView):
    """A horizontally scrolling strip of fixed-width children."""

    def __init__(self, height: float, spacing: float = theme.GAP, **kwargs) -> None:
        kwargs.setdefault("size_hint_y", None)
        kwargs.setdefault("do_scroll_y", False)
        kwargs.setdefault("bar_width", 0)
        super().__init__(**kwargs)
        self.height = height
        self.strip = BoxLayout(
            size_hint=(None, None),
            height=height,
            spacing=spacing,
            padding=[theme.GUTTER, 0, theme.GUTTER, 0],
        )
        self.strip.bind(minimum_width=self.strip.setter("width"))
        self.add_widget(self.strip)

    def set_children(self, widgets: Sequence[Widget]) -> None:
        self.strip.clear_widgets()
        for widget in widgets:
            self.strip.add_widget(widget)


class CategoryRow(BoxLayout):
    """One titled collection with its own loading, empty and error states.

    The row keeps a constant height across all states so lazily loading a row
    further down the page never makes the content the user is reading jump.
    """

    def __init__(
        self,
        title: str,
        subtitle: str = "",
        on_select: Callable[[GameDetails], None] | None = None,
        card_width: float = theme.CARD_WIDTH,
        **kwargs,
    ) -> None:
        kwargs.setdefault("orientation", "vertical")
        kwargs.setdefault("size_hint_y", None)
        kwargs.setdefault("spacing", theme.GAP_TIGHT)
        super().__init__(**kwargs)
        self._on_select = on_select
        self._card_width = card_width
        self._card_height = card_width * theme.CARD_ART_RATIO + theme.CARD_META_HEIGHT

        header = BoxLayout(
            orientation="vertical",
            size_hint_y=None,
            height=theme.ROW_HEADER_HEIGHT if subtitle else dp(34),
            padding=[theme.GUTTER, 0],
        )
        header.add_widget(
            LineLabel(
                text=title,
                font_size=theme.FONT_HEADING,
                bold=True,
                size_hint_y=None,
                height=dp(30),
            )
        )
        if subtitle:
            header.add_widget(
                LineLabel(
                    text=subtitle,
                    font_size=theme.FONT_CAPTION,
                    color=theme.TEXT_FAINT,
                    size_hint_y=None,
                    height=dp(19),
                )
            )
        self.add_widget(header)

        self.body = BoxLayout(size_hint_y=None, height=self._card_height)
        self.add_widget(self.body)
        self.height = header.height + self._card_height + theme.GAP_TIGHT

        self.cards = HorizontalCards(height=self._card_height)
        self.show_loading()

    def _set_body(self, widget: Widget) -> None:
        self.body.clear_widgets()
        self.body.add_widget(widget)

    def show_loading(self) -> None:
        self.cards.set_children([SkeletonCard() for _ in range(4)])
        self._set_body(self.cards)

    def show_games(self, games: Sequence[GameDetails]) -> None:
        if not games:
            self.show_empty()
            return
        self.cards.set_children(
            [
                GameCard(game=game, on_select=self._on_select, width=self._card_width)
                for game in games
            ]
        )
        self._set_body(self.cards)

    def show_empty(self, message: str = "Nothing here right now.") -> None:
        self._set_body(
            StateView("empty", "No games", message, compact=True, size_hint_y=1)
        )

    def show_error(
        self,
        message: str,
        on_retry: Callable[[], None] | None = None,
        kind: str = "error",
    ) -> None:
        self._set_body(
            StateView(
                kind,
                "Could not load",
                message,
                action_text="Retry" if on_retry else "",
                on_action=on_retry,
                compact=True,
                size_hint_y=1,
            )
        )


class SectionHeading(Label):
    """A consistent heading for the detail screen's sections."""

    def __init__(self, text: str, **kwargs) -> None:
        kwargs.setdefault("size_hint_y", None)
        kwargs.setdefault("height", dp(30))
        kwargs.setdefault("halign", "left")
        kwargs.setdefault("valign", "bottom")
        super().__init__(
            text=text.upper(),
            font_size=theme.FONT_CAPTION,
            bold=True,
            color=theme.TEXT_FAINT,
            **kwargs,
        )
        self.bind(size=lambda w, s: setattr(w, "text_size", s))


def platform_badges(names: Sequence[str], limit: int = 0) -> list[Badge]:
    """Badges for the platforms we have brand styling for."""
    badges: list[Badge] = []
    for name in names:
        style = platform_style(name)
        if style is None:
            continue
        badges.append(
            Badge(style.label, bg_color=theme.rgb(style.color), text_color=theme.TEXT)
        )
        if limit and len(badges) >= limit:
            break
    return badges


class StoreButton(ButtonBehavior, RoundedBox):
    """A storefront chip.

    When RAWG gave us a real URL the chip opens it; when it did not, the chip
    is rendered flat and muted so it reads as information rather than a dead
    button. No URL is ever guessed from a store's domain.
    """

    def __init__(self, link: StoreLink, **kwargs) -> None:
        kwargs.setdefault("size_hint", (None, None))
        kwargs.setdefault("padding", [dp(10), 0])
        style = store_style(link.store_id, link.name)
        actionable = link.actionable
        bg = theme.rgb(style.color) if actionable else theme.SURFACE_RAISED
        super().__init__(
            bg_color=bg,
            radius=theme.RADIUS_SM,
            border_color=None if actionable else theme.BORDER,
            **kwargs,
        )
        self.link = link
        self.height = dp(36)
        text = style.name if actionable else f"{style.name} (no link)"
        label = Label(
            text=text,
            font_size=theme.FONT_CAPTION,
            bold=actionable,
            color=theme.TEXT if actionable else theme.TEXT_FAINT,
            halign="center",
            valign="middle",
        )
        label.bind(size=lambda w, s: setattr(w, "text_size", s))
        self.add_widget(label)
        self.width = max(dp(96), dp(7.5) * len(text) + dp(22))
        self.disabled = not actionable
        if actionable:
            self.bind(on_release=self._open)

    def _open(self, *_args) -> None:
        if self.link.url:
            open_url(self.link.url)
