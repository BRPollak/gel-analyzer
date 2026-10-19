"""Manual lane bounds and crop pixels are checked against independent fixtures."""

from io import BytesIO
import importlib.util

import numpy as np
from PIL import Image
import pytest

from gel_analyzer.lane_crop import (
    LaneAdjustmentError,
    append_lane,
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
    with pytest.raises(LaneAdjustmentError, match="could not be read"):
        validate_lane_adjustments(WELLS, LANES, bad, SIZE)


@pytest.mark.parametrize("bad", [True, np.bool_(False), "17", None, float("nan"), -float("inf")])
def test_lane_bounds_reject_boolean_text_and_nonfinite_values(bad):
    lanes = ((30, bad, 80, 45), LANES[1])

    with pytest.raises(LaneAdjustmentError, match="could not be read"):
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
        (((30, 17, 80, 17), LANES[1]), "too narrow"),
        (((30, 46, 80, 45), LANES[1]), "too narrow"),
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

    with pytest.raises(LaneAdjustmentError, match="cannot be cropped"):
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


APPEND_WELLS = (
    Well((30, 20, 42, 40), (36, 30)),
    Well((35, 60, 47, 80), (41, 70)),
)


def test_append_uses_bottom_endpoint_and_preserves_reviewed_geometry():
    points = ((36, 15), (46, 140))

    result = append_lane(APPEND_WELLS, points, 90, (100, 200))

    assert result[:-1] == APPEND_WELLS
    assert result[-1] == Well((40, 130, 52, 150), (46, 140))
    assert append_lane(APPEND_WELLS, points[::-1], 90, (100, 200)) == result


def test_append_below_covered_endpoint_uses_spacing_and_extrapolates_guide():
    points = ((36, 15), (42, 75))

    result = append_lane(APPEND_WELLS, points, 90, (100, 200))

    assert result[:-1] == APPEND_WELLS
    assert result[-1].bounds == (40, 100, 52, 120)
    repeated = append_lane(result, points, 90, (100, 200))
    assert repeated[:-1] == result
    assert repeated[-1].bounds == (44, 140, 56, 160)
    assert all(a.bounds[3] <= b.bounds[1] for a, b in zip(repeated, repeated[1:]))


def test_empty_detection_can_seed_a_lane_at_the_bottom_of_a_guide():
    points = ((20, 20), (30, 160))

    result = append_lane((), points, 90, (100, 200))

    assert len(result) == 1
    assert result[0].center == pytest.approx((30, 160), abs=0.5)
    assert result[0].bounds[2] - result[0].bounds[0] == 4
    assert result[0].bounds[3] - result[0].bounds[1] == 7
    assert append_lane((), points[::-1], 90, (100, 200)) == result
    # The manual seed is accepted by the normal adjustment/crop path.
    assert crop_lanes(Image.new("L", (100, 200)), result, 90).wells


@pytest.mark.parametrize(
    "points,right_edge,size,expected",
    [
        (((0, 0), (0, 100)), 80, (100, 100), (0, 96, 4, 100)),
        (((100, 0), (100, 100)), 80, (100, 100), (76, 96, 80, 100)),
        (((1, 0), (1, 10)), 1, (1, 10), (0, 6, 1, 10)),
    ],
)
def test_empty_append_clamps_all_image_and_shared_right_edges(points, right_edge, size, expected):
    result = append_lane((), points, right_edge, size)

    assert result[0].bounds == expected
    assert all(type(value) is int for value in result[0].bounds)


@pytest.mark.parametrize(
    "well,points,right_edge,expected",
    [
        (Well((0, 10, 10, 30), (5, 20)), ((12, 10), (0, 30)), 80, (0, 35, 10, 55)),
        (Well((80, 10, 90, 30), (85, 20)), ((78, 10), (90, 30)), 90, (80, 35, 90, 55)),
    ],
)
def test_append_handles_sloped_guide_extrapolation_at_horizontal_borders(well, points, right_edge, expected):
    result = append_lane((well,), points, right_edge, (100, 100))

    assert result == (well, Well(expected, ((expected[0] + expected[2]) / 2, 45)))


def test_append_can_use_remaining_full_height_when_ideal_gap_does_not_fit():
    result = append_lane(APPEND_WELLS, ((36, 15), (42, 75)), 90, (100, 100))

    assert result[:-1] == APPEND_WELLS
    assert result[-1].bounds[1::2] == (80, 100)


@pytest.mark.parametrize("height", [81, 90, 99])
def test_append_shrinks_new_lane_to_remaining_space_without_moving_existing_lanes(height):
    result = append_lane(APPEND_WELLS, ((36, 15), (42, 75)), 90, (100, height))

    assert result[:-1] == APPEND_WELLS
    assert result[-1].bounds[1::2] == (80, height)
    assert crop_lanes(Image.new("L", (100, height)), result, 90).height == height - 17


def test_append_at_image_bottom_trims_only_one_row_from_last_lane():
    result = append_lane(APPEND_WELLS, ((36, 15), (42, 75)), 90, (100, 80))

    assert result[0] == APPEND_WELLS[0]
    assert result[1] == Well((35, 60, 47, 79), (41, 69.5))
    assert result[-1].bounds[1::2] == (79, 80)
    # The prior reviewed tuple remains available for back/revise operations.
    assert APPEND_WELLS[-1].bounds == (35, 60, 47, 80)


def test_append_at_image_bottom_uses_gap_above_one_pixel_lane():
    originals = (APPEND_WELLS[0], Well((35, 79, 47, 80), (41, 79.5)))

    result = append_lane(originals, ((36, 15), (42, 75)), 90, (100, 80))

    assert result[0] == originals[0]
    assert result[1] == Well((35, 78, 47, 79), (41, 78.5))
    assert result[-1].bounds[1::2] == (79, 80)


def test_repeated_append_at_image_bottom_keeps_every_lane_editable_and_crop_valid():
    result = APPEND_WELLS
    for count in range(3, 9):
        result = append_lane(result, ((36, 15), (42, 75)), 90, (100, 80))

        assert len(result) == count
        assert result[0] == APPEND_WELLS[0]
        assert result[-1].bounds[1::2] == (79, 80)
        assert all(a.bounds[3] <= b.bounds[1] for a, b in zip(result, result[1:]))
        cropped = crop_lanes(Image.new("L", (100, 80)), result, 90)
        assert len(cropped.wells) == count
        assert all(well.bounds[1] < well.bounds[3] for well in cropped.wells)


def test_append_reports_only_the_physical_one_lane_per_image_row_limit():
    originals = tuple(Well((0, y, 1, y + 1), (0.5, y + 0.5)) for y in range(8))

    with pytest.raises(LaneAdjustmentError, match="no room for another lane"):
        append_lane(originals, ((0, 0), (0, 8)), 1, (1, 8))


@pytest.mark.parametrize(
    "wells,points,right_edge,size,message",
    [
        (APPEND_WELLS[::-1], ((36, 15), (42, 75)), 90, (100, 200), "top-to-bottom"),
        ((APPEND_WELLS[0], Well((35, 35, 47, 55), (41, 45))), ((36, 15), (42, 75)), 90, (100, 200), "overlapping"),
        ((Well((-1, 0, 8, 20), (3.5, 10)),), ((36, 15), (42, 75)), 90, (100, 200), "inside the confirmed"),
        (APPEND_WELLS, ((36, 15), (42, 75)), 46, (100, 200), "at or beyond"),
        ((), ((36, 15), (42, 75)), 0, (100, 200), "at or beyond"),
        ((), ((36, 15), (42, 75)), 101, (100, 200), "at or beyond"),
        ((), ((36, 15), (42, 75)), 80.5, (100, 200), "could not be read"),
        ((), ((36, 15), (42, 75)), 90, (100.5, 200), "could not be read"),
        ((), (), 90, (100, 200), "two points"),
        ((), ((36, 15), (42, 15)), 90, (100, 200), "generally vertical"),
        ((), ((36, 15), (42, 17)), 90, (100, 200), "generally vertical"),
        ((), ((36, 15), (36, 17)), 90, (100, 200), "too short"),
        ((), ((36, 15), (42, 201)), 90, (100, 200), "inside the confirmed"),
    ],
)
def test_append_validates_existing_geometry_and_guide(wells, points, right_edge, size, message):
    with pytest.raises(LaneAdjustmentError, match=message):
        append_lane(wells, points, right_edge, size)
