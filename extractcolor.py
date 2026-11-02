from pathlib import Path

from PIL import Image

IMAGE_PATH = Path(__file__).parent / "img" / "colorgradiant.webp"


def extract_pixels(path, max_size=(32, 32)):
    """Return (width, height, pixels); pixels[i] is the (r, g, b) of pixel i, row by row."""
    img = Image.open(path).convert("RGB")
    img.thumbnail(max_size)  # shrinks in place, keeps aspect ratio
    width, height = img.size
    pixels = [img.getpixel((x, y)) for y in range(height) for x in range(width)]
    return width, height, pixels


if __name__ == "__main__":
    width, height, pixels = extract_pixels(IMAGE_PATH)
    for i, (r, g, b) in enumerate(pixels):
        print(f"P{i + 1} at ({i % width},{i // width}): R={r}, G={g}, B={b}")





























