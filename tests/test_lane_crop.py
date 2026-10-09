"""Manual lane bounds and crop pixels are checked against independent fixtures."""

from io import BytesIO
import importlib.util

import numpy as np
from PIL import Image
import pytest

from gel_analyzer.lane_crop import (
    LaneAdjustmentError,
    crop_lanes,
    validate_lane_adjustments,
)
from gel_analyzer.wells import Well
from gel_analyzer import wells as wells_module


WELLS = (
    Well((30, 20, 42, 40), (36, 30)),
    Well((35, 60, 48, 90), (41.5, 75)),
)
LANES = ((30, 17, 80, 45), (35, 61, 80, 97))
SIZE = (100, 110)


def _adjusted():
    return validate_lane_adjustments(WELLS, LANES, 80, SIZE)


def test_each_well_gets_its_own_adjusted_height_with_horizontal_bounds_fixed():
    adjusted = _adjusted()

    assert [well.bounds for well in adjusted] == [(30, 17, 42, 45), (35, 61, 48, 97)]
    assert [well.center for well in adjusted] == [(36, 31), (41.5, 79)]
    assert WELLS[0].bounds == (30, 20, 42, 40)
    assert WELLS[1].bounds == (35, 60, 48, 90)


def test_crop_has_left_and_vertical_padding_preserves_gaps_and_translates_geometry():
    values = np.arange(110 * 100, dtype=np.uint16).reshape(110, 100) * 3 + 17
    image = Image.fromarray(values)

    result = crop_lanes(image, _adjusted(), 80)

    assert result.crop_box == (27, 14, 80, 100)
    assert (result.width, result.height) == (53, 86)
    assert [well.bounds for well in result.wells] == [(3, 3, 15, 31), (8, 47, 21, 83)]
    assert [well.center for well in result.wells] == [(9, 17), (14.5, 65)]
    assert result.lanes == ((3, 3, 53, 31), (8, 47, 53, 83))
    with Image.open(BytesIO(result.preview_png)) as cropped:
        np.testing.assert_array_equal(np.asarray(cropped), values[14:100, 27:80])
        # Rows in the gap between lanes remain part of the contiguous crop.
        assert cropped.getpixel((10, 35)) == int(values[49, 37])


def test_left_padding_scales_with_original_width():
    image = Image.new("L", (1000, 110), 42)
    result = crop_lanes(image, WELLS, 900)

    assert result.crop_box == (20, 17, 900, 93)
    assert result.width == 880


@pytest.mark.parametrize(
    "height,top,bottom,expected_top,expected_bottom",
    [(1000, 200, 800, 190, 810), (110, 1, 108, 0, 110),
     (110, 0, 110, 0, 110), (50, 20, 25, 17, 28)],
)
def test_vertical_buffer_scales_with_height_and_clips_to_available_pixels(
    height, top, bottom, expected_top, expected_bottom,
):
    values = np.arange(height * 100, dtype=np.uint16).reshape(height, 100)
    well = Well((30, top, 42, bottom), (36, (top + bottom) / 2))

    result = crop_lanes(Image.fromarray(values), (well,), 80)

    assert result.crop_box == (27, expected_top, 80, expected_bottom)
    assert result.height == expected_bottom - expected_top
    assert result.wells[0].bounds[1::2] == (top - expected_top, bottom - expected_top)
    with Image.open(BytesIO(result.preview_png)) as cropped:
        np.testing.assert_array_equal(
            np.asarray(cropped), values[expected_top:expected_bottom, 27:80],
        )


def test_image_edges_clip_margin_and_support_one_pixel_lanes_that_touch():
    wells = (Well((1, 0, 8, 1), (4.5, 0.5)), Well((2, 1, 9, 10), (5.5, 5.5)))
    lanes = ((1, 0, 20, 1), (2, 1, 20, 10))
    adjusted = validate_lane_adjustments(wells, lanes, 20, (20, 10))

    result = crop_lanes(Image.new("L", (20, 10), 123), adjusted, 20)

    assert result.crop_box == (0, 0, 20, 10)
    assert result.lanes == lanes
    assert (result.width, result.height) == (20, 10)


def test_shared_right_may_touch_rightmost_well_but_not_cut_it():
    lanes = ((30, 20, 48, 40), (35, 60, 48, 90))
    assert validate_lane_adjustments(WELLS, lanes, 48, SIZE) == WELLS
    assert crop_lanes(Image.new("L", SIZE), WELLS, 48).width == 21


def test_finite_integer_valued_numeric_coordinates_are_accepted():
    lanes = ((np.int64(30), 17.0, 80.0, np.float64(45)), (35.0, 61, 80, 97))

    adjusted = validate_lane_adjustments(WELLS, lanes, np.float64(80), SIZE)

    assert adjusted == _adjusted()
    assert all(type(value) is int for well in adjusted for value in well.bounds)


@pytest.mark.parametrize("bad", [True, np.bool_(False), "80", None, float("nan"), float("inf"), 79.5])
def test_right_edge_requires_a_finite_integer_number(bad):
    with pytest.raises(LaneAdjustmentError, match="whole-pixel"):
        validate_lane_adjustments(WELLS, LANES, bad, SIZE)


@pytest.mark.parametrize("bad", [True, np.bool_(False), "17", None, float("nan"), -float("inf"), 17.5])
def test_lane_bounds_reject_boolean_text_nonfinite_and_fractional_values(bad):
    lanes = ((30, bad, 80, 45), LANES[1])

    with pytest.raises(LaneAdjustmentError, match="whole-pixel"):
        validate_lane_adjustments(WELLS, lanes, 80, SIZE)


@pytest.mark.parametrize("right", [-1, 0, 47, 101, 10**100])
def test_shared_right_outside_allowed_range_is_rejected_without_clamping(right):
    lanes = ((30, 17, right, 45), (35, 61, right, 97))

    with pytest.raises(LaneAdjustmentError, match="at or beyond"):
        validate_lane_adjustments(WELLS, lanes, right, SIZE)


@pytest.mark.parametrize("lanes", [(), LANES[:1], (*LANES, LANES[1])])
def test_adjustment_must_keep_exactly_one_lane_per_well(lanes):
    with pytest.raises(LaneAdjustmentError, match="exactly one"):
        validate_lane_adjustments(WELLS, lanes, 80, SIZE)


@pytest.mark.parametrize(
    "lanes,message",
    [
        (((29, 17, 80, 45), LANES[1]), "left edge"),
        (((30, 17, 79, 45), LANES[1]), "same shared right"),
        (((30, 17, 80, 17), LANES[1]), "one pixel high"),
        (((30, 46, 80, 45), LANES[1]), "one pixel high"),
        (((30, -1, 80, 45), LANES[1]), "inside the image"),
        ((LANES[0], (35, 61, 80, 111)), "inside the image"),
        (((30, 17, 80, 65), LANES[1]), "without overlapping"),
        (((30, 62, 80, 97), (35, 17, 80, 45)), "top-to-bottom"),
        (((30, 17, 80), LANES[1]), "left, top, right, and bottom"),
    ],
)
def test_invalid_lane_geometry_has_helpful_errors(lanes, message):
    with pytest.raises(LaneAdjustmentError, match=message):
        validate_lane_adjustments(WELLS, lanes, 80, SIZE)


def test_empty_wells_cannot_be_adjusted_or_cropped():
    with pytest.raises(LaneAdjustmentError, match="at least one"):
        validate_lane_adjustments((), (), 80, SIZE)
    with pytest.raises(LaneAdjustmentError, match="at least one"):
        crop_lanes(Image.new("L", SIZE), (), 80)


@pytest.mark.parametrize(
    "wells",
    [
        (Well((-1, 20, 42, 40), (20, 30)),),
        (Well((30, 20, 101, 40), (50, 30)),),
        (Well((30, 20, 42, 111), (36, 60)),),
        (Well((30, 20, 30, 40), (30, 30)),),
        (Well((30, 20, 42, 20), (36, 20)),),
        ({"bounds": (30, 20, 42, 40)},),
    ],
)
def test_crop_rejects_invalid_original_well_geometry(wells):
    with pytest.raises(LaneAdjustmentError, match="Well 1"):
        crop_lanes(Image.new("L", SIZE), wells, 80)


def test_crop_independently_checks_well_order_and_overlap():
    with pytest.raises(LaneAdjustmentError, match="top-to-bottom"):
        crop_lanes(Image.new("L", SIZE), WELLS[::-1], 80)
    overlapping = (WELLS[0], Well((35, 35, 48, 90), (41.5, 62.5)))
    with pytest.raises(LaneAdjustmentError, match="overlapping"):
        crop_lanes(Image.new("L", SIZE), overlapping, 80)


@pytest.mark.parametrize("dtype", ["<u2", ">u2"])
def test_sixteen_bit_crop_preserves_every_low_bit_and_original_pixel_storage(dtype):
    values = (np.arange(110 * 100, dtype=np.uint16).reshape(110, 100) * 5 + 19).astype(dtype)
    image = Image.fromarray(values)
    before, mode, size = image.tobytes(), image.mode, image.size

    result = crop_lanes(image, _adjusted(), 80)

    assert image.tobytes() == before
    assert image.mode == mode
    assert image.size == size
    with Image.open(BytesIO(result.preview_png)) as cropped:
        assert np.asarray(cropped).dtype.itemsize == 2
        np.testing.assert_array_equal(np.asarray(cropped), values[14:100, 27:80])


@pytest.mark.parametrize("mode,channels", [("RGB", 3), ("RGBA", 4), ("LA", 2)])
def test_color_and_alpha_pixels_survive_exactly(mode, channels):
    values = (np.arange(110 * 100 * channels).reshape(110, 100, channels) % 256).astype(np.uint8)
    image = Image.fromarray(values, mode=mode)
    before = image.tobytes()

    result = crop_lanes(image, _adjusted(), 80)

    assert image.tobytes() == before
    assert image.mode == mode
    with Image.open(BytesIO(result.preview_png)) as cropped:
        assert cropped.mode == mode
        np.testing.assert_array_equal(np.asarray(cropped), values[14:100, 27:80])


@pytest.mark.parametrize("mode", ["1", "L", "P"])
def test_other_supported_preview_modes_preserve_pixel_values(mode):
    image = Image.fromarray((np.indices((110, 100)).sum(axis=0) % 256).astype(np.uint8)).convert(mode)
    before = image.tobytes()

    result = crop_lanes(image, _adjusted(), 80)

    with Image.open(BytesIO(result.preview_png)) as cropped:
        np.testing.assert_array_equal(np.asarray(cropped), np.asarray(image)[14:100, 27:80])
        assert cropped.mode == mode
    assert image.tobytes() == before


@pytest.mark.parametrize("value", [-1, 65536])
def test_integer_values_outside_unsigned_sixteen_bit_range_are_not_truncated(value):
    image = Image.new("I", SIZE, value)

    with pytest.raises(LaneAdjustmentError, match="unsigned 16-bit"):
        crop_lanes(image, WELLS, 80)


def test_repeated_crop_copies_original_pixels_without_accumulating_transforms():
    image = Image.fromarray(np.arange(110 * 100, dtype=np.uint16).reshape(110, 100))

    first = crop_lanes(image, _adjusted(), 80)
    second = crop_lanes(image, _adjusted(), 80)

    assert first == second


def test_well_geometry_retained_across_module_reload_can_still_be_cropped():
    # Reexecute the actual model definitions without replacing the live
    # module. This reproduces session values created by another code version.
    spec = importlib.util.spec_from_file_location(wells_module.__name__, wells_module.__file__)
    reloaded = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(reloaded)
    retained = tuple(reloaded.Well(well.bounds, well.center) for well in WELLS)
    assert not isinstance(retained[0], Well)
    image = Image.new("I;16", SIZE, 32769)

    assert crop_lanes(image, retained, 80) == crop_lanes(image, WELLS, 80)
