"""Packet format and tone settings for sending over the air (speaker to microphone).

Every packet is a start pattern (4 tones), then 41 bytes sent as 4-bit tones (82 tones):

    kind (1) | sequence number (2) | aux (4) | data (32) | CRC16 (2)

`kind` says what the data is, and `aux` describes it (the file length, or the width and height of a pixel
picture). Every packet repeats both, so a receiver can join in at any packet.
"""

import binascii
from collections.abc import Iterator
from enum import IntEnum
from typing import NamedTuple

from common.tones import ToneFormat

SAMPLE_RATE = 44100  # what most microphones record at
TONE_SECONDS = 0.04  # long enough to survive room echo; 100 Hz steps are 4 FFT bins apart
FORMAT = ToneFormat(
    sample_rate=SAMPLE_RATE,
    tone_seconds=TONE_SECONDS,
    fade_seconds=0.003,  # short fades stop each tone clicking and smearing into the next
    amplitude=16000,  # about half of full scale
    lead_seconds=1.0,  # silence before and after, so a recording can start a little early
)

NIBBLE_BITS = 4  # each tone carries 4 bits
NUM_DATA_TONES = 1 << NIBBLE_BITS  # so there are 16 data tones
DATA_FREQUENCIES = [1000 + 100 * value for value in range(NUM_DATA_TONES)]
# Two more tones are used only in the start pattern, so it can never be mistaken for data.
SYNC_A_HZ, SYNC_B_HZ = 600, 800
FREQUENCIES = [*DATA_FREQUENCIES, SYNC_A_HZ, SYNC_B_HZ]  # indexed by tone number
SYNC_A, SYNC_B = NUM_DATA_TONES, NUM_DATA_TONES + 1  # tone numbers of the two sync tones
PREAMBLE = (SYNC_A, SYNC_B, SYNC_A, SYNC_B)

KIND_BYTES, SEQ_BYTES, AUX_BYTES, CRC_BYTES = 1, 2, 4, 2
DATA_BYTES = 32  # payload bytes carried by one packet
HEADER_BYTES = KIND_BYTES + SEQ_BYTES + AUX_BYTES
PACKET_BYTES = HEADER_BYTES + DATA_BYTES + CRC_BYTES
TONES_PER_PACKET = len(PREAMBLE) + 2 * PACKET_BYTES
PACKET_SECONDS = TONES_PER_PACKET * TONE_SECONDS

CRC_START = 0xFFFF
PIXEL_SIDE_BITS = 16  # width and height each take 16 bits of the aux field


class PayloadKind(IntEnum):
    """What a packet's data is."""

    FILE = 0  # bytes of an image file
    PIXELS = 1  # raw RGB bytes of a picture, row by row


class Packet(NamedTuple):
    """The contents of one decoded packet."""

    kind: PayloadKind
    seq: int  # which 32-byte slice of the payload this is
    aux: int
    data: bytes


def pixel_aux(width: int, height: int) -> int:
    """Pack a picture's size into the aux field."""
    return width << PIXEL_SIDE_BITS | height


def pixel_size(aux: int) -> tuple[int, int]:
    """Unpack (width, height) from the aux field of a pixel packet."""
    return aux >> PIXEL_SIDE_BITS, aux & ((1 << PIXEL_SIDE_BITS) - 1)


def payload_length(kind: PayloadKind, aux: int) -> int:
    """How many bytes the whole payload has."""
    if kind is PayloadKind.FILE:
        return aux
    width, height = pixel_size(aux)
    return width * height * 3


def packet_count(kind: PayloadKind, aux: int) -> int:
    """How many packets it takes to send the whole payload."""
    return max(1, -(-payload_length(kind, aux) // DATA_BYTES))  # rounded up


def build_packets(kind: PayloadKind, aux: int, payload: bytes) -> Iterator[bytes]:
    """Split a payload into packets of PACKET_BYTES bytes each."""
    for seq in range(packet_count(kind, aux)):
        chunk = payload[seq * DATA_BYTES:(seq + 1) * DATA_BYTES].ljust(DATA_BYTES, b"\0")
        body = (
            kind.to_bytes(KIND_BYTES, "big") + seq.to_bytes(SEQ_BYTES, "big")
            + aux.to_bytes(AUX_BYTES, "big") + chunk
        )
        yield body + binascii.crc_hqx(body, CRC_START).to_bytes(CRC_BYTES, "big")


def parse_packet(raw: bytes) -> Packet | None:
    """Decode a packet's bytes, or return None if it is damaged."""
    if len(raw) != PACKET_BYTES:
        return None
    body, crc = raw[:-CRC_BYTES], int.from_bytes(raw[-CRC_BYTES:], "big")
    if binascii.crc_hqx(body, CRC_START) != crc:
        return None
    try:
        kind = PayloadKind(body[0])
    except ValueError:
        return None
    seq = int.from_bytes(body[KIND_BYTES:KIND_BYTES + SEQ_BYTES], "big")
    aux = int.from_bytes(body[KIND_BYTES + SEQ_BYTES:HEADER_BYTES], "big")
    return Packet(kind, seq, aux, body[HEADER_BYTES:])
