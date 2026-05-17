import logging
import random
from collections.abc import Generator, Iterable
from decimal import Decimal

from common.game_state import Biome, Faction, Land, PlayerCharacter, Resource
from common.hex import Hex
from common.protocol import GameStateMessage, MsgType, TypedNetworkMessage


class MapBuilder:
    """TODO: Make this actually walk through the build actions of a map that players should take rather than generate"""

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

    def get_initial_map(self) -> dict[Hex, Land]:
        return self._generate_map()


def _generate_factions() -> Generator[Faction]:
    available_factions = list(Faction)
    while True:
        yield available_factions.pop(random.randrange(len(available_factions)))


class GameManager:
    def __init__(self) -> None:
        self._player_characters: dict[str, PlayerCharacter] = {}
        self._map: dict[Hex, Land] = {}

        # TODO: Implement player turns
        self.turn: int = -1

    def start(self, player_ids: Iterable[str]) -> None:
        if self.turn >= 0:
            logging.error("Can't start game again once already started...")
            return
        self._map = MapBuilder().get_initial_map()

        faction_gen = _generate_factions()
        for player_id in player_ids:
            self._player_characters[player_id] = PlayerCharacter(
                faction=next(faction_gen)
            )
        self.turn = 0

    def perform_action_learn(self, player_id: str) -> None:
        # TODO: Track history of actions for undo/redo
        self._player_characters[player_id].resources[Resource.Culture] += 1

    def as_game_state(self) -> GameStateMessage:
        if self.turn < 0:
            raise ValueError("Can't get state before game started.")
        return GameStateMessage(
            turn=self.turn,
            game_map=self._map,
            player_characters=self._player_characters,
        )
