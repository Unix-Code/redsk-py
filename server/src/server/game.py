import logging
import random
from decimal import Decimal

from common.game_state import Biome, Land, Resource
from common.hex import Hex
from common.protocol import GameStateMessage


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


class GameManager:
    def __init__(self) -> None:
        self._map: dict[Hex, Land] = {}

        # TODO: Implement player turns
        self.turn: int = -1

    def start(self) -> None:
        if self.turn >= 0:
            logging.error("Can't start game again once already started...")
            return
        self._map = MapBuilder().get_initial_map()
        self.turn = 0

    def as_game_state(self) -> GameStateMessage:
        if self.turn < 0:
            raise ValueError("Can't get state before game started.")
        return GameStateMessage(turn=self.turn, game_map=self._map)
