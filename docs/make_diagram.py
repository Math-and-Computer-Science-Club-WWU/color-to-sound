"""Draw docs/how-it-works.png, the one-page diagram of how an image becomes sound and back.

Run from the project root:  python docs/make_diagram.py
(Uses Windows fonts; change the FONT_* paths on another system.)
"""

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

OUTPUT = Path(__file__).with_name("how-it-works.png")
SIZE = (1900, 1400)
FONT_DIR = Path("C:/Windows/Fonts")

BOX_FILL, BOX_LINE = "#cfe2f3", "#3d5a80"
NOTE_FILL = "#cfe2f3"
INK = "#202020"
RED, GREEN, BLUE = "#d62828", "#2e8b3d", "#1a56db"
GREY = "#555555"
CHIP_LINE = "#c9c14a"


def font(name: str, size: int) -> ImageFont.FreeTypeFont:
    """Load a Windows font at a given size."""
    return ImageFont.truetype(str(FONT_DIR / name), size)


REGULAR, BOLD, MONO = "arial.ttf", "arialbd.ttf", "consola.ttf"


def wrap(draw: ImageDraw.ImageDraw, text: str, face: ImageFont.FreeTypeFont, width: int) -> list[str]:
    """Break text into lines no wider than `width` pixels."""
    lines: list[str] = []
    for paragraph in text.split("\n"):
        line = ""
        for word in paragraph.split():
            attempt = f"{line} {word}".strip()
            if draw.textlength(attempt, font=face) <= width:
                line = attempt
            else:
                lines.append(line)
                line = word
        lines.append(line)
    return lines


def text_block(draw, xy, text, face, width, fill=INK, centered=False, spacing=6) -> int:
    """Draw wrapped text with its top-left (or top-centre) at `xy`. Returns the y below the last line."""
    x, y = xy
    for line in wrap(draw, text, face, width):
        left = x - draw.textlength(line, font=face) / 2 if centered else x
        draw.text((left, y), line, font=face, fill=fill)
        y += face.size + spacing
    return y


def step_box(draw, box, title, code, body) -> None:
    """Draw one of the four numbered process boxes."""
    x0, y0, x1, _ = box
    draw.rectangle(box, fill=BOX_FILL, outline=BOX_LINE, width=3)
    centre = (x0 + x1) // 2
    y = text_block(draw, (centre, y0 + 14), title, font(BOLD, 30), x1 - x0 - 30, centered=True)
    y = text_block(draw, (centre, y + 2), code, font(MONO, 16), x1 - x0 - 24, fill=GREY, centered=True)
    text_block(draw, (centre, y + 10), body, font(REGULAR, 21), x1 - x0 - 40, centered=True)


def arrow(draw, start, end, thickness=64, head=60, label=None) -> None:
    """Draw a block arrow from `start` to `end` (horizontal or vertical), optionally with a label inside."""
    (x0, y0), (x1, y1) = start, end
    half = thickness // 2
    wing = 22  # how far the arrow head sticks out past the shaft
    if abs(x1 - x0) > abs(y1 - y0):  # horizontal
        sign = 1 if x1 > x0 else -1
        neck = x1 - sign * head
        points = [(x0, y0 - half), (neck, y0 - half), (neck, y0 - half - wing), (x1, y0),
                  (neck, y0 + half + wing), (neck, y0 + half), (x0, y0 + half)]
        label_at = ((x0 + neck) / 2, y0)
    else:  # vertical
        sign = 1 if y1 > y0 else -1
        neck = y1 - sign * head
        points = [(x0 - half, y0), (x0 - half, neck), (x0 - half - wing, neck), (x0, y1),
                  (x0 + half + wing, neck), (x0 + half, neck), (x0 + half, y0)]
        label_at = (x0, (y0 + neck) / 2)
    draw.polygon(points, fill=BOX_FILL)
    draw.line([*points, points[0]], fill=BOX_LINE, width=3)
    if label and abs(x1 - x0) > abs(y1 - y0):
        draw.text(label_at, label, font=font(BOLD, 22), fill=BOX_LINE, anchor="mm")
    elif label:  # vertical arrows stack the letters, like the original diagram
        face = font(BOLD, 24)
        step = 30
        top = label_at[1] - step * (len(label) - 1) / 2
        for number, letter in enumerate(label):
            draw.text((label_at[0], top + number * step), letter, font=face, fill=BOX_LINE, anchor="mm")


def chip(draw, x, y, label, colour=INK, width=None, sub=None) -> int:
    """Draw one tone as a little labelled chip. Returns the x where the next chip should start."""
    face = font(BOLD, 24)
    w = width or int(draw.textlength(label, font=face)) + 26
    draw.rectangle((x, y, x + w, y + 46), fill="#fffff0", outline=CHIP_LINE, width=2)
    draw.text((x + w / 2, y + 23), label, font=face, fill=colour, anchor="mm")
    if sub:
        draw.text((x + w / 2, y + 62), sub, font=font(REGULAR, 15), fill=GREY, anchor="mm")
    return x + w + 8


def draw_grid(draw, origin, label_fill=INK) -> None:
    """Draw the 3 x 3 example image, with P1 highlighted."""
    x0, y0 = origin
    cell_w, cell_h = 100, 76
    for index in range(9):
        row, col = divmod(index, 3)
        box = (x0 + col * cell_w, y0 + row * cell_h, x0 + (col + 1) * cell_w, y0 + (row + 1) * cell_h)
        draw.rectangle(box, fill="#ffeb00" if index == 0 else "#efefef", outline="#b0b0b0", width=2)
        draw.text((box[0] + 14, box[1] + 22), f"P{index + 1}", font=font(REGULAR, 28), fill=label_fill)


def cloud(draw, box, text) -> None:
    """Draw a thought-cloud (overlapping circles) with text inside."""
    x0, y0, x1, y1 = box
    blobs = [(0.0, 0.25, 0.45, 0.9), (0.2, 0.0, 0.7, 0.6), (0.45, 0.0, 0.95, 0.55), (0.6, 0.2, 1.0, 0.85),
             (0.25, 0.4, 0.8, 1.0), (0.05, 0.45, 0.5, 1.0)]
    w, h = x1 - x0, y1 - y0
    for outline in (True, False):  # outlines first, then fills on top, so the cloud has one clean edge
        for bx0, by0, bx1, by1 in blobs:
            rect = (x0 + bx0 * w, y0 + by0 * h, x0 + bx1 * w, y0 + by1 * h)
            if outline:
                draw.ellipse((rect[0] - 3, rect[1] - 3, rect[2] + 3, rect[3] + 3), fill=BOX_LINE)
            else:
                draw.ellipse(rect, fill=NOTE_FILL)
    centre_x, centre_y = (x0 + x1) // 2, (y0 + y1) // 2
    face = font(REGULAR, 25)
    lines = wrap(draw, text, face, int(w * 0.58))
    block_height = len(lines) * (face.size + 7)
    text_block(draw, (centre_x, centre_y - block_height / 2), text, face, int(w * 0.58), centered=True, spacing=7)


def draw_diagram() -> Image.Image:
    """Compose the whole diagram."""
    image = Image.new("RGB", SIZE, "white")
    draw = ImageDraw.Draw(image)
    draw.text((SIZE[0] // 2 - 60, 50), "Image \u2192 Sound \u2192 Image", font=font(REGULAR, 50), fill=INK, anchor="mm")

    # the picture on the left: what goes in, and where the rebuilt picture comes out
    draw.polygon([(60, 95), (360, 95), (360, 175), (230, 175), (210, 200), (190, 175), (60, 175)],
                 fill=BOX_FILL, outline=BOX_LINE)
    text_block(draw, (210, 108), "Example image\n3 x 3 pixels", font(REGULAR, 25), 280, centered=True, spacing=2)
    draw_grid(draw, (60, 215))
    text_block(draw, (210, 450), "The rebuilt picture appears in this same grid", font(REGULAR, 17), 300,
               fill=GREY, centered=True)

    # the four steps
    step_box(draw, (620, 150, 1040, 410), "1. Prepare",
             "Pixels: cable_channel/pixel_mode.py\nFile: common/image_budget.py",
             "Pixel preview: shrink the image and pull the R, G, B values out of every pixel.\n"
             "Exact copy: take the image file's own compressed bytes instead.")
    step_box(draw, (620, 650, 1040, 1010), "2. Encode",
             "Cable: cable_channel/pixel_mode.py\nAir: air_channel/transmitter.py",
             "Turn every number into a beep: a bigger number is a higher pitch.\n"
             "Cable: wrap each pixel in an index, separators and an end tone (right).\n"
             "Air: cut the data into packets, each with a start pattern and a checksum (right).")
    step_box(draw, (60, 905, 440, 1215), "3. Listen",
             "Cable: cable_channel/listener.py\nAir: air_channel/receiver.py",
             "Cut the sound into tiny slices and measure each beep's pitch (FFT) to get its number back.\n"
             "Air: find each packet's start pattern, check its CRC and skip damaged packets.")
    step_box(draw, (60, 570, 440, 800), "4. Assemble",
             "Pixels: cable_channel/pixel_mode.py\nLive view: live_decoding/",
             "Put each pixel at its index, or unpack the file bytes, to rebuild the picture. "
             "The window shows it filling in live.")

    # arrows between them
    arrow(draw, (380, 300), (610, 300), thickness=70)
    arrow(draw, (830, 420), (830, 640), thickness=84, label="Data")
    arrow(draw, (610, 960), (450, 960), thickness=70, label="Sound")
    arrow(draw, (250, 895), (250, 810), thickness=64, head=50)
    arrow(draw, (250, 562), (250, 502), thickness=64, head=40)
    draw.text((312, 850), "Numbers", font=font(BOLD, 22), fill=BOX_LINE, anchor="lm")
    draw.text((312, 530), "Picture", font=font(BOLD, 22), fill=BOX_LINE, anchor="lm")

    # note cloud
    cloud(draw, (1120, 40, 1860, 420),
          "Note: this sound is meant for a machine to read, not a person to enjoy: a sequence of "
          "discrete tones carries the data to the listener.")

    # key
    key = font(REGULAR, 19)
    draw.text((1130, 470), "Key:", font=font(BOLD, 21), fill=INK)
    rows = [("Value tone (any number 0-255)", INK), ("Red value's tone = R", RED), ("Green value's tone = G", GREEN),
            ("Blue value's tone = B", BLUE), ("Separation tone = S", INK),
            ("Pixel index (where it is in the image) = Ind", INK), ("End of pixel tone = E", INK)]
    for number, (label, colour) in enumerate(rows):
        draw.text((1130, 500 + number * 26), label, font=key, fill=colour)

    # cable channel: one pixel
    draw.rectangle((1130, 700, 1860, 880), fill=BOX_FILL, outline=BOX_LINE, width=3)
    draw.text((1495, 726), "Cable channel: encoding for one pixel", font=font(BOLD, 26), fill=INK, anchor="mm")
    x = 1160
    for label, colour, sub in (("Ind", INK, "high"), ("Ind", INK, "low"), ("B", BLUE, None), ("S", INK, None),
                               ("G", GREEN, None), ("S", INK, None), ("R", RED, None), ("E", INK, None)):
        x = chip(draw, x, 765, label, colour, width=70, sub=sub)
    draw.text((1495, 850), "R + G + B  =  pixel P1   (12.5 ms per tone, 8 tones per pixel)", font=font(REGULAR, 19),
              fill=GREY, anchor="mm")

    # air channel: one packet
    draw.rectangle((1130, 905, 1860, 1200), fill=BOX_FILL, outline=BOX_LINE, width=3)
    draw.text((1495, 931), "Air channel (speaker \u2192 microphone): one packet", font=font(BOLD, 26), fill=INK,
              anchor="mm")
    x = 1150
    for label, width, sub in (("A B A B", 120, "start pattern"), ("kind", 80, "file/pixels"), ("seq", 80, "position"),
                              ("aux", 80, "size"), ("32 data bytes", 190, "2 tones per byte"), ("CRC", 80, "checksum")):
        x = chip(draw, x, 975, label, INK, width=width, sub=sub)
    text_block(draw, (1150, 1062),
               "Every byte is sent as two 4-bit tones (16 pitches). The start pattern lets the listener find "
               "each packet wherever it lands, so a late start, noise, echo or clock drift only cost the "
               "packets they damage. The CRC catches a damaged packet. Sending each packet twice or three times "
               "fills in the gaps.", font(REGULAR, 19), 690, spacing=5)

    # the two channels and two results, along the bottom
    draw.line((60, 1240, 1840, 1240), fill=BOX_LINE, width=2)
    columns = [
        (60, "Cable / file channel", "Tones in a clean WAV file. Fast (12.5 ms tones), but one wrong tone can ruin "
                                    "the result. Not meant for a speaker and microphone."),
        (700, "Speaker \u2192 microphone channel", "Slow (40 ms tones) but built to survive a room. Packets with start "
                                                    "patterns, checksums and repeats."),
        (1340, "Two results", "Exact copy: the image file's bytes, identical to the original. Pixel preview: "
                              "shrunken, blurry, but visibly builds up pixel by pixel."),
    ]
    for x0, heading, body in columns:
        draw.text((x0, 1258), heading, font=font(BOLD, 24), fill=BOX_LINE)
        text_block(draw, (x0, 1294), body, font(REGULAR, 20), 500, spacing=5)
    return image


if __name__ == "__main__":
    draw_diagram().save(OUTPUT)
    print(f"Wrote {OUTPUT}")
