# color-to-sound
This is a side project for the m/cs club.

## Run

Requires Python 3, [Pillow](https://pypi.org/project/Pillow/) and [NumPy](https://numpy.org/).

```bash
pip install Pillow numpy
python extractcolor.py    # image -> values.txt (width height, then one "r g b" line per pixel)
python encodeColor.py     # values.txt -> out.wav (header tones, then 7 tones per pixel)
python assembleImage.py   # out.wav -> out.png (decodes the tones and rebuilds the image)
```

Set the source image with `IMAGE_PATH` in `extractcolor.py`. Images are shrunk to at most 16x16
because the pixel index is a single tone (256 values).
