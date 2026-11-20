"""Where the project's folders are."""

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
IMAGE_DIR = ROOT / "img"  # source images
OUTPUT_DIR = ROOT / "output"  # everything the program generates


def output_path(name: str) -> Path:
    """Return the path of a generated file inside output/, creating the folder if needed."""
    OUTPUT_DIR.mkdir(exist_ok=True)
    return OUTPUT_DIR / name
