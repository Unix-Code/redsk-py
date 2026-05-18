import logging
from collections.abc import Generator
from contextlib import contextmanager
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import ClassVar, Literal, Protocol, Self, Union

import pyray as pr

from client.utils import (
    StrPointer,
    bbox2d_contains_rect,
    bbox2d_encompassing,
    bbox2d_pad,
)

logger = logging.getLogger(__name__)


@dataclass
class WindowSettings:
    DEFAULT_SCREEN_HEIGHT: ClassVar[int] = 600

    screen_width: int = 800
    screen_height: int = 600

    @property
    def scale(self) -> float:
        return self.screen_height / self.DEFAULT_SCREEN_HEIGHT

    @property
    def screen_center(self) -> pr.Vector2:
        return pr.Vector2(
            self.screen_width / 2,
            self.screen_height / 2,
        )


class ScreenProtocol(Protocol):
    def __call__(self) -> "ScreenProtocol": ...


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
        self._bounding_box: pr.Rectangle = pr.Rectangle(
            self._placement_container.x, self._placement_container.y, 0, 0
        )

    @property
    def bounding_box(self) -> pr.Rectangle:
        """Returns the rectangle encompassing all placed elements."""
        return self._bounding_box

    def shift_cursor(self, width: float, height: float) -> None:
        """Given child width+height, shift the cursor ahead of the next placement,

        Note:
            Takes into account flow_direction and margin and reversed placement
        """
        if (
            self._anchor.snap_position.x == Placement.Snap.CENTER
            and self._anchor.snap_position.y == Placement.Snap.CENTER
        ):
            if not self._initial_placement:
                logger.warning("No where to place centered subsequent Rectangle")
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

    def place_rect(
        self,
        width: float | Literal["fill"],
        height: float | Literal["fill"],
        virtual: bool = False,
    ) -> pr.Rectangle:
        if width == "fill":
            width = self._placement_container.width

        if height == "fill":
            height = self._placement_container.height

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

        #   When it's a virtual placement (reservation), we don't actually change any state in
        #   our layout.
        if not virtual:
            self.shift_cursor(width, height)
            self._initial_placement = False
            self.include_rect(new_rect)

        return new_rect

    def include_rect(self, rect: pr.Rectangle) -> None:
        self._bounding_box = bbox2d_encompassing(self._bounding_box, rect)


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

    def _init_layout_strategy(self) -> None:
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

    def place_rect(
        self,
        width: float | Literal["fill"],
        height: float | Literal["fill"],
    ) -> pr.Rectangle:
        if self._layout_strategy is None:
            # TODO: Support other layout types...
            self._init_layout_strategy()
            assert self._layout_strategy is not None
        return self._layout_strategy.place_rect(width=width, height=height)

    def place_text(
        self, text: str, padding_x: float = 0, padding_y: float = 0
    ) -> pr.Rectangle:
        text_size = gui_measure_text_size(text)
        return self.place_rect(
            width=text_size.x + padding_x, height=text_size.y + padding_y
        )

    def place_virtual_rect(
        self,
        width: float | Literal["fill"],
        height: float | Literal["fill"],
    ) -> pr.Rectangle:
        if self._layout_strategy is None:
            # TODO: Support other layout types...
            self._init_layout_strategy()
            assert self._layout_strategy is not None
        return self._layout_strategy.place_rect(
            width=width, height=height, virtual=True
        )

    @property
    def bounding_box(self) -> pr.Rectangle:
        """Returns the rectangle encompassing all placed elements."""
        return (
            self._layout_strategy.bounding_box
            if self._layout_strategy is not None
            else pr.Rectangle(self._anchor.coords.x, self._anchor.coords.y, 0, 0)
        )

    def include_rect(self, rect: pr.Rectangle) -> None:
        if self._layout_strategy is None:
            # TODO: Support other layout types...
            self._init_layout_strategy()
            assert self._layout_strategy is not None
        self._layout_strategy.include_rect(rect)

    @property
    def reserved_box(self) -> pr.Rectangle:
        """Returns the rectangle encompassing the reserved rectangle for this layout."""
        return self._parent


@contextmanager
def gui_set_text_size(size: int) -> Generator[None]:
    pr.gui_set_style(pr.GuiControl.DEFAULT, pr.GuiDefaultProperty.TEXT_SIZE, size)
    yield
    pr.gui_load_style_default()


def gui_measure_text_size(text: str, spacing: float = 1) -> pr.Vector2:
    size = pr.gui_get_style(pr.GuiControl.DEFAULT, pr.GuiDefaultProperty.TEXT_SIZE)
    return pr.measure_text_ex(pr.gui_get_font(), text, size, spacing)


def gui_label(text: str, layout: LayoutBuilder) -> None:
    text_rect = layout.place_text(text, padding_x=3)
    pr.gui_label(text_rect, text)
