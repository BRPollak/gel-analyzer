"""Package the canonical GelAnalyzer.png artwork as a Windows icon.

Preserve the source artwork and transparency. Run with the project's Pillow
environment on any supported build platform; no macOS conversion is needed.
"""

from pathlib import Path

from PIL import Image


ROOT = Path(__file__).resolve().parents[1]
ICON_SIZES = (16, 20, 24, 32, 40, 48, 64, 128, 256)


def main() -> None:
    with Image.open(ROOT / "packaging" / "GelAnalyzer.png") as source:
        artwork = source.convert("RGBA")
        artwork.save(
            ROOT / "packaging" / "GelAnalyzer.ico",
            format="ICO",
            sizes=[(size, size) for size in ICON_SIZES],
        )


if __name__ == "__main__":
    main()
