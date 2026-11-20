"""Turning an image into air-ready audio."""

from pathlib import Path
from typing import NamedTuple

from air_channel.packets import PayloadKind, packet_count, pixel_aux
from air_channel.transmitter import write_air_audio
from cable_channel.pixel_mode import extract_raster
from common.image_budget import fit_image_file_to_budget
from common.modes import Mode

AIR_MAX_BYTES = 3000  # file budget over the air: about 94 packets, 5.4 minutes for one pass
DEFAULT_PIXEL_SIDE = 32


class AirTransmission(NamedTuple):
    """What was made by `send_over_air`."""

    payload_bytes: int
    packets: int
    seconds: float  # length of the audio, including repeats


def send_over_air(
    image_path: Path,
    wav_path: Path,
    mode: Mode,
    pixel_side: int = DEFAULT_PIXEL_SIDE,
    repeats: int = 1,
) -> AirTransmission:
    """Make air-ready audio from an image, as the image file (Mode.FILE) or as shrunken pixels (Mode.PIXELS)."""
    if mode is Mode.FILE:
        payload = fit_image_file_to_budget(image_path, AIR_MAX_BYTES)  # the file itself, shrunk only if over budget
        kind, aux = PayloadKind.FILE, len(payload)
    else:
        raster = extract_raster(image_path, (pixel_side, pixel_side))
        payload = raster.data
        kind, aux = PayloadKind.PIXELS, pixel_aux(raster.width, raster.height)
    seconds = write_air_audio(kind, aux, payload, wav_path, repeats)
    return AirTransmission(len(payload), packet_count(kind, aux), seconds)
