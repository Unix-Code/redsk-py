from dataclasses import dataclass, field
from enum import Enum, auto
from typing import NamedTuple


class Resource(Enum):
    Food = auto()
    Ore = auto()
    Wood = auto()
    Gold = auto()
    Culture = auto()


class Biome(Enum):
    """Purely used for Map Generation"""

    Grassland = auto()
    Mountains = auto()
    Forest = auto()
    Jungle = auto()
    Desert = auto()
    Plains = auto()
    Hills = auto()


@dataclass(frozen=True)
class Land:
    biome: Biome
    resources: dict[Resource, int]

    def __post_init__(self) -> None:
        for resource in Resource:
            if resource not in self.resources:
                self.resources[resource] = 0


class Alignment(Enum):
    Water = auto()
    Fire = auto()
    Earth = auto()
    Air = auto()
    Aether = auto()
    Void = auto()


class Faction(Enum):
    Wakewalkers = auto()
    Archivists = auto()
    Featherfolk = auto()
    Sporespawn = auto()
    Nightriders = auto()
    Humans = auto()


class FactionStart(NamedTuple):
    starting_resources: dict[Resource, int]
    starting_alignment: Alignment


AVAILABLE_FACTIONS = {
    Faction.Wakewalkers: FactionStart(
        starting_resources={Resource.Food: 1, Resource.Culture: 1, Resource.Gold: 1},
        starting_alignment=Alignment.Fire,
    ),
    Faction.Archivists: FactionStart(
        starting_resources={Resource.Food: 1, Resource.Culture: 2},
        starting_alignment=Alignment.Water,
    ),
    Faction.Featherfolk: FactionStart(
        starting_resources={Resource.Food: 1, Resource.Culture: 1, Resource.Wood: 2},
        starting_alignment=Alignment.Air,
    ),
    Faction.Sporespawn: FactionStart(
        starting_resources={Resource.Food: 1, Resource.Ore: 2, Resource.Wood: 1},
        starting_alignment=Alignment.Earth,
    ),
    Faction.Nightriders: FactionStart(
        starting_resources={Resource.Food: 1, Resource.Culture: 1, Resource.Gold: 1},
        starting_alignment=Alignment.Void,
    ),
    Faction.Humans: FactionStart(
        starting_resources={Resource.Food: 2, Resource.Ore: 1, Resource.Wood: 1},
        starting_alignment=Alignment.Aether,
    ),
}


@dataclass
class PlayerCharacter:
    faction: Faction
    resources: dict[Resource, int] = field(default_factory=dict)
    alignments: dict[Alignment, int] = field(default_factory=dict)

    def __post_init__(self) -> None:
        for resource in Resource:
            if resource not in self.resources:
                self.resources[resource] = 0
            self.resources[resource] += AVAILABLE_FACTIONS[
                self.faction
            ].starting_resources.get(resource, 0)
        for alignment in Alignment:
            if alignment not in self.alignments:
                self.alignments[alignment] = 0
            if alignment == AVAILABLE_FACTIONS[self.faction].starting_alignment:
                self.alignments[alignment] += 1
