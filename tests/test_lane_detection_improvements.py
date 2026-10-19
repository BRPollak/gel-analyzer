"""Outcome-based fixtures for automatic recovery and exact well counts."""

import numpy as np
from PIL import Image, ImageFilter
import pytest

from gel_analyzer.wells import SelectionError, detect_wells


WELL_ROWS = ((30, 66), (100, 136), (170, 206), (240, 276))
GUIDE = ((45, 26), (45, 280))


def _gel(*, rows=WELL_ROWS, contrasts=(80, 80, 80, 80)):
    values = np.full((310, 360), 120.0)
    for (top, bottom), contrast in zip(rows, contrasts):
        values[top:bottom, 36:54] += contrast
    return values


def _image(values):
    return Image.fromarray(values.astype(np.uint8))


def _coverage(lane, top, bottom):
    return max(0, min(lane[3], bottom) - max(lane[1], top)) / (bottom - top)


def _assert_ordered_lanes(result):
    assert len(result.lanes) == len(result.wells)
    assert all(first[3] <= second[1] for first, second in zip(result.lanes, result.lanes[1:]))
    assert all(0 <= left < right <= 360 and 0 <= top < bottom <= 310
               for left, top, right, bottom in result.lanes)


@pytest.mark.parametrize("band_contrast", (-70, 70))
def test_downstream_bands_recover_partial_lane_without_rewriting_well_outline(band_contrast):
    values = _gel()
    values[170:182, 36:54] = 120
    values[194:206, 36:54] = 120
    before_bands = detect_wells(_image(values), GUIDE)
    for left, right in ((135, 149), (235, 247)):
        values[170:206, left:right] += band_contrast

    recovered = detect_wells(_image(values), GUIDE)

    assert recovered.wells == before_bands.wells
    assert len(recovered.lanes) == 4
    assert _coverage(recovered.lanes[2], 170, 206) >= 0.90
    assert recovered.lanes[2][3] - recovered.lanes[2][1] <= 46
    # No band signal is needed to retain the other three empty lanes.
    for index in (0, 1, 3):
        assert recovered.lanes[index] == before_bands.lanes[index]
    _assert_ordered_lanes(recovered)


def test_clear_unequal_well_heights_are_not_forced_to_a_typical_thickness():
    rows = ((30, 66), (100, 122), (170, 214), (240, 270))

    result = detect_wells(_image(_gel(rows=rows)), GUIDE)

    assert len(result.lanes) == 4
    assert [well.bounds[1::2] for well in result.wells] == list(rows)
    assert [lane[1::2] for lane in result.lanes] == list(rows)


def test_nearby_guides_recover_fuller_partial_well_outline():
    values = _gel()
    values[170:206, 36:54] = 120
    values[170:206, 40:58] += 8
    values[181:195, 36:54] += 8
    values += np.random.default_rng(41).normal(0, 3, values.shape)

    result = detect_wells(_image(values), ((40, 26), (40, 280)))

    assert len(result.wells) == 4
    # The main guide sees only the middle fragment. Neighboring guides should
    # restore the actual well outline, independently of lane-height repair.
    assert _coverage(result.wells[2].bounds, 170, 206) >= 0.90
    assert result.wells[2].bounds[3] - result.wells[2].bounds[1] <= 44
    _assert_ordered_lanes(result)


def test_typical_thickness_repairs_weak_partial_outline_without_downstream_bands():
    # Three complete outlines provide the typical thickness. The weak,
    # blurred remnant of the fourth has no firm caps or downstream signal.
    values = _gel(rows=((30, 66), (100, 136), (182, 194), (240, 276)),
                  contrasts=(80, 80, 8, 80))
    blurred = _image(values).filter(ImageFilter.GaussianBlur(2))
    values = np.asarray(blurred).astype(float)
    values += np.random.default_rng(14).normal(0, 2, values.shape)

    result = detect_wells(_image(values.clip(0, 255)), GUIDE)

    assert len(result.lanes) == 4
    well = result.wells[2]
    lane = result.lanes[2]
    assert well.bounds[3] - well.bounds[1] <= 20
    assert 30 <= lane[3] - lane[1] <= 44
    assert _coverage(lane, 170, 206) >= 0.90
    assert any("thickness" in warning.lower() for warning in result.warnings)
    _assert_ordered_lanes(result)


def test_tall_scratch_does_not_hide_useful_downstream_bands():
    values = _gel()
    values[170:182, 36:54] = 120
    values[194:206, 36:54] = 120
    values[170:206, 135:149] -= 70
    values[170:206, 235:247] -= 60
    # This unrelated vertical feature crosses every lane and must be ignored
    # independently of the finite bands at other x positions.
    values[:, 195:199] -= 65

    result = detect_wells(_image(values), GUIDE)

    assert len(result.lanes) == 4
    assert _coverage(result.lanes[2], 170, 206) >= 0.90
    assert result.lanes[2][3] - result.lanes[2][1] <= 46
    _assert_ordered_lanes(result)


def test_downstream_refinement_expands_both_borders_and_retains_empty_lane():
    values = _gel()
    unchanged = detect_wells(_image(values), GUIDE)
    bands = ((24, 72), (94, 142), (None, None), (234, 282))
    for top, bottom in bands:
        if top is not None:
            values[top:bottom, 136:150] -= 70
            values[top:bottom, 230:243] -= 55

    result = detect_wells(_image(values), GUIDE)

    assert result.wells == unchanged.wells
    assert len(result.lanes) == 4
    for index in (0, 1, 3):
        top, bottom = bands[index]
        assert _coverage(result.lanes[index], top, bottom) >= 0.90
    assert result.lanes[2] == unchanged.lanes[2]
    _assert_ordered_lanes(result)


def test_neighboring_broad_bands_cannot_make_lane_rectangles_overlap():
    values = _gel()
    # Separate bands broaden toward each other beyond the midpoint between
    # the first two wells. Each lane must still have its own editable region.
    values[24:90, 135:149] -= 70
    values[78:145, 235:247] -= 60

    result = detect_wells(_image(values), GUIDE)

    assert len(result.lanes) == 4
    for lane, (top, bottom) in zip(result.lanes, WELL_ROWS):
        assert _coverage(lane, top, bottom) >= 0.95
    _assert_ordered_lanes(result)


@pytest.mark.parametrize("dx", (-4, 0, 4))
def test_small_guide_shifts_keep_the_same_wells_and_band_coverage(dx):
    values = _gel()
    values[170:182, 36:54] = 120
    values[194:206, 36:54] = 120
    values[170:206, 135:149] -= 70
    values[170:206, 235:247] -= 60

    result = detect_wells(_image(values), ((45 + dx, 26), (45 + dx, 280)))

    assert len(result.lanes) == 4
    for lane, (top, bottom) in zip(result.lanes, WELL_ROWS):
        assert _coverage(lane, top, bottom) >= 0.90
    _assert_ordered_lanes(result)


def test_nearby_guide_search_recovers_one_well_displaced_from_the_others():
    values = _gel()
    values[170:206, 36:54] = 120
    values[170:206, 40:58] = 200

    result = detect_wells(_image(values), ((35, 26), (35, 280)))

    assert len(result.lanes) == 4
    assert [well.bounds[1::2] for well in result.wells] == list(WELL_ROWS)
    np.testing.assert_allclose(result.wells[2].bounds, (40, 170, 58, 206), atol=1)
    _assert_ordered_lanes(result)


def test_small_endpoint_cuts_are_completed_with_a_review_warning():
    image = _image(_gel())
    complete = detect_wells(image, GUIDE)

    result = detect_wells(image, ((45, 34), (45, 272)))

    assert result.wells == complete.wells
    assert result.lanes == complete.lanes
    assert result.warnings
    assert any("endpoint" in warning.lower() or "extend" in warning.lower()
               or "complet" in warning.lower() for warning in result.warnings)


def test_endpoint_completion_does_not_add_wells_outside_selected_range():
    result = detect_wells(_image(_gel()), ((45, 104), (45, 202)))

    assert [well.bounds[1::2] for well in result.wells] == [(100, 136), (170, 206)]
    assert len(result.lanes) == 2


def test_endpoint_completion_does_not_search_arbitrarily_far_past_the_guide():
    result = detect_wells(_image(_gel()), ((45, 60), (45, 280)))

    # The first well's far border is 30px outside the selection. A small
    # automatic adjustment may not silently reinterpret this as a full gel.
    assert [well.bounds[1::2] for well in result.wells] == list(WELL_ROWS[1:])
    assert result.warnings


def test_expected_count_can_join_two_short_aligned_fragments_of_one_well():
    values = _gel()
    values[184:192, 36:54] = 120

    result = detect_wells(_image(values), GUIDE, expected_count=4)

    assert len(result.lanes) == 4
    assert _coverage(result.lanes[2], 170, 206) >= 0.90
    assert 170 <= result.wells[2].center[1] <= 206
    _assert_ordered_lanes(result)


def test_expected_count_recovers_a_faint_missing_well_with_local_rim_evidence():
    values = _gel()
    values[170:206, 36:54] = 120
    values[170:206, 36:38] += 3
    values[170:206, 52:54] += 3
    values += np.random.default_rng(41).normal(0, 0.5, values.shape)
    image = _image(values.clip(0, 255))
    conservative = detect_wells(image, GUIDE)

    result = detect_wells(image, GUIDE, expected_count=4)

    assert len(conservative.lanes) == 3
    assert len(result.lanes) == 4
    assert _coverage(result.lanes[2], 170, 206) >= 0.90
    assert 170 <= result.wells[2].center[1] <= 206
    assert result.warnings
    _assert_ordered_lanes(result)


def test_smaller_expected_count_retains_exactly_requested_supported_wells():
    image = _image(_gel())
    unchanged = detect_wells(image, GUIDE)

    result = detect_wells(image, GUIDE, expected_count=3)

    assert len(result.wells) == len(result.lanes) == 3
    assert all(well in unchanged.wells for well in result.wells)
    assert any("omitted 1" in warning for warning in result.warnings)
    _assert_ordered_lanes(result)


def test_expected_count_fills_a_gap_and_discloses_inferred_position():
    values = _gel()
    values[170:206, 36:54] = 120

    result = detect_wells(_image(values), GUIDE, expected_count=4)

    assert len(result.lanes) == 4
    assert [well.bounds[1::2] for well in result.wells] == list(WELL_ROWS)
    assert any("inferred" in warning and "wells 3" in warning and "not confirmed by image evidence" in warning
               for warning in result.warnings)
    _assert_ordered_lanes(result)


@pytest.mark.parametrize("seed", (None, 5, 19))
def test_expected_count_proposes_exact_count_on_blank_or_noisy_gels(seed):
    values = np.full((310, 360), 120.0)
    if seed is not None:
        values += np.random.default_rng(seed).normal(0, 3, values.shape)

    result = detect_wells(_image(values), GUIDE, expected_count=4)

    assert len(result.wells) == len(result.lanes) == 4
    assert any("4 position(s) were inferred" in warning and "not confirmed by image evidence" in warning
               for warning in result.warnings)
    assert not any("No wells" in warning for warning in result.warnings)
    _assert_ordered_lanes(result)


def test_downstream_bands_refine_count_based_lanes_without_claiming_well_evidence():
    values = np.full((310, 360), 120.0)
    for top, bottom in WELL_ROWS:
        values[top:bottom, 135:149] -= 70
        values[top:bottom, 235:247] -= 60

    result = detect_wells(_image(values), GUIDE, expected_count=4)

    assert len(result.wells) == len(result.lanes) == 4
    assert any("4 position(s) were inferred" in warning for warning in result.warnings)
    _assert_ordered_lanes(result)


@pytest.mark.parametrize("invalid_count", (0, -1, 2.5, True, "4"))
def test_expected_count_requires_a_positive_integer(invalid_count):
    with pytest.raises((SelectionError, ValueError)):
        detect_wells(_image(_gel()), GUIDE, expected_count=invalid_count)


@pytest.mark.parametrize("dtype", ("<u2", ">u2"))
def test_band_refinement_and_expected_count_preserve_sixteen_bit_source(dtype):
    values = _gel()
    values[170:182, 36:54] = 120
    values[194:206, 36:54] = 120
    values[170:206, 135:149] -= 70
    values[170:206, 235:247] -= 60
    image = Image.fromarray((values * 193 + 17).astype(dtype))
    original = image.tobytes(), image.mode, image.size

    result = detect_wells(image, GUIDE, expected_count=4)

    assert len(result.lanes) == 4
    assert _coverage(result.lanes[2], 170, 206) >= 0.90
    assert (image.tobytes(), image.mode, image.size) == original
    assert image.getpixel((0, 0)) == 120 * 193 + 17
