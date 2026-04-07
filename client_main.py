import logging
from enum import Enum, auto

import pyray as pr

from client.gui import (
    ScreenProtocol,
    WindowSettings,
)
from client.screens.non_game import ConnectScreen

logging.basicConfig(level=logging.INFO)


def main():
    WINDOW_SETTINGS = WindowSettings()

    pr.init_window(
        WINDOW_SETTINGS.screen_width, WINDOW_SETTINGS.screen_height, "Redsky"
    )

    current_screen: ScreenProtocol = ConnectScreen(window_settings=WINDOW_SETTINGS)

    while not pr.window_should_close():
        pr.begin_drawing()
        pr.gui_load_style_default()

        current_screen = current_screen()

        pr.clear_background(pr.LIGHTGRAY)

        pr.end_drawing()


if __name__ == "__main__":
    main()
