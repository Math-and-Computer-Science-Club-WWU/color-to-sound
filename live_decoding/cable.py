"""Live decoding of cable-channel recordings."""

import io
import time
from collections.abc import Iterator
from pathlib import Path
from threading import Event

from PIL import Image

from cable_channel.byte_stream import FRAME_OVERHEAD, LENGTH_BYTES, iter_byte_values, verify_frame
from cable_channel.listener import read_tone_frequencies, split_into_frames
from cable_channel.pixel_mode import iter_pixels, raster_to_picture, read_header
from cable_channel.settings import TONE_SECONDS
from common.modes import Channel, Mode
from common.pacing import paced
from common.raster import Raster
from live_decoding.events import BACKGROUND, UPDATE_SECONDS, LiveUpdate, byte_grid, signal_at

HEADER_TONES = 6  # a pixel-mode recording starts with a header frame of this many tones
PIXEL_FRAME_TONES = 8  # and then each pixel takes this many


def _paced_frequencies(wav_path: Path, speed: float, cancel: Event) -> Iterator[float]:
    """Return the pitches in a wav, released at `speed` times real time (0 means as fast as possible)."""
    return paced(read_tone_frequencies(wav_path), TONE_SECONDS / speed if speed else 0, cancel)


def decode_file_live(wav_path: Path, speed: float, cancel: Event) -> Iterator[LiveUpdate]:
    """Decode a file-mode recording, yielding an update as each byte arrives."""
    received = bytearray()
    total = None  # bytes expected, known once the length has arrived
    last_update = 0.0
    for value in iter_byte_values(_paced_frequencies(wav_path, speed, cancel)):
        received.append(value)
        if total is None and len(received) == LENGTH_BYTES:
            total = FRAME_OVERHEAD + int.from_bytes(received, "big")
        now = time.perf_counter()
        if total and (now - last_update >= UPDATE_SECONDS or len(received) == total):
            last_update = now
            yield LiveUpdate(
                progress=len(received) / total,
                text=f"Received {len(received)} of {total} bytes",
                image=byte_grid(received, total),
                blocky=True,
                mode=Mode.FILE,
                signal=signal_at(wav_path, len(received) * TONE_SECONDS, Channel.CABLE),
            )
    if cancel.is_set():
        return
    data = verify_frame(bytes(received))  # raises if incomplete or damaged
    with Image.open(io.BytesIO(data)) as image:
        yield LiveUpdate(1.0, "Checksum OK. Rebuilt the image from the bytes.", image.convert("RGB"),
                         final=True, mode=Mode.FILE)


def decode_pixels_live(wav_path: Path, speed: float, cancel: Event) -> Iterator[LiveUpdate]:
    """Decode a pixel-mode recording, yielding an update as each pixel is placed."""
    frames = split_into_frames(_paced_frequencies(wav_path, speed, cancel))
    width, height = read_header(frames)
    total = width * height
    canvas = Image.new("RGB", (width, height), BACKGROUND)
    placed = 0
    last_update = 0.0
    for index, pixel in iter_pixels(frames, width, height):
        canvas.putpixel((index % width, index // width), pixel)
        placed += 1
        now = time.perf_counter()
        if now - last_update >= UPDATE_SECONDS or placed == total:
            last_update = now
            red, green, blue = pixel
            yield LiveUpdate(
                progress=placed / total,
                text=f"Pixel {index + 1} of {total}: R={red} G={green} B={blue}",
                image=canvas.copy(),
                blocky=True,
                mode=Mode.PIXELS,
                signal=signal_at(wav_path, (HEADER_TONES + PIXEL_FRAME_TONES * placed) * TONE_SECONDS, Channel.CABLE),
            )
    if cancel.is_set():
        return
    picture = raster_to_picture(Raster(width, height, canvas.tobytes()))
    yield LiveUpdate(1.0, f"Placed {placed} of {total} pixels.", picture, final=True, mode=Mode.PIXELS)
