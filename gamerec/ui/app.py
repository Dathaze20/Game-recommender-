"""Application shell: wiring, navigation and the controller the screens call.

The screens deliberately know nothing about the API client or the filesystem —
they call methods on this object. That keeps the Kivy code focused on
presentation and leaves the testable work in the plain-Python modules.
"""

from __future__ import annotations

import logging
import logging.handlers
import os
from collections.abc import Sequence

from kivy.app import App
from kivy.core.window import Window
from kivy.loader import Loader
from kivy.uix.screenmanager import NoTransition, ScreenManager, SlideTransition

from .. import __version__
from ..api import RawgClient
from ..config import (
    SOURCE_SAVED,
    ApiKeyStore,
    ResolvedKey,
    resolve_api_key,
)
from ..constants import APP_NAME, SCREENSHOT_PAGE_SIZE, SEARCH_PAGE_SIZE, Category
from ..errors import RawgError
from ..models import (
    GameDetails,
    apply_store_urls,
    parse_game,
    parse_games,
    parse_screenshots,
    parse_store_urls,
)
from ..recommendations import similar_games
from ..storage import (
    LEGACY_FILENAME,
    STAT_GAMES_VIEWED,
    STAT_SEARCHES,
    Storage,
)
from .screens import DetailScreen, HomeScreen, SetupScreen

log = logging.getLogger(__name__)

SCREEN_SETUP = "setup"
SCREEN_HOME = "home"
SCREEN_DETAIL = "detail"

#: Android/desktop "back" maps to this key code in Kivy.
KEY_BACK = 27

#: Below this, it is worth spending a request on the screenshots endpoint.
MIN_GALLERY_SCREENSHOTS = 3


def configure_logging(data_dir: str, level: int = logging.INFO) -> None:
    """Send logs to a rotating file in the data directory, never the CWD.

    Falls back to stderr when the directory is not writable, which is the
    normal situation on a locked-down Android install.
    """
    root = logging.getLogger("gamerec")
    root.setLevel(level)
    if root.handlers:
        return
    formatter = logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
    try:
        os.makedirs(data_dir, exist_ok=True)
        handler: logging.Handler = logging.handlers.RotatingFileHandler(
            os.path.join(data_dir, "game_app.log"),
            maxBytes=512 * 1024,
            backupCount=2,
            encoding="utf-8",
        )
    except OSError:
        handler = logging.StreamHandler()
    handler.setFormatter(formatter)
    root.addHandler(handler)


class GameRecommenderApp(App):
    """Kivy application and the controller its screens delegate to."""

    def build(self):
        self.title = APP_NAME
        Window.clearcolor = (0.055, 0.058, 0.086, 1)
        self._tune_image_loader()

        data_dir = self.user_data_dir
        configure_logging(data_dir)
        log.info("Starting %s %s", APP_NAME, __version__)

        self.key_store = ApiKeyStore(data_dir)
        self.storage = Storage(data_dir)
        self._import_legacy_data()

        self.resolved_key: ResolvedKey = resolve_api_key(data_dir=data_dir)
        self.client = RawgClient(api_key=self.resolved_key.key)

        self.manager = ScreenManager(transition=SlideTransition(duration=0.18))
        self.home = HomeScreen(controller=self, name=SCREEN_HOME)
        self.detail = DetailScreen(controller=self, name=SCREEN_DETAIL)
        self.setup = SetupScreen(
            on_key_accepted=self._on_key_accepted,
            validator=self._validate_key,
            on_cancel=self._close_key_manager,
            on_clear=self._clear_saved_key,
            name=SCREEN_SETUP,
        )
        for screen in (self.setup, self.home, self.detail):
            self.manager.add_widget(screen)

        if self.client.has_key:
            self.manager.current = SCREEN_HOME
            self.home.show_tab("browse")
        else:
            # No key: show setup and make zero API calls.
            self.setup.configure(has_saved_key=False, key_source=None)
            self.manager.current = SCREEN_SETUP

        Window.bind(on_keyboard=self._on_keyboard)
        return self.manager

    @staticmethod
    def _tune_image_loader() -> None:
        """Fetch cover art in parallel without stuttering the scroll.

        Kivy's default of two loader threads makes a row of cards trickle in
        one at a time over mobile latency. `max_upload_per_frame` stays low on
        purpose: it caps how many decoded textures are pushed to the GPU per
        frame, and raising it is what turns image loading into visible jank
        while a row is moving.
        """
        Loader.num_workers = 6
        Loader.max_upload_per_frame = 2

    def on_stop(self) -> None:
        try:
            self.client.close()
        except Exception:  # noqa: BLE001 - shutdown must not raise
            log.debug("Error closing API client", exc_info=True)

    # ── first-run data migration ────────────────────────────────────────
    def _import_legacy_data(self) -> None:
        """Adopt a pre-1.0 config file from the working directory, once.

        Only Pydroid 3 and desktop runs ever had such a file. Inside an APK
        there is no meaningful working directory — and ``os.getcwd()`` can even
        raise there — so the lookup itself is inside the guard.
        """
        try:
            legacy_path = os.path.join(os.getcwd(), LEGACY_FILENAME)
            found_key = self.storage.import_legacy(legacy_path)
        except Exception:  # noqa: BLE001 - never block startup on migration
            log.warning("Legacy import failed", exc_info=True)
            return
        if found_key and not self.key_store.read():
            try:
                self.key_store.write(found_key)
                log.info("Moved the legacy API key into the credential store.")
            except (OSError, ValueError):
                log.warning("Could not migrate the legacy API key", exc_info=True)

    # ── API-key flow ────────────────────────────────────────────────────
    def _validate_key(self, candidate: str) -> None:
        """Confirm a candidate key against RAWG. Raises on failure."""
        probe = RawgClient(api_key=candidate, session=self.client.session)
        probe.validate_key()

    def _on_key_accepted(self, key: str) -> None:
        try:
            self.key_store.write(key)
        except (OSError, ValueError):
            log.warning("Could not persist the API key", exc_info=True)
        self.resolved_key = ResolvedKey(key, SOURCE_SAVED)
        self.client.set_api_key(key)
        self.manager.transition = NoTransition()
        self.manager.current = SCREEN_HOME
        self.manager.transition = SlideTransition(duration=0.18)
        self.home.show_tab("browse")

    def open_key_manager(self) -> None:
        self.setup.configure(
            has_saved_key=bool(self.key_store.read()),
            key_source=self.resolved_key.source,
        )
        self.manager.transition.direction = "left"
        self.manager.current = SCREEN_SETUP

    def _close_key_manager(self) -> None:
        if not self.client.has_key:
            # Nothing to go back to — the app is unusable without a key.
            return
        self.manager.transition.direction = "right"
        self.manager.current = SCREEN_HOME
        self.manager.transition.direction = "left"

    def _clear_saved_key(self) -> None:
        self.key_store.clear()
        refreshed = resolve_api_key(data_dir=self.user_data_dir)
        self.resolved_key = refreshed
        self.client.set_api_key(refreshed.key)
        self.setup.configure(has_saved_key=False, key_source=refreshed.source)
        if not refreshed.key:
            self.manager.current = SCREEN_SETUP

    # ── controller API used by the screens ──────────────────────────────
    def fetch_category(self, category: Category) -> list[GameDetails]:
        return parse_games(self.client.games(category.request_params()))

    def search(self, query: str) -> list[GameDetails]:
        self.storage.bump_stat(STAT_SEARCHES)
        return parse_games(self.client.search(query, page_size=SEARCH_PAGE_SIZE))

    def fetch_game_detail(self, game: GameDetails) -> GameDetails:
        """Full record for ``game``, enriched with store links and shots.

        The detail request is required; the two enrichment requests are
        best-effort, so a missing screenshot endpoint cannot blank the page.
        """
        full = parse_game(self.client.game(game.game_id))
        if not full.game_id:
            full.game_id = game.game_id
        if not full.background_image:
            full.background_image = game.background_image

        try:
            full = apply_store_urls(full, parse_store_urls(self.client.stores(game.game_id)))
        except RawgError as exc:
            log.info("No store links for %s: %s", game.game_id, exc)

        # The detail endpoint carries no screenshots of its own; the summary we
        # started from may have a couple. Top up from the dedicated endpoint
        # whenever we have less than a usable gallery.
        if len(full.screenshots) < MIN_GALLERY_SCREENSHOTS:
            try:
                fetched = parse_screenshots(
                    self.client.screenshots(game.game_id, page_size=SCREENSHOT_PAGE_SIZE)
                )
                if fetched:
                    full.screenshots = fetched
            except RawgError as exc:
                log.info("No screenshots for %s: %s", game.game_id, exc)

        return full

    def fetch_similar(self, game: GameDetails) -> list[GameDetails]:
        return similar_games(self.client, game)

    def toggle_collection(self, collection: str, game: GameDetails) -> bool:
        return self.storage.toggle(collection, game)

    # ── navigation ──────────────────────────────────────────────────────
    def open_game(self, game: GameDetails) -> None:
        self.storage.bump_stat(STAT_GAMES_VIEWED)
        self.manager.transition.direction = "left"
        self.manager.current = SCREEN_DETAIL
        self.detail.show(game)

    def go_back(self) -> None:
        self.manager.transition.direction = "right"
        self.manager.current = SCREEN_HOME
        self.manager.transition.direction = "left"
        self.home.refresh_current_tab()

    def _on_keyboard(self, _window, key: int, *_args) -> bool:
        """Make the hardware/ESC back key behave the way users expect."""
        if key != KEY_BACK:
            return False
        current = self.manager.current
        if current == SCREEN_DETAIL:
            self.go_back()
            return True
        if current == SCREEN_SETUP and self.client.has_key:
            self._close_key_manager()
            return True
        if current == SCREEN_HOME and self.home.tab != "browse":
            self.home.show_tab("browse")
            return True
        return False


def run(argv: Sequence[str] | None = None) -> int:
    """Entry point used by ``main.py``."""
    GameRecommenderApp().run()
    return 0
