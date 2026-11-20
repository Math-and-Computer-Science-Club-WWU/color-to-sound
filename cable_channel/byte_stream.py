"""Sending a stream of bytes over the cable channel: one tone per byte, with a length and a checksum."""

import zlib
from collections.abc import Iterable, Iterator
from pathlib import Path

from cable_channel.listener import classify_frequency, read_tone_frequencies
from cable_channel.settings import FORMAT, VALUE_FREQUENCIES
from common.tones import write_tones

LENGTH_BYTES = 4  # the stream starts with the data length
CRC_BYTES = 4  # and ends with a CRC32 of the data
FRAME_OVERHEAD = LENGTH_BYTES + CRC_BYTES


def write_byte_stream(data: bytes, path: Path) -> None:
    """Write `data` as tones: length, then the data, then a CRC32 to detect corruption."""
    framed = len(data).to_bytes(LENGTH_BYTES, "big") + data + zlib.crc32(data).to_bytes(CRC_BYTES, "big")
    write_tones((VALUE_FREQUENCIES[byte] for byte in framed), path, FORMAT)


def iter_byte_values(frequencies: Iterable[float]) -> Iterator[int]:
    """Turn a stream of pitches into byte values, one at a time."""
    for frequency in frequencies:
        symbol = classify_frequency(frequency)
        if not isinstance(symbol, int):
            raise ValueError(
                "This doesn't look like an exact-copy recording (found a pixel-mode tone). Is the mode right?"
            )
        yield symbol


def verify_frame(framed: bytes) -> bytes:
    """Check the length and CRC32 of a received byte stream and return the data inside it."""
    length = int.from_bytes(framed[:LENGTH_BYTES], "big")
    data_end = LENGTH_BYTES + length
    data = framed[LENGTH_BYTES:data_end]
    checksum = framed[data_end:data_end + CRC_BYTES]
    if len(data) != length or len(checksum) != CRC_BYTES or zlib.crc32(data) != int.from_bytes(checksum, "big"):
        raise ValueError("audio is incomplete or damaged (checksum mismatch)")
    return data


def read_byte_stream(path: Path) -> bytes:
    """Inverse of `write_byte_stream`. Raises ValueError if the audio is damaged."""
    return verify_frame(bytes(iter_byte_values(read_tone_frequencies(path))))
