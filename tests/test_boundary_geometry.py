"""Boundary wells retain precise displayed geometry through the analysis path."""

from dataclasses import replace
from io import BytesIO

import numpy as np
from PIL import Image
import pytest

from gel_analyzer.bands import detect_bands
from gel_analyzer.image_io import GelOrientation, load_image
from gel_analyzer.lane_crop import (
    LaneAdjustmentError, append_lane, crop_lanes, generate_boundary_lanes, seed_boundary_well,
    validate_boundary_adjustments, validate_lane_adjustments,
)
from gel_analyzer.projects import load_project, save_project
from gel_analyzer.wells import Well
from gel_analyzer.workflow_orientation import lane_bounds, swap_bounds, swap_point, swap_size


def well(bounds):
    return Well(tuple(bounds), ((bounds[0] + bounds[2]) / 2, (bounds[1] + bounds[3]) / 2))


@pytest.fixture(params=["wells_left", "wells_top"])
def geometry(request):
    orientation = request.param
    endpoints = (well((15, 12.25, 27, 20.25)), well((15, 375.75, 27, 383.75)))
    size, points = (220, 400), ((21, 16.25), (21, 379.75))
    if orientation == "wells_top":
        endpoints = tuple(well(swap_bounds(item.bounds)) for item in endpoints)
        size, points = swap_size(size), tuple(swap_point(point) for point in points)
    return orientation, endpoints, size, points


def generated(geometry, count=15):
    orientation, (first, last), size, _ = geometry
    return generate_boundary_lanes(first, last, count, 210, size, workflow_orientation=orientation)


def test_fifteen_total_lanes_have_thirteen_precise_interiors_and_equal_widths(geometry):
    orientation, endpoints, _, _ = geometry
    result = generated(geometry)
    axis = 0 if orientation == "wells_top" else 1
    assert len(result) == 15
    assert len(result[1:-1]) == 13
    assert (result[0], result[-1]) == endpoints
    first, last = endpoints
    for index, item in enumerate(result):
        fraction = index / 14
        assert item.center == pytest.approx(tuple(a + (b - a) * fraction for a, b in zip(first.center, last.center)))
        assert item.bounds[axis + 2] - item.bounds[axis] == pytest.approx(8)
    np.testing.assert_allclose(np.diff([item.center[axis] for item in result]), 363.5 / 14, rtol=0, atol=1e-12)
    assert any(value != round(value) for item in result[1:-1] for value in item.bounds)


def test_two_total_lanes_return_only_the_exact_boundaries(geometry):
    assert generated(geometry, 2) == geometry[1]


@pytest.mark.parametrize("count", [0, 1, -5, 2.5, 15.0, "15", None, True, np.bool_(False), float("inf"), float("nan")])
def test_invalid_total_lane_counts_are_rejected(geometry, count):
    with pytest.raises(LaneAdjustmentError, match="whole-number total lane count of at least 2"):
        generated(geometry, count)


@pytest.mark.parametrize("reverse", [False, True])
def test_coincident_and_reversed_boundaries_cannot_be_generated(geometry, reverse):
    orientation, (first, last), size, _ = geometry
    endpoints = (last, first) if reverse else (first, first)
    with pytest.raises(LaneAdjustmentError, match="distinct position"):
        generate_boundary_lanes(*endpoints, 2, 210, size, workflow_orientation=orientation)


@pytest.mark.parametrize("count", [100, 10**1000])
def test_lane_count_cannot_create_overlapping_lanes(geometry, count):
    with pytest.raises(LaneAdjustmentError, match="lanes would overlap"):
        generated(geometry, count)


def test_first_boundary_reuses_existing_resize_and_move_rules(geometry):
    orientation, (first, _), size, _ = geometry
    axis = 0 if orientation == "wells_top" else 1
    bounds = list(lane_bounds(first.bounds, 210, orientation))
    bounds[axis] += 1.5
    bounds[axis + 2] += 4.25
    adjusted = validate_boundary_adjustments((first,), (bounds,), 210, size, "boundary_first",
                                             workflow_orientation=orientation)
    assert adjusted[0].bounds[axis] == first.bounds[axis] + 1.5
    assert adjusted[0].bounds[axis + 2] - adjusted[0].bounds[axis] == 10.75


def test_last_boundary_keeps_first_fixed_and_width_linked(geometry):
    orientation, endpoints, size, _ = geometry
    axis = 0 if orientation == "wells_top" else 1
    lanes = [list(lane_bounds(item.bounds, 210, orientation)) for item in endpoints]
    lanes[1][axis] -= 40.5
    lanes[1][axis + 2] -= 40.5
    adjusted = validate_boundary_adjustments(endpoints, lanes, 210, size, "boundary_last",
                                             workflow_orientation=orientation)
    assert adjusted[0] == endpoints[0]
    assert adjusted[1].center[axis] == endpoints[1].center[axis] - 40.5
    lanes[0][axis] += 1
    with pytest.raises(LaneAdjustmentError, match="first well is fixed"):
        validate_boundary_adjustments(endpoints, lanes, 210, size, "boundary_last", workflow_orientation=orientation)
    lanes[0] = list(lane_bounds(endpoints[0].bounds, 210, orientation))
    lanes[1][axis + 2] += 1
    with pytest.raises(LaneAdjustmentError, match="width linked"):
        validate_boundary_adjustments(endpoints, lanes, 210, size, "boundary_last", workflow_orientation=orientation)


def test_last_boundary_can_move_across_first_while_editing(geometry):
    orientation, (first, last), size, _ = geometry
    lanes = (lane_bounds(first.bounds, 210, orientation), lane_bounds(first.bounds, 210, orientation))
    result = validate_boundary_adjustments((first, last), lanes, 210, size, "boundary_last",
                                           workflow_orientation=orientation)
    assert result == (first, first)
    with pytest.raises(LaneAdjustmentError, match="distinct position"):
        generate_boundary_lanes(*result, 15, 210, size, workflow_orientation=orientation)


@pytest.mark.parametrize("change, message", [("width", "width linked"), ("depth", "same upstream position and depth")])
def test_generation_rejects_boundaries_with_different_geometry(geometry, change, message):
    orientation, (first, last), size, _ = geometry
    cross_axis = 0 if orientation == "wells_top" else 1
    bounds = list(last.bounds)
    bounds[(cross_axis if change == "width" else 1 - cross_axis) + 2] += 1
    with pytest.raises(LaneAdjustmentError, match=message):
        generate_boundary_lanes(first, well(bounds), 15, 210, size, workflow_orientation=orientation)


def test_touching_fractional_lanes_are_valid_without_rounding(geometry):
    orientation, (first, _), size, _ = geometry
    cross_axis = 0 if orientation == "wells_top" else 1
    bounds = list(first.bounds)
    bounds[cross_axis] += 16
    bounds[cross_axis + 2] += 16
    wells = generate_boundary_lanes(first, well(bounds), np.int64(3), 210, size,
                                    workflow_orientation=orientation)
    assert len(wells) == 3
    assert all(a.bounds[cross_axis + 2] == b.bounds[cross_axis] for a, b in zip(wells, wells[1:]))
    assert len(crop_lanes(Image.new("L", size), wells, 210, workflow_orientation=orientation).lanes) == 3


def test_half_pixel_lane_width_is_rejected_by_edit_and_generation(geometry):
    orientation, endpoints, size, _ = geometry
    axis = 0 if orientation == "wells_top" else 1
    narrow = []
    for item in endpoints:
        bounds = list(item.bounds)
        bounds[axis + 2] = bounds[axis] + .5
        narrow.append(well(bounds))
    lanes = tuple(lane_bounds(item.bounds, 210, orientation) for item in narrow)
    with pytest.raises(LaneAdjustmentError, match="too narrow"):
        validate_lane_adjustments(endpoints, lanes, 210, size, workflow_orientation=orientation)
    with pytest.raises(LaneAdjustmentError, match="too narrow"):
        validate_boundary_adjustments(endpoints[:1], lanes[:1], 210, size, "boundary_first",
                                      workflow_orientation=orientation)
    with pytest.raises(LaneAdjustmentError, match="too narrow"):
        generate_boundary_lanes(*narrow, 15, 210, size, workflow_orientation=orientation)


def test_one_pixel_lane_keeps_float_noise_when_moved(geometry):
    orientation, endpoints, size, _ = geometry
    axis = 0 if orientation == "wells_top" else 1
    originals, lanes = [], []
    for item in endpoints:
        bounds = list(item.bounds)
        bounds[axis + 2] = bounds[axis] + 1 - 1e-12
        originals.append(well(bounds))
        bounds = list(lane_bounds(bounds, 210, orientation))
        bounds[axis] += .1
        bounds[axis + 2] += .1
        lanes.append(bounds)
    moved = validate_lane_adjustments(originals, lanes, 210, size, workflow_orientation=orientation)
    assert all(item.bounds[axis] == lane[axis] and item.bounds[axis + 2] == lane[axis + 2]
               for item, lane in zip(moved, lanes))
    result = generate_boundary_lanes(*moved, 15, 210, size, workflow_orientation=orientation)
    assert (result[0], result[-1]) == moved
    assert len(crop_lanes(Image.new("L", size), result, 210, workflow_orientation=orientation).lanes) == 15


@pytest.mark.parametrize("remainder", [.5, .125, 1e-12])
def test_append_reserves_a_full_pixel_after_fractional_generated_boundary(geometry, remainder):
    orientation, (first, last), size, points = geometry
    axis = 0 if orientation == "wells_top" else 1
    bounds = list(last.bounds)
    bounds[axis + 2] = size[axis] - remainder
    bounds[axis] = bounds[axis + 2] - 8
    originals = generate_boundary_lanes(first, well(bounds), 15, 210, size, workflow_orientation=orientation)
    result = append_lane(originals, points, 210, size, workflow_orientation=orientation)
    assert result[:-2] == originals[:-1]
    assert result[-2].bounds[axis] == originals[-1].bounds[axis]
    assert result[-2].bounds[axis + 2] == size[axis] - 1
    assert (result[-1].bounds[axis], result[-1].bounds[axis + 2]) == (size[axis] - 1, size[axis])
    assert all(item.bounds[axis + 2] - item.bounds[axis] >= 1 for item in result)
    assert len(crop_lanes(Image.new("L", size), result, 210, workflow_orientation=orientation).lanes) == 16


def test_append_moves_a_touching_one_pixel_tail_to_reserve_full_pixel(geometry):
    orientation, (first, _), size, points = geometry
    axis = 0 if orientation == "wells_top" else 1
    bounds = list(first.bounds)
    bounds[axis], bounds[axis + 2] = size[axis] - 3.5, size[axis] - 2.5
    first = well(bounds)
    bounds[axis] += 2
    bounds[axis + 2] += 2
    originals = generate_boundary_lanes(first, well(bounds), 3, 210, size, workflow_orientation=orientation)
    result = append_lane(originals, points, 210, size, workflow_orientation=orientation)
    assert len(result) == 4
    assert all(item.bounds[axis + 2] - item.bounds[axis] == 1 for item in result)
    assert [item.bounds[axis] for item in result] == list(range(size[axis] - 4, size[axis]))
    assert len(crop_lanes(Image.new("L", size), result, 210, workflow_orientation=orientation).lanes) == 4


def test_seed_reuses_first_existing_well_or_first_guide_endpoint(geometry):
    orientation, endpoints, size, points = geometry
    assert seed_boundary_well(endpoints, points, 210, size, workflow_orientation=orientation) == endpoints[0]
    assert seed_boundary_well(endpoints[::-1], points, 210, size, workflow_orientation=orientation) == endpoints[0]
    seed = seed_boundary_well((), points[::-1], 210, size, workflow_orientation=orientation)
    assert seed.center == pytest.approx(points[0], abs=.5)
    assert crop_lanes(Image.new("L", size), (seed,), 210, workflow_orientation=orientation).wells


def test_generated_lanes_remain_editable_and_crop_without_rounding_geometry(geometry):
    orientation, _, size, _ = geometry
    axis = 0 if orientation == "wells_top" else 1
    wells = generated(geometry)
    lanes = [list(lane_bounds(item.bounds, 210, orientation)) for item in wells]
    lanes[5][axis] += 0.25
    lanes[5][axis + 2] += 0.25
    edited = validate_lane_adjustments(wells, lanes, 210, size, workflow_orientation=orientation)
    assert edited[:5] == wells[:5]
    assert edited[6:] == wells[6:]
    assert edited[5].center[axis] == wells[5].center[axis] + .25
    pixels = np.arange(size[0] * size[1], dtype=np.uint16).reshape(size[1], size[0])
    crop = crop_lanes(Image.fromarray(pixels), edited, 210, workflow_orientation=orientation)
    left, top, right, bottom = crop.crop_box
    assert all(type(value) is int for value in crop.crop_box)
    with Image.open(BytesIO(crop.preview_png)) as copied:
        np.testing.assert_array_equal(np.asarray(copied), pixels[top:bottom, left:right])
    for original, translated in zip(edited, crop.wells):
        assert translated.bounds == tuple(value - offset for value, offset in zip(original.bounds, (left, top, left, top)))


def test_fractional_geometry_can_be_analyzed_and_saved_then_reopened(geometry):
    orientation, _, size, points = geometry
    wells = generated(geometry)
    # A migration band across every lane demonstrates actual downstream image
    # analysis, including rows/columns whose boundaries are fractional.
    pixels = np.full((400, 220), 100, dtype=np.uint8)
    pixels[:, 118:123] = 200
    if orientation == "wells_top":
        pixels = pixels.T
    image = Image.fromarray(pixels)
    source = BytesIO()
    image.save(source, format="PNG")
    gel = replace(load_image(source.getvalue(), "boundary.png"),
                  orientation=GelOrientation(((0., 0.), (size[0], 0.), size, (0., size[1])), 0., size),
                  workflow_orientation=orientation)
    crop = crop_lanes(image, wells, 210, workflow_orientation=orientation)
    with Image.open(BytesIO(crop.preview_png)) as copied:
        candidates = detect_bands(copied, crop.lanes, orientation, wells=crop.wells)
    assert len(candidates) == 15
    assert all(len(lane) == 1 for lane in candidates)
    axis = "x" if orientation == "wells_top" else "y"
    for lane, item in zip(candidates, crop.wells):
        assert lane[0][axis] == pytest.approx(item.center[0 if orientation == "wells_top" else 1])
    state = {"gel_image": gel, "well_points": points, "well_expected_count": 15,
             "lane_stage": "cropped", "lane_wells": wells, "lane_right": 210,
             "lane_crop": crop, "lane_source": gel}
    restored = load_project(save_project(state))
    assert restored["lane_wells"] == wells
    assert restored["lane_crop"] == crop
    assert restored["lane_source"] is restored["gel_image"]
