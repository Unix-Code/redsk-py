import logging
from collections.abc import Generator
from contextlib import contextmanager
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Literal, Self, Union

import pyray as pr

from client.utils import StrPointer, bbox2d_contains_rect, bbox2d_pad

logger = logging.getLogger(__name__)


class GuiTextInputBox:
    def __init__(self) -> None:
        self._is_editing: bool = False

    def __call__(
        self,
        bounds: pr.Rectangle,
        text_input: StrPointer,
    ) -> str | None:
        if pr.is_mouse_button_pressed(
            pr.MouseButton.MOUSE_BUTTON_LEFT
        ) and pr.check_collision_point_rec(pr.get_mouse_position(), bounds):
            self._is_editing = True

        if pr.gui_text_box(
            bounds, text_input.ptr, text_input.capacity, self._is_editing
        ):
            self._is_editing = False
            return text_input.value
        return None


@dataclass(frozen=True)
class Placement:
    class Snap(Enum):
        TOP = auto()
        BOTTOM = auto()
        LEFT = auto()
        RIGHT = auto()
        CENTER = auto()

    y: Literal[Snap.TOP, Snap.CENTER, Snap.BOTTOM]
    x: Literal[Snap.LEFT, Snap.CENTER, Snap.RIGHT]

    class Direction(Enum):
        VERTICAL = auto()
        HORIZONTAL = auto()


@dataclass
class Anchor:
    coords: pr.Vector2 = field(default_factory=pr.vector2_zero)
    snap_position: Placement = field(
        default_factory=lambda: Placement(y=Placement.Snap.TOP, x=Placement.Snap.LEFT)
    )


@dataclass
class FlowLayoutConfig:
    # NOTE: Primary axis of placement. Whether to begin placing vertically or horizontally.
    flow_direction: Placement.Direction
    # NOTE: Absolute (regardless of flow_direction) flags for:
    #   Whether vertical placement is top-to-bottom (False) or bottom-top (True)
    reversed_horizontal: bool = False
    # NOTE:
    #   Whether horizontal placement is left-to-right (False) or right-to-left (True)
    reversed_vertical: bool = False
    # NOTE: Spacing from parent container & anchor to begin & end placing in a given direction
    padding: float = 0
    # NOTE: Spacing between children containers to maintain
    margin: float = 0
    # NOTE: Whether to wrap

    @property
    def wrap_direction(self) -> Placement.Direction:
        """Secondary axis of placement. When there's no more space in the primary axis, we advance in this direction."""
        return (
            Placement.Direction.VERTICAL
            if self.flow_direction == Placement.Direction.HORIZONTAL
            else Placement.Direction.HORIZONTAL
        )


class FlowLayout:
    def __init__(
        self,
        config: FlowLayoutConfig,
        parent_container: pr.Rectangle,
        anchor: Anchor,
    ) -> None:
        self._config = config
        self._parent: pr.Rectangle = parent_container
        self._placement_container: pr.Rectangle = bbox2d_pad(
            self._parent, padding=self._config.padding
        )
        # FIXME: DEBUG
        # pr.draw_rectangle_lines_ex(self._parent, 3, pr.BLUE)
        # pr.draw_rectangle_lines_ex(self._placement_container, 3, pr.RED)
        self._anchor: Anchor = anchor
        self._cursor: pr.Vector2 = pr.Vector2(anchor.coords.x, anchor.coords.y)
        self._initial_placement: bool = True

    def place_rect(self, width: float, height: float) -> pr.Rectangle:
        # NOTE: Here we want to position the new rect placement point (always top-left) so that the
        #       snap position of the anchor aligns with the snap position of the new Rectangle.
        if self._anchor.snap_position.y == Placement.Snap.TOP:
            delta_y = 0
        elif self._anchor.snap_position.y == Placement.Snap.CENTER:
            delta_y = -height / 2
        elif self._anchor.snap_position.y == Placement.Snap.BOTTOM:
            delta_y = -height
        else:
            raise RuntimeError("Unreachable")

        if self._anchor.snap_position.x == Placement.Snap.LEFT:
            delta_x = 0
        elif self._anchor.snap_position.x == Placement.Snap.CENTER:
            delta_x = -width / 2
        elif self._anchor.snap_position.x == Placement.Snap.RIGHT:
            delta_x = -width
        else:
            raise RuntimeError("Unreachable")

        new_rect = pr.Rectangle(
            self._cursor.x + delta_x, self._cursor.y + delta_y, width, height
        )

        # TODO: Figure out wrapping...
        if not bbox2d_contains_rect(self._placement_container, new_rect):
            logger.warning(
                "Ran out of space to place %s inside parent container: %s",
                (new_rect.x, new_rect.y, new_rect.width, new_rect.height),
                (
                    self._placement_container.x,
                    self._placement_container.y,
                    self._placement_container.width,
                    self._placement_container.height,
                ),
            )

        if (
            self._anchor.snap_position.x == Placement.Snap.CENTER
            and self._anchor.snap_position.y == Placement.Snap.CENTER
        ):
            if not self._initial_placement:
                logger.warning("No where to place centered subsequent Rectangle")
        # NOTE: Now that we've placed a Rectangle, we need to shift our cursor to the next position,
        #       taking into account flow_direction and margin and reversed placement
        elif self._config.flow_direction == Placement.Direction.HORIZONTAL:
            shift = width + self._config.margin
            if self._config.reversed_horizontal:
                shift *= -1
            self._cursor = pr.Vector2(self._cursor.x + shift, self._cursor.y)
        elif self._config.flow_direction == Placement.Direction.VERTICAL:
            shift = height + self._config.margin
            if self._config.reversed_vertical:
                shift *= -1
            self._cursor = pr.Vector2(self._cursor.x, self._cursor.y + shift)

        self._initial_placement = False

        return new_rect


class LayoutBuilder:
    def __init__(self, padding: float = 0, margin: float = 0) -> None:
        """Initialize LayoutBuilder with a strategy"""
        self._padding = padding
        self._margin = margin
        self._reset()

    def _reset(self) -> None:
        self._flow_direction: Placement.Direction = Placement.Direction.HORIZONTAL
        self._anchor: Anchor = Anchor()
        # Use Screen as parent by default
        self._parent: pr.Rectangle = pr.Rectangle(
            0, 0, pr.get_screen_width(), pr.get_screen_height()
        )
        self._layout_strategy: FlowLayout | None = None

    def move(self, x: float = 0, y: float = 0) -> Self:
        self._reset()
        self._anchor = Anchor(
            pr.Vector2(x, y),
            snap_position=Placement(y=Placement.Snap.TOP, x=Placement.Snap.LEFT),
        )

        return self

    def snap(
        self, snap_position: Placement, parent: Union[pr.Rectangle, None] = None
    ) -> Self:
        if parent is None:
            # Use Screen as parent
            parent = pr.Rectangle(0, 0, pr.get_screen_width(), pr.get_screen_height())

        new_anchor = Anchor(
            coords=pr.Vector2(parent.x, parent.y), snap_position=snap_position
        )

        delta_x: float = 0
        delta_y: float = 0
        if new_anchor.snap_position.y == Placement.Snap.TOP:
            delta_y += self._padding
        elif new_anchor.snap_position.y == Placement.Snap.CENTER:
            delta_y = parent.height / 2
        elif new_anchor.snap_position.y == Placement.Snap.BOTTOM:
            delta_y += parent.height
            delta_y -= self._padding

        if new_anchor.snap_position.x == Placement.Snap.LEFT:
            delta_x += self._padding
        elif new_anchor.snap_position.x == Placement.Snap.CENTER:
            delta_x = parent.width / 2
        elif new_anchor.snap_position.x == Placement.Snap.RIGHT:
            delta_x += parent.width
            delta_x -= self._padding

        new_anchor.coords = pr.vector2_add(
            new_anchor.coords, pr.Vector2(delta_x, delta_y)
        )

        self._reset()
        self._anchor = new_anchor
        self._parent = parent
        return self

    def set_placement_direction(
        self, direction: Placement.Direction = Placement.Direction.HORIZONTAL
    ) -> Self:
        if self._layout_strategy is not None:
            self._reset()
        self._flow_direction = direction
        return self

    def place_rect(self, width: float, height: float) -> pr.Rectangle:
        if self._layout_strategy is None:
            # TODO: Support other layout types...
            self._layout_strategy = FlowLayout(
                config=FlowLayoutConfig(
                    flow_direction=self._flow_direction,
                    reversed_horizontal=(
                        self._anchor.snap_position.x == Placement.Snap.RIGHT
                    ),
                    reversed_vertical=(
                        self._anchor.snap_position.y == Placement.Snap.BOTTOM
                    ),
                    padding=self._padding,
                    margin=self._margin,
                ),
                parent_container=self._parent,
                anchor=self._anchor,
            )
        return self._layout_strategy.place_rect(width=width, height=height)


@contextmanager
def gui_set_text_size(size: int) -> Generator[None]:
    pr.gui_set_style(pr.GuiControl.DEFAULT, pr.GuiDefaultProperty.TEXT_SIZE, size)
    yield
    pr.gui_load_style_default()
