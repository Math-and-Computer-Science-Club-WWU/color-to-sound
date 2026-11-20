"""Making sure an image file isn't bigger than the audio we are willing to send for it."""

import io
from pathlib import Path

from PIL import Image

SCALES = (1, 0.75, 0.5, 0.35, 0.25)  # tried in order: keep the size first, then shrink
QUALITIES = (90, 75, 60, 45)  # for each size, from best quality to smallest file


def fit_image_file_to_budget(path: Path, max_bytes: int) -> bytes:
    """Return the image file's bytes, re-compressed smaller only if the file exceeds `max_bytes`.

    A file that already fits is returned untouched, so nothing is lost. If nothing fits, the smallest
    attempt is returned.
    """
    original = Path(path).read_bytes()
    if len(original) <= max_bytes:
        return original

    with Image.open(path) as source:
        image = source.convert("RGB")
    attempt = original
    for scale in SCALES:
        size = (max(1, int(image.width * scale)), max(1, int(image.height * scale)))
        resized = image.resize(size, Image.Resampling.LANCZOS)
        for quality in QUALITIES:
            buffer = io.BytesIO()
            resized.save(buffer, "WEBP", quality=quality)
            attempt = buffer.getvalue()
            if len(attempt) <= max_bytes:
                return attempt
    return attempt
