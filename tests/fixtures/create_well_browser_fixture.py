"""Make a TIFF for exercising the actual upload/orientation/overlay workflow.

Run from the project root with the project's Python. The output is ignored by
Git. After Rotate and Orient + Confirm, the gel is 520 x 360 with four bright
wells at the bounds below; the dark downstream bands must not become wells.
"""

from pathlib import Path

import numpy as np
from PIL import Image


WELLS = ((27, 36, 45, 52), (27, 93, 45, 120), (27, 192, 45, 218), (27, 268, 45, 291))


def main() -> None:
    pixels = np.full((360, 520), 24000, dtype=np.uint16)
    for left, top, right, bottom in WELLS:
        pixels[top:bottom, left:right] = 51000
        pixels[top:bottom, 180:185] = 9000
    # A centered physical gel and surrounding bright background exercise the
    # existing crop/orientation pipeline rather than bypassing its UI gate.
    source = np.full((620, 460), 55000, dtype=np.uint16)
    source[50:570, 50:410] = pixels.T
    path = Path("output/well-verification/synthetic-wells16.tif")
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(source).save(path)
    print(f"Created {path}")
    print("Guide: (36, 36) to (36, 291), in either order.")
    print(f"Expected well bounds: {WELLS}")
    print("Expected lanes: replace each well's right edge with 520.")


if __name__ == "__main__":
    main()
