"""API-key setup and management.

This screen is the app's front door when no key is configured. Critically, it
is reached *without* making a single API request — the previous build launched
straight into the browse grid and fired dozens of doomed calls whenever a key
was missing or wrong.
"""

from __future__ import annotations

import logging
import threading
from typing import Callable

from kivy.clock import Clock
from kivy.metrics import dp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.screenmanager import Screen
from kivy.uix.scrollview import ScrollView
from kivy.uix.textinput import TextInput
from kivy.uix.widget import Widget

from ...config import looks_like_api_key
from ...constants import RAWG_SIGNUP_URL
from ...errors import RawgError, describe
from .. import theme
from ..links import open_url
from ..widgets import LineLabel, PillButton, RoundedBox, WrapLabel, paint_background

log = logging.getLogger(__name__)

INTRO = (
    "This app reads game data from RAWG, a free video-game database. "
    "You need your own free API key to use it."
)

STEPS = (
    "1.  Open rawg.io/apikey in your browser.\n"
    "2.  Sign up with an email address.\n"
    "3.  Copy the API key shown on that page.\n"
    "4.  Paste it below and tap Save."
)

NOTE = (
    "Your key is stored only on this device and is never shared. "
    "You can change or remove it later from the key button in the header."
)


class SetupScreen(Screen):
    """Collect, validate and store the user's RAWG key."""

    def __init__(
        self,
        on_key_accepted: Callable[[str], None],
        validator: Callable[[str], None],
        on_cancel: Callable[[], None] | None = None,
        on_clear: Callable[[], None] | None = None,
        **kwargs,
    ) -> None:
        super().__init__(**kwargs)
        self._on_key_accepted = on_key_accepted
        self._validate = validator
        self._on_cancel = on_cancel
        self._on_clear = on_clear
        self._busy = False
        self._build()

    # ── construction ────────────────────────────────────────────────────
    def _build(self) -> None:
        root = BoxLayout(orientation="vertical")
        paint_background(root)

        scroll = ScrollView(do_scroll_x=False)
        content = BoxLayout(
            orientation="vertical",
            size_hint_y=None,
            spacing=theme.GAP,
            padding=[theme.GUTTER, theme.SECTION_GAP, theme.GUTTER, theme.SECTION_GAP],
        )
        content.bind(minimum_height=content.setter("height"))

        content.add_widget(
            LineLabel(
                text="Set up your RAWG key",
                font_size=theme.FONT_DISPLAY,
                bold=True,
                size_hint_y=None,
                height=dp(40),
            )
        )
        content.add_widget(WrapLabel(text=INTRO, color=theme.TEXT_MUTED))
        content.add_widget(Widget(size_hint_y=None, height=theme.GAP))

        steps_card = RoundedBox(
            orientation="vertical",
            bg_color=theme.SURFACE,
            size_hint_y=None,
            padding=[theme.GAP_LOOSE, theme.GAP_LOOSE],
        )
        steps_label = WrapLabel(
            text=STEPS,
            color=theme.TEXT,
            font_size=theme.FONT_BODY,
            line_height=1.5,
        )
        steps_label.bind(
            height=lambda _w, h: setattr(steps_card, "height", h + theme.GAP_LOOSE * 2)
        )
        steps_card.add_widget(steps_label)
        content.add_widget(steps_card)

        content.add_widget(
            PillButton(
                "Open rawg.io/apikey",
                on_press_callback=self._open_signup,
                bg_color=theme.SURFACE_RAISED,
                text_color=theme.TEXT,
            )
        )

        content.add_widget(Widget(size_hint_y=None, height=theme.GAP))
        content.add_widget(
            LineLabel(
                text="Paste your API key",
                font_size=theme.FONT_CAPTION,
                bold=True,
                color=theme.TEXT_FAINT,
                size_hint_y=None,
                height=dp(20),
            )
        )

        field = RoundedBox(
            bg_color=theme.SURFACE,
            border_color=theme.BORDER,
            size_hint_y=None,
            height=theme.CONTROL_HEIGHT,
            padding=[dp(4), dp(2)],
        )
        self.input = TextInput(
            hint_text="32-character key",
            multiline=False,
            write_tab=False,
            background_color=theme.TRANSPARENT,
            background_normal="",
            background_active="",
            foreground_color=theme.TEXT,
            hint_text_color=theme.TEXT_FAINT,
            cursor_color=theme.PRIMARY,
            font_size=theme.FONT_BODY,
            padding=[dp(10), dp(11)],
        )
        self.input.bind(on_text_validate=lambda _w: self._submit())
        self.input.bind(text=lambda *_a: self._clear_status())
        field.add_widget(self.input)
        content.add_widget(field)

        self.status = WrapLabel(
            text="",
            color=theme.DANGER,
            font_size=theme.FONT_CAPTION,
        )
        content.add_widget(self.status)

        self.save_button = PillButton("Save and continue", on_press_callback=self._submit)
        content.add_widget(self.save_button)

        self.secondary = BoxLayout(
            size_hint_y=None, height=theme.CONTROL_HEIGHT, spacing=theme.GAP
        )
        content.add_widget(self.secondary)

        content.add_widget(Widget(size_hint_y=None, height=theme.GAP))
        content.add_widget(
            WrapLabel(text=NOTE, color=theme.TEXT_FAINT, font_size=theme.FONT_CAPTION)
        )

        scroll.add_widget(content)
        root.add_widget(scroll)
        self.add_widget(root)

    # ── modes ───────────────────────────────────────────────────────────
    def configure(self, has_saved_key: bool, key_source: str | None = None) -> None:
        """Switch between first-run setup and managing an existing key."""
        self.secondary.clear_widgets()
        self._clear_status()
        self.input.text = ""

        if key_source and key_source != "saved":
            self.status.color = theme.TEXT_MUTED
            self.status.text = (
                f"A key is currently supplied by the {key_source}. Saving one here "
                "will be ignored until that is removed."
            )

        if has_saved_key and self._on_clear is not None:
            self.secondary.add_widget(
                PillButton(
                    "Remove saved key",
                    on_press_callback=self._clear_key,
                    bg_color=theme.SURFACE_RAISED,
                    text_color=theme.DANGER,
                )
            )
        if self._on_cancel is not None:
            self.secondary.add_widget(
                PillButton(
                    "Cancel",
                    on_press_callback=self._on_cancel,
                    bg_color=theme.SURFACE_RAISED,
                    text_color=theme.TEXT_MUTED,
                )
            )
        self.secondary.height = (
            theme.CONTROL_HEIGHT if self.secondary.children else 0
        )

    # ── actions ─────────────────────────────────────────────────────────
    def _open_signup(self) -> None:
        if not open_url(RAWG_SIGNUP_URL):
            self._show_status(
                "Couldn't open a browser. Visit rawg.io/apikey yourself to get a key.",
                theme.TEXT_MUTED,
            )

    def _clear_status(self, *_args) -> None:
        if not self._busy:
            self.status.text = ""

    def _show_status(self, message: str, color=theme.DANGER) -> None:
        self.status.color = color
        self.status.text = message

    def _clear_key(self) -> None:
        if self._on_clear is not None:
            self._on_clear()

    def _submit(self) -> None:
        if self._busy:
            return
        candidate = self.input.text.strip()
        if not candidate:
            self._show_status("Paste your RAWG API key first.")
            return
        if not looks_like_api_key(candidate):
            self._show_status(
                "That doesn't look like a RAWG key — they are 32 characters of "
                "letters a-f and digits. Check for a stray space."
            )
            return

        self._set_busy(True)
        self._show_status("Checking your key with RAWG...", theme.TEXT_MUTED)

        def _worker() -> None:
            try:
                self._validate(candidate)
            except RawgError as exc:
                _, message = describe(exc)
                Clock.schedule_once(lambda _dt, m=message: self._fail(m), 0)
            except Exception as exc:  # noqa: BLE001 - surface, never crash
                log.exception("Unexpected error validating API key")
                Clock.schedule_once(
                    lambda _dt, m=str(exc) or "Unexpected error.": self._fail(m), 0
                )
            else:
                Clock.schedule_once(lambda _dt: self._succeed(candidate), 0)

        threading.Thread(target=_worker, daemon=True).start()

    def _set_busy(self, busy: bool) -> None:
        self._busy = busy
        self.save_button.disabled = busy
        self.save_button.set_text("Checking..." if busy else "Save and continue")

    def _fail(self, message: str) -> None:
        self._set_busy(False)
        self._show_status(message)

    def _succeed(self, key: str) -> None:
        self._set_busy(False)
        self._show_status("Key accepted.", theme.SUCCESS)
        self._on_key_accepted(key)
