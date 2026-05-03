import logging
import random
from collections.abc import Set
from decimal import Decimal
from typing import override

import pyray as pr
from common.game_state import Biome, Land, Resource
from common.hex import Hex
from common.networking import ClientNetworking

from client.gui import ScreenProtocol, WindowSettings
from client.screens.draw_state import HexState
from client.screens.drawing import (
    draw_hexagon,
    hex_coord_to_world_coord,
    world_coord_to_hex_coord,
)


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
        self._camera = pr.Camera2D(
            # This means make screen center world center and place the camera there
            self.window_settings.screen_center,
            pr.vector2_zero(),
            0,
            1,
        )
        self._camera_controller = CameraController(
            window_settings=self.window_settings, camera=self._camera
        )
        self._target = pr.load_render_texture(
            self.window_settings.screen_width,
            self.window_settings.screen_height,
        )
        self._map: dict[Hex, Land] = self._generate_map()
        self._selection_controller = TileSelectionController(
            window_settings=self.window_settings,
            camera=self._camera,
            hex_size=self._hex_size,
            # NOTE: This is actually a KeysView which updates alongside the original dict
            selectable_hexes=self._map.keys(),
        )
        # TODO: We just start with tile selection turned on...
        self._selection_controller.reset(1)

    @classmethod
    def _generate_land(cls) -> Land:
        resources_points = 2
        resources: dict[Resource, int] = {}
        min_gen = False
        for i in range(resources_points):
            if min_gen and Decimal(random.random()) >= Decimal("0.5"):
                continue
            min_gen = True
            new_resource = random.choice(list(Resource))
            if new_resource not in resources:
                resources[new_resource] = 0
            resources[new_resource] += 1

        return Land(biome=random.choice(list(Biome)), resources=resources)

    @classmethod
    def _generate_map(cls) -> dict[Hex, Land]:
        game_map: dict[Hex, Land] = {}
        for r in range(7):
            for h in Hex.origin().ring(r):
                game_map[h] = cls._generate_land()
        return game_map

    @override
    def __call__(self) -> "ScreenProtocol":
        self._selection_controller.update()
        self._camera_controller.update()

        pr.begin_texture_mode(self._target)
        pr.begin_mode_2d(self._camera)
        pr.clear_background(pr.BLANK)
        for hex in self._map:
            draw_hexagon(
                hex_coord_to_world_coord(hex, self._hex_size),
                size=self._hex_size,
                color=pr.RED,
                state=self._selection_controller.get_state_of_hex(hex),
            )
        pr.end_mode_2d()
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

        # Draw HUD on top

        selected_hex_screen_pos = (
            self._selection_controller.get_selection_screen_coord()
        )
        if selected_hex_screen_pos is not None:
            selected_hex = self._selection_controller.selection[0]
            pr.draw_text(
                f"({selected_hex.q}, {selected_hex.r}, {selected_hex.s})",
                int(selected_hex_screen_pos.x),
                int(selected_hex_screen_pos.y),
                20,
                pr.BLUE,
            )

        return self


class TileSelectionController:
    def __init__(
        self,
        window_settings: WindowSettings,
        camera: pr.Camera2D,
        hex_size: int,
        selectable_hexes: Set[Hex],
    ) -> None:
        self._window_settings = window_settings
        self._camera = camera
        self._selection_size: int = 0
        self._hex_size = hex_size
        self._selectable_hexes: Set[Hex] = selectable_hexes
        self._is_clicking: bool = False
        self.selection: list[Hex] = []
        self.hovered: Hex | None = None

    def get_state_of_hex(self, hex: Hex) -> HexState:
        if hex not in self._selectable_hexes:
            return HexState.DISABLED
        elif hex in self.selection:
            return HexState.SELECTED
        elif self.hovered is not None and hex == self.hovered:
            return HexState.HOVERED
        else:
            return HexState.UNSELECTED

    def get_selection_screen_coord(
        self, selection_index: int = 0
    ) -> "pr.Vector2 | None":
        if not self.selection:
            return None

        return pr.get_world_to_screen_2d(
            hex_coord_to_world_coord(self.selection[selection_index], self._hex_size),
            self._camera,
        )

    @property
    def is_enabled(self) -> bool:
        return self._selection_size > 0

    def get_mouse_hex(self) -> Hex:
        mouse_screen_pos = pr.get_mouse_position()
        mouse_world_pos = pr.get_screen_to_world_2d(mouse_screen_pos, self._camera)
        hex = world_coord_to_hex_coord(
            mouse_world_pos,
            self._hex_size,
        )
        return hex

    def update(self) -> None:
        if not self.is_enabled:
            return

        self.hovered = self.get_mouse_hex()
        if (
            pr.is_mouse_button_pressed(pr.MouseButton.MOUSE_BUTTON_LEFT)
            and self.hovered in self._selectable_hexes
        ):
            self.toggle_selection_of_hovered()

        if (
            pr.is_mouse_button_pressed(pr.MouseButton.MOUSE_BUTTON_RIGHT)
            and self.selection
        ):
            _ = self.selection.pop()

    def toggle_selection_of_hovered(self) -> None:
        if self.hovered is None:
            logging.error(
                "Never updated selection manager - nothing is being hovered to toggle selection."
            )
            return
        if self.hovered not in self.selection:
            # If we've selected too many things, we deselect the first thing in our selection
            # to make room for the last.
            if self._selection_size <= len(self.selection):
                _ = self.selection.pop(0)
            self.selection.append(self.hovered)
        else:
            self.selection.remove(self.hovered)

    def reset(self, selection_size: int = 1) -> None:
        self.selection = []
        self.hovered = None
        self._selection_size = selection_size


class CameraController:
    def __init__(self, window_settings: WindowSettings, camera: pr.Camera2D) -> None:
        self._window_settings = window_settings
        self._camera = camera
        self._move_speed = 500
        self._zoom_speed = 500
        self._min_zoom = 0.33
        self._max_zoom = 3

    def reset(self) -> None:
        self._camera.zoom = 1
        self._camera.rotation = 0
        self._camera.target = pr.vector2_zero()
        self._camera.offset = self._window_settings.screen_center

    def update(self) -> None:
        dt = pr.get_frame_time()

        if pr.is_key_pressed(pr.KeyboardKey.KEY_ZERO):
            self.reset()

        zoom_delta = pr.get_mouse_wheel_move()
        if zoom_delta != 0:
            # Zoom to Mouse Position
            self._camera.target = pr.get_screen_to_world_2d(
                pr.get_mouse_position(), self._camera
            )
            self._camera.offset = pr.get_mouse_position()

            self._camera.zoom = pr.clamp(
                self._camera.zoom + (zoom_delta * self._zoom_speed * dt),
                self._min_zoom,
                self._max_zoom,
            )

        translation = pr.vector2_zero()
        if pr.is_key_down(pr.KeyboardKey.KEY_W):
            translation = pr.vector2_add(translation, pr.Vector2(0, -1))
        if pr.is_key_down(pr.KeyboardKey.KEY_S):
            translation = pr.vector2_add(translation, pr.Vector2(0, 1))
        if pr.is_key_down(pr.KeyboardKey.KEY_A):
            translation = pr.vector2_add(translation, pr.Vector2(-1, 0))
        if pr.is_key_down(pr.KeyboardKey.KEY_D):
            translation = pr.vector2_add(translation, pr.Vector2(1, 0))

        self._camera.target = pr.vector2_add(
            self._camera.target,
            pr.vector2_scale(
                pr.vector2_normalize(translation),
                self._move_speed * dt / self._camera.zoom,
            ),
        )
