from random import random
from typing import override

import pyray as pr
from common.hex import Hex
from common.networking import ClientNetworking

from client.drawing import (
    draw_hexagon,
    hex_coord_to_screen_cord,
    screen_coord_to_hex_coord,
)
from client.gui import ScreenProtocol, WindowSettings


class GameScreen(ScreenProtocol):
    def __init__(
        self,
        window_settings: WindowSettings,
        client_networking: ClientNetworking,
        player_id: str,
        registered_player_name: str,
    ) -> None:
        self.window_settings = window_settings
        self.client_networking = client_networking
        self.player_id: str = player_id
        self.registered_player_name: str = registered_player_name
        self._hex_size: int = 60
        self._target = pr.load_render_texture(
            self.window_settings.screen_width,
            self.window_settings.screen_height,
        )

    @override
    def __call__(self) -> "ScreenProtocol":
        pr.begin_texture_mode(self._target)
        pr.clear_background(pr.BLANK)
        screen_center = pr.Vector2(
            self.window_settings.screen_width / 2,
            self.window_settings.screen_height / 2,
        )
        mouse_pos = pr.get_mouse_position()
        for hex in Hex(q=0, r=0).neighbors():
            mouse_hex = screen_coord_to_hex_coord(
                pr.vector2_subtract(mouse_pos, screen_center), self._hex_size
            )
            print(mouse_hex)
            is_selected = mouse_hex == hex
            draw_hexagon(
                pr.vector2_add(
                    screen_center, hex_coord_to_screen_cord(hex, self._hex_size)
                ),
                size=self._hex_size - 1,
                color=pr.RED if is_selected else pr.BLACK,
            )
        pr.end_texture_mode()

        source_rec = pr.Rectangle(
            0, 0, self._target.texture.width, -self._target.texture.height
        )
        dest_rec = pr.Rectangle(
            0, 0, self._target.texture.width, self._target.texture.height
        )
        pr.draw_texture_pro(
            self._target.texture, source_rec, dest_rec, pr.Vector2(0, 0), 0, pr.WHITE
        )

        return self
