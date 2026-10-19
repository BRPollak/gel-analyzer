"""Independent well fixtures exercise geometry, evidence, and source precision."""

import json

import numpy as np
from PIL import Image, ImageDraw, ImageFilter
import pytest

from gel_analyzer.wells import SelectionError, _detect_supported_wells, detect_wells, validate_line


BOUNDS = ((34, 20, 49, 41), (36, 58, 51, 86), (37, 111, 52, 122), (38, 149, 54, 184))
GUIDE = ((41, 20), (46, 184))


def _gel(contrasts=(80, 80, 80, 80), dtype=np.uint8):
    values = np.full((220, 240), 120, dtype=float)
    for (left, top, right, bottom), contrast in zip(BOUNDS, contrasts):
        values[top:bottom, left:right] += contrast
    if np.dtype(dtype).itemsize == 2:
        values = values * 193 + 17
    return Image.fromarray(values.astype(dtype))


@pytest.mark.parametrize("contrasts", [(80,) * 4, (-80,) * 4, (80, 8, -70, -8)])
def test_detects_independent_bounds_with_unequal_spacing_heights_and_contrast(contrasts):
    result = detect_wells(_gel(contrasts), GUIDE, expected_count=4)

    assert len(result.wells) == len(BOUNDS)
    assert not result.warnings
    for well, expected, lane in zip(result.wells, BOUNDS, result.lanes):
        # Subpixel guide rounding permits one pixel horizontally. These crisp
        # independently specified vertical edges must be recovered exactly.
        np.testing.assert_allclose(well.bounds, expected, atol=1)
        assert well.bounds[1::2] == expected[1::2]
        left, top, right, bottom = well.bounds
        assert well.center == ((left + right) / 2, (top + bottom) / 2)
        assert lane == (left, top, 240, bottom)
        assert all(type(coordinate) is int for coordinate in lane)
    # Geometry is directly serializable by the local interaction component.
    json.dumps(result.lanes)


def test_reversed_click_order_is_identical_and_sloping_guide_keeps_horizontal_lanes():
    image = _gel()
    forward = detect_wells(image, GUIDE, expected_count=4)

    assert detect_wells(image, GUIDE[::-1], expected_count=4) == forward
    assert validate_line(GUIDE[::-1], image.size) == GUIDE
    assert [lane[1::2] for lane in forward.lanes] == [bounds[1::2] for bounds in BOUNDS]


def test_single_well_does_not_require_an_inter_well_gap_or_assumed_spacing():
    image = Image.new("L", (120, 120), 100)
    ImageDraw.Draw(image).rectangle((30, 20, 45, 79), fill=180)

    result = detect_wells(image, ((38, 20), (38, 80)), expected_count=1)

    assert [well.bounds for well in result.wells] == [(30, 20, 46, 80)]
    assert result.lanes == ((30, 20, 120, 80),)
    assert not result.warnings


def test_selection_range_excludes_visible_wells_above_and_below():
    result = detect_wells(_gel(), ((43, 58), (44, 122)), expected_count=2)

    assert len(result.wells) == 2
    assert [well.bounds[1::2] for well in result.wells] == [(58, 86), (111, 122)]


def test_small_endpoint_cuts_complete_existing_wells_without_inventing_edges():
    result = detect_wells(_gel(), ((41, 25), (46, 180)), expected_count=4)

    assert [well.bounds[1::2] for well in result.wells] == [bounds[1::2] for bounds in BOUNDS]
    assert any("beyond a guide endpoint" in warning for warning in result.warnings)


def test_downstream_bands_keep_supported_outlines_and_disclose_missing_well_inference():
    image = _gel()
    expected = detect_wells(image, GUIDE, expected_count=4)
    values = np.asarray(image).copy()
    # Very strong lane bands, including at y positions with no well, lie
    # outside the discovery strip and its nearby boundary-refinement margin.
    values[4:205:3, 90:230] = 0
    values[43:55, 95:115] = 255
    changed = detect_wells(Image.fromarray(values), GUIDE, expected_count=4)

    assert changed == expected
    values[:, :80] = 120
    inferred = detect_wells(Image.fromarray(values), GUIDE, expected_count=4)
    assert len(inferred.wells) == len(inferred.lanes) == 4
    assert any("4 position(s) were inferred" in warning for warning in inferred.warnings)


@pytest.mark.parametrize("value", [0, 120, 255])
def test_absent_wells_return_requested_geometry_with_inference_warning(value):
    result = detect_wells(Image.new("L", (240, 220), value), GUIDE, expected_count=4)

    assert len(result.wells) == len(result.lanes) == 4
    assert any("4 position(s) were inferred" in warning for warning in result.warnings)
    assert not any("No wells" in warning for warning in result.warnings)


@pytest.mark.parametrize("seed", range(5))
def test_noise_and_isolated_hot_pixels_do_not_count_as_supported_wells(seed):
    rng = np.random.default_rng(seed)
    values = rng.normal(120, 4, (220, 240)).clip(0, 255).astype(np.uint8)
    values[rng.integers(20, 184, 20), rng.integers(25, 61, 20)] = 255

    result = detect_wells(Image.fromarray(values), GUIDE, expected_count=4)

    assert len(result.wells) == len(result.lanes) == 4
    assert any("4 position(s) were inferred" in warning for warning in result.warnings)


def test_smooth_illumination_gradient_requires_inferred_wells():
    ys, xs = np.mgrid[:220, :240]
    image = Image.fromarray((80 + xs * 0.1 + ys * 0.2).astype(np.uint8))

    result = detect_wells(image, GUIDE, expected_count=4)
    assert len(result.wells) == len(result.lanes) == 4
    assert any("4 position(s) were inferred" in warning for warning in result.warnings)


def test_moderate_noise_and_soft_edges_retain_known_wells():
    image = _gel((40, -40, 30, -30)).filter(ImageFilter.GaussianBlur(0.7))
    rng = np.random.default_rng(14)
    values = np.asarray(image).astype(float) + rng.normal(0, 1.5, (220, 240))

    result = detect_wells(Image.fromarray(values.clip(0, 255).astype(np.uint8)), GUIDE, expected_count=4)

    assert len(result.wells) == 4
    for well, expected in zip(result.wells, BOUNDS):
        np.testing.assert_allclose(well.bounds, expected, atol=2)


def test_faint_wells_next_to_strong_wells_survive_moderate_noise():
    rng = np.random.default_rng(4)
    values = np.asarray(_gel((80, 8, -70, -8))).astype(float)
    values += rng.normal(0, 1.5, values.shape)

    result = detect_wells(Image.fromarray(values.clip(0, 255).astype(np.uint8)), GUIDE, expected_count=4)

    assert len(result.wells) == 4
    for well, expected in zip(result.wells, BOUNDS):
        np.testing.assert_allclose(well.bounds, expected, atol=1)
    assert any("Low contrast" in warning for warning in result.warnings)


def test_outlined_wells_include_top_and_bottom_caps():
    image = Image.new("L", (240, 220), 120)
    for left, top, right, bottom in BOUNDS:
        ImageDraw.Draw(image).rectangle((left, top, right - 1, bottom - 1), outline=200, width=4)

    result = detect_wells(image, GUIDE, expected_count=4)

    assert [well.bounds for well in result.wells] == list(BOUNDS)


@pytest.mark.parametrize("height,gap", [(220, 3), (700, 3), (700, 10)])
def test_clear_gaps_between_close_wells_are_not_closed_by_smoothing(height, gap):
    values = np.full((height, 240), 120, np.uint8)
    values[20:40, 34:49] = 200
    values[40 + gap:60 + gap, 34:49] = 200

    result = detect_wells(Image.fromarray(values), ((41, 20), (41, 60 + gap)), expected_count=2)

    assert [well.bounds for well in result.wells] == [(34, 20, 49, 40), (34, 40 + gap, 49, 60 + gap)]


@pytest.mark.parametrize("intensity", [0, 150, 180, 230])
def test_nearby_downstream_band_does_not_shift_well_boundary(intensity):
    values = np.full((220, 240), 120, np.uint8)
    values[20:40, 34:49] = 200
    values[21:39, 59:70] = intensity

    result = detect_wells(Image.fromarray(values), ((41, 20), (41, 40)), expected_count=1)

    assert [well.bounds for well in result.wells] == [(34, 20, 49, 40)]


@pytest.mark.parametrize("left,right,x", [(0, 12, 6), (110, 120, 115)])
def test_physical_image_edges_produce_clipped_half_open_bounds(left, right, x):
    values = np.full((100, 120), 100, np.uint8)
    values[:18, left:right] = 180
    values[60:, left:right] = 180

    result = detect_wells(Image.fromarray(values), ((x, 0), (x, 100)), expected_count=2)

    assert [well.bounds for well in result.wells] == [(left, 0, right, 18), (left, 60, right, 100)]
    assert result.lanes == ((left, 0, 120, 18), (left, 60, 120, 100))
    assert any("image edge" in warning for warning in result.warnings)


@pytest.mark.parametrize("dtype", ["<u2", ">u2"])
def test_sixteen_bit_detection_preserves_original_mode_bytes_and_low_bits(dtype):
    image = _gel(dtype=dtype)
    before, mode, size = image.tobytes(), image.mode, image.size

    result = detect_wells(image, GUIDE, expected_count=4)

    assert len(result.wells) == 4
    assert image.tobytes() == before
    assert image.mode == mode
    assert image.size == size
    assert image.getpixel((0, 0)) == 120 * 193 + 17


@pytest.mark.parametrize("mode", ["1", "L", "LA", "P", "RGB", "RGBA", "I"])
def test_supported_modes_do_not_modify_source_pixels(mode):
    image = _gel().convert(mode, dither=Image.Dither.NONE)
    before = image.tobytes()

    result = detect_wells(image, GUIDE, expected_count=4)

    assert len(result.wells) == 4
    assert image.mode == mode
    assert image.tobytes() == before


@pytest.mark.parametrize("mode", ["LA", "RGBA"])
def test_transparency_is_reported_without_modifying_pixels(mode):
    image = _gel().convert(mode)
    image.putalpha(100)
    before = image.tobytes()

    with pytest.raises(SelectionError, match="transparent"):
        detect_wells(image, GUIDE, expected_count=4)

    assert image.tobytes() == before


@pytest.mark.parametrize(
    "points,message",
    [
        ([], "two points"),
        (((20, 20),), "two points"),
        (((20, 20), (20, 20)), "same place"),
        (((20, 20), (20, 24)), "too short"),
        (((20, 20), (80, 22)), "vertical"),
        (((-1, 20), (20, 80)), "inside"),
        (((20, 20), (20, 221)), "inside"),
        (((20, float("nan")), (20, 80)), "could not be read"),
        (((20, 20), (float("inf"), 80)), "could not be read"),
        (((20, "not a number"), (20, 80)), "two points"),
    ],
)
def test_invalid_guide_reports_helpful_instruction(points, message):
    with pytest.raises(SelectionError, match=message):
        validate_line(points, (240, 220))


def test_boundary_coordinates_are_valid_points():
    assert validate_line(((240, 220), (240, 0)), (240, 220)) == ((240, 0), (240, 220))


def _fragmented_well_gel(seed):
    """Synthetic thin rims over an uneven field, independent of sample pixels."""
    ys, xs = np.mgrid[:1180, :1200]
    values = 150 + ys * 0.002 - xs * 0.01 - 9 * np.exp(-((xs - 210) / 60) ** 2)
    expected = []
    for index, top in enumerate((205, 340, 472, 603, 735, 868, 1002)):
        left, right, bottom = 164 - index, 209 - index * 2, top + 108
        expected.append((left, top, right, bottom))
        for row in range(top, bottom):
            fraction = (row - top) / (bottom - top)
            drift = int(2 * np.sin(fraction * np.pi * 2))
            strength = (10 + index * 2) * (0.6 + 0.4 * np.sin(fraction * np.pi * 3) ** 2)
            values[row, left + drift:left + drift + 4] -= strength
            values[row, right + drift - 4:right + drift] -= strength
            values[row, left + drift + 5:left + drift + 9] += strength * 0.7
        values[top:top + 3, left:right] -= 6
        values[bottom - 3:bottom, left:right] += 6
    values += np.random.default_rng(seed).normal(0, 4, values.shape)
    return Image.fromarray(values.clip(0, 255).astype(np.uint8)), expected


@pytest.mark.parametrize("seed", range(5))
def test_faint_fragmented_rims_recover_complete_separate_lanes(seed):
    image, expected = _fragmented_well_gel(seed)
    before = image.tobytes()

    result = detect_wells(image, ((184, 190), (174, 1130)), expected_count=7)

    assert len(result.wells) == len(expected)
    assert any("Low contrast" in warning for warning in result.warnings)
    for well, lane, (left, top, _, bottom) in zip(result.wells, result.lanes, expected):
        # Matching a count alone would miss the old failure: two fragments in
        # one prep substituted for a missed or substantially truncated lane.
        covered = max(0, min(bottom, lane[3]) - max(top, lane[1]))
        assert covered / (bottom - top) >= 0.87
        assert abs(lane[0] - left) <= 3
        assert top <= well.center[1] <= bottom
        assert lane[3] - lane[1] <= (bottom - top) * 1.2
    assert all(first[3] <= second[1] for first, second in zip(result.lanes, result.lanes[1:]))
    assert len(set(result.wells)) == len(result.wells)
    assert image.tobytes() == before


@pytest.mark.parametrize("seed", range(12))
def test_full_height_noisy_textured_background_does_not_trigger_faint_recovery(seed):
    rng = np.random.default_rng(seed)
    ys, xs = np.mgrid[:1180, :400]
    values = 120 + xs * 0.02 + ys * 0.003 + rng.normal(0, 4, xs.shape)
    values[rng.integers(190, 1130, 80), rng.integers(155, 210, 80)] = 255
    image = Image.fromarray(values.clip(0, 255).astype(np.uint8))

    result = _detect_supported_wells(image, ((184, 190), (174, 1130)))

    assert result.wells == result.lanes == ()


@pytest.mark.parametrize("seed", range(3))
def test_faint_recovery_preserves_clear_gaps_next_to_strong_wells(seed):
    ys, xs = np.mgrid[:700, :600]
    values = 120 + xs * 0.002 + np.zeros_like(ys, dtype=float)
    expected = ((30, 90), (98, 158), (166, 226), (234, 294))
    for (top, bottom), contrast in zip(expected, (80, 8, -60, -8)):
        values[top:bottom, 90:110] += contrast
    values += np.random.default_rng(seed).normal(0, 1.5, values.shape)

    result = detect_wells(
        Image.fromarray(values.clip(0, 255).astype(np.uint8)),
        ((100, 20), (100, 310)), expected_count=4,
    )

    assert len(result.wells) == 4
    for well, bounds in zip(result.wells, expected):
        np.testing.assert_allclose(well.bounds[1::2], bounds, atol=1)
    assert all(first[3] <= second[1] for first, second in zip(result.lanes, result.lanes[1:]))


@pytest.mark.parametrize("seed", (2, 6, 11))
def test_blurred_random_texture_is_not_promoted_to_a_set_of_faint_lanes(seed):
    rng = np.random.default_rng(seed)
    ys, xs = np.mgrid[:1180, :400]
    values = 120 + xs * 0.02 + ys * 0.003 + rng.normal(0, 4, xs.shape)
    image = Image.fromarray(values.clip(0, 255).astype(np.uint8)).filter(ImageFilter.GaussianBlur(0.6))

    result = _detect_supported_wells(image, ((184, 190), (174, 1130)))

    # The conservative detector has an existing limitation on correlated
    # texture: a few small weak fragments can survive. Recovery must not turn
    # those into the 13–15 proposed lanes seen without a contrast prerequisite.
    assert len(result.wells) <= 2
    assert all(well.bounds[3] - well.bounds[1] <= 24 for well in result.wells)
    assert any("Low contrast" in warning for warning in result.warnings)
