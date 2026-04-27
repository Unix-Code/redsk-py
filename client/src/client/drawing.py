"""We use pointy-top hexagons for the game."""

import math

import pyray as pr
from common.hex import Hex, HexCoord


def draw_hexagon(center: pr.Vector2, size: float, color: pr.Color) -> None:
    pr.draw_poly_lines(center, 6, size, 30, color)


def hex_coord_to_screen_cord(hex_coord: Hex, size: float) -> pr.Vector2:
    # Formula:
    # q_basis * hex_coord.q + r_basis * hex_coord.r = screen_coord
    q_basis = pr.Vector2(math.sqrt(3), 0)
    r_basis = pr.Vector2(math.sqrt(3) / 2, 3 / 2)

    return pr.vector2_scale(
        pr.Vector2(
            q_basis.x * hex_coord.q + r_basis.x * hex_coord.r,
            q_basis.y * hex_coord.q + r_basis.y * hex_coord.r,
        ),
        size,
    )


def screen_coord_to_hex_coord(screen_coord: pr.Vector2, size: float) -> Hex:
    scaled_screen_coord = pr.vector2_scale(
        screen_coord,
        1 / size,
    )
    # Formula (inverted hex->pixel matrix * screen_coord)
    return HexCoord(
        q=math.sqrt(3) / 3 * scaled_screen_coord.x - 1 / 3 * scaled_screen_coord.y,
        r=0 * scaled_screen_coord.x + 2 / 3 * scaled_screen_coord.y,
    ).round()
