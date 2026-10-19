"""Render the original vector icon as SVG and a complete macOS .icns.

Run with the project's Pillow environment on macOS. All geometry is in a
1024-square coordinate system; no remote images or fonts are used.
"""

from pathlib import Path
import subprocess
import tempfile

from PIL import Image, ImageDraw


ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    # x, y, width, height, corner radius, fill. The pale left lane is a ladder;
    # the three turquoise lanes contain example gel bands.
    shapes = [
        (78, 78, 868, 868, 195, "#152b3b"),
        (162, 170, 700, 684, 48, "#0b1b29"),
        (162, 170, 700, 8, 4, "#365566"),
    ]
    for x in (226, 394, 562, 730):
        shapes.append((x, 218, 68, 24, 8, "#3d5869"))
    for y, width in ((306, 72), (376, 68), (448, 72), (524, 72), (610, 68), (716, 72)):
        shapes.append((260 - width // 2, y, width, 18, 9, "#e5edbd"))
    for x, bands in (
        (428, (344, 486, 662)),
        (596, (376, 524, 716)),
        (764, (318, 448, 610)),
    ):
        for y in bands:
            shapes.append((x - 46, y - 7, 92, 32, 16, "#123f47"))
            shapes.append((x - 38, y, 76, 18, 9, "#71e4cb"))

    # Supersampling preserves soft, clean corners at small Dock sizes.
    scale = 2
    icon = Image.new("RGBA", (1024 * scale, 1024 * scale))
    draw = ImageDraw.Draw(icon)
    for x, y, width, height, radius, fill in shapes:
        draw.rounded_rectangle(
            (x * scale, y * scale, (x + width) * scale, (y + height) * scale),
            radius=radius * scale,
            fill=fill,
        )
    svg = ['<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1024 1024">']
    svg += [
        f'<rect x="{x}" y="{y}" width="{width}" height="{height}" rx="{radius}" fill="{fill}"/>'
        for x, y, width, height, radius, fill in shapes
    ]
    svg.append("</svg>")
    (ROOT / "packaging" / "GelAnalyzer.svg").write_text("\n".join(svg) + "\n")
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
