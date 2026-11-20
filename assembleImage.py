from pathlib import Path

from PIL import Image

from decodeSound import read_frames
from raster import Raster

HERE = Path(__file__).parent
SCALE = 20  # the image is tiny, so enlarge it to be viewable


def assemble(path):
    """Rebuild a Raster from a wav made by encodeColor.py."""
    frames = read_frames(path)
    width, height = next(frames)
    buf = bytearray(width * height * 3)  # pixels that never arrive stay black
    for i, b, g, r in frames:
        if i < width * height:
            buf[3 * i:3 * i + 3] = bytes((r, g, b))  # the index decides where it goes
    return Raster(width, height, bytes(buf))


if __name__ == "__main__":
    raster = assemble(HERE / "out.wav")
    img = Image.frombytes("RGB", (raster.width, raster.height), raster.data)
    img.resize((raster.width * SCALE, raster.height * SCALE), Image.Resampling.NEAREST).save(HERE / "out.png")
    print(f"Wrote out.png ({raster.width}x{raster.height} pixels)")
