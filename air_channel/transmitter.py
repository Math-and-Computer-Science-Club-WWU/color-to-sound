"""Turning a payload into air-ready audio."""

from pathlib import Path

from air_channel.packets import (
    FORMAT,
    FREQUENCIES,
    NIBBLE_BITS,
    PACKET_SECONDS,
    PREAMBLE,
    PayloadKind,
    build_packets,
)
from common.tones import write_tones

NIBBLE_MASK = (1 << NIBBLE_BITS) - 1


def packet_tone_numbers(packet: bytes) -> list[int]:
    """Return the tone numbers for one packet: the start pattern, then each byte as two 4-bit tones."""
    tones = list(PREAMBLE)
    for byte in packet:
        tones += [byte >> NIBBLE_BITS, byte & NIBBLE_MASK]
    return tones


def write_air_audio(kind: PayloadKind, aux: int, payload: bytes, path: Path, repeats: int = 1) -> float:
    """Write the payload as air-ready audio, sending each packet `repeats` times. Returns the seconds of audio."""
    packets = list(build_packets(kind, aux, payload))
    frequencies = (
        FREQUENCIES[tone] for _ in range(repeats) for packet in packets for tone in packet_tone_numbers(packet)
    )
    write_tones(frequencies, path, FORMAT)
    return 2 * FORMAT.lead_seconds + repeats * len(packets) * PACKET_SECONDS
