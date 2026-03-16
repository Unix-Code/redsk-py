from typing import Any, Protocol

import pyray as pr


def bbox2d_pad(rect: pr.Rectangle, padding: float) -> pr.Rectangle:
    return pr.Rectangle(
        rect.x + padding,
        rect.y + padding,
        rect.width - (padding * 2),
        rect.height - (padding * 2),
    )


def bbox2d_contains_rect(rect: pr.Rectangle, rect2: pr.Rectangle) -> bool:
    """Whether rect fully contains rect2"""
    return (
        rect2.x >= rect.x
        and rect2.y >= rect.y
        and (rect2.x + rect2.width) <= (rect.x + rect.width)
        and (rect2.y + rect2.height) <= (rect.y + rect.height)
    )


class Pointer[T](Protocol):
    @property
    def ptr(self) -> Any: ...

    @property
    def value(self) -> T: ...


class StrPointer(Pointer[str]):
    def __init__(self, capacity: int, initial_value: str = "") -> None:
        """Initializes StrPointer

        Notes:
          * This is entirely read-only in "python land" and is only modifiable via cffi

        Args:
          capacity: measured in bytes
          initial_value: initialized value
        """
        self._capacity = capacity
        self._pointer = pr.ffi.new(
            f"char[{self._capacity}]", initial_value.encode("utf-8")
        )

    @property
    def capacity(self) -> int:
        return self._capacity

    @property
    def ptr(self) -> Any:
        return self._pointer

    @property
    def value(self) -> str:
        """Retrieve value at pointer"""
        text_value = pr.ffi.string(self._pointer, self._capacity)
        return (
            text_value.decode("utf-8") if isinstance(text_value, bytes) else text_value
        )
