"""Extracted-band rectangles use bounded, detached native-pixel geometry."""

from types import SimpleNamespace

import pytest

from gel_analyzer.annotations import AnnotationError
from gel_analyzer.extracted_bands import validate_extracted_bands


CROP = SimpleNamespace(width=120, height=80)
RECTANGLE = {"x": 0.125, "y": 4.5, "width": 119.875, "height": 75.5}


def test_rectangles_preserve_fractional_coordinates_and_boundary_edges():
    rectangles = [dict(RECTANGLE), {"x": 10, "y": 20, "width": 4, "height": 8}]
    checked = validate_extracted_bands(rectangles, CROP)
    assert checked == rectangles
    rectangles[0]["x"] = 30
    rectangles.pop()
    assert checked == [RECTANGLE, {"x": 10, "y": 20, "width": 4, "height": 8}]
    assert validate_extracted_bands([], CROP) == []


@pytest.mark.parametrize("value", [
    None, {}, (), [None], [dict(RECTANGLE, extra=1)],
    [dict(RECTANGLE, x=True)], [dict(RECTANGLE, width="10")],
    [dict(RECTANGLE, x=float("nan"))], [dict(RECTANGLE, height=float("inf"))],
    [dict(RECTANGLE, width=10 ** 400)],
    [dict(RECTANGLE, x=-0.1)], [dict(RECTANGLE, y=-1)],
    [dict(RECTANGLE, width=0)], [dict(RECTANGLE, height=-1)],
    [dict(RECTANGLE, width=120)], [dict(RECTANGLE, height=80)],
    [RECTANGLE] * 501,
])
def test_invalid_rectangle_geometry_is_rejected(value):
    with pytest.raises(AnnotationError):
        validate_extracted_bands(value, CROP)
