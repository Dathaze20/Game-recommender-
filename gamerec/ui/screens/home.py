"""The main screen: browse, search, saved games and stats.

Loading strategy
----------------
The previous build requested every one of the ~36 collections at launch, in
batches, whether or not the user ever scrolled that far. This version renders
the first :data:`~gamerec.constants.INITIAL_CATEGORY_CHUNK` rows and then only
fetches more as the user approaches the bottom of the list, so a launch costs a
handful of requests instead of three dozen. Responses are cached by the client,
so returning to Browse from another tab costs nothing.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from typing import Callable

from kivy.clock import Clock
from kivy.graphics import Color, Rectangle
from kivy.metrics import dp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.screenmanager import Screen
from kivy.uix.scrollview import ScrollView
from kivy.uix.textinput import TextInput
from kivy.uix.widget import Widget

from ...constants import CATEGORIES, CATEGORY_CHUNK, INITIAL_CATEGORY_CHUNK, Category
from ...errors import describe
from ...models import GameDetails
from ...storage import summarise
from ...utils import Generation
from .. import theme
from ..tasks import guarded, run_async
from ..widgets import (
    CategoryRow,
    LineLabel,
    PillButton,
    RoundedBox,
    StateView,
    WrapLabel,
    paint_background,
)

log = logging.getLogger(__name__)

TAB_BROWSE = "browse"
TAB_LIBRARY = "library"
TAB_STATS = "stats"

TABS = (
    (TAB_BROWSE, "Browse"),
    (TAB_LIBRARY, "My Games"),
    (TAB_STATS, "Stats"),
)

#: Seconds of typing quiet before a search is actually sent.
SEARCH_DEBOUNCE = 0.65
MIN_SEARCH_LENGTH = 2

#: Start fetching the next chunk once the user is within this fraction of the end.
SCROLL_TRIGGER = 0.25


class HomeScreen(Screen):
    """Browse / My Games / Stats, plus search."""

    def __init__(self, controller, **kwargs) -> None:
        super().__init__(**kwargs)
        self.controller = controller
        self.tab = TAB_BROWSE

        self._browse_generation = Generation()
        self._search_generation = Generation()
        self._rows: list[CategoryRow] = []
        self._next_category = 0
        self._chunk_in_flight = False
        self._pending_in_chunk = 0
        self._searching = False
        self._suppress_search_events = False

        self._search_trigger = Clock.create_trigger(
            lambda _dt: self._run_search(), SEARCH_DEBOUNCE
        )
        self._build()

    # ── construction ────────────────────────────────────────────────────
    def _build(self) -> None:
        root = BoxLayout(orientation="vertical")
        paint_background(root)

        root.add_widget(self._build_header())
        root.add_widget(self._build_search())

        self.scroll = ScrollView(do_scroll_x=False, bar_width=dp(2))
        self.content = BoxLayout(
            orientation="vertical",
            size_hint_y=None,
            spacing=theme.GAP,
            padding=[0, theme.GAP, 0, theme.SECTION_GAP],
        )
        self.content.bind(minimum_height=self.content.setter("height"))
        self.scroll.add_widget(self.content)
        self.scroll.bind(scroll_y=lambda *_a: self._maybe_load_more())
        root.add_widget(self.scroll)

        root.add_widget(self._build_nav())
        self.add_widget(root)

    def _build_header(self) -> BoxLayout:
        header = BoxLayout(
            size_hint_y=None,
            height=theme.HEADER_HEIGHT,
            padding=[theme.GUTTER, 0, theme.GAP, 0],
            spacing=theme.GAP,
        )
        header.add_widget(
            LineLabel(
                # FONT_HEADING rather than FONT_TITLE: `sp` scales with the
                # device's font-size setting, and at the larger settings the
                # title was being ellipsised to "Game Recomme...".
                text="Game Recommender",
                font_size=theme.FONT_HEADING,
                bold=True,
            )
        )
        header.add_widget(
            PillButton(
                "Key",
                on_press_callback=self.controller.open_key_manager,
                bg_color=theme.SURFACE_RAISED,
                text_color=theme.TEXT_MUTED,
                font_size=theme.FONT_CAPTION,
                size_hint_x=None,
                width=dp(58),
                height=dp(36),
            )
        )
        return header

    def _build_search(self) -> BoxLayout:
        wrapper = BoxLayout(
            size_hint_y=None,
            height=theme.CONTROL_HEIGHT + theme.GAP,
            padding=[theme.GUTTER, 0, theme.GUTTER, theme.GAP],
            spacing=theme.GAP,
        )
        field = RoundedBox(
            bg_color=theme.SURFACE,
            border_color=theme.BORDER,
            radius=theme.RADIUS_SM,
            padding=[dp(4), dp(2)],
        )
        self.search_input = TextInput(
            hint_text="Search any game",
            multiline=False,
            write_tab=False,
            background_color=theme.TRANSPARENT,
            background_normal="",
            background_active="",
            foreground_color=theme.TEXT,
            hint_text_color=theme.TEXT_FAINT,
            cursor_color=theme.PRIMARY,
            font_size=theme.FONT_BODY,
            # Vertical padding is deliberately small: the field is a fixed
            # height and TextInput does not centre its own line, so generous
            # top padding is what pushed descenders out of the bottom.
            padding=[dp(12), dp(9)],
        )
        self.search_input.bind(text=self._on_search_text)
        self.search_input.bind(on_text_validate=lambda _w: self._run_search(immediate=True))
        field.add_widget(self.search_input)
        wrapper.add_widget(field)
        self._search_row = wrapper

        self.clear_button = PillButton(
            "Clear",
            on_press_callback=self._clear_search,
            bg_color=theme.SURFACE_RAISED,
            text_color=theme.TEXT_MUTED,
            font_size=theme.FONT_CAPTION,
            size_hint_x=None,
            width=dp(66),
        )
        self._clear_visible = False
        return wrapper

    def _build_nav(self) -> BoxLayout:
        nav = BoxLayout(
            size_hint_y=None,
            height=theme.NAV_HEIGHT,
            padding=[theme.GAP, theme.GAP_TIGHT],
            spacing=theme.GAP_TIGHT,
        )
        with nav.canvas.before:
            Color(*theme.SURFACE)
            rect = Rectangle(pos=nav.pos, size=nav.size)
        nav.bind(
            pos=lambda _w, p: setattr(rect, "pos", p),
            size=lambda _w, s: setattr(rect, "size", s),
        )

        self.tab_buttons = {}
        for key, label in TABS:
            button = PillButton(
                label,
                on_press_callback=self._tab_callback(key),
                bg_color=theme.PRIMARY if key == TAB_BROWSE else theme.SURFACE_RAISED,
                text_color=theme.TEXT_ON_PRIMARY if key == TAB_BROWSE else theme.TEXT_MUTED,
                font_size=theme.FONT_CAPTION,
                height=theme.NAV_HEIGHT - theme.GAP_TIGHT * 2,
            )
            nav.add_widget(button)
            self.tab_buttons[key] = button
        return nav

    def _tab_callback(self, key: str) -> Callable[[], None]:
        return lambda: self.show_tab(key)

    # ── tab switching ───────────────────────────────────────────────────
    def show_tab(self, tab: str) -> None:
        self.tab = tab
        for key, button in self.tab_buttons.items():
            active = key == tab
            button.set_colors(
                theme.PRIMARY if active else theme.SURFACE_RAISED,
                theme.TEXT_ON_PRIMARY if active else theme.TEXT_MUTED,
            )
        if tab == TAB_BROWSE:
            self._exit_search()
            self._render_browse()
        elif tab == TAB_LIBRARY:
            self._render_library()
        else:
            self._render_stats()

    def refresh_current_tab(self) -> None:
        """Re-render after returning from the detail screen."""
        if self.tab in (TAB_LIBRARY, TAB_STATS):
            self.show_tab(self.tab)

    def _reset_content(self) -> None:
        self.content.clear_widgets()
        self.scroll.scroll_y = 1.0

    # ── browse ──────────────────────────────────────────────────────────
    def _exit_search(self) -> None:
        """Drop any active search and empty the field without re-entering."""
        self._search_trigger.cancel()
        self._searching = False
        if self.search_input.text:
            self._suppress_search_events = True
            try:
                self.search_input.text = ""
            finally:
                self._suppress_search_events = False
        self._sync_clear_button(False)

    def _render_browse(self) -> None:
        self._browse_generation.next()
        self._search_generation.next()
        self._reset_content()
        self._rows = []
        self._next_category = 0
        self._chunk_in_flight = False
        self._load_chunk(INITIAL_CATEGORY_CHUNK)

    def _load_chunk(self, size: int) -> None:
        if self._chunk_in_flight or self._next_category >= len(CATEGORIES):
            return
        token = self._browse_generation.current
        batch = CATEGORIES[self._next_category : self._next_category + size]
        if not batch:
            return
        self._next_category += len(batch)
        self._chunk_in_flight = True
        self._pending_in_chunk = len(batch)

        # Appending rows makes the content taller; Kivy keeps `scroll_y` as a
        # ratio, so without this the viewport slides away from whatever the
        # user was reading.
        anchor = self._scroll_offset()

        for category in batch:
            row = CategoryRow(
                title=category.title,
                subtitle=category.subtitle,
                on_select=self.controller.open_game,
            )
            self.content.add_widget(row)
            self._rows.append(row)
            self._fetch_category(category, row, token)

        if anchor is not None:
            Clock.schedule_once(lambda _dt: self._restore_scroll(anchor), 0)

    def _scroll_offset(self) -> float | None:
        """Current distance from the top of the content, in pixels."""
        scrollable = self.content.height - self.scroll.height
        if scrollable <= 0:
            return None
        return (1.0 - self.scroll.scroll_y) * scrollable

    def _restore_scroll(self, offset: float) -> None:
        scrollable = self.content.height - self.scroll.height
        if scrollable <= 0:
            self.scroll.scroll_y = 1.0
            return
        self.scroll.scroll_y = max(0.0, min(1.0, 1.0 - offset / scrollable))

    def _fetch_category(self, category: Category, row: CategoryRow, token: int) -> None:
        row.show_loading()

        def _done(games: Sequence[GameDetails]) -> None:
            row.show_games(games)
            self._chunk_item_finished()

        def _failed(exc: BaseException) -> None:
            kind, message = describe(exc)
            row.show_error(
                message,
                on_retry=lambda: self._fetch_category(
                    category, row, self._browse_generation.current
                ),
                kind=kind,
            )
            self._chunk_item_finished()

        run_async(
            lambda: self.controller.fetch_category(category),
            guarded(self._browse_generation, token, _done),
            guarded(self._browse_generation, token, _failed),
            name=f"category-{category.key}",
        )

    def _chunk_item_finished(self) -> None:
        self._pending_in_chunk = max(0, self._pending_in_chunk - 1)
        if self._pending_in_chunk == 0:
            self._chunk_in_flight = False
            # Only ever auto-continue to fill a screen that is still too short
            # to scroll. Anything beyond that waits for a real scroll gesture,
            # otherwise parking at the bottom would quietly pull all 36 rows.
            Clock.schedule_once(lambda _dt: self._fill_viewport_if_short(), 0.1)

    def _can_load_more(self) -> bool:
        return (
            self.tab == TAB_BROWSE
            and not self._searching
            and not self._chunk_in_flight
            and self._next_category < len(CATEGORIES)
        )

    def _fill_viewport_if_short(self) -> None:
        """Top up when the loaded rows do not yet fill the screen."""
        if not self._can_load_more():
            return
        viewport = self.scroll.height or 1
        if self.content.height <= viewport * 1.1:
            self._load_chunk(CATEGORY_CHUNK)

    def _maybe_load_more(self) -> None:
        """Scroll-driven loading: one chunk per approach to the end."""
        if not self._can_load_more():
            return
        if self.scroll.scroll_y <= SCROLL_TRIGGER:
            self._load_chunk(CATEGORY_CHUNK)

    # ── search ──────────────────────────────────────────────────────────
    def _on_search_text(self, _widget, text: str) -> None:
        if self._suppress_search_events:
            return
        self._search_trigger.cancel()
        stripped = text.strip()
        self._sync_clear_button(bool(stripped))
        if len(stripped) >= MIN_SEARCH_LENGTH:
            self._search_trigger()
        elif not stripped and self._searching:
            # Emptying the field returns to the collections.
            self._searching = False
            self._render_browse()

    def _sync_clear_button(self, visible: bool) -> None:
        if visible == self._clear_visible:
            return
        self._clear_visible = visible
        parent = self.clear_button.parent
        if visible and parent is None:
            self._search_row.add_widget(self.clear_button)
        elif not visible and parent is not None:
            parent.remove_widget(self.clear_button)

    def _clear_search(self) -> None:
        self.show_tab(TAB_BROWSE)

    def _run_search(self, immediate: bool = False) -> None:
        if immediate:
            self._search_trigger.cancel()
        query = self.search_input.text.strip()
        if len(query) < MIN_SEARCH_LENGTH:
            return

        self._searching = True
        self.tab = TAB_BROWSE
        self._browse_generation.next()
        token = self._search_generation.next()

        self._reset_content()
        self.content.add_widget(
            StateView("loading", "Searching", f'Looking for "{query}"...')
        )

        def _done(games: Sequence[GameDetails]) -> None:
            self._render_search_results(query, games)

        def _failed(exc: BaseException) -> None:
            kind, message = describe(exc)
            self._reset_content()
            self.content.add_widget(
                StateView(
                    kind,
                    "Search failed",
                    message,
                    action_text="Try again",
                    on_action=lambda: self._run_search(immediate=True),
                )
            )

        run_async(
            lambda: self.controller.search(query),
            guarded(self._search_generation, token, _done),
            guarded(self._search_generation, token, _failed),
            name="search",
        )

    def _render_search_results(self, query: str, games: Sequence[GameDetails]) -> None:
        self._reset_content()
        if not games:
            self.content.add_widget(
                StateView(
                    "search",
                    "No matches",
                    f'Nothing on RAWG matches "{query}". Try a shorter or '
                    "differently spelled title.",
                    action_text="Back to browse",
                    on_action=self._clear_search,
                )
            )
            return

        row = CategoryRow(
            title=f"Results for “{query}”",
            subtitle=f"{len(games)} game{'s' if len(games) != 1 else ''}",
            on_select=self.controller.open_game,
        )
        self.content.add_widget(row)
        row.show_games(games[:20])

        if len(games) > 20:
            more = CategoryRow(
                title="More results",
                on_select=self.controller.open_game,
            )
            self.content.add_widget(more)
            more.show_games(games[20:])

    # ── library ─────────────────────────────────────────────────────────
    def _render_library(self) -> None:
        self._browse_generation.next()
        self._search_generation.next()
        self._searching = False
        self._reset_content()

        storage = self.controller.storage
        wishlist = storage.games("wishlist")
        played = storage.games("played")

        if not wishlist and not played:
            self.content.add_widget(
                StateView(
                    "empty",
                    "Nothing saved yet",
                    "Open any game and use “Want to play” or “Played it”. "
                    "Saved games live on this device only.",
                    action_text="Browse games",
                    on_action=lambda: self.show_tab(TAB_BROWSE),
                )
            )
            return

        if wishlist:
            row = CategoryRow(
                title="Want to play",
                subtitle=f"{len(wishlist)} saved",
                on_select=self.controller.open_game,
            )
            self.content.add_widget(row)
            row.show_games(wishlist)

        if played:
            row = CategoryRow(
                title="Played",
                subtitle=f"{len(played)} logged",
                on_select=self.controller.open_game,
            )
            self.content.add_widget(row)
            row.show_games(played)

    # ── stats ───────────────────────────────────────────────────────────
    def _render_stats(self) -> None:
        self._browse_generation.next()
        self._search_generation.next()
        self._searching = False
        self._reset_content()

        data = summarise(self.controller.storage)

        wrapper = BoxLayout(
            orientation="vertical",
            size_hint_y=None,
            spacing=theme.GAP,
            padding=[theme.GUTTER, 0],
        )
        wrapper.bind(minimum_height=wrapper.setter("height"))

        wrapper.add_widget(
            LineLabel(
                text="Your library",
                font_size=theme.FONT_TITLE,
                bold=True,
                size_hint_y=None,
                height=dp(34),
            )
        )

        wrapper.add_widget(
            _stat_grid(
                [
                    ("Want to play", str(data["wishlist_count"])),
                    ("Played", str(data["played_count"])),
                    ("Games opened", str(data["games_viewed"])),
                    ("Searches", str(data["searches"])),
                ]
            )
        )

        if data["played_count"]:
            wrapper.add_widget(Widget(size_hint_y=None, height=theme.GAP))
            wrapper.add_widget(
                LineLabel(
                    text="Your played games",
                    font_size=theme.FONT_HEADING,
                    bold=True,
                    size_hint_y=None,
                    height=dp(30),
                )
            )
            average_rating = data["average_rating"]
            average_mc = data["average_metacritic"]
            wrapper.add_widget(
                _stat_grid(
                    [
                        (
                            "Average rating",
                            f"{average_rating:.1f} / 5" if average_rating else "—",
                        ),
                        ("Average Metacritic", str(average_mc) if average_mc else "—"),
                    ]
                )
            )

        if data["top_genres"]:
            wrapper.add_widget(Widget(size_hint_y=None, height=theme.GAP))
            wrapper.add_widget(
                LineLabel(
                    text="Genres you save most",
                    font_size=theme.FONT_HEADING,
                    bold=True,
                    size_hint_y=None,
                    height=dp(30),
                )
            )
            wrapper.add_widget(
                WrapLabel(
                    text="  ·  ".join(data["top_genres"]),
                    color=theme.ACCENT,
                    font_size=theme.FONT_BODY,
                )
            )

        wrapper.add_widget(Widget(size_hint_y=None, height=theme.GAP_LOOSE))
        wrapper.add_widget(
            WrapLabel(
                text=(
                    "These numbers are calculated on this device from your saved "
                    "games. Nothing is uploaded anywhere."
                ),
                color=theme.TEXT_FAINT,
                font_size=theme.FONT_CAPTION,
            )
        )
        self.content.add_widget(wrapper)


def _stat_grid(items: Sequence) -> BoxLayout:
    """A stack of label/value rows."""
    box = BoxLayout(
        orientation="vertical",
        size_hint_y=None,
        spacing=theme.GAP_TIGHT,
    )
    height = 0.0
    for label, value in items:
        row = RoundedBox(
            bg_color=theme.SURFACE,
            size_hint_y=None,
            height=dp(52),
            padding=[theme.GAP_LOOSE, 0],
        )
        row.add_widget(
            LineLabel(
                text=label,
                font_size=theme.FONT_BODY,
                color=theme.TEXT_MUTED,
                size_hint_x=0.62,
            )
        )
        row.add_widget(
            LineLabel(
                text=value,
                font_size=theme.FONT_HEADING,
                bold=True,
                color=theme.ACCENT,
                halign="right",
                size_hint_x=0.38,
            )
        )
        box.add_widget(row)
        height += dp(52) + theme.GAP_TIGHT
    box.height = height
    return box
