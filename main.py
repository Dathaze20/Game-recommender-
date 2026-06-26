import os
import json
import logging
from collections import Counter
from functools import partial
from threading import Thread

import requests
from kivy.app import App
from kivy.uix.image import AsyncImage
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.label import Label
from kivy.uix.gridlayout import GridLayout
from kivy.uix.scrollview import ScrollView
from kivy.uix.textinput import TextInput
from kivy.clock import Clock
from kivy.config import Config
from kivy.core.window import Window
from kivy.uix.screenmanager import ScreenManager, Screen, SlideTransition
from kivy.uix.button import Button
from kivy.graphics import Color, RoundedRectangle, Rectangle
from kivy.metrics import dp, sp

logging.basicConfig(
    filename='game_app.log', level=logging.INFO,
    format='%(asctime)s:%(levelname)s:%(message)s'
)

Config.set('graphics', 'width', '420')
Config.set('graphics', 'height', '800')
Config.set('kivy', 'keyboard_mode', 'system')

BASE_URL = "https://api.rawg.io/api"
DEFAULT_API_KEY = "918f5c2b0203449c9024b928a332938c"
CONFIG_FILE = "game_recommender_config.json"

CATEGORIES = [
    {"title": "Trending Now",           "params": {"ordering": "-added", "page_size": 20}},
    {"title": "Top Rated",              "params": {"ordering": "-rating", "page_size": 20, "metacritic": "80,100"}},
    {"title": "All-Time Greatest",      "params": {"metacritic": "95,100", "ordering": "-metacritic", "page_size": 20}},
    {"title": "Perfect Scores",         "params": {"metacritic": "98,100", "ordering": "-metacritic", "page_size": 20}},
    {"title": "Highest Rated RPGs",     "params": {"genres": "role-playing-games-rpg", "metacritic": "85,100", "ordering": "-metacritic", "page_size": 20}},
    {"title": "Japanese Masterpieces",  "params": {"developers": "nintendo,square-enix,capcom,konami,fromsoftware,atlus,sega,bandai-namco-entertainment,platinum-games", "ordering": "-metacritic", "page_size": 20}},
    {"title": "New Releases",           "params": {"ordering": "-released", "page_size": 20}},
    {"title": "PlayStation 5",          "params": {"platforms": 187, "ordering": "-added", "page_size": 20}},
    {"title": "Xbox Series X|S",        "params": {"platforms": 186, "ordering": "-added", "page_size": 20}},
    {"title": "Nintendo Switch",        "params": {"platforms": 7, "ordering": "-added", "page_size": 20}},
    {"title": "PC Games",               "params": {"platforms": 4, "ordering": "-rating", "page_size": 20}},
    {"title": "Best Action Games",      "params": {"genres": "action", "ordering": "-rating", "page_size": 20}},
    {"title": "RPG Adventures",         "params": {"genres": "role-playing-games-rpg", "ordering": "-rating", "page_size": 20}},
    {"title": "Shooters",               "params": {"genres": "shooter", "ordering": "-rating", "page_size": 20}},
    {"title": "Strategy & Tactics",     "params": {"genres": "strategy", "ordering": "-rating", "page_size": 20}},
    {"title": "Racing Games",           "params": {"genres": "racing", "ordering": "-rating", "page_size": 20}},
    {"title": "Fighting Games",         "params": {"genres": "fighting", "ordering": "-rating", "page_size": 20}},
    {"title": "Platformers",            "params": {"genres": "platformer", "ordering": "-rating", "page_size": 20}},
    {"title": "Sports Games",           "params": {"genres": "sports", "ordering": "-added", "page_size": 20}},
    {"title": "Indie Gems",             "params": {"genres": "indie", "ordering": "-rating", "page_size": 20}},
    {"title": "PlayStation 4",          "params": {"platforms": 18, "ordering": "-rating", "page_size": 20}},
    {"title": "Xbox One",               "params": {"platforms": 1, "ordering": "-rating", "page_size": 20}},
    {"title": "Retro: Sega Genesis",    "params": {"platforms": 167, "ordering": "-rating", "page_size": 20}},
    {"title": "Retro: Neo Geo",         "params": {"platforms": 12, "ordering": "-rating", "page_size": 20}},
    {"title": "Retro: SNES",            "params": {"platforms": 79, "ordering": "-rating", "page_size": 20}},
    {"title": "Retro: NES",             "params": {"platforms": 49, "ordering": "-rating", "page_size": 20}},
    {"title": "Retro: Nintendo 64",     "params": {"platforms": 83, "ordering": "-rating", "page_size": 20}},
    {"title": "Retro: Dreamcast",       "params": {"platforms": 106, "ordering": "-rating", "page_size": 20}},
    {"title": "Retro: PlayStation 1",   "params": {"platforms": 27, "ordering": "-rating", "page_size": 20}},
    {"title": "Retro: PlayStation 2",   "params": {"platforms": 15, "ordering": "-rating", "page_size": 20}},
    {"title": "Retro: GameCube",        "params": {"platforms": 105, "ordering": "-rating", "page_size": 20}},
    {"title": "Retro: Game Boy Advance","params": {"platforms": 24, "ordering": "-rating", "page_size": 20}},
    {"title": "Retro: Atari 2600",      "params": {"platforms": 31, "ordering": "-rating", "page_size": 20}},
    {"title": "Retro: Sega Saturn",     "params": {"platforms": 107, "ordering": "-rating", "page_size": 20}},
    {"title": "Mobile: iOS",            "params": {"platforms": 3, "ordering": "-rating", "page_size": 20}},
    {"title": "Mobile: Android",        "params": {"platforms": 21, "ordering": "-rating", "page_size": 20}},
]

PLATFORM_BADGES = {
    "PlayStation 5": ("PS5", 0.0, 0.32, 0.73),
    "PlayStation 4": ("PS4", 0.0, 0.27, 0.63),
    "PlayStation 3": ("PS3", 0.0, 0.22, 0.53),
    "PlayStation 2": ("PS2", 0.15, 0.15, 0.55),
    "PlayStation":   ("PS1", 0.45, 0.45, 0.5),
    "PS Vita":       ("Vita", 0.0, 0.22, 0.53),
    "PSP":           ("PSP", 0.25, 0.25, 0.45),
    "Xbox Series S/X": ("XSX", 0.07, 0.49, 0.04),
    "Xbox One":      ("XB1", 0.04, 0.38, 0.03),
    "Xbox 360":      ("360", 0.06, 0.42, 0.03),
    "Xbox":          ("Xbox", 0.04, 0.38, 0.03),
    "Nintendo Switch": ("NSW", 0.89, 0.05, 0.05),
    "Wii U":         ("WiiU", 0.0, 0.47, 0.78),
    "Wii":           ("Wii", 0.5, 0.5, 0.55),
    "GameCube":      ("GCN", 0.38, 0.2, 0.55),
    "Nintendo 64":   ("N64", 0.2, 0.5, 0.2),
    "Nintendo DS":   ("NDS", 0.6, 0.6, 0.6),
    "Nintendo 3DS":  ("3DS", 0.8, 0.1, 0.1),
    "Game Boy Advance": ("GBA", 0.4, 0.2, 0.6),
    "Game Boy Color": ("GBC", 0.3, 0.3, 0.6),
    "Game Boy":      ("GB", 0.3, 0.45, 0.2),
    "SNES":          ("SNES", 0.3, 0.3, 0.7),
    "Super Nintendo": ("SNES", 0.3, 0.3, 0.7),
    "NES":           ("NES", 0.7, 0.2, 0.2),
    "PC":            ("PC", 0.4, 0.4, 0.5),
    "macOS":         ("Mac", 0.35, 0.35, 0.35),
    "Linux":         ("LNX", 0.85, 0.55, 0.1),
    "iOS":           ("iOS", 0.35, 0.35, 0.35),
    "Android":       ("AND", 0.24, 0.6, 0.18),
    "Genesis":       ("GEN", 0.1, 0.1, 0.6),
    "Sega Genesis":  ("GEN", 0.1, 0.1, 0.6),
    "SEGA Genesis":  ("GEN", 0.1, 0.1, 0.6),
    "Sega Master System": ("SMS", 0.1, 0.1, 0.5),
    "Sega Saturn":   ("SAT", 0.35, 0.35, 0.55),
    "Sega CD":       ("SCD", 0.15, 0.15, 0.5),
    "Dreamcast":     ("DC", 0.3, 0.45, 0.7),
    "Neo Geo":       ("NGeo", 0.6, 0.15, 0.15),
    "Atari 2600":    ("2600", 0.55, 0.35, 0.1),
    "Atari 7800":    ("7800", 0.5, 0.3, 0.1),
    "3DO":           ("3DO", 0.4, 0.4, 0.2),
}

STORE_NAMES = {
    1: "Steam", 2: "Xbox Store", 3: "PlayStation Store", 4: "App Store",
    5: "GOG", 6: "Nintendo eShop", 7: "Xbox 360 Store", 8: "Google Play",
    9: "itch.io", 11: "Epic Games",
}

STORE_COLORS = {
    "Steam": (0.12, 0.15, 0.25), "Xbox Store": (0.07, 0.49, 0.04),
    "PlayStation Store": (0.0, 0.32, 0.73), "Nintendo eShop": (0.89, 0.05, 0.05),
    "Epic Games": (0.15, 0.15, 0.15), "GOG": (0.5, 0.1, 0.6),
    "App Store": (0.0, 0.48, 1.0), "Google Play": (0.24, 0.6, 0.18),
    "itch.io": (0.85, 0.25, 0.35),
}

GENRE_SLUG_MAP = {
    "Action": "action", "Adventure": "adventure", "RPG": "role-playing-games-rpg",
    "Strategy": "strategy", "Shooter": "shooter", "Puzzle": "puzzle",
    "Racing": "racing", "Sports": "sports", "Simulation": "simulation",
    "Platformer": "platformer", "Fighting": "fighting", "Indie": "indie",
}


def load_config():
    try:
        if os.path.exists(CONFIG_FILE):
            with open(CONFIG_FILE, 'r') as f:
                return json.load(f)
    except Exception:
        pass
    return {}


def save_config(data):
    try:
        with open(CONFIG_FILE, 'w') as f:
            json.dump(data, f)
    except Exception as e:
        logging.error(f"Save config: {e}")


def get_api_key():
    cfg = load_config()
    return cfg.get('api_key') or os.getenv('GAME_API_KEY', DEFAULT_API_KEY)


def saved_to_game(data):
    return GameDetails(
        game_id=data.get('game_id', 0), name=data.get('name', 'Unknown'),
        background_image=data.get('background_image', ''),
        rating=data.get('rating', 0), release_date=data.get('release_date', ''),
        metacritic=data.get('metacritic'), genres=data.get('genres', []),
        platforms=[], stores=[], screenshots=[],
        description='', esrb='', playtime=0,
        developers=[], publishers=[], tags=[]
    )


def game_to_saved(game):
    return {
        'game_id': game.game_id, 'name': game.name,
        'background_image': game.background_image or '',
        'rating': game.rating or 0, 'release_date': game.release_date or '',
        'genres': game.genres or [], 'metacritic': game.metacritic
    }


def update_stat(key):
    cfg = load_config()
    stats = cfg.get('stats', {})
    stats[key] = stats.get(key, 0) + 1
    cfg['stats'] = stats
    save_config(cfg)


class GameDetails:
    __slots__ = ['game_id', 'name', 'description', 'release_date', 'background_image',
                 'rating', 'metacritic', 'genres', 'platforms', 'stores', 'screenshots',
                 'esrb', 'playtime', 'developers', 'publishers', 'tags']

    def __init__(self, **kw):
        for k in self.__slots__:
            setattr(self, k, kw.get(k))


def parse_game(d):
    genres = [g['name'] for g in d.get('genres', [])]
    platforms = [p['platform']['name'] for p in d.get('platforms', []) if 'platform' in p]
    stores = [STORE_NAMES.get(s.get('store', {}).get('id'), s.get('store', {}).get('name', ''))
              for s in d.get('stores', [])]
    ss = [x.get('image', '') for x in d.get('short_screenshots', d.get('screenshots', []))]
    esrb = d.get('esrb_rating') or {}
    return GameDetails(
        game_id=d.get('id', 0), name=d.get('name', 'Unknown'),
        description=d.get('description_raw', d.get('description', '')),
        release_date=d.get('released', 'Unknown'),
        rating=d.get('rating', 0.0), metacritic=d.get('metacritic'),
        genres=genres, platforms=platforms, stores=stores, screenshots=ss,
        esrb=esrb.get('name', '') if esrb else '',
        playtime=d.get('playtime', 0),
        developers=[x['name'] for x in d.get('developers', [])],
        publishers=[x['name'] for x in d.get('publishers', [])],
        tags=[t['name'] for t in d.get('tags', [])[:10]],
        background_image=d.get('background_image', '')
    )


def api_get(endpoint, params, api_key):
    params['key'] = api_key
    try:
        r = requests.get(f"{BASE_URL}/{endpoint}", params=params, timeout=15)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        logging.error(f"API [{endpoint}]: {e}")
    return None


def rating_text(r):
    filled = min(5, int(r))
    empty = 5 - filled
    return f"{'*' * filled}{'.' * empty} {r:.1f}"


def mc_color(score):
    if score >= 75:
        return (0.2, 0.9, 0.2, 1)
    if score >= 50:
        return (0.9, 0.9, 0.2, 1)
    return (0.9, 0.3, 0.3, 1)


class GameCard(BoxLayout):
    def __init__(self, game, on_tap=None, card_width=None, **kw):
        super().__init__(**kw)
        self.orientation = 'vertical'
        self.size_hint = (None, None)
        w = card_width or dp(140)
        self.width = w
        img_h = w * 1.25
        self.height = img_h + dp(58)
        self.padding = [dp(3), dp(3), dp(3), dp(5)]
        self.spacing = dp(3)

        with self.canvas.before:
            Color(0.13, 0.13, 0.19, 1)
            self._bg = RoundedRectangle(pos=self.pos, size=self.size, radius=[dp(10)])
        self.bind(pos=self._u, size=self._u)

        if game.background_image:
            self.add_widget(AsyncImage(
                source=game.background_image, size_hint=(None, None),
                width=w - dp(6), height=img_h, allow_stretch=True, keep_ratio=False
            ))
        else:
            self.add_widget(Label(text="No Image", size_hint=(None, None),
                                  width=w - dp(6), height=img_h, color=(0.3, 0.3, 0.3, 1)))

        self.add_widget(Label(
            text=game.name, font_size=sp(12), size_hint=(None, None),
            width=w - dp(8), height=dp(30), bold=True, color=(1, 1, 1, 1),
            text_size=(w - dp(10), dp(30)), halign='left', valign='middle',
            shorten=True, shorten_from='right'
        ))

        info = BoxLayout(size_hint=(None, None), width=w - dp(8), height=dp(18), spacing=dp(4))
        rt = rating_text(game.rating or 0)
        info.add_widget(Label(text=rt, font_size=sp(10), color=(1, 0.85, 0.3, 1),
                              size_hint_x=0.6, halign='left',
                              text_size=(w * 0.5, None)))
        year = (game.release_date or "")[:4]
        info.add_widget(Label(text=year, font_size=sp(10), color=(0.5, 0.5, 0.6, 1),
                              size_hint_x=0.4, halign='right'))
        self.add_widget(info)

        if on_tap:
            self.bind(on_touch_down=lambda inst, t: on_tap(game) if inst.collide_point(*t.pos) else None)

    def _u(self, *a):
        self._bg.pos = self.pos
        self._bg.size = self.size


class CategoryRow(BoxLayout):
    def __init__(self, title, games, on_game_tap, **kw):
        super().__init__(**kw)
        self.orientation = 'vertical'
        self.size_hint_y = None
        card_w = dp(140)
        card_h = card_w * 1.25 + dp(58)
        self.height = dp(36) + card_h + dp(10)
        self.spacing = dp(4)
        self.padding = [dp(8), dp(2), dp(0), dp(6)]

        self.add_widget(Label(
            text=title, font_size=sp(16), bold=True, size_hint_y=None,
            height=dp(30), halign='left', color=(1, 1, 1, 1),
            text_size=(Window.width - dp(20), dp(30)), valign='middle'
        ))

        scroll = ScrollView(size_hint_y=None, height=card_h + dp(8),
                            do_scroll_y=False, scroll_type=['bars', 'content'])
        row = BoxLayout(size_hint=(None, None), height=card_h, spacing=dp(10))
        row.bind(minimum_width=row.setter('width'))

        for g in games:
            row.add_widget(GameCard(game=g, on_tap=on_game_tap, card_width=card_w))

        scroll.add_widget(row)
        self.add_widget(scroll)


class PlatBadge(BoxLayout):
    def __init__(self, text, r, g, b, **kw):
        super().__init__(**kw)
        self.size_hint = (None, None)
        self.size = (dp(38), dp(20))
        self.padding = [dp(4), dp(2)]
        with self.canvas.before:
            Color(r, g, b, 1)
            self._bg = RoundedRectangle(pos=self.pos, size=self.size, radius=[dp(4)])
        self.bind(pos=self._u, size=self._u)
        self.add_widget(Label(text=text, font_size=sp(8), bold=True))

    def _u(self, *a):
        self._bg.pos = self.pos
        self._bg.size = self.size


class StoreBadge(Button):
    def __init__(self, name, **kw):
        c = STORE_COLORS.get(name, (0.2, 0.2, 0.3))
        super().__init__(text=name, size_hint=(None, None), width=dp(110),
                         height=dp(32), background_color=(*c, 1), font_size=sp(11),
                         bold=True, background_normal='', **kw)


class GameRecommenderApp(App):
    def __init__(self, **kw):
        super().__init__(**kw)
        self.api_key = get_api_key()
        self.loaded_categories = {}
        self.current_tab = "browse"

    def build(self):
        self.title = "Game Recommender"
        Window.clearcolor = (0.07, 0.07, 0.11, 1)
        self.sm = ScreenManager(transition=SlideTransition())
        self.sm.add_widget(self._build_main())
        self.sm.add_widget(Screen(name="detail"))
        return self.sm

    def _build_main(self):
        screen = Screen(name="main")
        root = BoxLayout(orientation='vertical', spacing=dp(4),
                         padding=[dp(0), dp(8), dp(0), dp(0)])

        header = BoxLayout(size_hint_y=None, height=dp(44), padding=[dp(12), dp(0)])
        header.add_widget(Label(
            text="Game Recommender", font_size=sp(22), bold=True,
            halign='left', text_size=(Window.width - dp(24), dp(44)),
            valign='middle', color=(1, 1, 1, 1)
        ))
        root.add_widget(header)

        search_row = BoxLayout(size_hint_y=None, height=dp(42),
                               spacing=dp(6), padding=[dp(12), dp(0), dp(12), dp(0)])
        self.search_input = TextInput(
            hint_text='Search for any game...', multiline=False,
            size_hint_x=0.82,
            background_color=(0.13, 0.13, 0.19, 1), foreground_color=(1, 1, 1, 1),
            hint_text_color=(0.4, 0.4, 0.5, 1), cursor_color=(0.5, 0.4, 1, 1),
            padding=[dp(14), dp(10)], font_size=sp(14)
        )
        self.search_input.bind(on_text_validate=lambda x: self._do_search())
        search_row.add_widget(self.search_input)
        sbtn = Button(text="Go", size_hint_x=0.18, font_size=sp(14), bold=True,
                      background_normal='', background_color=(0.38, 0.31, 0.85, 1))
        sbtn.bind(on_release=lambda x: self._do_search())
        search_row.add_widget(sbtn)
        root.add_widget(search_row)

        self.main_scroll = ScrollView(do_scroll_x=False)
        self.main_content = BoxLayout(orientation='vertical', size_hint_y=None,
                                      spacing=dp(4), padding=[dp(0), dp(6), dp(0), dp(20)])
        self.main_content.bind(minimum_height=self.main_content.setter('height'))

        self.main_content.add_widget(Label(
            text="Loading games...", font_size=sp(14), size_hint_y=None,
            height=dp(60), color=(0.5, 0.5, 0.6, 1)
        ))

        self.main_scroll.add_widget(self.main_content)
        root.add_widget(self.main_scroll)

        nav = BoxLayout(size_hint_y=None, height=dp(48), spacing=dp(2),
                        padding=[dp(4), dp(4)])
        with nav.canvas.before:
            Color(0.1, 0.1, 0.16, 1)
            nav._bg = Rectangle(pos=nav.pos, size=nav.size)
        nav.bind(pos=lambda w, p: setattr(w._bg, 'pos', p),
                 size=lambda w, s: setattr(w._bg, 'size', s))

        self.nav_buttons = {}
        for tab_name in ["Browse", "My Games", "Stats"]:
            is_active = tab_name == "Browse"
            btn = Button(text=tab_name, font_size=sp(13), bold=True,
                         background_normal='',
                         background_color=(0.38, 0.31, 0.85, 1) if is_active else (0.18, 0.18, 0.28, 1))
            btn.bind(on_release=partial(self._switch_tab, tab_name))
            nav.add_widget(btn)
            self.nav_buttons[tab_name] = btn
        root.add_widget(nav)

        screen.add_widget(root)
        Clock.schedule_once(lambda dt: self._load_categories_batch(0), 0.3)
        return screen

    def _switch_tab(self, tab, *args):
        self.current_tab = tab.lower().replace(" ", "_")
        for name, btn in self.nav_buttons.items():
            if name == tab:
                btn.background_color = (0.38, 0.31, 0.85, 1)
            else:
                btn.background_color = (0.18, 0.18, 0.28, 1)
        if tab == "Browse":
            self._show_browse()
        elif tab == "My Games":
            self._show_my_games()
        elif tab == "Stats":
            self._show_stats()

    def _show_browse(self):
        self.search_input.text = ""
        self.main_content.clear_widgets()
        self.loaded_categories = {}
        self.main_content.add_widget(Label(
            text="Loading...", font_size=sp(14), size_hint_y=None,
            height=dp(50), color=(0.5, 0.5, 0.6, 1)
        ))
        self._load_categories_batch(0)

    def _show_my_games(self):
        self.main_content.clear_widgets()
        cfg = load_config()
        wishlist = cfg.get('wishlist', [])
        played = cfg.get('played', [])

        if wishlist:
            games = [saved_to_game(g) for g in wishlist]
            self.main_content.add_widget(
                CategoryRow(title=f"Want to Play ({len(games)})",
                            games=games, on_game_tap=self._show_detail))

        if played:
            games = [saved_to_game(g) for g in played]
            self.main_content.add_widget(
                CategoryRow(title=f"Played ({len(games)})",
                            games=games, on_game_tap=self._show_detail))

        if not wishlist and not played:
            empty_box = BoxLayout(orientation='vertical', size_hint_y=None,
                                  height=dp(200), padding=[dp(20), dp(40)])
            empty_box.add_widget(Label(
                text="No games saved yet!", font_size=sp(18), bold=True,
                size_hint_y=None, height=dp(30), color=(0.6, 0.6, 0.7, 1)
            ))
            empty_box.add_widget(Label(
                text="Browse games and tap\nWant to Play or Played It\non any game detail page.",
                font_size=sp(14), size_hint_y=None, height=dp(80),
                color=(0.45, 0.45, 0.55, 1), halign='center',
                text_size=(Window.width - dp(60), None)
            ))
            self.main_content.add_widget(empty_box)

    def _show_stats(self):
        self.main_content.clear_widgets()
        cfg = load_config()
        wishlist = cfg.get('wishlist', [])
        played = cfg.get('played', [])
        stats = cfg.get('stats', {})

        box = BoxLayout(orientation='vertical', size_hint_y=None,
                        spacing=dp(10), padding=[dp(16), dp(16)])
        box.bind(minimum_height=box.setter('height'))

        box.add_widget(Label(
            text="Your Gaming Stats", font_size=sp(20), bold=True,
            size_hint_y=None, height=dp(40), color=(0.5, 0.4, 1, 1)
        ))

        items = [
            ("Want to Play", str(len(wishlist))),
            ("Games Played", str(len(played))),
            ("Games Explored", str(stats.get('games_viewed', 0))),
            ("Searches Made", str(stats.get('searches', 0))),
        ]

        all_genres = []
        for g in played + wishlist:
            all_genres.extend(g.get('genres', []))
        if all_genres:
            top = Counter(all_genres).most_common(3)
            items.append(("Top Genres", ", ".join(t[0] for t in top)))

        for label_text, value in items:
            row = BoxLayout(size_hint_y=None, height=dp(40),
                            padding=[dp(12), dp(6)])
            with row.canvas.before:
                Color(0.12, 0.12, 0.18, 1)
                row._bg = RoundedRectangle(pos=row.pos, size=row.size, radius=[dp(8)])
            row.bind(pos=lambda w, p: setattr(w._bg, 'pos', p),
                     size=lambda w, s: setattr(w._bg, 'size', s))
            row.add_widget(Label(text=label_text, font_size=sp(13),
                                  color=(0.7, 0.7, 0.8, 1), halign='left',
                                  text_size=(dp(180), None)))
            row.add_widget(Label(text=value, font_size=sp(15), bold=True,
                                  color=(1, 0.85, 0.3, 1), halign='right',
                                  text_size=(dp(140), None)))
            box.add_widget(row)

        box.add_widget(Label(size_hint_y=None, height=dp(20)))

        if played:
            avg_rating = sum(g.get('rating', 0) for g in played) / len(played)
            mc_games = [g for g in played if g.get('metacritic')]
            avg_mc = sum(g['metacritic'] for g in mc_games) / len(mc_games) if mc_games else 0

            extra_box = BoxLayout(orientation='vertical', size_hint_y=None,
                                  spacing=dp(8), padding=[dp(0), dp(8)])
            extra_box.bind(minimum_height=extra_box.setter('height'))

            extra_box.add_widget(Label(
                text="Played Games Breakdown", font_size=sp(16), bold=True,
                size_hint_y=None, height=dp(30), color=(0.5, 0.4, 1, 1)
            ))

            for elabel, evalue in [("Avg Rating", f"{avg_rating:.1f} / 5"),
                                    ("Avg Metacritic", f"{avg_mc:.0f}" if avg_mc else "N/A")]:
                erow = BoxLayout(size_hint_y=None, height=dp(36),
                                 padding=[dp(12), dp(4)])
                with erow.canvas.before:
                    Color(0.12, 0.12, 0.18, 1)
                    erow._bg = RoundedRectangle(pos=erow.pos, size=erow.size, radius=[dp(8)])
                erow.bind(pos=lambda w, p: setattr(w._bg, 'pos', p),
                          size=lambda w, s: setattr(w._bg, 'size', s))
                erow.add_widget(Label(text=elabel, font_size=sp(13),
                                       color=(0.7, 0.7, 0.8, 1), halign='left',
                                       text_size=(dp(180), None)))
                erow.add_widget(Label(text=evalue, font_size=sp(15), bold=True,
                                       color=(1, 0.85, 0.3, 1), halign='right',
                                       text_size=(dp(140), None)))
                extra_box.add_widget(erow)

            box.add_widget(extra_box)

        self.main_content.add_widget(box)

    def _load_categories_batch(self, start_idx):
        batch_size = 4
        end_idx = min(start_idx + batch_size, len(CATEGORIES))
        cats = CATEGORIES[start_idx:end_idx]
        if not cats:
            return

        def _fetch():
            results = []
            for cat in cats:
                data = api_get("games", dict(cat["params"]), self.api_key)
                games = [parse_game(g) for g in data.get('results', [])] if data else []
                results.append((cat["title"], games))
            Clock.schedule_once(lambda dt: self._add_rows(results, end_idx))

        Thread(target=_fetch, daemon=True).start()

    def _add_rows(self, results, next_idx):
        if next_idx <= 4:
            self.main_content.clear_widgets()

        for title, games in results:
            if games:
                self.loaded_categories[title] = games
                self.main_content.add_widget(
                    CategoryRow(title=title, games=games, on_game_tap=self._show_detail))

        if not self.loaded_categories and next_idx >= len(CATEGORIES):
            self.main_content.add_widget(Label(
                text="Could not load games.\nCheck your internet connection.",
                font_size=sp(13), size_hint_y=None, height=dp(80),
                color=(1, 0.5, 0.5, 1), halign='center',
                text_size=(Window.width - dp(40), None)
            ))

        if next_idx < len(CATEGORIES):
            Clock.schedule_once(lambda dt: self._load_categories_batch(next_idx), 0.5)

    def _do_search(self):
        query = self.search_input.text.strip()
        if not query:
            return
        update_stat('searches')
        self.main_content.clear_widgets()
        self.main_content.add_widget(Label(
            text=f'Searching "{query}"...', font_size=sp(14),
            size_hint_y=None, height=dp(50), color=(0.5, 0.5, 0.6, 1)
        ))

        def _fetch():
            data = api_get("games", {'search': query, 'page_size': 40}, self.api_key)
            games = [parse_game(g) for g in data.get('results', [])] if data else []
            Clock.schedule_once(lambda dt: self._show_search(query, games))

        Thread(target=_fetch, daemon=True).start()

    def _show_search(self, query, games):
        self.main_content.clear_widgets()

        back_row = BoxLayout(size_hint_y=None, height=dp(40), padding=[dp(8), dp(4)])
        bb = Button(text="< Back to Browse", size_hint_x=None, width=dp(160),
                    font_size=sp(12), background_normal='',
                    background_color=(0.2, 0.2, 0.3, 1))
        bb.bind(on_release=lambda x: self._switch_tab("Browse"))
        back_row.add_widget(bb)
        back_row.add_widget(Label())
        self.main_content.add_widget(back_row)

        if games:
            self.main_content.add_widget(
                CategoryRow(title=f'Results for "{query}" ({len(games)})',
                            games=games[:20], on_game_tap=self._show_detail))
            if len(games) > 20:
                self.main_content.add_widget(
                    CategoryRow(title="More Results",
                                games=games[20:], on_game_tap=self._show_detail))
        else:
            self.main_content.add_widget(Label(
                text="No games found.", font_size=sp(14),
                size_hint_y=None, height=dp(60), color=(0.5, 0.5, 0.6, 1)
            ))

    def _show_detail(self, game):
        update_stat('games_viewed')
        ds = self.sm.get_screen("detail")
        ds.clear_widgets()
        temp = BoxLayout()
        with temp.canvas.before:
            Color(0.07, 0.07, 0.11, 1)
            Rectangle(pos=(0, 0), size=Window.size)
        temp.add_widget(Label(text="Loading...", font_size=sp(15), color=(0.5, 0.5, 0.6, 1)))
        ds.add_widget(temp)
        self.sm.current = "detail"

        def _fetch():
            data = api_get(f"games/{game.game_id}", {}, self.api_key)
            full = game
            if data:
                ss = api_get(f"games/{game.game_id}/screenshots", {'page_size': 8}, self.api_key)
                if ss:
                    data['screenshots'] = ss.get('results', [])
                full = parse_game(data)
            Clock.schedule_once(lambda dt: self._render_detail(full))

        Thread(target=_fetch, daemon=True).start()

    def _render_detail(self, game):
        ds = self.sm.get_screen("detail")
        ds.clear_widgets()

        root = BoxLayout(orientation='vertical')
        with root.canvas.before:
            Color(0.07, 0.07, 0.11, 1)
            Rectangle(pos=(0, 0), size=Window.size)

        top = BoxLayout(size_hint_y=None, height=dp(44), padding=[dp(8), dp(6)])
        bb = Button(text="< Back", size_hint_x=None, width=dp(80), font_size=sp(13),
                    background_normal='', background_color=(0.18, 0.18, 0.28, 1))
        bb.bind(on_release=lambda x: self._go_back())
        top.add_widget(bb)
        top.add_widget(Label())
        root.add_widget(top)

        scroll = ScrollView(do_scroll_x=False)
        c = BoxLayout(orientation='vertical', spacing=dp(10),
                      padding=[dp(14), dp(4), dp(14), dp(30)], size_hint_y=None)
        c.bind(minimum_height=c.setter('height'))

        c.add_widget(Label(
            text=game.name, font_size=sp(22), bold=True, size_hint_y=None,
            height=dp(34), color=(1, 1, 1, 1), halign='left',
            text_size=(Window.width - dp(30), None)
        ))

        if game.background_image:
            c.add_widget(AsyncImage(
                source=game.background_image, size_hint_y=None,
                height=dp(220), allow_stretch=True, keep_ratio=True
            ))

        bar = BoxLayout(size_hint_y=None, height=dp(40), spacing=dp(8), padding=[dp(10), dp(6)])
        with bar.canvas.before:
            Color(0.12, 0.12, 0.18, 1)
            bar._bg = RoundedRectangle(pos=bar.pos, size=bar.size, radius=[dp(8)])
        bar.bind(pos=lambda w, p: setattr(w._bg, 'pos', p),
                 size=lambda w, s: setattr(w._bg, 'size', s))

        bar.add_widget(Label(text=rating_text(game.rating or 0), font_size=sp(14),
                             color=(1, 0.85, 0.3, 1), size_hint_x=0.3))
        if game.metacritic:
            bar.add_widget(Label(text=f"MC: {game.metacritic}", font_size=sp(14),
                                 color=mc_color(game.metacritic), size_hint_x=0.2, bold=True))
        if game.playtime:
            bar.add_widget(Label(text=f"~{game.playtime}h", font_size=sp(12),
                                 color=(0.6, 0.6, 0.7, 1), size_hint_x=0.2))
        if game.esrb:
            bar.add_widget(Label(text=game.esrb, font_size=sp(11),
                                 color=(0.6, 0.6, 0.7, 1), size_hint_x=0.3))
        c.add_widget(bar)

        cfg = load_config()
        wl = cfg.get('wishlist', [])
        pl = cfg.get('played', [])
        in_wl = any(g.get('game_id') == game.game_id for g in wl)
        in_pl = any(g.get('game_id') == game.game_id for g in pl)

        btn_row = BoxLayout(size_hint_y=None, height=dp(40), spacing=dp(8))
        wl_btn = Button(
            text="[Wishlisted]" if in_wl else "+ Want to Play",
            font_size=sp(12), bold=True, background_normal='',
            background_color=(0.5, 0.4, 1, 1) if in_wl else (0.22, 0.22, 0.33, 1)
        )
        wl_btn.bind(on_release=lambda x: self._toggle_wishlist(game, x))
        pl_btn = Button(
            text="[Played]" if in_pl else "+ Played It",
            font_size=sp(12), bold=True, background_normal='',
            background_color=(0.2, 0.7, 0.3, 1) if in_pl else (0.22, 0.22, 0.33, 1)
        )
        pl_btn.bind(on_release=lambda x: self._toggle_played(game, x))
        btn_row.add_widget(wl_btn)
        btn_row.add_widget(pl_btn)
        c.add_widget(btn_row)

        lines = []
        if game.release_date:
            lines.append(f"Released: {game.release_date}")
        if game.developers:
            lines.append(f"Developer: {', '.join(game.developers)}")
        if game.publishers:
            lines.append(f"Publisher: {', '.join(game.publishers)}")
        if lines:
            ml = Label(text="\n".join(lines), font_size=sp(12), size_hint_y=None,
                       color=(0.65, 0.65, 0.75, 1), halign='left', valign='top',
                       text_size=(Window.width - dp(30), None))
            ml.bind(texture_size=ml.setter('size'))
            c.add_widget(ml)

        if game.platforms:
            c.add_widget(self._section("Available On"))
            ps = ScrollView(size_hint_y=None, height=dp(26), do_scroll_y=False)
            pr = BoxLayout(size_hint=(None, 1), spacing=dp(4))
            pr.bind(minimum_width=pr.setter('width'))
            for p in game.platforms:
                if p in PLATFORM_BADGES:
                    txt, r, g, b = PLATFORM_BADGES[p]
                    pr.add_widget(PlatBadge(txt, r, g, b))
            ps.add_widget(pr)
            c.add_widget(ps)

        if game.stores:
            c.add_widget(self._section("Buy / Download"))
            ss = ScrollView(size_hint_y=None, height=dp(38), do_scroll_y=False)
            sr = BoxLayout(size_hint=(None, 1), spacing=dp(6))
            sr.bind(minimum_width=sr.setter('width'))
            for st in game.stores:
                if st:
                    sr.add_widget(StoreBadge(st))
            ss.add_widget(sr)
            c.add_widget(ss)

        if game.genres:
            c.add_widget(Label(
                text=f"Genres:  {'  /  '.join(game.genres)}",
                font_size=sp(12), size_hint_y=None, height=dp(24),
                color=(0.6, 0.7, 0.85, 1), halign='left',
                text_size=(Window.width - dp(30), None)
            ))

        if game.tags:
            c.add_widget(Label(
                text=f"Tags:  {', '.join(game.tags)}",
                font_size=sp(10), size_hint_y=None, height=dp(22),
                color=(0.5, 0.5, 0.55, 1), halign='left',
                text_size=(Window.width - dp(30), None)
            ))

        desc = game.description or ''
        if desc:
            c.add_widget(self._section("About This Game"))
            dl = Label(text=desc[:2500], font_size=sp(12), size_hint_y=None,
                       text_size=(Window.width - dp(34), None), halign='left',
                       valign='top', color=(0.78, 0.78, 0.8, 1), line_height=1.4)
            dl.bind(texture_size=dl.setter('size'))
            c.add_widget(dl)

        if game.screenshots:
            c.add_widget(self._section("Screenshots"))
            sscr = ScrollView(size_hint_y=None, height=dp(160), do_scroll_y=False)
            srow = BoxLayout(size_hint=(None, 1), spacing=dp(8))
            srow.bind(minimum_width=srow.setter('width'))
            for url in game.screenshots[:8]:
                if url:
                    srow.add_widget(AsyncImage(source=url, size_hint=(None, 1),
                                               width=dp(260), allow_stretch=True, keep_ratio=True))
            sscr.add_widget(srow)
            c.add_widget(sscr)

        c.add_widget(self._section("You Might Also Like"))
        sim_scroll = ScrollView(size_hint_y=None, height=dp(250), do_scroll_y=False)
        sim_row = BoxLayout(size_hint=(None, None), height=dp(240), spacing=dp(10))
        sim_row.bind(minimum_width=sim_row.setter('width'))
        sim_row.add_widget(Label(text="Loading...", size_hint=(None, None),
                                 width=dp(100), height=dp(240), color=(0.4, 0.4, 0.5, 1)))
        sim_scroll.add_widget(sim_row)
        c.add_widget(sim_scroll)

        scroll.add_widget(c)
        root.add_widget(scroll)
        ds.add_widget(root)

        def _fetch():
            similar = None
            d = api_get(f"games/{game.game_id}/suggested", {'page_size': 10}, self.api_key)
            if d and d.get('results'):
                similar = [parse_game(g) for g in d['results']]
            if not similar:
                d = api_get(f"games/{game.game_id}/game-series", {'page_size': 10}, self.api_key)
                if d and d.get('results'):
                    similar = [parse_game(g) for g in d['results']]
            if not similar and game.genres:
                slug = GENRE_SLUG_MAP.get(game.genres[0])
                if slug:
                    d = api_get("games", {'genres': slug, 'page_size': 10, 'ordering': '-rating'}, self.api_key)
                    if d:
                        similar = [parse_game(g) for g in d.get('results', [])
                                   if g.get('id') != game.game_id][:10]
            Clock.schedule_once(lambda dt: self._fill_similar(sim_row, similar))

        Thread(target=_fetch, daemon=True).start()

    def _toggle_wishlist(self, game, btn):
        cfg = load_config()
        wl = cfg.get('wishlist', [])
        idx = next((i for i, g in enumerate(wl) if g.get('game_id') == game.game_id), None)
        if idx is not None:
            wl.pop(idx)
            btn.text = "+ Want to Play"
            btn.background_color = (0.22, 0.22, 0.33, 1)
        else:
            wl.append(game_to_saved(game))
            btn.text = "[Wishlisted]"
            btn.background_color = (0.5, 0.4, 1, 1)
        cfg['wishlist'] = wl
        save_config(cfg)

    def _toggle_played(self, game, btn):
        cfg = load_config()
        pl = cfg.get('played', [])
        idx = next((i for i, g in enumerate(pl) if g.get('game_id') == game.game_id), None)
        if idx is not None:
            pl.pop(idx)
            btn.text = "+ Played It"
            btn.background_color = (0.22, 0.22, 0.33, 1)
        else:
            pl.append(game_to_saved(game))
            btn.text = "[Played]"
            btn.background_color = (0.2, 0.7, 0.3, 1)
        cfg['played'] = pl
        save_config(cfg)

    def _fill_similar(self, row, games):
        row.clear_widgets()
        if games:
            for g in games:
                row.add_widget(GameCard(game=g, on_tap=self._show_detail, card_width=dp(140)))
        else:
            row.add_widget(Label(text="No recommendations found", size_hint=(None, None),
                                 width=dp(200), height=dp(240), color=(0.4, 0.4, 0.5, 1)))

    def _section(self, text):
        return Label(text=text, font_size=sp(15), bold=True,
                     size_hint_y=None, height=dp(28), color=(0.5, 0.4, 1, 1),
                     halign='left', text_size=(Window.width - dp(30), None))

    def _go_back(self):
        self.sm.transition.direction = 'right'
        self.sm.current = "main"
        self.sm.transition.direction = 'left'


if __name__ == '__main__':
    GameRecommenderApp().run()
