"""Typical lane thickness keeps its reference behavior with bounded memory."""

import math

import numpy as np
import pytest

from gel_analyzer.lane_refinement import _typical_height
from gel_analyzer.wells import Well


def _wells(heights):
    top = 0
    wells = []
    for height in heights:
        height = int(height)
        wells.append(Well((2, top, 8, top + height), (5., top + height / 2)))
        top += height + 1
    return tuple(wells)


def _reference(heights):
    """The original grouping semantics, limited to small test inputs."""
    if len(heights) < 3:
        return None
    heights = np.asarray(heights)
    groups = [heights[np.abs(heights - height) <= height * .20] for height in heights]
    group = max(groups, key=lambda values: (len(values), float(np.median(values))))
    return float(np.median(group)) if len(group) >= max(2, math.ceil(len(heights) * .6)) else None


@pytest.mark.parametrize("heights,expected", [
    ([], None), ([10], None), ([10, 10], None),
    ([10, 10, 10], 10.), ([20, 24, 25], 24.),
    ([10, 12, 14, 16, 18], 16.),  # Equal support chooses the larger median.
    ([10, 10, 10, 20, 20], 10.),
    ([10, 10, 12, 20, 20, 24], None),
])
def test_support_threshold_inclusive_bounds_and_tie_breaking(heights, expected):
    assert _typical_height(_wells(heights)) == expected == _reference(heights)


@pytest.mark.parametrize("seed", range(30))
def test_matches_original_grouping_for_variable_height_distributions(seed):
    rng = np.random.default_rng(seed)
    for size in (3, 4, 7, 20, 50, 100):
        # Include distinct broad distributions and concentrated groups at
        # integer tolerance boundaries, with enough outliers to vary support.
        uniform = rng.integers(1, 500, size=size)
        center = int(rng.integers(5, 200))
        clustered = rng.integers(max(1, center - center // 5), center + center // 5 + 1, size=size)
        clustered[:size // 4] = rng.integers(1, 500, size=size // 4)
        for heights in (uniform, clustered):
            assert _typical_height(_wells(heights)) == _reference(heights)


def test_ten_thousand_identical_one_pixel_lanes_have_a_typical_height():
    assert _typical_height(_wells([1] * 10_000)) == 1.
