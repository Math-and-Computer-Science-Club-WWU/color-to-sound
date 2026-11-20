"""Turning frequencies into audio and writing them to wav files."""

import math
import wave
from array import array
from collections.abc import Iterable
from dataclasses import dataclass
from functools import cache
from pathlib import Path

SAMPLE_BYTES = 2  # all audio here is 16-bit


@dataclass(frozen=True)
class ToneFormat:
    """How a sequence of tones is laid out in a wav file."""

    sample_rate: int  # samples per second
    tone_seconds: float  # how long each tone lasts
    fade_seconds: float = 0.0  # fade at each tone's edges so tones don't click or smear together
    amplitude: int = 12000  # loudest sample value (32767 is full scale)
    lead_seconds: float = 0.0  # silence before and after all the tones

    @property
    def samples_per_tone(self) -> int:
        """Number of samples in one tone."""
        return int(self.sample_rate * self.tone_seconds)


@cache  # only a few hundred distinct tones exist, so each is synthesized once
def synthesize_tone(frequency: float, tone_format: ToneFormat) -> bytes:
    """Return one tone as raw 16-bit samples."""
    length = tone_format.samples_per_tone
    fade = int(tone_format.sample_rate * tone_format.fade_seconds)

    def envelope(t: int) -> float:
        """Volume from 0 to 1: ramps up over the first `fade` samples and down over the last."""
        edge_distance = min(t, length - 1 - t)
        if edge_distance >= fade:
            return 1.0
        return 0.5 * (1 - math.cos(math.pi * edge_distance / fade))

    angular_step = 2 * math.pi * frequency / tone_format.sample_rate
    samples = (int(tone_format.amplitude * envelope(t) * math.sin(angular_step * t)) for t in range(length))
    return array("h", samples).tobytes()


def write_tones(frequencies: Iterable[float], path: Path, tone_format: ToneFormat) -> None:
    """Write one tone per frequency to a mono wav, with silence before and after if the format asks for it."""
    silence = bytes(SAMPLE_BYTES) * int(tone_format.sample_rate * tone_format.lead_seconds)
    with wave.open(str(path), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(SAMPLE_BYTES)
        wav.setframerate(tone_format.sample_rate)
        wav.writeframes(silence)
        for frequency in frequencies:
            wav.writeframes(synthesize_tone(frequency, tone_format))
        wav.writeframes(silence)
