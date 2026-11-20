"""Live decoding of air-channel audio, from a wav file or straight from the microphone."""

import io
import math
import time
from collections.abc import Iterator
from pathlib import Path
from threading import Event

import numpy as np
from PIL import Image

from air_channel.microphone import microphone_chunks
from air_channel.packets import SAMPLE_RATE, PayloadKind, pixel_size
from air_channel.receiver import AirReceiver
from cable_channel.pixel_mode import raster_to_picture
from common.modes import Channel, Mode
from common.pacing import paced
from common.paths import output_path
from common.raster import BYTES_PER_PIXEL, Raster
from common.spectrogram import spectrogram_image
from common.wav_files import iter_chunks, wav_info, write_wav
from live_decoding.events import (
    BACKGROUND,
    SIGNAL_VIEWS,
    UPDATE_SECONDS,
    LiveUpdate,
    byte_grid,
    packet_map,
)

CHUNK_SECONDS = 0.1  # how much audio is fed to the receiver at a time
RECORDING_NAME = "recorded.wav"
MODE_OF_KIND = {PayloadKind.FILE: Mode.FILE, PayloadKind.PIXELS: Mode.PIXELS}


def _partial_picture(receiver: AirReceiver) -> Image.Image:
    """Draw the reconstruction from the packets that have arrived so far (missing parts stay dark)."""
    data, known = receiver.assemble_payload()
    if receiver.kind is PayloadKind.PIXELS:
        width, height = pixel_size(receiver.aux)
        pixels = data.reshape(height, width, BYTES_PER_PIXEL).copy()
        arrived = known.reshape(height, width, BYTES_PER_PIXEL).all(axis=2)  # a pixel counts only if all 3 bytes did
        pixels[~arrived] = BACKGROUND
        return Image.fromarray(pixels)
    return byte_grid(data.tolist(), len(data), known.tolist())


def _final_update(receiver: AirReceiver, common: dict, note: str) -> LiveUpdate:
    """Build the last update of a decode: the finished picture, or what we have if packets are missing."""
    total = receiver.total
    received = len(receiver.packets)
    if not receiver.complete:
        text = (f"Stopped with {received} of {total} packets; {total - received} missing{note}. "
                "Send again, or use more repeats.")
        return LiveUpdate(received / total, text, _partial_picture(receiver), blocky=True,
                          final=True, is_complete=False, **common)

    data, _ = receiver.assemble_payload()
    if receiver.kind is PayloadKind.PIXELS:
        width, height = pixel_size(receiver.aux)
        picture = raster_to_picture(Raster(width, height, bytes(data)))
        return LiveUpdate(1.0, f"Received all {total} packets{note}.", picture, final=True, **common)
    try:
        with Image.open(io.BytesIO(bytes(data))) as image:
            picture = image.convert("RGB")
    except OSError:
        return LiveUpdate(1.0, "All packets arrived but the file isn't a readable image.", _partial_picture(receiver),
                          blocky=True, final=True, is_complete=False, **common)
    return LiveUpdate(1.0, f"Received all {total} packets{note}. Rebuilt the image from the file.", picture,
                      final=True, **common)


def _update_from(receiver: AirReceiver, final: bool = False) -> LiveUpdate:
    """Describe the receiver's current state for the window."""
    signal = spectrogram_image(receiver.recent, receiver.sample_rate, SIGNAL_VIEWS[Channel.AIR])
    if receiver.kind is None:  # nothing decoded yet
        decibels = 20 * math.log10(receiver.level + 1e-9)
        text = "Heard no packets." if final else f"Listening... level {decibels:.0f} dB. Waiting for a start pattern."
        return LiveUpdate(0.0, text, final=final, is_complete=False, signal=signal)

    received, total = len(receiver.packets), receiver.total
    common = {
        "mode": MODE_OF_KIND[receiver.kind],
        "signal": signal,
        "packet_map": packet_map(receiver.packets.keys(), total),
    }
    note = f" ({receiver.damaged} damaged and skipped)" if receiver.damaged else ""
    if final:
        return _final_update(receiver, common, note)
    return LiveUpdate(received / total, f"Packet {received} of {total} received{note}",
                      _partial_picture(receiver), blocky=True, **common)


def decode_air_live(chunks: Iterator[np.ndarray], sample_rate: int,
                    recorded: list[np.ndarray] | None = None) -> Iterator[LiveUpdate]:
    """Decode air audio piece by piece, yielding updates as it goes. Stops once everything has arrived.

    The `chunks` iterator decides when the audio ends (end of file, or the user pressing Stop). If `recorded`
    is given, every piece of audio is also appended to it.
    """
    receiver = AirReceiver(sample_rate)
    last_update = 0.0
    try:
        for chunk in chunks:
            if recorded is not None:
                recorded.append(chunk)
            receiver.feed(chunk)
            now = time.perf_counter()
            if now - last_update >= UPDATE_SECONDS or receiver.complete:
                last_update = now
                yield _update_from(receiver)
            if receiver.complete:
                break
    finally:
        chunks.close()
    yield _update_from(receiver, final=True)  # also after Stop or a timeout: reports what did arrive


def decode_air_file_live(wav_path: Path, speed: float, cancel: Event) -> Iterator[LiveUpdate]:
    """Decode an air-channel wav at `speed` times real time (0 means as fast as possible)."""
    sample_rate, _ = wav_info(wav_path)
    chunks = paced(iter_chunks(wav_path, CHUNK_SECONDS), CHUNK_SECONDS / speed if speed else 0, cancel)
    return decode_air_live(chunks, sample_rate)


def decode_air_microphone_live(cancel: Event) -> Iterator[LiveUpdate]:
    """Listen to the microphone and decode live. The recording is saved to output/recorded.wav afterwards."""
    recorded: list[np.ndarray] = []
    try:
        yield from decode_air_live(microphone_chunks(cancel), SAMPLE_RATE, recorded)
    finally:
        if recorded:
            write_wav(output_path(RECORDING_NAME), np.concatenate(recorded), SAMPLE_RATE)
