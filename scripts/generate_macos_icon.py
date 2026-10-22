"""Package the canonical GelAnalyzer.png artwork as a complete macOS .icns.

Run with the project's Pillow environment on macOS. Preserve the source
artwork and transparency; only resize it for the required icon representations.
"""

from pathlib import Path
import subprocess
import tempfile

from PIL import Image


ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    with Image.open(ROOT / "packaging" / "GelAnalyzer.png") as source:
        if source.width != source.height or source.width < 1024:
            raise ValueError("Icon artwork must be square and at least 1024 pixels wide")
        icon = source.convert("RGBA")
    with tempfile.TemporaryDirectory(prefix="gel-analyzer-icon-") as temp:
        iconset = Path(temp) / "GelAnalyzer.iconset"
        iconset.mkdir()
        for size in (16, 32, 128, 256, 512):
            for density in (1, 2):
                suffix = "@2x" if density == 2 else ""
                icon.resize((size * density,) * 2, Image.Resampling.LANCZOS).save(
                    iconset / f"icon_{size}x{size}{suffix}.png"
                )
        subprocess.run(
            ["/usr/bin/iconutil", "--convert", "icns", "--output",
             str(ROOT / "packaging" / "GelAnalyzer.icns"), str(iconset)],
            check=True,
        )


if __name__ == "__main__":
    main()
