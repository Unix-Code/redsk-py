import logging
import sys
import time

from common.networking import ServerNetworking
from common.protocol import (
    GreetingsMessage,
    MsgType,
    RegistrationMessageCodec,
)

from server.game import GameManager

logging.basicConfig(level=logging.INFO)

TICK_RATE = 10
TICK_INTERVAL = 1.0 / TICK_RATE

if __name__ == "__main__":
    if len(sys.argv) == 2:
        port = int(sys.argv[1])
        server = ServerNetworking(port=port)
    else:
        server = ServerNetworking()
    player_names: dict[str, str] = {}
    last_tick = time.time()

    game_manager = GameManager()

    try:
        while True:
            # Calculate how much time is left until the next tick
            time_to_next_tick = max(0, (last_tick + TICK_INTERVAL) - time.time())
            for client_id, msg_payloads in server.poll(
                timeout=time_to_next_tick
            ).items():
                logging.info(
                    "Got %s messages from Client(%s)", len(msg_payloads), client_id
                )
                for msg_type, payload_bytes in msg_payloads:
                    if msg_type == MsgType.REGISTRATION:
                        if client_id in player_names:
                            logging.error(
                                "Client(%s) already registered as: %s!",
                                client_id,
                                player_names[client_id],
                            )
                            continue
                        player_names[client_id] = (
                            RegistrationMessageCodec().unpack(payload_bytes).name
                        )
                        logging.info(
                            "Client(%s) registered as: %s",
                            client_id,
                            player_names[client_id],
                        )
                        server.send_message(
                            client_id,
                            GreetingsMessage(
                                player_id=client_id, player_name=player_names[client_id]
                            ),
                        )
                    elif msg_type == MsgType.START_GAME:
                        # TODO: Do some role management / checks here?
                        game_manager.start()
                        server.send_message(client_id, game_manager.as_game_state())
                    else:
                        logging.error(
                            "Encountered unexpected message type: %s from Client(%s)",
                            msg_type,
                            client_id,
                        )
            last_tick = time.time()
    except (KeyboardInterrupt, SystemExit):
        server.close()
        raise
