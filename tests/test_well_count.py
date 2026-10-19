"""Exact entered counts remain valid through detection, refinement and cropping."""

import numpy as np
from PIL import Image
import pytest

from gel_analyzer.lane_crop import crop_lanes, validate_lane_adjustments
from gel_analyzer.wells import SelectionError, detect_wells
from gel_analyzer.workflow_orientation import swap_bounds, swap_point


ROWS = ((30, 66), (100, 136), (170, 206), (240, 276))
GUIDE = ((45, 26), (45, 280))


def _fixture(rows=ROWS, *, contrasts=None, dtype="uint8"):
    pixels = np.full((310, 360), 120.0)
    for (top, bottom), contrast in zip(rows, contrasts or [80] * len(rows)):
        pixels[top:bottom, 36:54] += contrast
    if np.dtype(dtype).itemsize == 2:
        pixels = pixels * 193 + 17
    return Image.fromarray(pixels.astype(dtype))


def _detect(image, count, orientation, guide=GUIDE):
    if orientation == "wells_top":
        image = image.transpose(Image.Transpose.TRANSPOSE)
        guide = tuple(swap_point(point) for point in guide)
    result = detect_wells(image, guide, expected_count=count, workflow_orientation=orientation)
    return image, result


def _assert_valid(image, result, count, orientation):
    assert len(result.wells) == len(result.lanes) == count
    assert len(set(result.wells)) == count
    cross = 0 if orientation == "wells_top" else 1
    assert all(first.bounds[cross + 2] <= second.bounds[cross]
               for first, second in zip(result.wells, result.wells[1:]))
    assert all(first[cross + 2] <= second[cross]
               for first, second in zip(result.lanes, result.lanes[1:]))
    for well, lane in zip(result.wells, result.lanes):
        for bounds in (well.bounds, lane):
            left, top, right, bottom = bounds
            assert all(type(value) is int for value in bounds)
            assert 0 <= left < right <= image.width
            assert 0 <= top < bottom <= image.height
        assert well.center == ((well.bounds[0] + well.bounds[2]) / 2,
                               (well.bounds[1] + well.bounds[3]) / 2)
    extent = image.height if orientation == "wells_top" else image.width
    edited = validate_lane_adjustments(result.wells, result.lanes, extent, image.size,
                                       workflow_orientation=orientation)
    crop = crop_lanes(image, edited, extent, workflow_orientation=orientation)
    assert len(crop.wells) == len(crop.lanes) == count


@pytest.mark.parametrize("count,orientation", [
    # Both axes exercise the minimum and saturated span; intermediate counts
    # cover dropping, matching and adding wells without duplicating the sweep.
    (1, "wells_left"), (1, "wells_top"), (2, "wells_left"),
    (3, "wells_top"), (4, "wells_left"), (6, "wells_top"),
    (16, "wells_left"), (254, "wells_left"), (254, "wells_top"),
])
def test_representative_counts_have_exact_valid_geometry_through_crop(count, orientation):
    image, result = _detect(_fixture(), count, orientation)

    _assert_valid(image, result, count, orientation)


@pytest.mark.parametrize("orientation", ("wells_left", "wells_top"))
@pytest.mark.parametrize("rows", (ROWS[:1], ROWS[1:2], ROWS[2:3], ROWS[3:], ROWS[:1] + ROWS[3:]))
def test_missing_positions_use_supported_spacing_and_guide_endpoints(rows, orientation):
    image, result = _detect(_fixture(rows), 4, orientation)
    _, supported = _detect(_fixture(rows), len(rows), orientation)

    _assert_valid(image, result, 4, orientation)
    assert all(well in result.wells for well in supported.wells)
    assert any(f"{4 - len(rows)} position(s) were inferred" in warning for warning in result.warnings)
    # Independent fixture positions: a sparse set should produce proposals
    # near all four wells, rather than packing additions around one anchor.
    axis = 0 if orientation == "wells_top" else 1
    np.testing.assert_allclose([well.center[axis] for well in result.wells], (48, 118, 188, 258), atol=8)


@pytest.mark.parametrize("orientation", ("wells_left", "wells_top"))
def test_excess_candidates_drop_lower_evidence_without_moving_remaining_outlines(orientation):
    rows = (ROWS[0], (80, 92), *ROWS[1:])
    fixture = _fixture(rows, contrasts=(80, 10, 80, 80, 80))
    _, automatic = _detect(fixture, len(rows), orientation)
    image, constrained = _detect(fixture, 4, orientation)

    assert len(automatic.wells) == 5
    assert constrained.wells == automatic.wells[:1] + automatic.wells[2:]
    assert any("omitted 1" in warning for warning in constrained.warnings)
    assert not any("not confirmed by image evidence" in warning for warning in constrained.warnings)
    _assert_valid(image, constrained, 4, orientation)


@pytest.mark.parametrize("orientation", ("wells_left", "wells_top"))
def test_matching_count_preserves_nonuniform_supported_geometry_exactly(orientation):
    rows = ((30, 66), (100, 122), (170, 214), (240, 270))
    image = _fixture(rows)
    _, constrained = _detect(image, 4, orientation)

    expected = [(36, top, 54, bottom) for top, bottom in rows]
    if orientation == "wells_top":
        expected = [swap_bounds(bounds) for bounds in expected]
    assert [well.bounds for well in constrained.wells] == expected
    assert not constrained.warnings


@pytest.mark.parametrize("orientation", ("wells_left", "wells_top"))
@pytest.mark.parametrize("count", (4, 10, 23))
def test_inference_uses_available_gaps_before_narrowing_unequal_supported_wells(orientation, count):
    values = np.full((100, 80), 120, dtype=np.uint8)
    for top, bottom in ((10, 50), (60, 70), (80, 90)):
        values[top:bottom, 20:30] = 200
    source = Image.fromarray(values)
    guide = ((25, 10), (25, 90))
    _, supported = _detect(source, 3, orientation, guide)

    image, result = _detect(source, count, orientation, guide)

    _assert_valid(image, result, count, orientation)
    assert len(supported.wells) == 3
    assert all(well in result.wells for well in supported.wells)
    assert not any("narrowed" in warning for warning in result.warnings)


@pytest.mark.parametrize("orientation", ("wells_left", "wells_top"))
@pytest.mark.parametrize("migration", (0, 120))
def test_blank_full_span_supports_one_pixel_per_lane_at_both_image_edges(orientation, migration):
    image, result = _detect(Image.new("L", (120, 40), 120), 40, orientation,
                            ((migration, 0), (migration, 40)))

    _assert_valid(image, result, 40, orientation)
    axis = 0 if orientation == "wells_top" else 1
    assert [(well.bounds[axis], well.bounds[axis + 2]) for well in result.wells] == [(i, i + 1) for i in range(40)]
    assert any("40 position(s) were inferred" in warning for warning in result.warnings)


@pytest.mark.parametrize("orientation", ("wells_left", "wells_top"))
def test_fractional_reversed_guide_uses_covering_integer_pixel_span(orientation):
    image = Image.new("L", (120, 40), 120)
    guide = ((45.5, 4.8), (49.5, 20.2))
    _, forward = _detect(image, 17, orientation, guide)
    oriented, backward = _detect(image, 17, orientation, guide[::-1])

    assert backward == forward
    _assert_valid(oriented, forward, 17, orientation)
    with pytest.raises(SelectionError, match="18 wells cannot fit along this guide"):
        _detect(image, 18, orientation, guide)


@pytest.mark.parametrize("orientation", ("wells_left", "wells_top"))
@pytest.mark.parametrize("count", (None, 0, -1, 2.5, 4.0, True, False, "4", float("nan"), float("inf")))
def test_invalid_count_is_rejected_before_reading_or_allocating_image_data(monkeypatch, count, orientation):
    def unexpected_analysis(*args, **kwargs):
        pytest.fail("Invalid counts must fail before reading or allocating image data.")

    image = _fixture()
    monkeypatch.setattr("gel_analyzer.wells._analysis_pixels", unexpected_analysis)
    monkeypatch.setattr("gel_analyzer.wells._detect_supported_wells", unexpected_analysis)
    monkeypatch.setattr(Image.Image, "transpose", unexpected_analysis)

    with pytest.raises(SelectionError, match="positive integer"):
        detect_wells(image, GUIDE, expected_count=count, workflow_orientation=orientation)


def test_expected_count_is_a_required_keyword_argument():
    # No image object is needed: the API rejects omitted or positional counts
    # before executing its body or inspecting image pixels.
    with pytest.raises(TypeError, match="expected_count"):
        detect_wells(None, GUIDE)
    with pytest.raises(TypeError):
        detect_wells(None, GUIDE, 4)


def test_numpy_integer_count_is_accepted():
    image, result = _detect(_fixture(), np.int64(4), "wells_left")
    _assert_valid(image, result, 4, "wells_left")


@pytest.mark.parametrize("orientation", ("wells_left", "wells_top"))
def test_impossible_count_is_rejected_before_any_image_analysis(monkeypatch, orientation):
    def unexpected_analysis(*args, **kwargs):
        pytest.fail("Impossible counts must fail before allocating image analysis arrays.")

    monkeypatch.setattr("gel_analyzer.wells._detect_supported_wells", unexpected_analysis)
    monkeypatch.setattr("gel_analyzer.wells._analysis_pixels", unexpected_analysis)
    monkeypatch.setattr(Image.Image, "transpose", unexpected_analysis)
    image = Image.new("L", (120, 40) if orientation == "wells_left" else (40, 120))
    guide = ((45, 0), (45, 40)) if orientation == "wells_left" else ((0, 45), (40, 45))
    with pytest.raises(SelectionError, match="cannot fit"):
        detect_wells(image, guide, expected_count=10**100, workflow_orientation=orientation)


@pytest.mark.parametrize("orientation", ("wells_left", "wells_top"))
@pytest.mark.parametrize("dtype", ("uint8", "<u2", ">u2"))
def test_inference_never_changes_source_pixels_or_native_precision(dtype, orientation):
    source = _fixture(ROWS[:1], dtype=dtype)
    if orientation == "wells_top":
        source = source.transpose(Image.Transpose.TRANSPOSE)
    before = source.tobytes(), source.mode, source.size
    guide = tuple(swap_point(point) for point in GUIDE) if orientation == "wells_top" else GUIDE

    result = detect_wells(source, guide, expected_count=7, workflow_orientation=orientation)

    _assert_valid(source, result, 7, orientation)
    assert (source.tobytes(), source.mode, source.size) == before


def test_downstream_refinement_cannot_change_requested_count():
    source = np.asarray(_fixture(ROWS[:1])).copy()
    for top, bottom in ROWS:
        source[top:bottom, 130:150] = 30
        source[top:bottom, 230:250] = 30
    image = Image.fromarray(source)

    for orientation in ("wells_left", "wells_top"):
        oriented, result = _detect(image, 6, orientation)
        _assert_valid(oriented, result, 6, orientation)


def test_top_fit_is_exact_transpose_of_default_with_matching_review_warnings():
    image = _fixture(ROWS[:2])
    _, default = _detect(image, 4, "wells_left")
    _, top = _detect(image, 4, "wells_top")

    assert [well.bounds for well in top.wells] == [swap_bounds(well.bounds) for well in default.wells]
    assert top.lanes == tuple(swap_bounds(lane) for lane in default.lanes)
    assert top.warnings == default.warnings
