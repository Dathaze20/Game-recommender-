"""Game detail screen.

Rendering is progressive: whatever the card already knew (title, art, rating)
is painted immediately, and the richer fields fill in when the detail request
lands. A user tapping a card therefore never sees an empty "Loading…" page, and
a failed enrichment degrades to the summary rather than a dead end.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence

from kivy.metrics import dp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.screenmanager import Screen
from kivy.uix.scrollview import ScrollView
from kivy.uix.widget import Widget

from ...errors import describe
from ...models import GameDetails
from ...utils import Generation, format_release, join_names, rating_text
from .. import theme
from ..tasks import guarded, run_async
from ..widgets import (
    Badge,
    GameCard,
    HorizontalCards,
    LineLabel,
    PillButton,
    RemoteImage,
    RoundedBox,
    SectionHeading,
    StateView,
    StoreButton,
    WrapLabel,
    paint_background,
    platform_badges,
)

log = logging.getLogger(__name__)

DESCRIPTION_LIMIT = 2600


class DetailScreen(Screen):
    """Everything known about one game, plus what to play next."""

    def __init__(self, controller, **kwargs) -> None:
        super().__init__(**kwargs)
        self.controller = controller
        self.game: GameDetails | None = None
        self._generation = Generation()
        self._build()

    def _build(self) -> None:
        root = BoxLayout(orientation="vertical")
        paint_background(root)

        bar = BoxLayout(
            size_hint_y=None,
            height=theme.HEADER_HEIGHT,
            padding=[theme.GAP, theme.GAP_TIGHT],
            spacing=theme.GAP,
        )
        bar.add_widget(
            PillButton(
                "< Back",
                on_press_callback=self.controller.go_back,
                bg_color=theme.SURFACE_RAISED,
                text_color=theme.TEXT,
                font_size=theme.FONT_BODY,
                size_hint_x=None,
                width=dp(96),
                height=dp(38),
            )
        )
        self.title_label = LineLabel(
            text="",
            font_size=theme.FONT_SUBHEADING,
            bold=True,
            color=theme.TEXT_MUTED,
        )
        bar.add_widget(self.title_label)
        root.add_widget(bar)

        self.scroll = ScrollView(do_scroll_x=False, bar_width=dp(2))
        self.content = BoxLayout(
            orientation="vertical",
            size_hint_y=None,
            spacing=theme.GAP,
            padding=[theme.GUTTER, 0, theme.GUTTER, theme.SECTION_GAP],
        )
        self.content.bind(minimum_height=self.content.setter("height"))
        self.scroll.add_widget(self.content)
        root.add_widget(self.scroll)
        self.add_widget(root)

    # ── entry point ─────────────────────────────────────────────────────
    def show(self, game: GameDetails) -> None:
        """Display ``game``, then enrich it in the background."""
        token = self._generation.next()
        self.game = game
        self.title_label.text = game.name
        self.scroll.scroll_y = 1.0
        self._render(game, enriching=not game.has_detail)

        if game.has_detail:
            self._load_similar(game, token)
            return

        def _done(full: GameDetails) -> None:
            self.game = full
            self._render(full, enriching=False)
            self._load_similar(full, self._generation.current)

        def _failed(exc: BaseException) -> None:
            kind, message = describe(exc)
            self._render(game, enriching=False, error=(kind, message))
            self._load_similar(game, self._generation.current)

        run_async(
            lambda: self.controller.fetch_game_detail(game),
            guarded(self._generation, token, _done),
            guarded(self._generation, token, _failed),
            name=f"detail-{game.game_id}",
        )

    # ── rendering ───────────────────────────────────────────────────────
    def _render(
        self,
        game: GameDetails,
        enriching: bool,
        error: tuple | None = None,
    ) -> None:
        self.content.clear_widgets()
        add = self.content.add_widget

        if game.background_image:
            add(
                RemoteImage(
                    source=game.background_image,
                    fallback_text=game.name,
                    radius=theme.RADIUS_MD,
                    request_width=theme.HERO_IMAGE_WIDTH,
                    size_hint_y=None,
                    height=theme.HERO_HEIGHT,
                )
            )

        add(
            WrapLabel(
                text=game.name,
                font_size=theme.FONT_DISPLAY,
                bold=True,
                color=theme.TEXT,
            )
        )

        add(self._facts_bar(game))
        add(self._action_bar(game))

        if error is not None:
            kind, message = error
            add(
                StateView(
                    kind,
                    "Couldn't load full details",
                    f"{message} Showing what we already had.",
                    action_text="Retry",
                    on_action=lambda: self.show(game),
                    compact=True,
                )
            )
        elif enriching:
            add(
                LineLabel(
                    text="Loading full details...",
                    font_size=theme.FONT_CAPTION,
                    color=theme.TEXT_FAINT,
                    size_hint_y=None,
                    height=dp(22),
                )
            )

        meta_lines = []
        if game.release_date:
            meta_lines.append(f"Released    {format_release(game.release_date)}")
        if game.developers:
            meta_lines.append(f"Developer   {join_names(game.developers, limit=3)}")
        if game.publishers:
            meta_lines.append(f"Publisher   {join_names(game.publishers, limit=3)}")
        if meta_lines:
            card = RoundedBox(
                orientation="vertical",
                bg_color=theme.SURFACE,
                size_hint_y=None,
                padding=[theme.GAP_LOOSE, theme.GAP],
            )
            body = WrapLabel(
                text="\n".join(meta_lines),
                font_size=theme.FONT_CAPTION,
                color=theme.TEXT_MUTED,
                line_height=1.6,
            )
            body.bind(height=lambda _w, h: setattr(card, "height", h + theme.GAP * 2))
            card.add_widget(body)
            add(card)

        badges = platform_badges(game.platforms)
        if badges:
            add(SectionHeading("Available on"))
            strip = HorizontalCards(height=dp(28), spacing=theme.GAP_TIGHT)
            strip.set_children(badges)
            add(strip)

        if game.stores:
            add(SectionHeading("Where to get it"))
            strip = HorizontalCards(height=dp(40), spacing=theme.GAP_TIGHT)
            strip.set_children([StoreButton(link) for link in game.stores])
            add(strip)
            if not any(link.actionable for link in game.stores):
                add(
                    LineLabel(
                        text="RAWG has no direct links for this title.",
                        font_size=theme.FONT_MICRO,
                        color=theme.TEXT_FAINT,
                        size_hint_y=None,
                        height=dp(18),
                    )
                )

        if game.genres:
            add(SectionHeading("Genres"))
            strip = HorizontalCards(height=dp(28), spacing=theme.GAP_TIGHT)
            strip.set_children(
                [
                    Badge(
                        genre,
                        bg_color=theme.PRIMARY_SOFT,
                        text_color=theme.TEXT,
                        font_size=theme.FONT_CAPTION,
                    )
                    for genre in game.genres
                ]
            )
            add(strip)

        if game.description:
            add(SectionHeading("About this game"))
            add(
                WrapLabel(
                    text=game.description[:DESCRIPTION_LIMIT],
                    font_size=theme.FONT_BODY,
                    color=theme.TEXT_MUTED,
                    line_height=1.45,
                )
            )

        if game.screenshots:
            add(SectionHeading("Screenshots"))
            strip = HorizontalCards(height=theme.SHOT_HEIGHT, spacing=theme.GAP)
            strip.set_children(
                [
                    RemoteImage(
                        source=url,
                        radius=theme.RADIUS_SM,
                        request_width=theme.SHOT_IMAGE_WIDTH,
                        size_hint=(None, None),
                        width=theme.SHOT_WIDTH,
                        height=theme.SHOT_HEIGHT,
                    )
                    for url in game.screenshots[:8]
                ]
            )
            add(strip)

        if game.tags:
            add(SectionHeading("Tags"))
            add(
                WrapLabel(
                    text=join_names(game.tags, separator="  ·  ", limit=10),
                    font_size=theme.FONT_CAPTION,
                    color=theme.TEXT_FAINT,
                )
            )

        add(SectionHeading("You might also like"))
        self.similar_slot = BoxLayout(
            orientation="vertical", size_hint_y=None, height=theme.CARD_HEIGHT
        )
        add(self.similar_slot)
        self._set_similar(
            StateView("loading", "Finding similar games", compact=True, size_hint_y=1)
        )

    def _facts_bar(self, game: GameDetails) -> RoundedBox:
        bar = RoundedBox(
            bg_color=theme.SURFACE,
            size_hint_y=None,
            height=dp(46),
            padding=[theme.GAP_LOOSE, theme.GAP_TIGHT],
            spacing=theme.GAP,
        )
        bar.add_widget(
            LineLabel(
                text=rating_text(game.rating),
                font_size=theme.FONT_BODY,
                bold=True,
                color=theme.ACCENT,
            )
        )
        facts = []
        if game.metacritic:
            facts.append(("MC " + str(game.metacritic), theme.metacritic_color(game.metacritic)))
        if game.playtime:
            facts.append((f"~{game.playtime}h", theme.TEXT_MUTED))
        if game.esrb:
            facts.append((game.esrb, theme.TEXT_MUTED))
        for text, color in facts:
            bar.add_widget(
                Badge(
                    text,
                    bg_color=theme.SURFACE_RAISED,
                    text_color=color,
                    font_size=theme.FONT_CAPTION,
                    height=dp(26),
                )
            )
        if not facts:
            bar.add_widget(Widget())
        return bar

    def _action_bar(self, game: GameDetails) -> BoxLayout:
        bar = BoxLayout(size_hint_y=None, height=theme.CONTROL_HEIGHT, spacing=theme.GAP)
        self.wishlist_button = PillButton(
            "", on_press_callback=lambda: self._toggle("wishlist", game)
        )
        self.played_button = PillButton(
            "", on_press_callback=lambda: self._toggle("played", game)
        )
        bar.add_widget(self.wishlist_button)
        bar.add_widget(self.played_button)
        self._sync_action_buttons(game)
        return bar

    def _sync_action_buttons(self, game: GameDetails) -> None:
        storage = self.controller.storage
        wished = storage.contains("wishlist", game.game_id)
        played = storage.contains("played", game.game_id)

        self.wishlist_button.set_text("Saved to play" if wished else "+ Want to play")
        self.wishlist_button.set_colors(
            theme.PRIMARY if wished else theme.SURFACE_RAISED,
            theme.TEXT_ON_PRIMARY if wished else theme.TEXT,
        )
        self.played_button.set_text("Played" if played else "+ Played it")
        self.played_button.set_colors(
            theme.SUCCESS if played else theme.SURFACE_RAISED,
            theme.TEXT_ON_PRIMARY if played else theme.TEXT,
        )

    def _toggle(self, collection: str, game: GameDetails) -> None:
        self.controller.toggle_collection(collection, game)
        self._sync_action_buttons(game)

    # ── similar games ───────────────────────────────────────────────────
    def _set_similar(self, widget: Widget) -> None:
        self.similar_slot.clear_widgets()
        self.similar_slot.add_widget(widget)

    def _load_similar(self, game: GameDetails, token: int) -> None:
        def _done(games: Sequence[GameDetails]) -> None:
            if not games:
                self._set_similar(
                    StateView(
                        "empty",
                        "No suggestions",
                        "RAWG has nothing similar on file for this title.",
                        compact=True,
                        size_hint_y=1,
                    )
                )
                return
            strip = HorizontalCards(height=theme.CARD_HEIGHT)
            strip.set_children(
                [
                    GameCard(game=item, on_select=self.controller.open_game)
                    for item in games
                ]
            )
            self._set_similar(strip)

        def _failed(exc: BaseException) -> None:
            kind, message = describe(exc)
            self._set_similar(
                StateView(
                    kind,
                    "Couldn't load suggestions",
                    message,
                    action_text="Retry",
                    on_action=lambda: self._load_similar(game, self._generation.current),
                    compact=True,
                    size_hint_y=1,
                )
            )

        run_async(
            lambda: self.controller.fetch_similar(game),
            guarded(self._generation, token, _done),
            guarded(self._generation, token, _failed),
            name=f"similar-{game.game_id}",
        )
