"""Preparing pictures for display, including the animation that brings the finished picture into focus."""

from PIL import Image

from common.modes import Mode

COARSEST_BLOCKS = 4  # the unpack animation starts with this many blocks across...
BLOCK_GROWTH = 1.45  # ...and gets finer by this factor each frame
BLEND_STEPS = 10  # frames used to fade the pixel preview into the smoothed picture
FILE_FRAME_MS = 85  # delay between frames of the unpack animation
PIXELS_FRAME_MS = 40  # delay between frames of the fade


def fit_preview(image: Image.Image, fit: tuple[int, int], blocky: bool = False) -> Image.Image:
    """Return a copy of `image` that fits inside `fit`.

    A blocky picture is enlarged with hard edges so that every pixel, byte or packet stays visible; anything
    else is only ever shrunk, smoothly.
    """
    preview = image.copy()
    if blocky:
        scale = min(fit[0] / image.width, fit[1] / image.height)
        size = (max(1, int(image.width * scale)), max(1, int(image.height * scale)))
        return preview.resize(size, Image.Resampling.NEAREST)
    preview.thumbnail(fit, Image.Resampling.LANCZOS)
    return preview


def reveal_frames(
    final: Image.Image,
    mode: Mode,
    current: Image.Image | None,
    fit: tuple[int, int],
) -> tuple[list[Image.Image], int]:
    """Frames that bring the finished picture into focus, and the delay between them in milliseconds.

    Pixel previews fade from the blocky picture that was on screen. Exact copies sharpen from coarse blocks,
    like a page loading, because their picture can only exist once every byte has arrived.
    """
    base = final.copy()
    base.thumbnail(fit, Image.Resampling.LANCZOS)
    if mode is Mode.PIXELS and current is not None:
        start = current.resize(base.size, Image.Resampling.NEAREST).convert("RGB")
        target = base.convert("RGB")
        return [Image.blend(start, target, step / BLEND_STEPS) for step in range(1, BLEND_STEPS + 1)], PIXELS_FRAME_MS

    frames = []
    blocks = COARSEST_BLOCKS
    while blocks < base.width:
        rows = max(1, round(blocks * base.height / base.width))
        blocky = base.resize((blocks, rows), Image.Resampling.BOX).resize(base.size, Image.Resampling.NEAREST)
        frames.append(blocky)
        blocks = int(blocks * BLOCK_GROWTH) + 1
    frames.append(base)
    return frames, FILE_FRAME_MS
