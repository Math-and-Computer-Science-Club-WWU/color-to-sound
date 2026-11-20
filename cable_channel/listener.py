"""Listening to a cable-channel wav: turning each tone back into a number or a marker."""

from collections.abc import Iterable, Iterator
from enum import Enum
from pathlib import Path

import numpy as np

from cable_channel.settings import BASE_HZ, END_HZ, SAMPLE_RATE, SEPARATOR_HZ, STEP_HZ, TONE_SECONDS, VALUE_COUNT
from common.wav_files import read_slice, wav_info


class Marker(Enum):
    """The two tones that carry no value, only structure."""

    SEPARATOR = "separator"
    END = "end"


Symbol = int | Marker


def read_tone_frequencies(path: Path) -> Iterator[float]:
    """Yield the loudest pitch (Hz) in each tone-sized slice of the wav."""
    _, duration = wav_info(path)
    samples, _ = read_slice(path, 0, duration)
    length = int(SAMPLE_RATE * TONE_SECONDS)
    for start in range(0, len(samples) - length + 1, length):
        spectrum = np.abs(np.fft.rfft(samples[start:start + length]))
        yield int(np.argmax(spectrum)) * SAMPLE_RATE / length  # FFT bin k is k * rate / length Hz


def classify_frequency(frequency: float) -> Symbol:
    """Turn a pitch into a marker, or into the value 0-255 it stands for."""
    if abs(frequency - SEPARATOR_HZ) < STEP_HZ / 2:
        return Marker.SEPARATOR
    if abs(frequency - END_HZ) < STEP_HZ / 2:
        return Marker.END
    return min(VALUE_COUNT - 1, max(0, round((frequency - BASE_HZ) / STEP_HZ)))


def split_into_frames(frequencies: Iterable[float]) -> Iterator[list[int]]:
    """Group tones into frames: each frame's values, ending where an END tone is heard."""
    frame: list[int] = []
    for symbol in map(classify_frequency, frequencies):
        if symbol is Marker.END:
            yield frame
            frame = []
        elif symbol is not Marker.SEPARATOR:
            frame.append(symbol)


def read_frames(path: Path) -> Iterator[list[int]]:
    """Yield the frames of a cable-channel pixel-mode wav."""
    return split_into_frames(read_tone_frequencies(path))
