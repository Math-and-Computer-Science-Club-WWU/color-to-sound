"""Reading and writing wav files as arrays of samples."""

import wave
from collections.abc import Iterator
from pathlib import Path

import numpy as np

from common.tones import SAMPLE_BYTES

FULL_SCALE = 32768  # 16-bit samples are divided by this to get values between -1 and 1


def wav_info(path: Path) -> tuple[int, float]:
    """Return (sample rate, duration in seconds) of a wav."""
    with wave.open(str(path), "rb") as wav:
        return wav.getframerate(), wav.getnframes() / wav.getframerate()


def _to_mono_floats(raw: bytes, channels: int, sample_bytes: int) -> np.ndarray:
    """Convert raw 16-bit wav data to mono float samples between -1 and 1."""
    if sample_bytes != SAMPLE_BYTES:
        raise ValueError("only 16-bit wav files are supported")
    samples = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / FULL_SCALE
    return samples.reshape(-1, channels).mean(axis=1) if channels > 1 else samples


def read_slice(path: Path, start_seconds: float, seconds: float) -> tuple[np.ndarray, int]:
    """Read a short stretch of a wav without loading the whole file. Returns (samples, sample rate)."""
    with wave.open(str(path), "rb") as wav:
        rate = wav.getframerate()
        wav.setpos(min(wav.getnframes(), max(0, int(start_seconds * rate))))
        raw = wav.readframes(int(seconds * rate))
        return _to_mono_floats(raw, wav.getnchannels(), wav.getsampwidth()), rate


def iter_chunks(path: Path, seconds: float) -> Iterator[np.ndarray]:
    """Yield a wav piece by piece (mono float samples), without loading it all at once."""
    with wave.open(str(path), "rb") as wav:
        frames_per_chunk = int(seconds * wav.getframerate())
        while raw := wav.readframes(frames_per_chunk):
            yield _to_mono_floats(raw, wav.getnchannels(), wav.getsampwidth())


def write_wav(path: Path, samples: np.ndarray, rate: int) -> None:
    """Write float samples between -1 and 1 as a mono 16-bit wav."""
    pcm = (np.clip(np.asarray(samples, dtype=np.float32), -1, 1) * (FULL_SCALE - 1)).astype(np.int16)
    with wave.open(str(path), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(SAMPLE_BYTES)
        wav.setframerate(rate)
        wav.writeframes(pcm.tobytes())
