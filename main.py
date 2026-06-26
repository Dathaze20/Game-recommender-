import os
import logging
from typing import List, Optional
from functools import partial

import requests
from dotenv import load_dotenv
from kivy.app import App
from kivy.uix.image import AsyncImage
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.label import Label
from kivy.uix.gridlayout import GridLayout
from kivy.uix.scrollview import ScrollView
from kivy.uix.spinner import Spinner
from kivy.uix.popup import Popup
from kivy.uix.textinput import TextInput
from kivy.clock import Clock
from kivy.config import Config
from kivy.core.window import Window
from kivy.uix.screenmanager import ScreenManager, Screen, SlideTransition
from kivy.uix.button import Button
from kivy.graphics import Color, Rectangle, RoundedRectangle

logging.basicConfig(
    filename='game_app.log',
    level=logging.INFO,
    format='%(asctime)s:%(levelname)s:%(message)s'
)

load_dotenv()

Config.set('graphics', 'width', '800')
Config.set('graphics', 'height', '600')
Config.set('kivy', 'keyboard_mode', 'system')
Config.set('graphics', 'fullscreen', 'auto')

API_KEY = os.getenv('GAME_API_KEY', 'your_api_key_here')
BASE_URL = "https://api.rawg.io/api"

GENRES = [
    "All", "Action", "Adventure", "RPG", "Strategy", "Shooter",
    "Puzzle", "Racing", "Sports", "Simulation", "Platformer", "Indie"
]

GENRE_SLUG_MAP = {
    "Action": "action", "Adventure": "adventure", "RPG": "role-playing-games-rpg",
    "Strategy": "strategy", "Shooter": "shooter", "Puzzle": "puzzle",
    "Racing": "racing", "Sports": "sports", "Simulation": "simulation",
    "Platformer": "platformer", "Indie": "indie"
}


class GameDetails:
    def __init__(self, game_id: int, name: str, description: str,
                 release_date: str, background_image: str, rating: float,
                 metacritic: Optional[int], genres: List[str],
                 platforms: List[str]):
        self.game_id = game_id
        self.name = name
        self.description = description
        self.release_date = release_date
        self.background_image = background_image
        self.rating = rating
        self.metacritic = metacritic
        self.genres = genres
        self.platforms = platforms


def parse_game(game_data: dict) -> GameDetails:
    genres = [g['name'] for g in game_data.get('genres', [])]
    platforms = [p['platform']['name'] for p in game_data.get('platforms', []) if 'platform' in p]
    return GameDetails(
        game_id=game_data.get('id', 0),
        name=game_data.get('name', 'Unknown'),
        description=game_data.get('description_raw', game_data.get('description', 'No description available')),
        release_date=game_data.get('released', 'Unknown'),
        rating=game_data.get('rating', 0.0),
        metacritic=game_data.get('metacritic'),
        genres=genres,
        platforms=platforms,
        background_image=game_data.get('background_image', '')
    )


def fetch_popular_games(page: int = 1, genre: str = None, page_size: int = 12) -> Optional[List[GameDetails]]:
    try:
        params = {'key': API_KEY, 'page': page, 'page_size': page_size, 'ordering': '-rating'}
        if genre and genre in GENRE_SLUG_MAP:
            params['genres'] = GENRE_SLUG_MAP[genre]
        response = requests.get(f"{BASE_URL}/games", params=params, timeout=15)
        response.raise_for_status()
        return [parse_game(g) for g in response.json().get('results', [])]
    except requests.RequestException as e:
        logging.error(f"Fetch popular games error: {e}")
    return None


def search_games(query: str, page: int = 1) -> Optional[List[GameDetails]]:
    try:
        params = {'key': API_KEY, 'search': query, 'page': page, 'page_size': 12}
        response = requests.get(f"{BASE_URL}/games", params=params, timeout=15)
        response.raise_for_status()
        return [parse_game(g) for g in response.json().get('results', [])]
    except requests.RequestException as e:
        logging.error(f"Search games error: {e}")
    return None


def fetch_game_details(game_id: int) -> Optional[GameDetails]:
    try:
        params = {'key': API_KEY}
        response = requests.get(f"{BASE_URL}/games/{game_id}", params=params, timeout=15)
        response.raise_for_status()
        return parse_game(response.json())
    except requests.RequestException as e:
        logging.error(f"Fetch game details error: {e}")
    return None


def fetch_similar_games(game_id: int) -> Optional[List[GameDetails]]:
    try:
        params = {'key': API_KEY, 'page_size': 6}
        response = requests.get(f"{BASE_URL}/games/{game_id}/suggested", params=params, timeout=15)
        response.raise_for_status()
        return [parse_game(g) for g in response.json().get('results', [])]
    except requests.RequestException as e:
        logging.error(f"Fetch similar games error: {e}")
    return None


class NoKeyboardTextInput(TextInput):
    def on_touch_down(self, touch):
        if self.collide_point(*touch.pos):
            Window.release_all_keyboards()
        return super().on_touch_down(touch)


class GameCard(BoxLayout):
    def __init__(self, game: GameDetails, on_tap=None, **kwargs):
        super().__init__(**kwargs)
        self.orientation = 'vertical'
        self.size_hint_y = None
        self.height = 350
        self.padding = 5
        self.spacing = 5
        self.game = game

        with self.canvas.before:
            Color(0.15, 0.15, 0.2, 1)
            self._bg = RoundedRectangle(pos=self.pos, size=self.size, radius=[10])
        self.bind(pos=self._update_bg, size=self._update_bg)

        if game.background_image:
            img = AsyncImage(source=game.background_image, size_hint_y=None, height=220, allow_stretch=True)
            self.add_widget(img)
        else:
            placeholder = Label(text="No Image", size_hint_y=None, height=220, color=(0.5, 0.5, 0.5, 1))
            self.add_widget(placeholder)

        name_label = Label(
            text=game.name, font_size='14sp', size_hint_y=None,
            height=40, text_size=(None, None), halign='center',
            valign='middle', bold=True
        )
        self.add_widget(name_label)

        info_layout = BoxLayout(orientation='horizontal', size_hint_y=None, height=25, spacing=5)

        star = Label(text=f"[color=ffcc00]★[/color] {game.rating:.1f}", markup=True,
                     font_size='12sp', size_hint_x=0.5)
        info_layout.add_widget(star)

        if game.metacritic:
            mc_color = "00ff00" if game.metacritic >= 75 else "ffff00" if game.metacritic >= 50 else "ff0000"
            mc = Label(text=f"[color={mc_color}]MC: {game.metacritic}[/color]", markup=True,
                       font_size='12sp', size_hint_x=0.5)
            info_layout.add_widget(mc)
        else:
            info_layout.add_widget(Label(text="", size_hint_x=0.5))

        self.add_widget(info_layout)

        release = Label(text=game.release_date or "Unknown", font_size='11sp',
                        size_hint_y=None, height=20, color=(0.7, 0.7, 0.7, 1))
        self.add_widget(release)

        if on_tap:
            self.bind(on_touch_down=lambda inst, touch: on_tap(game) if inst.collide_point(*touch.pos) else None)

    def _update_bg(self, *args):
        self._bg.pos = self.pos
        self._bg.size = self.size


class GameRecommenderApp(App):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.current_page = 1
        self.current_genre = "All"
        self.search_query = ""
        self.all_games = []
        self.search_event = None

    def build(self):
        self.title = "Game Recommender"
        Window.clearcolor = (0.08, 0.08, 0.12, 1)

        self.sm = ScreenManager(transition=SlideTransition())
        self.sm.add_widget(self._build_main_screen())
        self.sm.add_widget(self._build_detail_screen())
        return self.sm

    def _build_main_screen(self):
        screen = Screen(name="main")
        root = BoxLayout(orientation='vertical', spacing=5, padding=10)

        header = BoxLayout(size_hint_y=None, height=50)
        title = Label(text="[b]Game Recommender[/b]", markup=True,
                      font_size='26sp', color=(0.4, 0.7, 1, 1))
        header.add_widget(title)
        root.add_widget(header)

        search_row = BoxLayout(size_hint_y=None, height=45, spacing=10)
        self.search_input = NoKeyboardTextInput(
            hint_text='Search games...', multiline=False,
            background_color=(0.15, 0.15, 0.2, 1), foreground_color=(1, 1, 1, 1),
            hint_text_color=(0.5, 0.5, 0.5, 1), cursor_color=(1, 1, 1, 1),
            size_hint_x=0.7
        )
        self.search_input.bind(text=self._on_search_text)
        search_row.add_widget(self.search_input)

        search_btn = Button(text="Search", size_hint_x=0.15,
                            background_color=(0.3, 0.5, 0.9, 1))
        search_btn.bind(on_release=lambda x: self._do_search())
        search_row.add_widget(search_btn)

        clear_btn = Button(text="Clear", size_hint_x=0.15,
                           background_color=(0.5, 0.3, 0.3, 1))
        clear_btn.bind(on_release=lambda x: self._clear_search())
        search_row.add_widget(clear_btn)
        root.add_widget(search_row)

        genre_scroll = ScrollView(size_hint_y=None, height=45, do_scroll_y=False)
        self.genre_bar = BoxLayout(size_hint=(None, 1), spacing=5)
        self.genre_bar.bind(minimum_width=self.genre_bar.setter('width'))
        self.genre_buttons = {}
        for genre in GENRES:
            btn = Button(text=genre, size_hint=(None, 1), width=100,
                         background_color=(0.3, 0.5, 0.9, 1) if genre == "All" else (0.2, 0.2, 0.3, 1))
            btn.bind(on_release=partial(self._on_genre_select, genre))
            self.genre_bar.add_widget(btn)
            self.genre_buttons[genre] = btn
        genre_scroll.add_widget(self.genre_bar)
        root.add_widget(genre_scroll)

        self.status_label = Label(text="", size_hint_y=None, height=25,
                                  color=(1, 0.5, 0.5, 1), font_size='12sp')
        root.add_widget(self.status_label)

        scroll = ScrollView(do_scroll_x=False)
        self.grid = GridLayout(cols=3, spacing=10, padding=5, size_hint_y=None)
        self.grid.bind(minimum_height=self.grid.setter('height'))
        scroll.add_widget(self.grid)
        root.add_widget(scroll)

        nav = BoxLayout(size_hint_y=None, height=45, spacing=10)
        self.prev_btn = Button(text="◄ Previous", background_color=(0.25, 0.25, 0.35, 1))
        self.prev_btn.bind(on_release=lambda x: self._change_page(-1))
        self.prev_btn.disabled = True
        nav.add_widget(self.prev_btn)

        self.page_label = Label(text="Page 1", font_size='14sp')
        nav.add_widget(self.page_label)

        self.next_btn = Button(text="Next ►", background_color=(0.25, 0.25, 0.35, 1))
        self.next_btn.bind(on_release=lambda x: self._change_page(1))
        nav.add_widget(self.next_btn)
        root.add_widget(nav)

        screen.add_widget(root)

        self.loading_popup = Popup(
            title='Loading Games...', content=Label(text="Please wait..."),
            size_hint=(None, None), size=(250, 150), auto_dismiss=False
        )
        self.loading_popup.open()
        Clock.schedule_once(lambda dt: self._load_games(), 0.5)

        return screen

    def _build_detail_screen(self):
        screen = Screen(name="detail")
        self.detail_layout = BoxLayout(orientation='vertical')
        screen.add_widget(self.detail_layout)
        return screen

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

    def _on_genre_select(self, genre, *args):
        self.current_genre = genre
        self.current_page = 1
        for g, btn in self.genre_buttons.items():
            btn.background_color = (0.3, 0.5, 0.9, 1) if g == genre else (0.2, 0.2, 0.3, 1)
        self._load_games()

    def _change_page(self, delta):
        self.current_page += delta
        if self.current_page < 1:
            self.current_page = 1
        self._load_games()

    def _load_games(self):
        self.status_label.text = "Loading..."
        self.grid.clear_widgets()

        if not API_KEY or API_KEY == 'your_api_key_here':
            self.status_label.text = "Error: Set GAME_API_KEY in your .env file (get one free at rawg.io/apidocs)"
            if self.loading_popup._is_open:
                self.loading_popup.dismiss()
            return

        Clock.schedule_once(lambda dt: self._fetch_and_display(), 0.1)

    def _fetch_and_display(self, *args):
        try:
            if self.search_query:
                games = search_games(self.search_query, self.current_page)
                header = f'Results for "{self.search_query}"'
            else:
                genre = self.current_genre if self.current_genre != "All" else None
                games = fetch_popular_games(self.current_page, genre)
                header = f"Popular {self.current_genre} Games" if self.current_genre != "All" else "Popular Games"

            if games:
                self.all_games = games
                self.grid.clear_widgets()
                for game in games:
                    card = GameCard(game=game, on_tap=self._show_detail)
                    self.grid.add_widget(card)
                self.status_label.text = f"{header} — {len(games)} games"
            else:
                self.status_label.text = "No games found. Check your API key or try a different search."

            self.prev_btn.disabled = self.current_page <= 1
            self.page_label.text = f"Page {self.current_page}"

        except Exception as e:
            self.status_label.text = f"Error: {e}"
            logging.error(f"Display error: {e}")
        finally:
            try:
                if self.loading_popup._is_open:
                    self.loading_popup.dismiss()
            except Exception:
                pass

    def _show_detail(self, game: GameDetails):
        self.detail_layout.clear_widgets()

        with self.detail_layout.canvas.before:
            Color(0.08, 0.08, 0.12, 1)
            Rectangle(pos=self.detail_layout.pos, size=Window.size)

        scroll = ScrollView(do_scroll_x=False)
        content = BoxLayout(orientation='vertical', spacing=10, padding=15, size_hint_y=None)
        content.bind(minimum_height=content.setter('height'))

        top_bar = BoxLayout(size_hint_y=None, height=45)
        back_btn = Button(text="◄ Back", size_hint_x=0.2, background_color=(0.3, 0.3, 0.45, 1))
        back_btn.bind(on_release=lambda x: self._go_back())
        top_bar.add_widget(back_btn)
        top_bar.add_widget(Label(text=f"[b]{game.name}[/b]", markup=True,
                                 font_size='20sp', size_hint_x=0.8, color=(0.4, 0.7, 1, 1)))
        content.add_widget(top_bar)

        if game.background_image:
            img = AsyncImage(source=game.background_image, size_hint_y=None, height=350, allow_stretch=True)
            content.add_widget(img)

        info_box = BoxLayout(orientation='horizontal', size_hint_y=None, height=40, spacing=10)
        info_box.add_widget(Label(text=f"[color=ffcc00]★[/color] {game.rating:.1f}/5", markup=True, font_size='16sp'))
        if game.metacritic:
            mc_color = "00ff00" if game.metacritic >= 75 else "ffff00" if game.metacritic >= 50 else "ff0000"
            info_box.add_widget(Label(text=f"[color={mc_color}]Metacritic: {game.metacritic}[/color]",
                                      markup=True, font_size='16sp'))
        info_box.add_widget(Label(text=f"Released: {game.release_date}", font_size='14sp',
                                  color=(0.7, 0.7, 0.7, 1)))
        content.add_widget(info_box)

        if game.genres:
            genre_text = "Genres: " + ", ".join(game.genres)
            content.add_widget(Label(text=genre_text, font_size='13sp', size_hint_y=None,
                                     height=30, color=(0.6, 0.8, 1, 1)))

        if game.platforms:
            plat_text = "Platforms: " + ", ".join(game.platforms)
            content.add_widget(Label(text=plat_text, font_size='13sp', size_hint_y=None,
                                     height=30, color=(0.8, 0.8, 0.6, 1), text_size=(Window.width - 30, None)))

        if game.description and game.description != 'No description available':
            desc_text = game.description[:1500]
            desc_label = Label(
                text=desc_text, font_size='13sp', size_hint_y=None,
                text_size=(Window.width - 40, None), halign='left', valign='top',
                color=(0.85, 0.85, 0.85, 1)
            )
            desc_label.bind(texture_size=desc_label.setter('size'))
            content.add_widget(desc_label)

        content.add_widget(Label(text="[b]You Might Also Like[/b]", markup=True,
                                 font_size='18sp', size_hint_y=None, height=45,
                                 color=(0.4, 0.7, 1, 1)))

        similar_grid = GridLayout(cols=3, spacing=10, size_hint_y=None)
        similar_grid.bind(minimum_height=similar_grid.setter('height'))
        content.add_widget(similar_grid)

        scroll.add_widget(content)
        self.detail_layout.add_widget(scroll)
        self.sm.current = "detail"

        Clock.schedule_once(lambda dt: self._load_similar(game.game_id, similar_grid, game), 0.3)

    def _load_similar(self, game_id: int, grid: GridLayout, original_game: GameDetails):
        similar = fetch_similar_games(game_id)

        if not similar and original_game.genres:
            try:
                genre_slug = GENRE_SLUG_MAP.get(original_game.genres[0])
                if genre_slug:
                    params = {'key': API_KEY, 'genres': genre_slug, 'page_size': 6, 'ordering': '-rating'}
                    resp = requests.get(f"{BASE_URL}/games", params=params, timeout=15)
                    resp.raise_for_status()
                    similar = [parse_game(g) for g in resp.json().get('results', [])
                               if g.get('id') != game_id][:6]
            except Exception as e:
                logging.error(f"Fallback similar fetch error: {e}")

        if similar:
            for sg in similar:
                card = GameCard(game=sg, on_tap=self._show_detail)
                grid.add_widget(card)
        else:
            grid.add_widget(Label(text="No recommendations available", size_hint_y=None,
                                  height=50, color=(0.5, 0.5, 0.5, 1)))

    def _go_back(self):
        self.sm.transition.direction = 'right'
        self.sm.current = "main"
        self.sm.transition.direction = 'left'


if __name__ == '__main__':
    GameRecommenderApp().run()
