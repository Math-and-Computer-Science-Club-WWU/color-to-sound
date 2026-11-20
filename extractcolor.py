from pathlib import Path

from PIL import Image

from raster import Raster, write_values

HERE = Path(__file__).parent
IMAGE_PATH = HERE / "img" / "lake.webp"
OUT_PATH = HERE / "values.txt"


def extract_pixels(path, max_size=(16, 16)):
    with Image.open(path) as src:
        img = src.convert("RGB")
    img.thumbnail(max_size)  # in place, keeps aspect ratio
    return Raster(img.width, img.height, img.tobytes())


if __name__ == "__main__":
    raster = extract_pixels(IMAGE_PATH)  # extract first so a failure can't wipe the old file
    write_values(raster, OUT_PATH)