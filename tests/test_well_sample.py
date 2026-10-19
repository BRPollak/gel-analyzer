"""Opt-in validation of the user-provided TIFF; private pixels stay out of Git.

Run with GEL_ANALYZER_EXAMPLE_TIFF set to 20251106_pBRP112-117_midipreps.tif.
Band windows below were inspected independently, to the right of the wells;
they are validation inputs only and are never passed into the detector.
"""

from io import BytesIO
import os
from pathlib import Path

import numpy as np
from PIL import Image
import pytest

from gel_analyzer.image_io import load_tiff, orient_gel_image
from gel_analyzer.wells import detect_wells


@pytest.fixture(scope="module")
def oriented_sample():
    path = os.environ.get("GEL_ANALYZER_EXAMPLE_TIFF")
    if not path:
        pytest.skip("Set GEL_ANALYZER_EXAMPLE_TIFF to run the private sample regression.")
    source = Path(path).read_bytes()
    gel = orient_gel_image(load_tiff(source, Path(path).name))
    image = Image.open(BytesIO(gel.preview_png))
    image.load()
    assert image.size == (1896, 1179)
    assert gel.source_bytes == source
    return image


@pytest.mark.parametrize("dx", (-3, 0, 3))
@pytest.mark.parametrize("dy", (-5, 0, 5))
def test_sample_ladder_and_six_preps_are_separate_under_small_guide_changes(oriented_sample, dx, dy):
    image = oriented_sample
    before = image.tobytes()
    result = detect_wells(image, ((184 + dx, 190 + dy), (174 + dx, 1130 + dy)), expected_count=7)

    assert len(result.wells) == 7
    assert len(set(result.wells)) == 7
    assert all(first[3] <= second[1] for first, second in zip(result.lanes, result.lanes[1:]))
    pixels = np.asarray(image.convert("L"))
    windows = ((190, 327), (327, 459), (460, 589), (590, 720),
               (725, 854), (855, 986), (988, 1115))
    for well, lane, (top, bottom) in zip(result.wells, result.lanes, windows):
        assert 140 <= well.bounds[0] < well.bounds[2] <= 230
        assert top <= well.center[1] <= bottom
        # Dark band cores provide independent downstream evidence. The top
        # window contains the ladder; each following one contains a prep.
        profile = (pixels[top:bottom, 680:1220] < 90).sum(axis=1)
        band_rows = np.flatnonzero(profile >= 3) + top
        band_top, band_bottom = int(band_rows[0]), int(band_rows[-1]) + 1
        covered = max(0, min(lane[3], band_bottom) - max(lane[1], band_top))
        assert covered / (band_bottom - band_top) >= 0.89
        included = profile[max(0, lane[1] - top):min(bottom - top, lane[3] - top)].sum()
        assert included / profile.sum() >= 0.90
        # One lane cannot silently replace two groups or a tiny fragment.
        assert 90 <= lane[3] - lane[1] <= 150
    assert image.tobytes() == before
