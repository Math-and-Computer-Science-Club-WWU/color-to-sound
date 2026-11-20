"""File mode on the cable channel: send the image file itself and get an exact copy back.

Command line:
    python -m cable_channel.file_mode send [--image PATH]
    python -m cable_channel.file_mode receive
"""

import argparse
import io
from pathlib import Path

from PIL import Image

from cable_channel.byte_stream import read_byte_stream, write_byte_stream
from cable_channel.settings import TONE_SECONDS
from common.image_budget import fit_image_file_to_budget
from common.paths import IMAGE_DIR, output_path

DEFAULT_IMAGE = IMAGE_DIR / "lake.webp"
WAV_NAME = "image.wav"
RECEIVED_NAME = "received.png"
MAX_BYTES = 30000  # audio budget: one 12.5 ms tone per byte, so 30000 bytes is about 6 minutes


def send_file(image_path: Path, wav_path: Path, max_bytes: int = MAX_BYTES) -> int:
    """Turn an image file into a wav of tones. Returns the number of bytes sent."""
    data = fit_image_file_to_budget(image_path, max_bytes)
    write_byte_stream(data, wav_path)
    return len(data)


def receive_file(wav_path: Path) -> Image.Image:
    """Decode a wav made by `send_file` back into an RGB picture."""
    with Image.open(io.BytesIO(read_byte_stream(wav_path))) as image:
        return image.convert("RGB")


def main() -> None:
    """Run the command line."""
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    commands = parser.add_subparsers(dest="command", required=True)
    send = commands.add_parser("send", help="image file -> output/image.wav")
    send.add_argument("--image", type=Path, default=DEFAULT_IMAGE)
    commands.add_parser("receive", help="output/image.wav -> output/received.png")
    args = parser.parse_args()

    if args.command == "send":
        sent = send_file(args.image, output_path(WAV_NAME))
        print(f"Sent {sent} bytes (~{sent * TONE_SECONDS:.0f} s of audio) to {WAV_NAME}")
    else:
        image = receive_file(output_path(WAV_NAME))
        image.save(output_path(RECEIVED_NAME))
        print(f"Wrote {RECEIVED_NAME} ({image.width}x{image.height})")


if __name__ == "__main__":
    main()
