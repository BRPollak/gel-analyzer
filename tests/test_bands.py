from io import BytesIO

import numpy as np
from PIL import Image
import pytest

from gel_analyzer.bands import detect_bands, fit_ladder, band_measurements, validate_band_rows, band_review_image
from gel_analyzer.wells import Well


@pytest.mark.parametrize("orientation", ["wells_left", "wells_top"])
@pytest.mark.parametrize("contrast", [-80, 80])
def test_band_profiles_follow_migration_and_preserve_pixels(orientation, contrast):
    pixels = np.full((80, 240), 120, dtype=np.uint16)
    pixels[10:30, 8:16] = 200
    for position in (60, 110, 180):
        pixels[12:28, position - 2:position + 3] = 120 + contrast
    # Single bright pixel outside the center strip cannot establish a band.
    pixels[10, 85] = 65535
    pixels *= 100
    lanes = ((8, 10, 235, 30), (8, 45, 235, 65))
    wells = (Well((8, 10, 16, 30), (12, 20)), Well((8, 45, 16, 65), (12, 55)))
    if orientation == "wells_top":
        pixels = pixels.T
        lanes = tuple((t, l, b, r) for l, t, r, b in lanes)
        wells = tuple(Well((w.bounds[1], w.bounds[0], w.bounds[3], w.bounds[2]), w.center[::-1]) for w in wells)
    image = Image.fromarray(pixels)
    original = image.tobytes()
    bands = detect_bands(image, lanes, orientation, wells=wells)
    assert len(bands[0]) == 3
    assert bands[1] == []
    np.testing.assert_allclose([b["position"] for b in bands[0]], (60, 110, 180), atol=1.5)
    assert all(b["x" if orientation == "wells_top" else "y"] == 20 for b in bands[0])
    assert image.tobytes() == original


@pytest.mark.parametrize("orientation", ["wells_left", "wells_top"])
def test_ladder_calibration_and_manual_band_edits_use_correct_axis(orientation):
    positions = [20, 120, 220]
    ladder = {"preset": {"labels": ["10 kb", "1 kb", "100 bp"]}, "placements": [
        {"markerIndex": i, "x": 10 if orientation == "wells_top" else p,
         "y": p if orientation == "wells_top" else 10} for i, p in enumerate(positions)]}
    calibration = fit_ladder(ladder, orientation)
    assert calibration["r_squared"] == pytest.approx(1)
    assert calibration["unit"] == "bp"
    lanes = [(0, 0, 30, 240)] if orientation == "wells_top" else [(0, 0, 240, 30)]
    bands = validate_band_rows([{"Lane": 1, "Migration (px)": 70}, {"Lane": 1, "Migration (px)": 230}], lanes, orientation)
    rows = band_measurements(bands, calibration)
    assert rows[0]["Estimated size"] == pytest.approx(3162.278)
    assert rows[1]["Estimated size"] is None
    assert rows[1]["Status"] == "Outside calibration range"
    with pytest.raises(ValueError, match="existing lane"):
        validate_band_rows([{"Lane": 2, "Migration (px)": 70}], lanes, orientation)
    with pytest.raises(ValueError, match="between"):
        validate_band_rows([{"Lane": 1, "Migration (px)": 240}], lanes, orientation)


def test_ambiguous_ladder_labels_do_not_invent_a_calibration():
    ladder = {"preset": {"labels": ["500/517 bp", "100 bp"]}, "placements": [
        {"markerIndex": 0, "x": 30, "y": 10}, {"markerIndex": 1, "x": 90, "y": 10}]}
    with pytest.raises(ValueError, match="unambiguous"):
        fit_ladder(ladder)
    ladder["preset"]["labels"] = ["100 bp", "500 bp"]
    with pytest.raises(ValueError, match="decrease"):
        fit_ladder(ladder)


def test_blank_and_gradient_lanes_have_no_band_candidates():
    pixels = np.tile(np.arange(240, dtype=np.uint8), (80, 1))
    assert detect_bands(Image.fromarray(pixels), [(0, 0, 240, 80)]) == [[]]


def test_band_review_keeps_high_bit_depth_gray_visible():
    pixels = np.array([[0, 4096, 32768, 65535]], dtype=np.uint16)
    png = BytesIO()
    Image.fromarray(pixels).save(png, format="PNG")
    image = band_review_image(png.getvalue())
    assert np.asarray(image)[0, :, 0].tolist() == [0, 16, 128, 255]
