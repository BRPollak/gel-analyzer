"""Wells-at-top fixtures use real displayed XY; no preparation rotation."""

from io import BytesIO

import numpy as np
from PIL import Image
import pytest

from gel_analyzer.lane_crop import LaneAdjustmentError, append_lane, crop_lanes, validate_lane_adjustments
from gel_analyzer.wells import SelectionError, Well, detect_wells, validate_line


TOP = "wells_top"
WELLS = (Well((20, 30, 40, 42), (30, 36)), Well((60, 35, 90, 48), (75, 41.5)))
LANES = ((17, 30, 45, 80), (61, 35, 97, 80))


@pytest.mark.parametrize("dtype", [np.uint8, np.uint16])
@pytest.mark.parametrize("contrast", [80, -80])
def test_auto_detection_locates_columns_and_extends_downward_without_changing_source(dtype, contrast):
    bounds = ((20, 34, 41, 49), (58, 36, 86, 51), (111, 37, 122, 52), (149, 38, 184, 54))
    values = np.full((240, 220), 120, dtype=float)
    for left, top, right, bottom in bounds:
        values[top:bottom, left:right] += contrast
    if dtype == np.uint16:
        values = values * 193 + 17
    image = Image.fromarray(values.astype(dtype))
    before = image.tobytes()
    guide = ((20, 41), (184, 46))

    result = detect_wells(image, guide, workflow_orientation=TOP)

    assert len(result.wells) == 4
    for well, expected, lane in zip(result.wells, bounds, result.lanes):
        np.testing.assert_allclose(well.bounds, expected, atol=1)
        assert well.bounds[::2] == expected[::2]
        assert lane == (well.bounds[0], well.bounds[1], well.bounds[2], 240)
    assert detect_wells(image, guide[::-1], workflow_orientation=TOP) == result
    assert image.size == (220, 240)
    assert image.tobytes() == before


def test_horizontal_guide_validates_in_display_coordinates_and_reports_horizontal_errors():
    assert validate_line(((90, 20), (10, 25)), (100, 80), workflow_orientation=TOP) == ((10, 25), (90, 20))
    with pytest.raises(SelectionError, match="generally horizontal"):
        validate_line(((30, 10), (30, 70)), (100, 80), workflow_orientation=TOP)
    with pytest.raises(SelectionError, match="outside left and right"):
        validate_line(((30, 10), (32, 10)), (100, 80), workflow_orientation=TOP)


def test_manual_width_adjustment_keeps_well_depth_and_lane_order():
    adjusted = validate_lane_adjustments(WELLS, LANES, 80, (110, 100), workflow_orientation=TOP)
    assert [well.bounds for well in adjusted] == [(17, 30, 45, 42), (61, 35, 97, 48)]
    assert [well.center for well in adjusted] == [(31, 36), (79, 41.5)]
    with pytest.raises(LaneAdjustmentError, match="left-to-right"):
        validate_lane_adjustments(WELLS[::-1], LANES[::-1], 80, (110, 100), workflow_orientation=TOP)
    with pytest.raises(LaneAdjustmentError, match="bottom edge"):
        validate_lane_adjustments(WELLS, LANES, 47, (110, 100), workflow_orientation=TOP)


@pytest.mark.parametrize("dtype", ["<u2", ">u2"])
def test_crop_preserves_displayed_pixels_and_low_bits_with_top_and_side_margins(dtype):
    values = (np.arange(100 * 110, dtype=np.uint16).reshape(100, 110) * 3 + 17).astype(dtype)
    image = Image.fromarray(values)
    before = image.tobytes()
    adjusted = validate_lane_adjustments(WELLS, LANES, 80, image.size, workflow_orientation=TOP)

    crop = crop_lanes(image, adjusted, 80, workflow_orientation=TOP)

    assert crop.workflow_orientation == TOP
    assert crop.crop_box == (14, 27, 100, 80)
    assert (crop.width, crop.height) == (86, 53)
    assert [well.bounds for well in crop.wells] == [(3, 3, 31, 15), (47, 8, 83, 21)]
    assert crop.lanes == ((3, 3, 31, 53), (47, 8, 83, 53))
    with Image.open(BytesIO(crop.preview_png)) as copied:
        np.testing.assert_array_equal(np.asarray(copied), values[27:80, 14:100])
    assert image.tobytes() == before


def test_manual_recovery_appends_to_right_and_keeps_bottom_extent():
    added = append_lane(WELLS, ((15, 36), (160, 42)), 90, (200, 100), workflow_orientation=TOP)
    assert added[:-1] == WELLS
    assert added[-1].center[0] == pytest.approx(160, abs=0.5)
    assert added[-1].bounds[0] >= WELLS[-1].bounds[2]
    assert added[-1].bounds[3] <= 90
    assert crop_lanes(Image.new("L", (200, 100)), added, 90, workflow_orientation=TOP).lanes[-1][3] > 0
    seeded = append_lane((), ((15, 36), (160, 42)), 90, (200, 100), workflow_orientation=TOP)
    assert seeded[0].center == pytest.approx((160, 42), abs=0.5)


def test_manual_append_at_right_boundary_retains_every_lane_and_makes_one_column():
    added = append_lane(WELLS, ((15, 36), (85, 42)), 90, (90, 100), workflow_orientation=TOP)
    assert added[0] == WELLS[0]
    assert added[1].bounds[2] == 89
    assert added[2].bounds[::2] == (89, 90)
    assert all(first.bounds[2] <= second.bounds[0] for first, second in zip(added, added[1:]))


@pytest.mark.parametrize("contrast", [-70, 70])
def test_downward_band_evidence_expands_vertical_lanes_horizontally(contrast):
    values = np.full((360, 310), 120, dtype=np.int16)
    columns = ((30, 66), (100, 136), (170, 206), (240, 276))
    for left, right in columns:
        values[36:54, left:right] += 80
    guide = ((26, 45), (280, 45))
    original = detect_wells(Image.fromarray(values.astype(np.uint8)), guide, workflow_orientation=TOP)
    broad_bands = ((24, 72), (94, 142), (234, 282))
    for left, right in broad_bands:
        values[136:150, left:right] += contrast
        values[230:243, left:right] += contrast

    result = detect_wells(Image.fromarray(values.astype(np.uint8)), guide, workflow_orientation=TOP)

    assert result.wells == original.wells
    for index, (left, right) in zip((0, 1, 3), broad_bands):
        lane = result.lanes[index]
        assert (min(lane[2], right) - max(lane[0], left)) / (right - left) >= 0.9
    assert result.lanes[2] == original.lanes[2]
    assert all(first[2] <= second[0] for first, second in zip(result.lanes, result.lanes[1:]))
