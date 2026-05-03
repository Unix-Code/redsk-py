from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal
from typing import Generic, TypeAlias, TypeVar, cast, override

T = TypeVar("T", int, float)


def _proper_round(value: float | Decimal, decimals: int = 0) -> Decimal:
    d = Decimal(str(value))
    precision = Decimal("1") if decimals == 0 else Decimal("10") ** -decimals
    return d.quantize(precision, rounding=ROUND_HALF_UP)


def _proper_round_to_int(value: float | Decimal) -> int:
    return int(_proper_round(value, decimals=0))


@dataclass(frozen=True, slots=True)
class HexCoord(Generic[T]):
    """Hex Coordinate

    Notes:
      * q + r + s = 0
    """

    q: T
    r: T

    @classmethod
    def origin(cls) -> "HexCoord[T]":
        return HexCoord[T](q=cast(T, 0), r=cast(T, 0))

    @property
    def s(self) -> T:
        return -self.q - self.r

    @override
    def __hash__(self) -> int:
        return hash((self.q, self.r))

    def __sub__(self, other: "HexCoord[T]") -> "HexCoord[T]":
        return HexCoord[T](q=self.q - other.q, r=self.r - other.r)

    def scale(self, scale: T) -> "HexCoord[T]":
        return HexCoord[T](q=self.q * scale, r=self.r * scale)

    def __add__(self, other: "HexCoord[T]") -> "HexCoord[T]":
        return HexCoord[T](q=self.q + other.q, r=self.r + other.r)

    def dist(self, other: "HexCoord[T]") -> T:
        diff = self - other
        return cast(T, abs(diff.q) + abs(diff.r) + abs(diff.s))

    def neighbors(self: "Hex") -> list["Hex"]:
        return self.ring(radius=1)

    def ring(self: "Hex", radius: int) -> list["Hex"]:
        if radius < 0:
            return []
        elif radius == 0:
            return [self]

        hexes: list[Hex] = []
        # We just pick a random start on the ring to start walking
        pos: Hex = self + HexCoord(+1, 0).scale(radius - 1)
        for dir_hex in (
            HexCoord(-1, +1),
            HexCoord(-1, 0),
            HexCoord(0, -1),
            HexCoord(+1, -1),
            HexCoord(+1, 0),
            HexCoord(0, +1),
        ):
            for r in range(radius):
                if r == 0:
                    continue
                pos += dir_hex
                hexes.append(pos)
        return hexes

    def round(self: "HexCoord[float]") -> "HexCoord[int]":
        q = _proper_round_to_int(self.q)
        r = _proper_round_to_int(self.r)
        s = _proper_round_to_int(self.s)

        q_diff = abs(self.q - q)
        r_diff = abs(self.r - r)
        s_diff = abs(self.s - s)

        if q_diff > r_diff and q_diff > s_diff:
            q = -r - s
        elif r_diff > s_diff:
            r = -q - s

        return HexCoord[int](q=q, r=r)


Hex: TypeAlias = HexCoord[int]
