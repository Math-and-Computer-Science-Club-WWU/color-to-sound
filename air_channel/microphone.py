"""Recording from the microphone."""

import queue
from collections.abc import Iterator
from threading import Event

import numpy as np

from air_channel.packets import SAMPLE_RATE

CHUNK_SECONDS = 0.1  # how much audio is handed over at a time
POLL_SECONDS = 0.2  # how long to wait for audio before checking whether to stop


def microphone_chunks(cancel: Event, sample_rate: int = SAMPLE_RATE) -> Iterator[np.ndarray]:
    """Yield pieces of microphone audio (mono floats) until `cancel` is set."""
    try:
        import sounddevice  # noqa: PLC0415 - imported here so the rest of the program works without it
    except ImportError as error:
        raise RuntimeError("Microphone support needs the sounddevice package: pip install sounddevice") from error

    pieces: queue.Queue[np.ndarray] = queue.Queue()

    def on_audio(indata: np.ndarray, frames: int, time_info: object, status: object) -> None:  # noqa: ARG001
        """Receive audio from the driver (on its own thread) and hand it over."""
        pieces.put(indata[:, 0].copy())

    try:
        stream = sounddevice.InputStream(
            samplerate=sample_rate,
            channels=1,
            dtype="float32",
            callback=on_audio,
            blocksize=int(sample_rate * CHUNK_SECONDS),
        )
        stream.start()
    except Exception as error:
        raise RuntimeError(f"Could not open the microphone: {error}") from error
    try:
        while not cancel.is_set():
            try:
                yield pieces.get(timeout=POLL_SECONDS)
            except queue.Empty:
                continue
    finally:
        stream.stop()
        stream.close()
