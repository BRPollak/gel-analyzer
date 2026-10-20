"""Convert the shipped macOS artwork into a multi-resolution Windows icon.

The existing ICNS is the source of truth; this does not redraw or replace it.
Run with the project's Pillow environment on any supported build platform.
"""

from pathlib import Path

from PIL import Image


ROOT = Path(__file__).resolve().parents[1]
ICON_SIZES = (16, 20, 24, 32, 40, 48, 64, 128, 256)


def main() -> None:
    with Image.open(ROOT / "packaging" / "GelAnalyzer.icns") as source:
        artwork = source.convert("RGBA")
        artwork.save(
            ROOT / "packaging" / "GelAnalyzer.ico",
            format="ICO",
            sizes=[(size, size) for size in ICON_SIZES],
        )


if __name__ == "__main__":
    main()
