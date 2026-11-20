"""What the live decoders report to the window, and the small pictures they draw."""

import colorsys
import math
from collections.abc import Collection, Sequence
from dataclasses import dataclass
from pathlib import Path

from PIL import Image

from common.modes import Channel, Mode
from common.spectrogram import SpectrogramView, spectrogram_image
from common.wav_files import read_slice

UPDATE_SECONDS = 1 / 30  # the most often a new picture is handed to the window (smooth enough to look fluid)

BACKGROUND = (28, 28, 28)  # not heard yet
PACKET_RECEIVED = (70, 200, 110)
PACKET_MISSING = (80, 80, 80)
MAP_BACKGROUND = (14, 14, 14)
# one color per byte value, spread around the color wheel
BYTE_COLORS = [tuple(int(c * 255) for c in colorsys.hsv_to_rgb(v / 256, 0.8, 0.95)) for v in range(256)]

SIGNAL_SIZE = (340, 130)
SIGNAL_VIEWS = {
    Channel.CABLE: SpectrogramView(seconds=1.5, min_hz=300, max_hz=21000, size=SIGNAL_SIZE),
    Channel.AIR: SpectrogramView(seconds=3.0, min_hz=500, max_hz=2800, size=SIGNAL_SIZE),
}


@dataclass(frozen=True)
class LiveUpdate:
    """A snapshot of a decode in progress."""

    progress: float  # 0 to 1
    text: str  # what to tell the user right now
    image: Image.Image | None = None  # the reconstruction so far
    blocky: bool = False  # True: enlarge with hard edges so individual pixels are visible
    final: bool = False  # True for the last update of a decode
    is_complete: bool = True  # on a final update: False if the picture is only partial
    mode: Mode | None = None  # what is being sent, once known
    signal: Image.Image | None = None  # spectrogram of the sound being heard
    packet_map: Image.Image | None = None  # one square per packet: received or missing


def signal_at(wav_path: Path, seconds_in: float, channel: Channel) -> Image.Image:
    """Spectrogram of the sound just before `seconds_in` seconds into a wav."""
    view = SIGNAL_VIEWS[channel]
    start = max(0.0, seconds_in - view.seconds)
    samples, rate = read_slice(wav_path, start, seconds_in - start)
    return spectrogram_image(samples, rate, view)


def byte_grid(values: Sequence[int], total: int, known: Sequence[bool] | None = None) -> Image.Image:
    """Draw a byte stream as colored squares in reading order. Bytes not yet known stay dark."""
    columns = math.ceil(math.sqrt(total * 4 / 3))  # roughly the shape of the preview panel
    rows = math.ceil(total / columns)
    colors = [
        BYTE_COLORS[value] if known is None or known[index] else BACKGROUND
        for index, value in enumerate(values)
    ]
    image = Image.new("RGB", (columns, rows), BACKGROUND)
    image.putdata(colors + [BACKGROUND] * (columns * rows - len(colors)))
    return image


def packet_map(received: Collection[int], total: int) -> Image.Image:
    """Draw one square per packet: green once received, grey while still missing."""
    columns = math.ceil(math.sqrt(total * 4))  # wide and short, to suit the panel
    rows = math.ceil(total / columns)
    squares = [PACKET_RECEIVED if seq in received else PACKET_MISSING for seq in range(total)]
    image = Image.new("RGB", (columns, rows), MAP_BACKGROUND)
    image.putdata(squares + [MAP_BACKGROUND] * (columns * rows - total))
    return image
