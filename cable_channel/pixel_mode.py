"""Pixel mode on the cable channel: send each pixel's color, and rebuild a (blurry) picture from them.

Every pixel is sent as a frame of 8 tones: index (high, low), blue, separator, green, separator, red, end.
The audio starts with a header frame carrying the width and height.

Command line (run from the project root):
    python -m cable_channel.pixel_mode extract [--image PATH] [--size N]   image -> output/values.txt
    python -m cable_channel.pixel_mode encode                              output/values.txt -> output/out.wav
    python -m cable_channel.pixel_mode assemble                            output/out.wav -> output/out.png
"""

import argparse
from collections.abc import Iterator
from pathlib import Path

from PIL import Image

from cable_channel.listener import read_frames
from cable_channel.settings import END_HZ, FORMAT, SEPARATOR_HZ, VALUE_FREQUENCIES
from common.paths import IMAGE_DIR, output_path
from common.raster import BYTES_PER_PIXEL, Pixel, Raster, read_values, write_values
from common.tones import write_tones

BYTE_RANGE = 256  # a number too big for one tone is sent as a high byte and a low byte
MAX_PIXELS = BYTE_RANGE * BYTE_RANGE  # so the pixel index can count up to 65536
PIXEL_FRAME_VALUES = 5  # index high, index low, blue, green, red
DEFAULT_SIDE = 64  # longest side, in pixels, of the shrunken picture
VIEW_SIZE = 800  # the rebuilt picture is enlarged to about this many pixels on its longest side
DEFAULT_IMAGE = IMAGE_DIR / "rainbow.webp"
VALUES_NAME, WAV_NAME, PICTURE_NAME = "values.txt", "out.wav", "out.png"


def extract_raster(image_path: Path, max_size: tuple[int, int] = (DEFAULT_SIDE, DEFAULT_SIDE)) -> Raster:
    """Shrink an image to fit inside `max_size` (keeping its proportions) and read its pixels."""
    with Image.open(image_path) as source:
        image = source.convert("RGB")
    image.thumbnail(max_size, Image.Resampling.LANCZOS)  # shrinks in place
    return Raster(image.width, image.height, image.tobytes())


def _split_bytes(number: int) -> tuple[int, int]:
    """Split a number below 65536 into (high byte, low byte)."""
    return number // BYTE_RANGE, number % BYTE_RANGE


def pixel_frame(index: int, pixel: Pixel) -> list[float]:
    """Return the pitches that send one pixel: its index, then blue, green and red with separators between."""
    red, green, blue = pixel
    high, low = _split_bytes(index)
    return [
        VALUE_FREQUENCIES[high], VALUE_FREQUENCIES[low], VALUE_FREQUENCIES[blue], SEPARATOR_HZ,
        VALUE_FREQUENCIES[green], SEPARATOR_HZ, VALUE_FREQUENCIES[red], END_HZ,
    ]


def header_frame(width: int, height: int) -> list[float]:
    """Return the pitches that send the picture's width and height."""
    width_high, width_low = _split_bytes(width)
    height_high, height_low = _split_bytes(height)
    return [
        VALUE_FREQUENCIES[width_high], VALUE_FREQUENCIES[width_low], SEPARATOR_HZ,
        VALUE_FREQUENCIES[height_high], VALUE_FREQUENCIES[height_low], END_HZ,
    ]


def encode_raster(raster: Raster, path: Path) -> None:
    """Write a raster as tones: the header frame, then one frame per pixel."""
    if raster.width * raster.height > MAX_PIXELS:
        raise ValueError(f"image has more than {MAX_PIXELS} pixels; use a smaller size")

    def pitches() -> Iterator[float]:
        yield from header_frame(raster.width, raster.height)
        for index, pixel in enumerate(raster.pixels()):
            yield from pixel_frame(index, pixel)

    write_tones(pitches(), path, FORMAT)


def read_header(frames: Iterator[list[int]]) -> tuple[int, int]:
    """Read the first frame of a pixel-mode recording and return (width, height)."""
    try:
        width_high, width_low, height_high, height_low = next(frames)
    except (StopIteration, ValueError) as error:
        raise ValueError("This doesn't look like a pixel-mode recording. Is the mode right?") from error
    return width_high * BYTE_RANGE + width_low, height_high * BYTE_RANGE + height_low


def iter_pixels(frames: Iterator[list[int]], width: int, height: int) -> Iterator[tuple[int, Pixel]]:
    """Yield (pixel index, (r, g, b)) for each pixel frame as it arrives. Damaged frames are skipped."""
    for frame in frames:
        if len(frame) != PIXEL_FRAME_VALUES:
            continue
        index_high, index_low, blue, green, red = frame
        index = index_high * BYTE_RANGE + index_low
        if index < width * height:
            yield index, (red, green, blue)  # the index decides where it goes


def assemble_raster(path: Path) -> Raster:
    """Rebuild a raster from a pixel-mode wav. Pixels that never arrive stay black."""
    frames = read_frames(path)
    width, height = read_header(frames)
    data = bytearray(width * height * BYTES_PER_PIXEL)
    for index, pixel in iter_pixels(frames, width, height):
        start = BYTES_PER_PIXEL * index
        data[start:start + BYTES_PER_PIXEL] = bytes(pixel)
    return Raster(width, height, bytes(data))


def raster_to_picture(raster: Raster) -> Image.Image:
    """Turn a raster into a picture, enlarged smoothly so it is easy to see."""
    image = Image.frombytes("RGB", (raster.width, raster.height), raster.data)
    scale = max(1, VIEW_SIZE // max(raster.width, raster.height))
    # smooth enlarging looks closer to the original than big blocky squares
    return image.resize((raster.width * scale, raster.height * scale), Image.Resampling.BICUBIC)


def send_pixels(image_path: Path, wav_path: Path, max_size: tuple[int, int] = (DEFAULT_SIDE, DEFAULT_SIDE)) -> int:
    """Shrink an image and send its pixels as tones. Returns the number of pixels sent."""
    raster = extract_raster(image_path, max_size)
    encode_raster(raster, wav_path)
    return raster.width * raster.height


def main() -> None:
    """Run the command line."""
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    commands = parser.add_subparsers(dest="command", required=True)
    extract = commands.add_parser("extract", help="image -> output/values.txt")
    extract.add_argument("--image", type=Path, default=DEFAULT_IMAGE)
    extract.add_argument("--size", type=int, default=DEFAULT_SIDE, help="longest side in pixels")
    commands.add_parser("encode", help="output/values.txt -> output/out.wav")
    commands.add_parser("assemble", help="output/out.wav -> output/out.png")
    args = parser.parse_args()

    if args.command == "extract":
        # extract first, so a failure can't wipe the old file
        write_values(extract_raster(args.image, (args.size, args.size)), output_path(VALUES_NAME))
    elif args.command == "encode":
        encode_raster(read_values(output_path(VALUES_NAME)), output_path(WAV_NAME))
    else:
        picture = raster_to_picture(assemble_raster(output_path(WAV_NAME)))
        picture.save(output_path(PICTURE_NAME))
        print(f"Wrote {PICTURE_NAME}")


if __name__ == "__main__":
    main()
