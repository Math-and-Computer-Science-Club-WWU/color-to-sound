"""A picture stored as plain numbers, and the text file format used to save it."""

from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

BYTES_PER_PIXEL = 3  # red, green, blue

Pixel = tuple[int, int, int]


@dataclass(frozen=True)
class Raster:
    """A picture as a flat run of pixel bytes: R,G,B,R,G,B,... row by row, left to right.

    Pixel number `i` sits at column `i % width`, row `i // width`, so no position is stored per pixel.
    """

    width: int
    height: int
    data: bytes

    def __post_init__(self) -> None:
        """Reject data that doesn't match the stated size."""
        if len(self.data) != self.width * self.height * BYTES_PER_PIXEL:
            raise ValueError("data must hold width * height RGB triples")

    def pixels(self) -> Iterator[Pixel]:
        """Yield each pixel as (red, green, blue), in order."""
        return zip(self.data[0::3], self.data[1::3], self.data[2::3], strict=True)


def write_values(raster: Raster, path: Path) -> None:
    """Save a raster as text: a "width height" line, then one "r g b" line per pixel.

    Pixel `i` is on line `i + 2`, so the file needs no pixel numbers.
    """
    with open(path, "w", encoding="utf-8", newline="\n") as file:
        file.write(f"{raster.width} {raster.height}\n")
        file.writelines(f"{r} {g} {b}\n" for r, g, b in raster.pixels())


def read_values(path: Path) -> Raster:
    """Load a raster saved by `write_values`."""
    with open(path, encoding="utf-8") as file:
        width, height = map(int, file.readline().split())
        data = bytes(int(value) for line in file for value in line.split())
    return Raster(width, height, data)
