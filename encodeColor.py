import math
import wave
from array import array
from functools import cache
from pathlib import Path

from protocol import END_HZ, FREQ, RATE, SEP_HZ, TONE_SEC
from raster import read_values

HERE = Path(__file__).parent


@cache  # at most 258 distinct tones, so each is synthesized once
def tone(freq):
    """Generate a tone for the given frequency."""
    n = int(RATE * TONE_SEC)
    samples = (int(12000 * math.sin(2 * math.pi * freq * t / RATE)) for t in range(n))
    return array("h", samples).tobytes()


def pixel_freqs(i, r, g, b):
    """Return the sequence of frequencies for a pixel with index i and RGB values."""
    return [FREQ[i], FREQ[b], SEP_HZ, FREQ[g], SEP_HZ, FREQ[r], END_HZ]


def frames(raster):
    """Yield the header frame (width, height), then one frame per pixel."""
    if raster.width * raster.height > len(FREQ):
        raise ValueError("image has more pixels than one index tone can address; lower max_size")
    yield [FREQ[raster.width], SEP_HZ, FREQ[raster.height], END_HZ]
    for i, (r, g, b) in enumerate(raster.pixels()):
        yield pixel_freqs(i, r, g, b)


def encode(raster, path):
    """Encode the raster as a sequence of tones and write to the given path."""
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(RATE)
        for frame in frames(raster):
            for f in frame:
                w.writeframes(tone(f))


if __name__ == "__main__":
    # Encode values.txt to out.wav
    encode(read_values(HERE / "values.txt"), HERE / "out.wav")