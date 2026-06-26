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
from kivy.graphics import Color, Rectangle, RoundedRectangle, Line
from kivy.uix.anchorlayout import AnchorLayout
from kivy.uix.widget import Widget

logging.basicConfig(
    filename='game_app.log',
    level=logging.INFO,
    format='%(asctime)s:%(levelname)s:%(message)s'
)

load_dotenv()

Config.set('graphics', 'width', '900')
Config.set('graphics', 'height', '700')
Config.set('kivy', 'keyboard_mode', 'system')
Config.set('graphics', 'fullscreen', 'auto')

API_KEY = os.getenv('GAME_API_KEY', 'your_api_key_here')
BASE_URL = "https://api.rawg.io/api"

# --- Platform definitions (RAWG platform IDs) ---
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
    "All":      (0.3, 0.5, 0.9, 1),
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
    1: "Steam",
    2: "Xbox Store",
    3: "PlayStation Store",
    4: "App Store",
    5: "GOG",
    6: "Nintendo eShop",
    7: "Xbox 360 Store",
    8: "Google Play",
    9: "itch.io",
    11: "Epic Games",
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

GENRES = [
    "All", "Action", "Adventure", "RPG", "Strategy", "Shooter",
    "Puzzle", "Racing", "Sports", "Simulation", "Platformer",
    "Fighting", "Indie", "Horror"
]

GENRE_SLUG_MAP = {
    "Action": "action", "Adventure": "adventure", "RPG": "role-playing-games-rpg",
    "Strategy": "strategy", "Shooter": "shooter", "Puzzle": "puzzle",
    "Racing": "racing", "Sports": "sports", "Simulation": "simulation",
    "Platformer": "platformer", "Fighting": "fighting", "Indie": "indie",
    "Horror": "horror"
}

SORT_OPTIONS = {
    "Top Rated":    "-rating",
    "Most Popular": "-added",
    "Newest":       "-released",
    "Metacritic":   "-metacritic",
    "Name A-Z":     "name",
}


class GameDetails:
    def __init__(self, game_id: int, name: str, description: str,
                 release_date: str, background_image: str, rating: float,
                 metacritic: Optional[int], genres: List[str],
                 platforms: List[str], stores: List[str],
                 screenshots: List[str], esrb: str,
                 playtime: int, developers: List[str],
                 publishers: List[str], tags: List[str]):
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
        store_id = store_obj.get('id')
        stores.append(STORE_NAMES.get(store_id, store_obj.get('name', 'Unknown')))
    screenshots = [ss.get('image', '') for ss in data.get('short_screenshots', data.get('screenshots', []))]
    esrb = data.get('esrb_rating', {})
    esrb_name = esrb.get('name', 'Not Rated') if esrb else 'Not Rated'
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
        genres=genres,
        platforms=platforms,
        stores=stores,
        screenshots=screenshots,
        esrb=esrb_name,
        playtime=data.get('playtime', 0),
        developers=developers,
        publishers=publishers,
        tags=tags,
        background_image=data.get('background_image', '')
    )


def api_get(endpoint: str, params: dict) -> Optional[dict]:
    params['key'] = API_KEY
    try:
        resp = requests.get(f"{BASE_URL}/{endpoint}", params=params, timeout=15)
        resp.raise_for_status()
        return resp.json()
    except requests.RequestException as e:
        logging.error(f"API error [{endpoint}]: {e}")
    return None


def fetch_games(page=1, genre=None, platform_id=None, ordering='-rating', page_size=12, search=None):
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


def fetch_game_full(game_id: int) -> Optional[GameDetails]:
    data = api_get(f"games/{game_id}", {})
    if data:
        ss_data = api_get(f"games/{game_id}/screenshots", {'page_size': 6})
        if ss_data:
            data['screenshots'] = ss_data.get('results', [])
        return parse_game(data)
    return None


def fetch_similar_games(game_id: int):
    data = api_get(f"games/{game_id}/suggested", {'page_size': 6})
    if data and data.get('results'):
        return [parse_game(g) for g in data['results']]
    data = api_get(f"games/{game_id}/game-series", {'page_size': 6})
    if data and data.get('results'):
        return [parse_game(g) for g in data['results']]
    return None


class NoKeyboardTextInput(TextInput):
    def on_touch_down(self, touch):
        if self.collide_point(*touch.pos):
            Window.release_all_keyboards()
        return super().on_touch_down(touch)


class PlatformBadge(BoxLayout):
    def __init__(self, text, color, **kwargs):
        super().__init__(**kwargs)
        self.size_hint = (None, None)
        self.size = (38, 18)
        self.padding = [3, 1, 3, 1]
        with self.canvas.before:
            Color(*color)
            self._bg = RoundedRectangle(pos=self.pos, size=self.size, radius=[4])
        self.bind(pos=self._upd, size=self._upd)
        self.add_widget(Label(text=text, font_size='9sp', bold=True, size_hint=(1, 1)))

    def _upd(self, *a):
        self._bg.pos = self.pos
        self._bg.size = self.size


class GameCard(BoxLayout):
    def __init__(self, game: GameDetails, on_tap=None, **kwargs):
        super().__init__(**kwargs)
        self.orientation = 'vertical'
        self.size_hint_y = None
        self.height = 400
        self.padding = 6
        self.spacing = 4
        self.game = game

        with self.canvas.before:
            Color(0.12, 0.12, 0.18, 1)
            self._bg = RoundedRectangle(pos=self.pos, size=self.size, radius=[12])
        self.bind(pos=self._update_bg, size=self._update_bg)

        if game.background_image:
            img = AsyncImage(source=game.background_image, size_hint_y=None, height=200,
                             allow_stretch=True, keep_ratio=True)
            self.add_widget(img)
        else:
            ph = Label(text="No Image", size_hint_y=None, height=200, color=(0.4, 0.4, 0.4, 1))
            self.add_widget(ph)

        name_label = Label(
            text=game.name, font_size='13sp', size_hint_y=None, height=38,
            text_size=(None, 38), halign='center', valign='middle',
            bold=True, shorten=True, shorten_from='right'
        )
        self.add_widget(name_label)

        badge_row = BoxLayout(size_hint_y=None, height=22, spacing=2, padding=[2, 0, 2, 0])
        badge_count = 0
        for plat in game.platforms:
            if plat in PLATFORM_BADGES and badge_count < 5:
                abbr, col = PLATFORM_BADGES[plat]
                badge_row.add_widget(PlatformBadge(abbr, col))
                badge_count += 1
        if badge_count == 0:
            badge_row.add_widget(Label(text="", size_hint_y=None, height=22))
        self.add_widget(badge_row)

        rating_row = BoxLayout(size_hint_y=None, height=24, spacing=4)
        stars = int(game.rating)
        half = game.rating - stars >= 0.5
        star_str = "[color=ffcc00]" + ("★" * stars) + ("½" if half else "") + "[/color]"
        star_str += "[color=444444]" + ("★" * (5 - stars - (1 if half else 0))) + "[/color]"
        rating_row.add_widget(Label(text=f"{star_str} {game.rating:.1f}", markup=True,
                                    font_size='11sp', size_hint_x=0.55))
        if game.metacritic:
            mc_c = "00ff00" if game.metacritic >= 75 else "ffff00" if game.metacritic >= 50 else "ff4444"
            rating_row.add_widget(Label(text=f"[color={mc_c}]{game.metacritic}[/color]", markup=True,
                                        font_size='12sp', bold=True, size_hint_x=0.2))
        else:
            rating_row.add_widget(Label(text="--", font_size='11sp', size_hint_x=0.2, color=(0.4, 0.4, 0.4, 1)))

        if game.genres:
            rating_row.add_widget(Label(text=game.genres[0], font_size='10sp', size_hint_x=0.25,
                                        color=(0.55, 0.7, 0.9, 1)))
        self.add_widget(rating_row)

        bottom_row = BoxLayout(size_hint_y=None, height=22, spacing=4)
        bottom_row.add_widget(Label(text=game.release_date or "TBA", font_size='10sp',
                                    color=(0.55, 0.55, 0.55, 1), size_hint_x=0.5))
        if game.playtime:
            bottom_row.add_widget(Label(text=f"~{game.playtime}h", font_size='10sp',
                                        color=(0.55, 0.55, 0.55, 1), size_hint_x=0.25))
        bottom_row.add_widget(Label(text=game.esrb if game.esrb != 'Not Rated' else '',
                                    font_size='10sp', color=(0.55, 0.55, 0.55, 1), size_hint_x=0.25))
        self.add_widget(bottom_row)

        if on_tap:
            self.bind(on_touch_down=lambda inst, touch: on_tap(game) if inst.collide_point(*touch.pos) else None)

    def _update_bg(self, *a):
        self._bg.pos = self.pos
        self._bg.size = self.size


class StoreBadge(Button):
    def __init__(self, store_name, **kwargs):
        col = STORE_COLORS.get(store_name, (0.2, 0.2, 0.3, 1))
        super().__init__(text=store_name, size_hint=(None, None), width=130, height=36,
                         background_color=col, font_size='12sp', bold=True, **kwargs)


class GameRecommenderApp(App):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.current_page = 1
        self.current_genre = "All"
        self.current_platform = "All"
        self.current_sort = "Top Rated"
        self.search_query = ""
        self.total_count = 0
        self.search_event = None

    def build(self):
        self.title = "Game Recommender"
        Window.clearcolor = (0.06, 0.06, 0.1, 1)
        self.sm = ScreenManager(transition=SlideTransition())
        self.sm.add_widget(self._build_main_screen())
        self.sm.add_widget(self._build_detail_screen())
        return self.sm

    # ─── Main Screen ───
    def _build_main_screen(self):
        screen = Screen(name="main")
        root = BoxLayout(orientation='vertical', spacing=6, padding=[12, 8, 12, 8])

        # Header
        header = BoxLayout(size_hint_y=None, height=55, spacing=10)
        header.add_widget(Label(text="[b]GAME[/b] [color=4488ff]RECOMMENDER[/color]", markup=True,
                                font_size='28sp', size_hint_x=0.6, halign='left'))

        self.sort_buttons = {}
        sort_row = BoxLayout(size_hint_x=0.4, spacing=3)
        for sname in ["Top Rated", "Newest", "Most Popular"]:
            sb = Button(text=sname, font_size='10sp', size_hint_x=None, width=85,
                        background_color=(0.3, 0.5, 0.9, 1) if sname == "Top Rated" else (0.15, 0.15, 0.22, 1))
            sb.bind(on_release=partial(self._on_sort_select, sname))
            sort_row.add_widget(sb)
            self.sort_buttons[sname] = sb
        header.add_widget(sort_row)
        root.add_widget(header)

        # Search row
        search_row = BoxLayout(size_hint_y=None, height=42, spacing=8)
        self.search_input = NoKeyboardTextInput(
            hint_text='Search for any game...', multiline=False,
            background_color=(0.12, 0.12, 0.18, 1), foreground_color=(1, 1, 1, 1),
            hint_text_color=(0.4, 0.4, 0.5, 1), cursor_color=(0.4, 0.7, 1, 1),
            size_hint_x=0.72, padding=[12, 10, 12, 10]
        )
        self.search_input.bind(text=self._on_search_text)
        self.search_input.bind(on_text_validate=lambda x: self._do_search())
        search_row.add_widget(self.search_input)
        search_btn = Button(text="Search", size_hint_x=0.14, background_color=(0.2, 0.45, 0.9, 1),
                            font_size='13sp', bold=True)
        search_btn.bind(on_release=lambda x: self._do_search())
        search_row.add_widget(search_btn)
        clear_btn = Button(text="Clear", size_hint_x=0.14, background_color=(0.45, 0.2, 0.2, 1),
                           font_size='13sp')
        clear_btn.bind(on_release=lambda x: self._clear_search())
        search_row.add_widget(clear_btn)
        root.add_widget(search_row)

        # Platform filter bar
        plat_scroll = ScrollView(size_hint_y=None, height=40, do_scroll_y=False)
        self.plat_bar = BoxLayout(size_hint=(None, 1), spacing=4)
        self.plat_bar.bind(minimum_width=self.plat_bar.setter('width'))
        self.plat_buttons = {}
        for pname in PLATFORMS:
            col = PLATFORM_COLORS.get(pname, (0.2, 0.2, 0.3, 1))
            active = pname == "All"
            btn = Button(text=pname, size_hint=(None, 1), width=90, font_size='12sp', bold=active,
                         background_color=col if active else (0.15, 0.15, 0.22, 1))
            btn.bind(on_release=partial(self._on_platform_select, pname))
            self.plat_bar.add_widget(btn)
            self.plat_buttons[pname] = btn
        plat_scroll.add_widget(self.plat_bar)
        root.add_widget(plat_scroll)

        # Genre filter bar
        genre_scroll = ScrollView(size_hint_y=None, height=36, do_scroll_y=False)
        self.genre_bar = BoxLayout(size_hint=(None, 1), spacing=4)
        self.genre_bar.bind(minimum_width=self.genre_bar.setter('width'))
        self.genre_buttons = {}
        for genre in GENRES:
            btn = Button(text=genre, size_hint=(None, 1), width=90, font_size='11sp',
                         background_color=(0.25, 0.4, 0.7, 1) if genre == "All" else (0.13, 0.13, 0.2, 1))
            btn.bind(on_release=partial(self._on_genre_select, genre))
            self.genre_bar.add_widget(btn)
            self.genre_buttons[genre] = btn
        genre_scroll.add_widget(self.genre_bar)
        root.add_widget(genre_scroll)

        # Status / info bar
        self.status_label = Label(text="", size_hint_y=None, height=22,
                                  color=(0.8, 0.8, 0.8, 1), font_size='11sp', halign='left')
        root.add_widget(self.status_label)

        # Game grid
        scroll = ScrollView(do_scroll_x=False)
        self.grid = GridLayout(cols=3, spacing=10, padding=5, size_hint_y=None)
        self.grid.bind(minimum_height=self.grid.setter('height'))
        scroll.add_widget(self.grid)
        root.add_widget(scroll)

        # Pagination
        nav = BoxLayout(size_hint_y=None, height=42, spacing=10)
        self.prev_btn = Button(text="◄ Previous", background_color=(0.18, 0.18, 0.28, 1),
                               font_size='13sp', disabled=True)
        self.prev_btn.bind(on_release=lambda x: self._change_page(-1))
        nav.add_widget(self.prev_btn)
        self.page_label = Label(text="Page 1", font_size='13sp', color=(0.6, 0.6, 0.7, 1))
        nav.add_widget(self.page_label)
        self.next_btn = Button(text="Next ►", background_color=(0.18, 0.18, 0.28, 1), font_size='13sp')
        self.next_btn.bind(on_release=lambda x: self._change_page(1))
        nav.add_widget(self.next_btn)
        root.add_widget(nav)

        screen.add_widget(root)

        # Initial load
        self.loading_popup = Popup(
            title='Loading Games...', content=Label(text="Please wait...", font_size='14sp'),
            size_hint=(None, None), size=(260, 140), auto_dismiss=False
        )
        self.loading_popup.open()
        Clock.schedule_once(lambda dt: self._load_games(), 0.3)
        return screen

    def _build_detail_screen(self):
        screen = Screen(name="detail")
        self.detail_layout = BoxLayout(orientation='vertical')
        screen.add_widget(self.detail_layout)
        return screen

    # ─── Filters & Search ───
    def _on_search_text(self, instance, value):
        if self.search_event:
            self.search_event.cancel()
        self.search_event = Clock.schedule_once(lambda dt: self._do_search(), 0.8)

    def _do_search(self):
        query = self.search_input.text.strip()
        if query:
            self.search_query = query
            self.current_page = 1
            self._load_games()
        elif self.search_query:
            self._clear_search()

    def _clear_search(self):
        self.search_input.text = ""
        self.search_query = ""
        self.current_page = 1
        self._load_games()

    def _on_platform_select(self, pname, *args):
        self.current_platform = pname
        self.current_page = 1
        for name, btn in self.plat_buttons.items():
            active = name == pname
            col = PLATFORM_COLORS.get(name, (0.2, 0.2, 0.3, 1))
            btn.background_color = col if active else (0.15, 0.15, 0.22, 1)
            btn.bold = active
        self._load_games()

    def _on_genre_select(self, genre, *args):
        self.current_genre = genre
        self.current_page = 1
        for g, btn in self.genre_buttons.items():
            btn.background_color = (0.25, 0.4, 0.7, 1) if g == genre else (0.13, 0.13, 0.2, 1)
        self._load_games()

    def _on_sort_select(self, sname, *args):
        self.current_sort = sname
        self.current_page = 1
        for s, btn in self.sort_buttons.items():
            btn.background_color = (0.3, 0.5, 0.9, 1) if s == sname else (0.15, 0.15, 0.22, 1)
        self._load_games()

    def _change_page(self, delta):
        self.current_page = max(1, self.current_page + delta)
        self._load_games()

    # ─── Load & Display ───
    def _load_games(self):
        self.status_label.text = "Loading..."
        self.grid.clear_widgets()

        if not API_KEY or API_KEY == 'your_api_key_here':
            self.status_label.text = "Set GAME_API_KEY in .env  —  get one free at rawg.io/apidocs"
            self._dismiss_loading()
            return

        def _fetch():
            platform_id = PLATFORMS.get(self.current_platform)
            genre = self.current_genre if self.current_genre != "All" else None
            ordering = SORT_OPTIONS.get(self.current_sort, '-rating')
            search = self.search_query if self.search_query else None
            games, count = fetch_games(
                page=self.current_page, genre=genre, platform_id=platform_id,
                ordering=ordering, search=search
            )
            Clock.schedule_once(lambda dt: self._display_games(games, count))

        Thread(target=_fetch, daemon=True).start()

    def _display_games(self, games, count):
        self.grid.clear_widgets()
        self.total_count = count

        filters = []
        if self.search_query:
            filters.append(f'"{self.search_query}"')
        if self.current_platform != "All":
            filters.append(self.current_platform)
        if self.current_genre != "All":
            filters.append(self.current_genre)
        header = " · ".join(filters) if filters else "Popular Games"

        if games:
            for game in games:
                card = GameCard(game=game, on_tap=self._show_detail)
                self.grid.add_widget(card)
            total_pages = max(1, (count + 11) // 12)
            self.status_label.text = f"{header}  —  {count:,} games found  ·  {self.current_sort}"
            self.page_label.text = f"Page {self.current_page} / {total_pages}"
            self.prev_btn.disabled = self.current_page <= 1
            self.next_btn.disabled = self.current_page >= total_pages
        else:
            self.status_label.text = "No games found. Try a different filter or check your API key."
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
    def _show_detail(self, game: GameDetails):
        self.detail_layout.clear_widgets()

        with self.detail_layout.canvas.before:
            Color(0.06, 0.06, 0.1, 1)
            Rectangle(pos=self.detail_layout.pos, size=Window.size)

        loading = Label(text="Loading game details...", font_size='16sp', color=(0.5, 0.5, 0.6, 1))
        self.detail_layout.add_widget(loading)
        self.sm.current = "detail"

        def _fetch():
            full = fetch_game_full(game.game_id)
            if not full:
                full = game
            Clock.schedule_once(lambda dt: self._render_detail(full))

        Thread(target=_fetch, daemon=True).start()

    def _render_detail(self, game: GameDetails):
        self.detail_layout.clear_widgets()

        scroll = ScrollView(do_scroll_x=False)
        content = BoxLayout(orientation='vertical', spacing=12, padding=[16, 10, 16, 16], size_hint_y=None)
        content.bind(minimum_height=content.setter('height'))

        # Top bar
        top_bar = BoxLayout(size_hint_y=None, height=48, spacing=10)
        back_btn = Button(text="◄ Back to Browse", size_hint_x=0.25, background_color=(0.2, 0.2, 0.35, 1),
                          font_size='12sp')
        back_btn.bind(on_release=lambda x: self._go_back())
        top_bar.add_widget(back_btn)
        top_bar.add_widget(Label(text=f"[b]{game.name}[/b]", markup=True,
                                 font_size='22sp', size_hint_x=0.75, color=(0.4, 0.75, 1, 1),
                                 halign='center'))
        content.add_widget(top_bar)

        # Main image
        if game.background_image:
            img = AsyncImage(source=game.background_image, size_hint_y=None, height=380,
                             allow_stretch=True, keep_ratio=True)
            content.add_widget(img)

        # Rating / Metacritic / ESRB row
        info_box = BoxLayout(size_hint_y=None, height=45, spacing=15, padding=[10, 0, 10, 0])
        with info_box.canvas.before:
            Color(0.1, 0.1, 0.16, 1)
            info_box._bg = RoundedRectangle(pos=info_box.pos, size=info_box.size, radius=[8])
        info_box.bind(pos=lambda w, p: setattr(w._bg, 'pos', p),
                      size=lambda w, s: setattr(w._bg, 'size', s))

        stars = int(game.rating)
        half = game.rating - stars >= 0.5
        star_str = "[color=ffcc00]" + ("★" * stars) + ("½" if half else "") + "[/color]"
        star_str += "[color=333333]" + ("★" * (5 - stars - (1 if half else 0))) + "[/color]"
        info_box.add_widget(Label(text=f"{star_str}  {game.rating:.1f}/5", markup=True, font_size='16sp'))

        if game.metacritic:
            mc_c = "00ff00" if game.metacritic >= 75 else "ffff00" if game.metacritic >= 50 else "ff4444"
            info_box.add_widget(Label(text=f"Metacritic: [color={mc_c}][b]{game.metacritic}[/b][/color]",
                                      markup=True, font_size='15sp'))
        info_box.add_widget(Label(text=f"ESRB: {game.esrb}", font_size='13sp', color=(0.6, 0.6, 0.7, 1)))
        if game.playtime:
            info_box.add_widget(Label(text=f"~{game.playtime} hours", font_size='13sp', color=(0.6, 0.6, 0.7, 1)))
        content.add_widget(info_box)

        # Release / Developer / Publisher
        meta_box = BoxLayout(orientation='vertical', size_hint_y=None, spacing=4, padding=[5, 8, 5, 8])
        meta_box.bind(minimum_height=meta_box.setter('height'))
        meta_items = [("Released", game.release_date or "TBA")]
        if game.developers:
            meta_items.append(("Developer", ", ".join(game.developers)))
        if game.publishers:
            meta_items.append(("Publisher", ", ".join(game.publishers)))
        for label, value in meta_items:
            row = BoxLayout(size_hint_y=None, height=24)
            row.add_widget(Label(text=f"[color=6699cc]{label}:[/color]", markup=True,
                                 font_size='12sp', size_hint_x=0.25, halign='right',
                                 text_size=(None, None)))
            row.add_widget(Label(text=value, font_size='12sp', size_hint_x=0.75,
                                 color=(0.85, 0.85, 0.85, 1), halign='left'))
            meta_box.add_widget(row)
        content.add_widget(meta_box)

        # Platform badges
        if game.platforms:
            plat_section = BoxLayout(orientation='vertical', size_hint_y=None, spacing=4)
            plat_section.bind(minimum_height=plat_section.setter('height'))
            plat_section.add_widget(Label(text="[b]Available On[/b]", markup=True, font_size='15sp',
                                          size_hint_y=None, height=30, color=(0.4, 0.75, 1, 1),
                                          halign='left', text_size=(Window.width - 40, None)))
            badge_flow = BoxLayout(size_hint_y=None, height=28, spacing=6)
            for plat in game.platforms:
                if plat in PLATFORM_BADGES:
                    abbr, col = PLATFORM_BADGES[plat]
                    badge_flow.add_widget(PlatformBadge(abbr, col))
            plat_section.add_widget(badge_flow)
            content.add_widget(plat_section)

        # Store badges
        if game.stores:
            store_section = BoxLayout(orientation='vertical', size_hint_y=None, spacing=6)
            store_section.bind(minimum_height=store_section.setter('height'))
            store_section.add_widget(Label(text="[b]Available At[/b]", markup=True, font_size='15sp',
                                           size_hint_y=None, height=30, color=(0.4, 0.75, 1, 1),
                                           halign='left', text_size=(Window.width - 40, None)))
            store_row = BoxLayout(size_hint_y=None, height=40, spacing=8)
            for store in game.stores:
                store_row.add_widget(StoreBadge(store))
            store_section.add_widget(store_row)
            content.add_widget(store_section)

        # Genres + tags
        if game.genres:
            genre_row = BoxLayout(size_hint_y=None, height=30, spacing=6)
            genre_row.add_widget(Label(text="[color=6699cc]Genres:[/color]", markup=True,
                                       font_size='12sp', size_hint_x=0.15))
            genre_row.add_widget(Label(text="  ·  ".join(game.genres), font_size='12sp',
                                       size_hint_x=0.85, color=(0.7, 0.8, 0.95, 1), halign='left',
                                       text_size=(Window.width - 120, None)))
            content.add_widget(genre_row)

        if game.tags:
            tags_text = ", ".join(game.tags)
            tags_label = Label(text=f"[color=6699cc]Tags:[/color]  {tags_text}", markup=True,
                               font_size='11sp', size_hint_y=None, height=28, halign='left',
                               text_size=(Window.width - 40, None), color=(0.6, 0.6, 0.65, 1))
            content.add_widget(tags_label)

        # Description
        if game.description and game.description != 'No description available':
            content.add_widget(Label(text="[b]About This Game[/b]", markup=True, font_size='16sp',
                                     size_hint_y=None, height=35, color=(0.4, 0.75, 1, 1),
                                     halign='left', text_size=(Window.width - 40, None)))
            desc_label = Label(
                text=game.description[:2000], font_size='12sp', size_hint_y=None,
                text_size=(Window.width - 50, None), halign='left', valign='top',
                color=(0.8, 0.8, 0.82, 1), line_height=1.4
            )
            desc_label.bind(texture_size=desc_label.setter('size'))
            content.add_widget(desc_label)

        # Screenshots
        if game.screenshots:
            content.add_widget(Label(text="[b]Screenshots[/b]", markup=True, font_size='16sp',
                                     size_hint_y=None, height=35, color=(0.4, 0.75, 1, 1),
                                     halign='left', text_size=(Window.width - 40, None)))
            ss_scroll = ScrollView(size_hint_y=None, height=200, do_scroll_y=False)
            ss_row = BoxLayout(size_hint=(None, 1), spacing=10)
            ss_row.bind(minimum_width=ss_row.setter('width'))
            for ss_url in game.screenshots[:6]:
                if ss_url:
                    ss_img = AsyncImage(source=ss_url, size_hint=(None, 1), width=320,
                                        allow_stretch=True, keep_ratio=True)
                    ss_row.add_widget(ss_img)
            ss_scroll.add_widget(ss_row)
            content.add_widget(ss_scroll)

        # Similar games
        content.add_widget(Label(text="[b]You Might Also Like[/b]", markup=True, font_size='16sp',
                                 size_hint_y=None, height=40, color=(0.4, 0.75, 1, 1),
                                 halign='left', text_size=(Window.width - 40, None)))
        similar_grid = GridLayout(cols=3, spacing=10, size_hint_y=None)
        similar_grid.bind(minimum_height=similar_grid.setter('height'))
        similar_grid.add_widget(Label(text="Loading recommendations...", size_hint_y=None,
                                      height=50, color=(0.4, 0.4, 0.5, 1)))
        content.add_widget(similar_grid)

        scroll.add_widget(content)
        self.detail_layout.add_widget(scroll)

        def _fetch_similar():
            similar = fetch_similar_games(game.game_id)
            if not similar and game.genres:
                slug = GENRE_SLUG_MAP.get(game.genres[0])
                if slug:
                    data = api_get("games", {'genres': slug, 'page_size': 6, 'ordering': '-rating'})
                    if data:
                        similar = [parse_game(g) for g in data.get('results', [])
                                   if g.get('id') != game.game_id][:6]
            Clock.schedule_once(lambda dt: self._render_similar(similar_grid, similar))

        Thread(target=_fetch_similar, daemon=True).start()

    def _render_similar(self, grid, similar):
        grid.clear_widgets()
        if similar:
            for sg in similar:
                card = GameCard(game=sg, on_tap=self._show_detail)
                grid.add_widget(card)
        else:
            grid.add_widget(Label(text="No recommendations available", size_hint_y=None,
                                  height=50, color=(0.4, 0.4, 0.5, 1)))

    def _go_back(self):
        self.sm.transition.direction = 'right'
        self.sm.current = "main"
        self.sm.transition.direction = 'left'


if __name__ == '__main__':
    GameRecommenderApp().run()
