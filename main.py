import os
import logging
from typing import List, Optional
from functools import partial
from threading import Thread

import requests
from dotenv import load_dotenv
from kivy.app import App
from kivy.uix.image import AsyncImage
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.label import Label
from kivy.uix.gridlayout import GridLayout
from kivy.uix.scrollview import ScrollView
from kivy.uix.popup import Popup
from kivy.uix.textinput import TextInput
from kivy.clock import Clock
from kivy.config import Config
from kivy.core.window import Window
from kivy.uix.screenmanager import ScreenManager, Screen, SlideTransition
from kivy.uix.button import Button
from kivy.uix.togglebutton import ToggleButton
from kivy.graphics import Color, Rectangle, RoundedRectangle
from kivy.lang import Builder
from kivy.metrics import dp, sp

logging.basicConfig(
    filename='game_app.log',
    level=logging.INFO,
    format='%(asctime)s:%(levelname)s:%(message)s'
)

load_dotenv()

Config.set('graphics', 'width', '420')
Config.set('graphics', 'height', '750')
Config.set('kivy', 'keyboard_mode', 'system')

API_KEY = os.getenv('GAME_API_KEY', 'your_api_key_here')
BASE_URL = "https://api.rawg.io/api"

# RAWG platform IDs
PLATFORMS = {
    "All":       None,
    "PS5":       187,
    "PS4":       18,
    "Xbox X|S":  186,
    "Xbox One":  1,
    "Switch":    7,
    "PC":        4,
    "iOS":       3,
    "Android":   21,
}

PLATFORM_COLORS = {
    "PS5":      (0.0, 0.32, 0.73, 1),
    "PS4":      (0.0, 0.27, 0.63, 1),
    "Xbox X|S": (0.07, 0.49, 0.04, 1),
    "Xbox One": (0.04, 0.38, 0.03, 1),
    "Switch":   (0.89, 0.05, 0.05, 1),
    "PC":       (0.4, 0.4, 0.5, 1),
    "iOS":      (0.35, 0.35, 0.35, 1),
    "Android":  (0.24, 0.6, 0.18, 1),
}

PLATFORM_BADGES = {
    "PlayStation 5": ("PS5", (0.0, 0.32, 0.73, 1)),
    "PlayStation 4": ("PS4", (0.0, 0.27, 0.63, 1)),
    "PlayStation 3": ("PS3", (0.0, 0.22, 0.53, 1)),
    "Xbox Series S/X": ("XSX", (0.07, 0.49, 0.04, 1)),
    "Xbox One": ("XB1", (0.04, 0.38, 0.03, 1)),
    "Xbox 360": ("360", (0.06, 0.42, 0.03, 1)),
    "Nintendo Switch": ("NSW", (0.89, 0.05, 0.05, 1)),
    "PC": ("PC", (0.4, 0.4, 0.5, 1)),
    "macOS": ("Mac", (0.35, 0.35, 0.35, 1)),
    "Linux": ("LNX", (0.85, 0.55, 0.1, 1)),
    "iOS": ("iOS", (0.35, 0.35, 0.35, 1)),
    "Android": ("AND", (0.24, 0.6, 0.18, 1)),
    "Nintendo 3DS": ("3DS", (0.8, 0.1, 0.1, 1)),
    "PS Vita": ("PSV", (0.0, 0.22, 0.53, 1)),
    "Wii U": ("WiiU", (0.0, 0.47, 0.78, 1)),
}

STORE_NAMES = {
    1: "Steam", 2: "Xbox Store", 3: "PlayStation Store", 4: "App Store",
    5: "GOG", 6: "Nintendo eShop", 7: "Xbox 360 Store", 8: "Google Play",
    9: "itch.io", 11: "Epic Games",
}

STORE_COLORS = {
    "Steam":             (0.08, 0.11, 0.18, 1),
    "Xbox Store":        (0.07, 0.49, 0.04, 1),
    "PlayStation Store": (0.0, 0.32, 0.73, 1),
    "Nintendo eShop":    (0.89, 0.05, 0.05, 1),
    "Epic Games":        (0.1, 0.1, 0.1, 1),
    "GOG":               (0.5, 0.1, 0.6, 1),
    "App Store":         (0.0, 0.48, 1.0, 1),
    "Google Play":       (0.24, 0.6, 0.18, 1),
    "itch.io":           (0.85, 0.25, 0.35, 1),
}

GENRE_SLUG_MAP = {
    "Action": "action", "Adventure": "adventure", "RPG": "role-playing-games-rpg",
    "Strategy": "strategy", "Shooter": "shooter", "Puzzle": "puzzle",
    "Racing": "racing", "Sports": "sports", "Simulation": "simulation",
    "Platformer": "platformer", "Fighting": "fighting", "Indie": "indie",
}

SORT_OPTIONS = {
    "Popular":    "-added",
    "Top Rated":  "-rating",
    "New Releases": "-released",
}

# ─── Kivy Style ───
Builder.load_string('''
<TabBtn@ToggleButton>:
    size_hint: None, 1
    width: dp(110)
    font_size: sp(13)
    bold: True
    background_normal: ''
    background_down: ''
    background_color: (0.38, 0.31, 0.85, 1) if self.state == 'down' else (0.14, 0.14, 0.20, 1)
    color: (1, 1, 1, 1)
    markup: True

<PlatBtn@ToggleButton>:
    size_hint: None, 1
    width: dp(70)
    font_size: sp(11)
    bold: True
    background_normal: ''
    background_down: ''
    color: (1, 1, 1, 1)
    markup: True

<GenreBtn@Button>:
    size_hint: None, 1
    width: dp(80)
    font_size: sp(11)
    background_normal: ''
    background_down: ''
    color: (1, 1, 1, 1)
''')


class GameDetails:
    def __init__(self, game_id, name, description, release_date, background_image,
                 rating, metacritic, genres, platforms, stores, screenshots,
                 esrb, playtime, developers, publishers, tags):
        self.game_id = game_id
        self.name = name
        self.description = description
        self.release_date = release_date
        self.background_image = background_image
        self.rating = rating
        self.metacritic = metacritic
        self.genres = genres
        self.platforms = platforms
        self.stores = stores
        self.screenshots = screenshots
        self.esrb = esrb
        self.playtime = playtime
        self.developers = developers
        self.publishers = publishers
        self.tags = tags


def parse_game(data: dict) -> GameDetails:
    genres = [g['name'] for g in data.get('genres', [])]
    platforms = [p['platform']['name'] for p in data.get('platforms', []) if 'platform' in p]
    stores = []
    for s in data.get('stores', []):
        store_obj = s.get('store', {})
        sid = store_obj.get('id')
        stores.append(STORE_NAMES.get(sid, store_obj.get('name', 'Unknown')))
    screenshots = [ss.get('image', '') for ss in data.get('short_screenshots', data.get('screenshots', []))]
    esrb = data.get('esrb_rating') or {}
    developers = [d['name'] for d in data.get('developers', [])]
    publishers = [p['name'] for p in data.get('publishers', [])]
    tags = [t['name'] for t in data.get('tags', [])[:8]]
    return GameDetails(
        game_id=data.get('id', 0),
        name=data.get('name', 'Unknown'),
        description=data.get('description_raw', data.get('description', 'No description available')),
        release_date=data.get('released', 'Unknown'),
        rating=data.get('rating', 0.0),
        metacritic=data.get('metacritic'),
        genres=genres, platforms=platforms, stores=stores,
        screenshots=screenshots,
        esrb=esrb.get('name', 'Not Rated') if esrb else 'Not Rated',
        playtime=data.get('playtime', 0),
        developers=developers, publishers=publishers, tags=tags,
        background_image=data.get('background_image', '')
    )


def api_get(endpoint, params):
    params['key'] = API_KEY
    try:
        resp = requests.get(f"{BASE_URL}/{endpoint}", params=params, timeout=15)
        resp.raise_for_status()
        return resp.json()
    except requests.RequestException as e:
        logging.error(f"API error [{endpoint}]: {e}")
    return None


def fetch_games(page=1, genre=None, platform_id=None, ordering='-added', page_size=12, search=None):
    params = {'page': page, 'page_size': page_size, 'ordering': ordering}
    if genre and genre in GENRE_SLUG_MAP:
        params['genres'] = GENRE_SLUG_MAP[genre]
    if platform_id:
        params['platforms'] = platform_id
    if search:
        params['search'] = search
        params.pop('ordering', None)
    data = api_get("games", params)
    if data:
        return [parse_game(g) for g in data.get('results', [])], data.get('count', 0)
    return None, 0


def fetch_game_full(game_id):
    data = api_get(f"games/{game_id}", {})
    if data:
        ss_data = api_get(f"games/{game_id}/screenshots", {'page_size': 6})
        if ss_data:
            data['screenshots'] = ss_data.get('results', [])
        return parse_game(data)
    return None


def fetch_similar_games(game_id):
    data = api_get(f"games/{game_id}/suggested", {'page_size': 6})
    if data and data.get('results'):
        return [parse_game(g) for g in data['results']]
    data = api_get(f"games/{game_id}/game-series", {'page_size': 6})
    if data and data.get('results'):
        return [parse_game(g) for g in data['results']]
    return None


# ─── Custom Widgets ───

class GameCard(BoxLayout):
    def __init__(self, game, on_tap=None, **kwargs):
        super().__init__(**kwargs)
        self.orientation = 'vertical'
        self.size_hint_y = None
        self.padding = [dp(4), dp(4), dp(4), dp(6)]
        self.spacing = dp(4)
        self.game = game

        card_width = (Window.width - dp(40)) / 3
        img_height = card_width * 1.35
        self.height = img_height + dp(70)

        with self.canvas.before:
            Color(0.12, 0.12, 0.18, 1)
            self._bg = RoundedRectangle(pos=self.pos, size=self.size, radius=[dp(8)])
        self.bind(pos=self._upd, size=self._upd)

        if game.background_image:
            img = AsyncImage(source=game.background_image, size_hint_y=None,
                             height=img_height, allow_stretch=True, keep_ratio=False)
            self.add_widget(img)
        else:
            self.add_widget(Label(text="No Image", size_hint_y=None, height=img_height,
                                  color=(0.3, 0.3, 0.3, 1)))

        name_label = Label(
            text=game.name, font_size=sp(12), size_hint_y=None, height=dp(32),
            text_size=(card_width - dp(10), dp(32)), halign='left', valign='middle',
            shorten=True, shorten_from='right', bold=True, color=(1, 1, 1, 1)
        )
        self.add_widget(name_label)

        info_row = BoxLayout(size_hint_y=None, height=dp(18), spacing=dp(2))

        stars_filled = int(game.rating)
        star_text = "[color=ffcc00]" + ("★" * stars_filled) + "[/color]"
        star_text += "[color=555555]" + ("★" * (5 - stars_filled)) + "[/color]"
        star_text += f" {game.rating:.1f}"
        info_row.add_widget(Label(text=star_text, markup=True, font_size=sp(10),
                                  size_hint_x=0.65, halign='left',
                                  text_size=(card_width * 0.6, None), color=(1, 0.85, 0.3, 1)))

        year = (game.release_date or "")[:4]
        info_row.add_widget(Label(text=year, font_size=sp(10), size_hint_x=0.35,
                                  halign='right', color=(0.5, 0.5, 0.6, 1)))
        self.add_widget(info_row)

        if on_tap:
            self.bind(on_touch_down=lambda inst, touch: on_tap(game) if inst.collide_point(*touch.pos) else None)

    def _upd(self, *a):
        self._bg.pos = self.pos
        self._bg.size = self.size


class PlatformBadge(BoxLayout):
    def __init__(self, text, color, **kwargs):
        super().__init__(**kwargs)
        self.size_hint = (None, None)
        self.size = (dp(36), dp(18))
        self.padding = [dp(3), dp(1)]
        with self.canvas.before:
            Color(*color)
            self._bg = RoundedRectangle(pos=self.pos, size=self.size, radius=[dp(4)])
        self.bind(pos=self._u, size=self._u)
        self.add_widget(Label(text=text, font_size=sp(9), bold=True))

    def _u(self, *a):
        self._bg.pos = self.pos
        self._bg.size = self.size


class StoreBadge(Button):
    def __init__(self, store_name, **kwargs):
        col = STORE_COLORS.get(store_name, (0.2, 0.2, 0.3, 1))
        super().__init__(text=store_name, size_hint=(None, None), width=dp(120),
                         height=dp(34), background_color=col, font_size=sp(11),
                         bold=True, background_normal='', **kwargs)


# ─── Main App ───

class GameRecommenderApp(App):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.current_page = 1
        self.current_genre = "All"
        self.current_platform = "All"
        self.current_sort = "Popular"
        self.search_query = ""
        self.total_count = 0
        self.search_event = None

    def build(self):
        self.title = "Game Recommender"
        Window.clearcolor = (0.09, 0.09, 0.13, 1)
        self.sm = ScreenManager(transition=SlideTransition())
        self.sm.add_widget(self._build_main_screen())
        self.sm.add_widget(Screen(name="detail"))
        return self.sm

    # ─── Main Screen ───
    def _build_main_screen(self):
        screen = Screen(name="main")
        root = BoxLayout(orientation='vertical', spacing=dp(6),
                         padding=[dp(10), dp(10), dp(10), dp(6)])

        # Title
        root.add_widget(Label(
            text="[b]Popular Games[/b]", markup=True, font_size=sp(26),
            size_hint_y=None, height=dp(44), halign='left',
            text_size=(Window.width - dp(20), dp(44)), valign='middle',
            color=(1, 1, 1, 1)
        ))

        # Search bar
        search_row = BoxLayout(size_hint_y=None, height=dp(42), spacing=dp(6))
        self.search_input = TextInput(
            hint_text='Search games...', multiline=False,
            size_hint_x=0.82,
            background_color=(0.16, 0.16, 0.22, 1), foreground_color=(1, 1, 1, 1),
            hint_text_color=(0.4, 0.4, 0.5, 1), cursor_color=(0.5, 0.4, 1, 1),
            padding=[dp(14), dp(10), dp(14), dp(10)],
            font_size=sp(14)
        )
        self.search_input.bind(on_text_validate=lambda x: self._do_search())
        search_row.add_widget(self.search_input)
        search_btn = Button(text="🔍", size_hint_x=0.18, font_size=sp(18),
                            background_normal='', background_color=(0.38, 0.31, 0.85, 1))
        search_btn.bind(on_release=lambda x: self._do_search())
        search_row.add_widget(search_btn)
        root.add_widget(search_row)

        # Sort tabs (Popular / Top Rated / New Releases) — matches movie app style
        tab_row = BoxLayout(size_hint_y=None, height=dp(38), spacing=dp(4))
        self.sort_buttons = {}
        for sname in SORT_OPTIONS:
            btn = ToggleButton(
                text=sname, group='sort', size_hint_x=1,
                font_size=sp(13), bold=True,
                state='down' if sname == "Popular" else 'normal',
                background_normal='', background_down='',
                background_color=(0.38, 0.31, 0.85, 1) if sname == "Popular" else (0.14, 0.14, 0.20, 1),
                color=(1, 1, 1, 1)
            )
            btn.bind(on_release=partial(self._on_sort_select, sname))
            tab_row.add_widget(btn)
            self.sort_buttons[sname] = btn
        root.add_widget(tab_row)

        # Platform filter bar (scrollable)
        plat_scroll = ScrollView(size_hint_y=None, height=dp(34), do_scroll_y=False)
        plat_row = BoxLayout(size_hint=(None, 1), spacing=dp(4))
        plat_row.bind(minimum_width=plat_row.setter('width'))
        self.plat_buttons = {}
        for pname in PLATFORMS:
            col = PLATFORM_COLORS.get(pname, (0.3, 0.5, 0.9, 1))
            active = pname == "All"
            btn = ToggleButton(
                text=pname, group='platform', size_hint=(None, 1), width=dp(68),
                font_size=sp(11), bold=True,
                state='down' if active else 'normal',
                background_normal='', background_down='',
                background_color=col if active else (0.14, 0.14, 0.20, 1),
                color=(1, 1, 1, 1)
            )
            btn.bind(on_release=partial(self._on_platform_select, pname))
            plat_row.add_widget(btn)
            self.plat_buttons[pname] = btn
        plat_scroll.add_widget(plat_row)
        root.add_widget(plat_scroll)

        # Genre filter bar (scrollable)
        genre_scroll = ScrollView(size_hint_y=None, height=dp(30), do_scroll_y=False)
        genre_row = BoxLayout(size_hint=(None, 1), spacing=dp(3))
        genre_row.bind(minimum_width=genre_row.setter('width'))
        self.genre_buttons = {}
        genres = ["All", "Action", "Adventure", "RPG", "Shooter", "Strategy",
                  "Racing", "Sports", "Puzzle", "Platformer", "Fighting", "Indie", "Simulation"]
        for g in genres:
            active = g == "All"
            btn = Button(
                text=g, size_hint=(None, 1), width=dp(75),
                font_size=sp(10),
                background_normal='', background_down='',
                background_color=(0.28, 0.22, 0.65, 1) if active else (0.12, 0.12, 0.18, 1),
                color=(0.85, 0.85, 0.95, 1) if active else (0.5, 0.5, 0.6, 1)
            )
            btn.bind(on_release=partial(self._on_genre_select, g))
            genre_row.add_widget(btn)
            self.genre_buttons[g] = btn
        genre_scroll.add_widget(genre_row)
        root.add_widget(genre_scroll)

        # Game grid (scrollable)
        scroll = ScrollView(do_scroll_x=False)
        self.grid = GridLayout(cols=3, spacing=dp(8), padding=[dp(2), dp(6), dp(2), dp(6)],
                               size_hint_y=None)
        self.grid.bind(minimum_height=self.grid.setter('height'))
        scroll.add_widget(self.grid)
        root.add_widget(scroll)

        # Pagination
        nav = BoxLayout(size_hint_y=None, height=dp(38), spacing=dp(8))
        self.prev_btn = Button(text="◄ Prev", background_normal='',
                               background_color=(0.16, 0.16, 0.24, 1),
                               font_size=sp(12), disabled=True)
        self.prev_btn.bind(on_release=lambda x: self._change_page(-1))
        nav.add_widget(self.prev_btn)
        self.page_label = Label(text="Page 1", font_size=sp(12), color=(0.55, 0.55, 0.65, 1))
        nav.add_widget(self.page_label)
        self.next_btn = Button(text="Next ►", background_normal='',
                               background_color=(0.16, 0.16, 0.24, 1), font_size=sp(12))
        self.next_btn.bind(on_release=lambda x: self._change_page(1))
        nav.add_widget(self.next_btn)
        root.add_widget(nav)

        screen.add_widget(root)

        # Show loading and fetch
        self.loading_popup = Popup(
            title='', content=Label(text="Loading games...", font_size=sp(14)),
            size_hint=(None, None), size=(dp(200), dp(100)), auto_dismiss=False,
            separator_height=0, background_color=(0.1, 0.1, 0.15, 0.9)
        )
        self.loading_popup.open()
        Clock.schedule_once(lambda dt: self._load_games(), 0.3)
        return screen

    # ─── Filters ───
    def _do_search(self):
        query = self.search_input.text.strip()
        if query:
            self.search_query = query
            self.current_page = 1
            self._load_games()
        elif self.search_query:
            self.search_query = ""
            self.current_page = 1
            self._load_games()

    def _on_sort_select(self, sname, btn):
        self.current_sort = sname
        self.current_page = 1
        for s, b in self.sort_buttons.items():
            b.background_color = (0.38, 0.31, 0.85, 1) if s == sname else (0.14, 0.14, 0.20, 1)
            b.state = 'down' if s == sname else 'normal'
        self._load_games()

    def _on_platform_select(self, pname, btn):
        self.current_platform = pname
        self.current_page = 1
        for name, b in self.plat_buttons.items():
            active = name == pname
            col = PLATFORM_COLORS.get(name, (0.3, 0.5, 0.9, 1))
            b.background_color = col if active else (0.14, 0.14, 0.20, 1)
            b.state = 'down' if active else 'normal'
        self._load_games()

    def _on_genre_select(self, genre, btn):
        self.current_genre = genre
        self.current_page = 1
        for g, b in self.genre_buttons.items():
            active = g == genre
            b.background_color = (0.28, 0.22, 0.65, 1) if active else (0.12, 0.12, 0.18, 1)
            b.color = (0.85, 0.85, 0.95, 1) if active else (0.5, 0.5, 0.6, 1)
        self._load_games()

    def _change_page(self, delta):
        self.current_page = max(1, self.current_page + delta)
        self._load_games()

    # ─── Load Games ───
    def _load_games(self):
        self.grid.clear_widgets()
        self.grid.add_widget(Label(text="Loading...", font_size=sp(14),
                                   size_hint_y=None, height=dp(50), color=(0.5, 0.5, 0.6, 1)))

        if not API_KEY or API_KEY == 'your_api_key_here':
            self.grid.clear_widgets()
            self.grid.add_widget(Label(
                text="Set GAME_API_KEY in .env\nGet one free at rawg.io/apidocs",
                font_size=sp(13), size_hint_y=None, height=dp(80),
                color=(1, 0.5, 0.5, 1), halign='center', valign='middle',
                text_size=(Window.width - dp(40), None)
            ))
            self._dismiss_loading()
            return

        def _fetch():
            platform_id = PLATFORMS.get(self.current_platform)
            genre = self.current_genre if self.current_genre != "All" else None
            ordering = SORT_OPTIONS.get(self.current_sort, '-added')
            search = self.search_query or None
            games, count = fetch_games(page=self.current_page, genre=genre,
                                       platform_id=platform_id, ordering=ordering,
                                       search=search)
            Clock.schedule_once(lambda dt: self._display_games(games, count))

        Thread(target=_fetch, daemon=True).start()

    def _display_games(self, games, count):
        self.grid.clear_widgets()
        self.total_count = count

        if games:
            for game in games:
                card = GameCard(game=game, on_tap=self._show_detail)
                self.grid.add_widget(card)
            total_pages = max(1, (count + 11) // 12)
            self.page_label.text = f"Page {self.current_page} / {total_pages}"
            self.prev_btn.disabled = self.current_page <= 1
            self.next_btn.disabled = self.current_page >= total_pages
        else:
            self.grid.add_widget(Label(
                text="No games found.\nTry a different filter.", font_size=sp(13),
                size_hint_y=None, height=dp(80), color=(0.5, 0.5, 0.6, 1),
                halign='center', text_size=(Window.width - dp(40), None)
            ))
            self.page_label.text = "Page 1"
            self.prev_btn.disabled = True
            self.next_btn.disabled = True

        self._dismiss_loading()

    def _dismiss_loading(self):
        try:
            if self.loading_popup._is_open:
                self.loading_popup.dismiss()
        except Exception:
            pass

    # ─── Detail Screen ───
    def _show_detail(self, game):
        detail_screen = self.sm.get_screen("detail")
        detail_screen.clear_widgets()

        loading_layout = BoxLayout(orientation='vertical')
        with loading_layout.canvas.before:
            Color(0.09, 0.09, 0.13, 1)
            Rectangle(pos=(0, 0), size=Window.size)
        loading_layout.add_widget(Label(text="Loading details...", font_size=sp(16),
                                        color=(0.5, 0.5, 0.6, 1)))
        detail_screen.add_widget(loading_layout)
        self.sm.current = "detail"

        def _fetch():
            full = fetch_game_full(game.game_id) or game
            Clock.schedule_once(lambda dt: self._render_detail(full))

        Thread(target=_fetch, daemon=True).start()

    def _render_detail(self, game):
        detail_screen = self.sm.get_screen("detail")
        detail_screen.clear_widgets()

        root = BoxLayout(orientation='vertical')
        with root.canvas.before:
            Color(0.09, 0.09, 0.13, 1)
            Rectangle(pos=(0, 0), size=Window.size)

        # Back button bar
        top_bar = BoxLayout(size_hint_y=None, height=dp(44), padding=[dp(8), dp(4)])
        back_btn = Button(text="◄  Back", size_hint_x=None, width=dp(90),
                          font_size=sp(13), background_normal='',
                          background_color=(0.2, 0.2, 0.3, 1))
        back_btn.bind(on_release=lambda x: self._go_back())
        top_bar.add_widget(back_btn)
        top_bar.add_widget(Label())
        root.add_widget(top_bar)

        scroll = ScrollView(do_scroll_x=False)
        content = BoxLayout(orientation='vertical', spacing=dp(10),
                            padding=[dp(14), dp(6), dp(14), dp(20)], size_hint_y=None)
        content.bind(minimum_height=content.setter('height'))

        # Game title
        content.add_widget(Label(
            text=f"[b]{game.name}[/b]", markup=True, font_size=sp(22),
            size_hint_y=None, height=dp(36), color=(1, 1, 1, 1),
            halign='left', text_size=(Window.width - dp(30), None)
        ))

        # Main image
        if game.background_image:
            content.add_widget(AsyncImage(
                source=game.background_image, size_hint_y=None,
                height=dp(220), allow_stretch=True, keep_ratio=True
            ))

        # Rating bar
        info_bar = BoxLayout(size_hint_y=None, height=dp(40), spacing=dp(8),
                             padding=[dp(10), dp(6)])
        with info_bar.canvas.before:
            Color(0.12, 0.12, 0.18, 1)
            info_bar._bg = RoundedRectangle(pos=info_bar.pos, size=info_bar.size, radius=[dp(8)])
        info_bar.bind(pos=lambda w, p: setattr(w._bg, 'pos', p),
                      size=lambda w, s: setattr(w._bg, 'size', s))

        stars = int(game.rating)
        star_str = "[color=ffcc00]" + ("★" * stars) + "[/color]"
        star_str += "[color=444444]" + ("★" * (5 - stars)) + "[/color]"
        info_bar.add_widget(Label(text=f"{star_str} {game.rating:.1f}", markup=True,
                                  font_size=sp(14), size_hint_x=0.3))
        if game.metacritic:
            mc_c = "00ff00" if game.metacritic >= 75 else "ffff00" if game.metacritic >= 50 else "ff4444"
            info_bar.add_widget(Label(text=f"MC: [color={mc_c}][b]{game.metacritic}[/b][/color]",
                                      markup=True, font_size=sp(13), size_hint_x=0.25))
        if game.playtime:
            info_bar.add_widget(Label(text=f"~{game.playtime}h", font_size=sp(12),
                                      color=(0.6, 0.6, 0.7, 1), size_hint_x=0.2))
        info_bar.add_widget(Label(text=game.esrb if game.esrb != 'Not Rated' else '',
                                  font_size=sp(11), color=(0.6, 0.6, 0.7, 1), size_hint_x=0.25))
        content.add_widget(info_bar)

        # Release / Developer / Publisher
        meta_lines = [f"Released: {game.release_date or 'TBA'}"]
        if game.developers:
            meta_lines.append(f"Developer: {', '.join(game.developers)}")
        if game.publishers:
            meta_lines.append(f"Publisher: {', '.join(game.publishers)}")
        meta_text = "\n".join(meta_lines)
        meta_label = Label(text=meta_text, font_size=sp(11), size_hint_y=None,
                           color=(0.6, 0.65, 0.75, 1), halign='left', valign='top',
                           text_size=(Window.width - dp(30), None))
        meta_label.bind(texture_size=meta_label.setter('size'))
        content.add_widget(meta_label)

        # Platform badges
        if game.platforms:
            content.add_widget(Label(text="[b]Available On[/b]", markup=True, font_size=sp(14),
                                     size_hint_y=None, height=dp(28), color=(0.5, 0.4, 1, 1),
                                     halign='left', text_size=(Window.width - dp(30), None)))
            badge_row = BoxLayout(size_hint_y=None, height=dp(24), spacing=dp(4))
            for plat in game.platforms:
                if plat in PLATFORM_BADGES:
                    abbr, col = PLATFORM_BADGES[plat]
                    badge_row.add_widget(PlatformBadge(abbr, col))
            badge_row.add_widget(Label())  # spacer
            content.add_widget(badge_row)

        # Stores
        if game.stores:
            content.add_widget(Label(text="[b]Buy / Download[/b]", markup=True, font_size=sp(14),
                                     size_hint_y=None, height=dp(28), color=(0.5, 0.4, 1, 1),
                                     halign='left', text_size=(Window.width - dp(30), None)))
            store_scroll = ScrollView(size_hint_y=None, height=dp(40), do_scroll_y=False)
            store_row = BoxLayout(size_hint=(None, 1), spacing=dp(6))
            store_row.bind(minimum_width=store_row.setter('width'))
            for store in game.stores:
                store_row.add_widget(StoreBadge(store))
            store_scroll.add_widget(store_row)
            content.add_widget(store_scroll)

        # Genres
        if game.genres:
            genre_text = "  ·  ".join(game.genres)
            content.add_widget(Label(text=f"[color=7788bb]Genres:[/color]  {genre_text}",
                                     markup=True, font_size=sp(11), size_hint_y=None,
                                     height=dp(24), halign='left',
                                     text_size=(Window.width - dp(30), None),
                                     color=(0.7, 0.75, 0.85, 1)))

        # Tags
        if game.tags:
            tag_text = ", ".join(game.tags)
            content.add_widget(Label(text=f"[color=7788bb]Tags:[/color]  {tag_text}",
                                     markup=True, font_size=sp(10), size_hint_y=None,
                                     height=dp(22), halign='left',
                                     text_size=(Window.width - dp(30), None),
                                     color=(0.55, 0.55, 0.6, 1)))

        # Description
        if game.description and game.description != 'No description available':
            content.add_widget(Label(text="[b]About This Game[/b]", markup=True,
                                     font_size=sp(14), size_hint_y=None, height=dp(30),
                                     color=(0.5, 0.4, 1, 1), halign='left',
                                     text_size=(Window.width - dp(30), None)))
            desc_label = Label(
                text=game.description[:2000], font_size=sp(11), size_hint_y=None,
                text_size=(Window.width - dp(36), None), halign='left', valign='top',
                color=(0.78, 0.78, 0.8, 1), line_height=1.4
            )
            desc_label.bind(texture_size=desc_label.setter('size'))
            content.add_widget(desc_label)

        # Screenshots
        if game.screenshots:
            content.add_widget(Label(text="[b]Screenshots[/b]", markup=True, font_size=sp(14),
                                     size_hint_y=None, height=dp(30), color=(0.5, 0.4, 1, 1),
                                     halign='left', text_size=(Window.width - dp(30), None)))
            ss_scroll = ScrollView(size_hint_y=None, height=dp(160), do_scroll_y=False)
            ss_row = BoxLayout(size_hint=(None, 1), spacing=dp(8))
            ss_row.bind(minimum_width=ss_row.setter('width'))
            for url in game.screenshots[:6]:
                if url:
                    ss_row.add_widget(AsyncImage(source=url, size_hint=(None, 1),
                                                 width=dp(260), allow_stretch=True, keep_ratio=True))
            ss_scroll.add_widget(ss_row)
            content.add_widget(ss_scroll)

        # Similar games
        content.add_widget(Label(text="[b]You Might Also Like[/b]", markup=True, font_size=sp(14),
                                 size_hint_y=None, height=dp(34), color=(0.5, 0.4, 1, 1),
                                 halign='left', text_size=(Window.width - dp(30), None)))
        similar_grid = GridLayout(cols=3, spacing=dp(8), size_hint_y=None)
        similar_grid.bind(minimum_height=similar_grid.setter('height'))
        similar_grid.add_widget(Label(text="Loading...", size_hint_y=None, height=dp(40),
                                      color=(0.4, 0.4, 0.5, 1)))
        content.add_widget(similar_grid)

        scroll.add_widget(content)
        root.add_widget(scroll)
        detail_screen.add_widget(root)

        def _fetch():
            similar = fetch_similar_games(game.game_id)
            if not similar and game.genres:
                slug = GENRE_SLUG_MAP.get(game.genres[0])
                if slug:
                    data = api_get("games", {'genres': slug, 'page_size': 6, 'ordering': '-rating'})
                    if data:
                        similar = [parse_game(g) for g in data.get('results', [])
                                   if g.get('id') != game.game_id][:6]
            Clock.schedule_once(lambda dt: self._render_similar(similar_grid, similar))

        Thread(target=_fetch, daemon=True).start()

    def _render_similar(self, grid, similar):
        grid.clear_widgets()
        if similar:
            for sg in similar:
                card = GameCard(game=sg, on_tap=self._show_detail)
                grid.add_widget(card)
        else:
            grid.add_widget(Label(text="No recommendations found", size_hint_y=None,
                                  height=dp(40), color=(0.4, 0.4, 0.5, 1)))

    def _go_back(self):
        self.sm.transition.direction = 'right'
        self.sm.current = "main"
        self.sm.transition.direction = 'left'


if __name__ == '__main__':
    GameRecommenderApp().run()
