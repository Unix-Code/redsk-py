from typing import override

import pyray as pr
from common.networking import ClientNetworking, ConnectionState
from common.protocol import (
    GreetingsMessageCodec,
    MsgType,
    RegistrationMessage,
    StartGameMessage,
)

from client.gui import (
    GuiTextInputBox,
    LayoutBuilder,
    Placement,
    ScreenProtocol,
    WindowSettings,
    gui_set_text_size,
)
from client.screens import GameScreen
from client.utils import StrPointer


class ConnectScreen(ScreenProtocol):
    def __init__(self, window_settings: WindowSettings) -> None:
        self.window_settings = window_settings
        self.hostname = StrPointer(capacity=64, initial_value="localhost")
        self.hostname_text_box = GuiTextInputBox()
        self.port = StrPointer(capacity=16, initial_value="65434")
        self.port_text_box = GuiTextInputBox()
        self.client_networking: ClientNetworking = ClientNetworking()

    @override
    def __call__(self) -> ScreenProtocol:
        main_layout = LayoutBuilder(padding=50 * self.window_settings.scale).snap(
            Placement(y=Placement.Snap.CENTER, x=Placement.Snap.CENTER)
        )
        main_panel = main_layout.place_rect(
            width=self.window_settings.screen_width / 2,
            height=self.window_settings.screen_height / 2,
        )
        with gui_set_text_size(20):
            pr.gui_panel(main_panel, "Connect")

        if self.client_networking.connection_state == ConnectionState.IN_PROGRESS:
            pr.gui_disable()
        else:
            pr.gui_enable()
            if self.client_networking.connection_state == ConnectionState.FAILED:
                self.client_networking.reset()
            elif self.client_networking.connection_state == ConnectionState.CONNECTED:
                return RegistrationScreen(
                    window_settings=self.window_settings,
                    client_networking=self.client_networking,
                )

        self.client_networking.poll()

        connect_inputs = (
            LayoutBuilder(
                padding=50 * self.window_settings.scale,
                margin=10 * self.window_settings.scale,
            )
            .snap(
                Placement(y=Placement.Snap.TOP, x=Placement.Snap.CENTER),
                parent=main_panel,
            )
            .set_placement_direction(Placement.Direction.VERTICAL)
        )

        with gui_set_text_size(20):
            pr.gui_label(
                connect_inputs.place_rect(
                    width=pr.measure_text(
                        "Host Name",
                        20,
                    ),
                    height=24 * self.window_settings.scale,
                ),
                "Host Name",
            )
        self.hostname_text_box(
            bounds=connect_inputs.place_rect(
                width=200 * self.window_settings.scale,
                height=30 * self.window_settings.scale,
            ),
            text_input=self.hostname,
        )

        with gui_set_text_size(20):
            pr.gui_label(
                connect_inputs.place_rect(
                    width=pr.measure_text(
                        "Port",
                        20,
                    ),
                    height=24 * self.window_settings.scale,
                ),
                "Port",
            )
        self.port_text_box(
            bounds=connect_inputs.place_rect(
                width=200 * self.window_settings.scale,
                height=30 * self.window_settings.scale,
            ),
            text_input=self.port,
        )

        with gui_set_text_size(20):
            if pr.gui_button(
                connect_inputs.place_rect(
                    width=pr.measure_text("Connect", 20) + 10,
                    height=24 * self.window_settings.scale,
                ),
                "Connect",
            ):
                self.client_networking.connect(
                    host=self.hostname.value, port=int(self.port.value)
                )

        return self


class RegistrationScreen(ScreenProtocol):
    def __init__(
        self, window_settings: WindowSettings, client_networking: ClientNetworking
    ) -> None:
        self.window_settings = window_settings
        self.client_networking = client_networking
        self.player_name = StrPointer(capacity=64, initial_value="")
        self.player_name_text_box = GuiTextInputBox()
        self.is_registering = False
        self._greetings_msg_codec = GreetingsMessageCodec()

    @override
    def __call__(self) -> ScreenProtocol:
        messages = self.client_networking.poll()
        for msg_type, payload in messages:
            if self.is_registering and msg_type == MsgType.GREETINGS:
                msg = self._greetings_msg_codec.unpack(payload)
                return LobbyScreen(
                    window_settings=self.window_settings,
                    client_networking=self.client_networking,
                    player_id=msg.player_id,
                    registered_player_name=msg.player_name,
                )

        main_layout = LayoutBuilder(padding=50 * self.window_settings.scale).snap(
            Placement(y=Placement.Snap.CENTER, x=Placement.Snap.CENTER)
        )
        main_panel = main_layout.place_rect(
            width=self.window_settings.screen_width / 2,
            height=self.window_settings.screen_height / 2,
        )
        with gui_set_text_size(20):
            pr.gui_panel(main_panel, "Registration")

        registration_inputs = (
            LayoutBuilder(
                padding=50 * self.window_settings.scale,
                margin=10 * self.window_settings.scale,
            )
            .snap(
                Placement(y=Placement.Snap.TOP, x=Placement.Snap.CENTER),
                parent=main_panel,
            )
            .set_placement_direction(Placement.Direction.VERTICAL)
        )

        self.player_name_text_box(
            bounds=registration_inputs.place_rect(
                width=200 * self.window_settings.scale,
                height=30 * self.window_settings.scale,
            ),
            text_input=self.player_name,
        )

        with gui_set_text_size(20):
            if not self.player_name.value or self.is_registering:
                pr.gui_disable()
            if pr.gui_button(
                registration_inputs.place_rect(
                    width=pr.measure_text("Register", 20) + 10,
                    height=24 * self.window_settings.scale,
                ),
                "Register",
            ):
                self.client_networking.send_message(
                    RegistrationMessage(self.player_name.value)
                )
                self.is_registering = True
            pr.gui_enable()
        return self


class LobbyScreen(ScreenProtocol):
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
        self.is_game_starting: bool = False

    @override
    def __call__(self) -> ScreenProtocol:
        messages = self.client_networking.poll()
        for msg_type, payload in messages:
            if self.is_game_starting and msg_type == MsgType.GAME_STATE:
                return GameScreen(
                    window_settings=self.window_settings,
                    client_networking=self.client_networking,
                    player_id=self.player_id,
                    registered_player_name=self.registered_player_name,
                )

        # TODO: We should probably poll for network messages like disconnects, etc...

        main_layout = LayoutBuilder(padding=50 * self.window_settings.scale).snap(
            Placement(y=Placement.Snap.CENTER, x=Placement.Snap.CENTER)
        )
        main_panel = main_layout.place_rect(
            width=self.window_settings.screen_width / 2,
            height=self.window_settings.screen_height / 2,
        )
        with gui_set_text_size(20):
            pr.gui_panel(main_panel, "Lobby")

        lobby_inputs = (
            LayoutBuilder(
                padding=50 * self.window_settings.scale,
                margin=10 * self.window_settings.scale,
            )
            .snap(
                Placement(y=Placement.Snap.CENTER, x=Placement.Snap.CENTER),
                parent=main_panel,
            )
            .set_placement_direction(Placement.Direction.VERTICAL)
        )

        with gui_set_text_size(20):
            if self.is_game_starting:
                pr.gui_disable()
            if pr.gui_button(
                lobby_inputs.place_rect(
                    width=pr.measure_text("Start Game", 20) + 10,
                    height=24 * self.window_settings.scale,
                ),
                "Start Game",
            ):
                self.client_networking.send_message(StartGameMessage())
                self.is_game_starting = True
            pr.gui_enable()

        return self
