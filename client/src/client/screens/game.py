import logging
from collections.abc import Set
from typing import override

import pyray as pr
from common.game_state import Land, PlayerCharacter, Resource
from common.hex import Hex
from common.networking import ClientNetworking
from common.protocol import (
    ActionLearnMessage,
    GameStateMessage,
    GameStateMessageCodec,
    MsgType,
)

from client.gui import (
    LayoutBuilder,
    Placement,
    ScreenProtocol,
    WindowSettings,
    gui_label,
    gui_measure_text_size,
    gui_set_text_size,
)
from client.screens.draw_state import HexState
from client.screens.drawing import (
    draw_land,
    hex_coord_to_world_coord,
    world_coord_to_hex_coord,
)
from client.utils import bbox2d_pad


class GameScreen(ScreenProtocol):
    def __init__(
        self,
        window_settings: WindowSettings,
        client_networking: ClientNetworking,
        player_id: str,
        registered_player_name: str,
        initial_game_state: GameStateMessage,
    ) -> None:
        self.window_settings = window_settings
        self.client_networking = client_networking
        self._game_state_message_codec = GameStateMessageCodec()
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
        self._game_state = initial_game_state
        self._selectable_hexes = set(self._game_state.game_map.keys())
        self._selection_controller = TileSelectionController(
            window_settings=self.window_settings,
            camera=self._camera,
            hex_size=self._hex_size,
            selectable_hexes=self._selectable_hexes,
        )
        # TODO: We just start with tile selection turned on...
        self._selection_controller.reset(1)
        self._is_action_pending = False
        self._is_action_drawer_open = False

    @property
    def my_character(self) -> PlayerCharacter:
        return self._game_state.player_characters[self.player_id]

    def _update_game_state(self, new_game_state: GameStateMessage) -> None:
        # TODO: Maybe this is incorrect behavior? Actions may be independent from game state updates.
        print("Updating Game State...")
        self._is_action_pending = False

        self._game_state = new_game_state
        # Update in place
        self._selectable_hexes.clear()
        self._selectable_hexes.update(self._game_state.game_map.keys())

    def _render_map(self) -> None:
        pr.begin_texture_mode(self._target)
        pr.begin_mode_2d(self._camera)
        pr.clear_background(pr.BLANK)
        for hex, land in self._game_state.game_map.items():
            draw_land(
                hex_coord_to_world_coord(hex, self._hex_size),
                size=self._hex_size,
                state=self._selection_controller.get_state_of_hex(hex),
                land=land,
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

    def _render_hud(self) -> None:
        root_layout = (
            LayoutBuilder()
            .snap(Placement(y=Placement.Snap.TOP, x=Placement.Snap.RIGHT))
            .set_placement_direction(Placement.Direction.VERTICAL)
        )
        header_rect = root_layout.place_rect(width="fill", height=50)
        header_layout = (
            LayoutBuilder(padding=10, margin=10)
            .snap(
                Placement(y=Placement.Snap.CENTER, x=Placement.Snap.LEFT),
                parent=header_rect,
            )
            .set_placement_direction(Placement.Direction.HORIZONTAL)
        )

        pr.draw_rectangle_rec(bbox2d_pad(header_rect, 1), pr.LIGHTGRAY)
        pr.draw_rectangle_lines_ex(header_rect, 1, pr.BLACK)

        self._selection_controller.mute_screen_rect(header_rect)
        self._camera_controller.mute_screen_rect(header_rect)

        with gui_set_text_size(20):
            gui_label(text=f"Turn: {self._game_state.turn}", layout=header_layout)
            gui_label(
                text=f"Faction: {self.my_character.faction.name}", layout=header_layout
            )

            for resource in Resource:
                gui_label(
                    text=f"{resource.name}: {self.my_character.resources[resource]}",
                    layout=header_layout,
                )

        if pr.is_key_pressed(pr.KeyboardKey.KEY_I):
            self._is_action_drawer_open = not self._is_action_drawer_open

        if self._is_action_drawer_open:
            action_drawer_rect = root_layout.place_rect(
                width=300,
                height=self.window_settings.screen_height - header_rect.height,
            )
            action_drawer_layout = (
                LayoutBuilder(padding=20, margin=20)
                .snap(
                    Placement(y=Placement.Snap.TOP, x=Placement.Snap.CENTER),
                    parent=action_drawer_rect,
                )
                .set_placement_direction(Placement.Direction.VERTICAL)
            )

            pr.draw_rectangle_rec(bbox2d_pad(action_drawer_rect, 1), pr.LIGHTGRAY)
            pr.draw_rectangle_lines_ex(action_drawer_rect, 1, pr.BLACK)

            self._selection_controller.mute_screen_rect(action_drawer_rect)
            self._camera_controller.mute_screen_rect(action_drawer_rect)

            with gui_set_text_size(30):
                gui_label(text="ACTIONS", layout=action_drawer_layout)

            with gui_set_text_size(20):
                action_learn_button_text = "Learn"
                action_learn_button = action_drawer_layout.place_rect(
                    width=150,
                    height=gui_measure_text_size(action_learn_button_text).y + 10,
                )
                if pr.gui_button(action_learn_button, action_learn_button_text):
                    self.client_networking.send_message(ActionLearnMessage())
                    self._is_action_pending = True

    @override
    def __call__(self) -> "ScreenProtocol":
        messages = self.client_networking.poll()
        for msg_type, payload in messages:
            if msg_type == MsgType.GAME_STATE:
                self._update_game_state(
                    new_game_state=self._game_state_message_codec.unpack(payload)
                )

        self._selection_controller.unmute()
        self._camera_controller.unmute()

        self._render_map()

        if self._is_action_pending:
            pr.gui_disable()
        else:
            pr.gui_enable()

        # Selected Hex tooltips
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

        self._render_hud()

        # Update UI Inputs
        self._selection_controller.update()
        self._camera_controller.update()

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
        self._muted_screen_rects: list[pr.Rectangle] = []

    def mute_screen_rect(self, rect: pr.Rectangle) -> None:
        self._muted_screen_rects.append(rect)

    def unmute(self) -> None:
        self._muted_screen_rects.clear()

    def _is_mouse_in_muted_area(self) -> bool:
        return any(
            pr.check_collision_point_rec(pr.get_mouse_position(), muted_rect)
            for muted_rect in self._muted_screen_rects
        )

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
        if not self.is_enabled or self._is_mouse_in_muted_area():
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
        self._zoom_speed = 50
        self._min_zoom = 0.33
        self._max_zoom = 3
        self._muted_screen_rects: list[pr.Rectangle] = []

    def mute_screen_rect(self, rect: pr.Rectangle) -> None:
        self._muted_screen_rects.append(rect)

    def unmute(self) -> None:
        self._muted_screen_rects.clear()

    def _is_mouse_in_muted_area(self) -> bool:
        return any(
            pr.check_collision_point_rec(pr.get_mouse_position(), muted_rect)
            for muted_rect in self._muted_screen_rects
        )

    def reset(self) -> None:
        self._camera.zoom = 1
        self._camera.rotation = 0
        self._camera.target = pr.vector2_zero()
        self._camera.offset = self._window_settings.screen_center

    def update(self) -> None:
        dt = pr.get_frame_time()

        if pr.is_key_pressed(pr.KeyboardKey.KEY_ZERO):
            self.reset()

        if not self._is_mouse_in_muted_area():
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
