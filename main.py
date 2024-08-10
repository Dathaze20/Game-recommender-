import os
import logging
from typing import List, Optional

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
from kivy.uix.screenmanager import ScreenManager, Screen
from kivy.uix.button import Button

# Configure logging
logging.basicConfig(filename='game_app.log', level=logging.INFO, format='%(asctime)s:%(levelname)s:%(message)s')

# Load environment variables
load_dotenv()

# Set Kivy configurations
Config.set('graphics', 'width', '800')
Config.set('graphics', 'height', '600')
Config.set('kivy', 'keyboard_mode', 'system')
Config.set('graphics', 'fullscreen', 'auto')

# Replace with your actual API key or use environment variables
api_key = os.getenv('GAME_API_KEY', 'your_api_key_here')  # Update to your game API key
# Example for RAWG API
game_api_base_url = "https://api.rawg.io/api/games"

# GameDetails class to store game details
class GameDetails:
    def __init__(self, name: str, description: str, release_date: str, background_image: str):
        self.name = name
        self.description = description
        self.release_date = release_date
        self.background_image = background_image

# Function to fetch popular games
def fetch_popular_games(page_number: int) -> Optional[List[GameDetails]]:
    try:
        params = {
            'key': api_key,
            'page': page_number,
            'page_size': 10
        }
        response = requests.get(game_api_base_url, params=params)
        response.raise_for_status()
        games = response.json().get('results', [])
        return [
            GameDetails(
                name=game_data['name'],
                description=game_data.get('description', 'No description available'),
                release_date=game_data.get('released', 'Unknown release date'),
                background_image=game_data.get('background_image', '')
            )
            for game_data in games
        ]
    except requests.RequestException as request_error:
        logging.error(f"Request error occurred: {request_error}")
    except Exception as general_error:
        logging.error(f"Unexpected error: {general_error}")
    return None

# TextInput class to disable virtual keyboard
class NoKeyboardTextInput(TextInput):
    def on_touch_down(self, touch):
        if self.collide_point(*touch.pos):
            Window.release_all_keyboards()
        return super().on_touch_down(touch)

# Main app class
class GamePosterApp(App):
    def build(self):
        self.screen_manager = ScreenManager()

        # Main screen
        self.main_screen = Screen(name="Main Screen")
        root_layout = BoxLayout(orientation='vertical')
        
        title_label = Label(text="Popular Games", font_size='24sp', size_hint_y=None, height=50)
        root_layout.add_widget(title_label)
        
        search_bar = NoKeyboardTextInput(hint_text='Search for a game...', multiline=False, size_hint_y=None, height=Window.height * 0.07)
        root_layout.add_widget(search_bar)
        
        self.error_label = Label(text="", color=(1, 0, 0, 1), size_hint_y=None, height=30)
        root_layout.add_widget(self.error_label)
        
        scroll_view = ScrollView(size_hint=(1, 1), do_scroll_x=False)
        root_layout.add_widget(scroll_view)
        
        self.poster_grid_layout = GridLayout(cols=3, spacing=10, size_hint_y=None)
        self.poster_grid_layout.bind(minimum_height=self.poster_grid_layout.setter('height'))
        scroll_view.add_widget(self.poster_grid_layout)
        
        self.loading_popup = Popup(title='Loading', content=Spinner(), size_hint=(None, None), size=(200, 200))
        self.loading_popup.open()

        if not api_key:
            self.error_label.text = "Error: API key not found. Please check your environment variables or the default API key in the code."
            self.loading_popup.dismiss()
            return root_layout

        Clock.schedule_once(self.load_games, 1)

        self.main_screen.add_widget(root_layout)
        self.screen_manager.add_widget(self.main_screen)

        # Detail screen
        self.detail_screen = Screen(name="Detail Screen")
        self.screen_manager.add_widget(self.detail_screen)

        return self.screen_manager

    # Function to load games
    def load_games(self, dt):
        try:
            all_popular_games = []
            for page_number in range(1, 6):
                popular_games_page = fetch_popular_games(page_number)
                if popular_games_page:
                    all_popular_games.extend(popular_games_page)
                else:
                    logging.error(f"Failed to get popular games for page {page_number}")
                    continue

            for game_details in all_popular_games:
                background_image = game_details.background_image
                if background_image:
                    try:
                        game_poster = AsyncImage(source=background_image, size_hint_y=None, height=300)
                        game_poster.bind(on_release=self.show_game_details)
                        self.poster_grid_layout.add_widget(game_poster)
                    except Exception as image_error:
                        logging.error(f"Error loading poster: {image_error}")
                        self.error_label.text = "Error loading poster image. Please check your internet connection and try again."
                else:
                    logging.warning(f"No image available for the game: {game_details.name}")

        except Exception as general_error:
            self.error_label.text = f"General error: {general_error}. Please check your setup and try again."
            logging.error(self.error_label.text)
        finally:
            self.loading_popup.dismiss()

    # Function to show game details
    def show_game_details(self, instance):
        self.detail_screen.clear_widgets()
        detail_layout = BoxLayout(orientation='vertical')
        game_name = Label(text="Game Name", font_size='24sp', size_hint_y=None, height=50)
        detail_layout.add_widget(game_name)
        game_description = Label(text="Game Description", font_size='16sp')
        detail_layout.add_widget(game_description)
        game_release_date = Label(text="Release Date", font_size='16sp')
        detail_layout.add_widget(game_release_date)
        back_button = Button(text="Back", size_hint_y=None, height=50)
        back_button.bind(on_release=self.go_back)
        detail_layout.add_widget(back_button)
        self.detail_screen.add_widget(detail_layout)
        self.screen_manager.current = "Detail Screen"

    # Function to go back to main screen
    def go_back(self, instance):
        self.screen_manager.current = "Main Screen"

if __name__ == '__main__':
    GamePosterApp().run()