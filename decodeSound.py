import wave

import numpy as np

from protocol import BASE_HZ, END_HZ, RATE, SEP_HZ, STEP_HZ, TONE_SEC


def read_freqs(path):
    """Yield the loudest frequency (Hz) of each tone-sized window of the wav."""
    with wave.open(str(path), "rb") as w:
        samples = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16)
    n = int(RATE * TONE_SEC)
    for start in range(0, len(samples) - n + 1, n):
        spectrum = np.abs(np.fft.rfft(samples[start:start + n]))
        yield int(np.argmax(spectrum)) * RATE / n  # bin k is k * RATE / n Hz


def to_symbol(freq):
    """Turn a frequency into "S", "E" or a value 0-255."""
    if abs(freq - SEP_HZ) < STEP_HZ / 2:
        return "S"
    if abs(freq - END_HZ) < STEP_HZ / 2:
        return "E"
    return min(255, max(0, round((freq - BASE_HZ) / STEP_HZ)))


def read_frames(path):
    """Yield one list of values per frame (frames end at the E tone)."""
    frame = []
    for symbol in map(to_symbol, read_freqs(path)):
        if symbol == "E":
            yield frame
            frame = []
        elif symbol != "S":
            frame.append(symbol)
