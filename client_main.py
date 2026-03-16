import logging
from enum import Enum, auto

import pyray as pr

from client.gui import GuiTextInputBox, LayoutBuilder, Placement, gui_set_text_size
from client.utils import StrPointer
from common.networking import ClientNetworking, ConnectionState, MessagePayloads
from common.protocol import GreetingsMessage, MsgType, RegistrationMessage

logging.basicConfig(level=logging.INFO)


class Screen(Enum):
    CONNECT = auto()
    REGISTRATION = auto()
    LOBBY = auto()


def main():
    SCREEN_WIDTH = 800
    DEFAULT_SCREEN_HEIGHT = 600
    SCREEN_HEIGHT = 600
    SCALE = SCREEN_HEIGHT / DEFAULT_SCREEN_HEIGHT

    pr.init_window(SCREEN_WIDTH, SCREEN_HEIGHT, "Redsky")

    current_screen = Screen.CONNECT

    hostname = StrPointer(capacity=64, initial_value="localhost")
    hostname_text_box = GuiTextInputBox()
    port = StrPointer(capacity=16, initial_value="65432")
    port_text_box = GuiTextInputBox()

    player_name = StrPointer(capacity=64, initial_value="")
    player_name_text_box = GuiTextInputBox()
    is_registering = False

    client_networking: ClientNetworking = ClientNetworking()
    message_buffer: MessagePayloads = []
    player_id: str | None = None
    registered_player_name: str | None = None

    while not pr.window_should_close():
        pr.begin_drawing()
        pr.gui_load_style_default()

        if current_screen == Screen.CONNECT:
            main_layout = LayoutBuilder(padding=50 * SCALE).snap(
                Placement(y=Placement.Snap.CENTER, x=Placement.Snap.CENTER)
            )
            main_panel = main_layout.place_rect(
                width=SCREEN_WIDTH / 2, height=SCREEN_HEIGHT / 2
            )
            with gui_set_text_size(20):
                pr.gui_panel(main_panel, "Connect")

            if client_networking.connection_state == ConnectionState.IN_PROGRESS:
                pr.gui_disable()
            else:
                pr.gui_enable()
                if client_networking.connection_state == ConnectionState.CONNECTED:
                    current_screen = Screen.REGISTRATION
                    continue

            client_networking.poll()

            connect_inputs = (
                LayoutBuilder(padding=50 * SCALE, margin=10 * SCALE)
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
                        height=24 * SCALE,
                    ),
                    "Host Name",
                )
            hostname_text_box(
                bounds=connect_inputs.place_rect(width=200 * SCALE, height=30 * SCALE),
                text_input=hostname,
            )

            with gui_set_text_size(20):
                pr.gui_label(
                    connect_inputs.place_rect(
                        width=pr.measure_text(
                            "Port",
                            20,
                        ),
                        height=24 * SCALE,
                    ),
                    "Port",
                )
            port_text_box(
                bounds=connect_inputs.place_rect(width=200 * SCALE, height=30 * SCALE),
                text_input=port,
            )

            with gui_set_text_size(20):
                if pr.gui_button(
                    connect_inputs.place_rect(
                        width=pr.measure_text("Connect", 20) + 10, height=24 * SCALE
                    ),
                    "Connect",
                ):
                    client_networking.connect(host=hostname.value, port=int(port.value))
        elif current_screen == Screen.REGISTRATION:
            messages = client_networking.poll()
            for msg_type, payload in messages:
                if is_registering and msg_type == MsgType.GREETINGS:
                    msg = GreetingsMessage.unpack(payload)
                    player_id = msg.player_id
                    registered_player_name = msg.player_name
                    is_registering = False
                    current_screen = Screen.LOBBY
                else:
                    messages.append((msg_type, payload))

            if current_screen != Screen.REGISTRATION:
                continue

            main_layout = LayoutBuilder(padding=50 * SCALE).snap(
                Placement(y=Placement.Snap.CENTER, x=Placement.Snap.CENTER)
            )
            main_panel = main_layout.place_rect(
                width=SCREEN_WIDTH / 2, height=SCREEN_HEIGHT / 2
            )
            with gui_set_text_size(20):
                pr.gui_panel(main_panel, "Registration")

                registration_inputs = (
                    LayoutBuilder(padding=50 * SCALE, margin=10 * SCALE)
                    .snap(
                        Placement(y=Placement.Snap.TOP, x=Placement.Snap.CENTER),
                        parent=main_panel,
                    )
                    .set_placement_direction(Placement.Direction.VERTICAL)
                )

            player_name_text_box(
                bounds=registration_inputs.place_rect(
                    width=200 * SCALE, height=30 * SCALE
                ),
                text_input=player_name,
            )

            with gui_set_text_size(20):
                if not player_name.value or is_registering:
                    pr.gui_disable()
                if pr.gui_button(
                    registration_inputs.place_rect(
                        width=pr.measure_text("Register", 20) + 10, height=24 * SCALE
                    ),
                    "Register",
                ):
                    print("Send Registration")
                    client_networking.send_message(
                        RegistrationMessage(player_name.value)
                    )
                    is_registering = True
                pr.gui_enable()
        elif current_screen == Screen.LOBBY:
            assert registered_player_name is not None
            assert player_id is not None
            print(f"Hi, {registered_player_name}. Your ID: {player_id}")

        pr.clear_background(pr.LIGHTGRAY)

        pr.end_drawing()


if __name__ == "__main__":
    main()
    # port = int(sys.argv[1])
    # is_registered = False
    # is_registering = False
    #
    # client = ClientNetworking(port=port)
    # try:
    #     while True:
    #         if not is_registered and not is_registering:
    #             logging.info("Registering...")
    #             client.send_message(RegistrationMessage("Bob"))
    #             is_registering = True
    #
    #         for msg_type, payload_bytes in client.poll():
    #             if msg_type == MsgType.GREETINGS:
    #                 greetings = GreetingsMessage.unpack(payload_bytes)
    #                 logging.info(
    #                     "GREETED BY SERVER: Player(name=%s, id=%s) !",
    #                     greetings.player_name,
    #                     greetings.player_id,
    #                 )
    #                 is_registering = False
    #                 is_registered = True
    #             else:
    #                 logging.error("Encountered unexpected msg_type: %s", msg_type)
    # except (KeyboardInterrupt, SystemExit):
    #     client.close()
    #     raise
