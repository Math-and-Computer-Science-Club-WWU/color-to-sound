"""Turning audio into a spectrogram picture: pitch going up, time going right."""

from dataclasses import dataclass

import numpy as np
from PIL import Image

FFT_SIZE = 1024  # samples analysed per column
DB_FOR_FULL_SCALE_SINE = 48  # what a full-scale sine measures with this FFT size
DYNAMIC_RANGE_DB = 70  # how far below that level the picture still shows something


@dataclass(frozen=True)
class SpectrogramView:
    """What part of the sound to show, and how big to draw it."""

    seconds: float  # how much of the most recent audio to show
    min_hz: float  # lowest pitch shown
    max_hz: float  # highest pitch shown
    size: tuple[int, int]  # picture width and height in pixels


def _build_colormap() -> np.ndarray:
    """Return 256 RGB colors running from dark purple through red to pale yellow."""
    stops = [(0.0, (8, 6, 28)), (0.4, (80, 25, 120)), (0.7, (225, 75, 55)), (1.0, (255, 240, 160))]
    positions = np.linspace(0, 1, 256)
    channels = [np.interp(positions, [s[0] for s in stops], [s[1][c] for s in stops]) for c in range(3)]
    return np.stack(channels, axis=1).astype(np.uint8)


COLORMAP = _build_colormap()


def spectrogram_image(samples: np.ndarray, rate: int, view: SpectrogramView) -> Image.Image:
    """Draw the last `view.seconds` of audio as a heat map (newest at the right edge)."""
    wanted = int(view.seconds * rate)
    recent = np.asarray(samples, dtype=np.float32)[-wanted:]
    if len(recent) < wanted:  # not enough audio yet: pad on the left so the newest sound stays at the right
        recent = np.concatenate((np.zeros(wanted - len(recent), dtype=np.float32), recent))

    columns = view.size[0]
    starts = np.linspace(0, wanted - FFT_SIZE, columns).astype(int)
    frames = np.stack([recent[s:s + FFT_SIZE] for s in starts]) * np.hanning(FFT_SIZE)
    magnitude = np.abs(np.fft.rfft(frames, axis=1))

    pitches = np.fft.rfftfreq(FFT_SIZE, 1 / rate)
    shown = (pitches >= view.min_hz) & (pitches <= view.max_hz)
    decibels = 20 * np.log10(magnitude[:, shown] + 1e-6)
    # absolute scale, so silence stays dark instead of being stretched to look loud
    brightness = np.clip((decibels - (DB_FOR_FULL_SCALE_SINE - DYNAMIC_RANGE_DB)) / DYNAMIC_RANGE_DB, 0, 1)
    pixels = COLORMAP[(brightness * 255).astype(int)].transpose(1, 0, 2)[::-1]  # high pitches at the top
    return Image.fromarray(np.ascontiguousarray(pixels)).resize(view.size, Image.Resampling.BILINEAR)
