"""TODO: Reorganize the modules a bit..."""

from enum import Enum, auto


class HexState(Enum):
    """Visual state of a Hex.

    NOTES:
      * The states are ordered hierarchically on purpose.
      * If a Hex is hovered while selected, we basically just want to draw it selected.

    """

    DISABLED = auto()
    UNSELECTED = auto()
    HOVERED = auto()
    SELECTED = auto()
