from dataclasses import replace
from io import BytesIO

import numpy as np
from PIL import Image
import pytest

from gel_analyzer.orientation import orient_gel, rectangle_from_selection
from gel_analyzer.image_io import load_tiff, orient_gel_image


@pytest.mark.parametrize("mode", ["L", "RGB", "I;16"])
def test_top_manual_crop_retains_actual_pixel_axes(mode):
    pixels = np.arange(24 * 30, dtype=np.uint16).reshape(24, 30)
    image = Image.fromarray(pixels).convert(mode) if mode != "I;16" else Image.fromarray(pixels * 80)
    rectangle = rectangle_from_selection(dict(cx=15, cy=12, width=20, height=16, angle_degrees=0), image.size)
    result = orient_gel(image, rectangle, workflow_orientation="wells_top")
    assert result.image.size == (20, 16)
    assert result.counterclockwise_degrees == 0
    np.testing.assert_array_equal(np.asarray(result.image), np.asarray(image.crop((5, 4, 25, 20))))
    default = orient_gel(image, rectangle)
    np.testing.assert_array_equal(np.asarray(default.image), np.asarray(image.crop((5, 4, 25, 20)).transpose(Image.Transpose.TRANSPOSE)))


@pytest.mark.parametrize("angle", [-90, -25, 0, 45, 90, 180])
def test_top_manual_rotation_is_only_the_requested_tilt(angle):
    y, x = np.mgrid[:100, :100]
    image = Image.fromarray((x + y * 100).astype(np.uint16))
    rectangle = rectangle_from_selection(dict(cx=50, cy=50, width=30, height=40, angle_degrees=angle), image.size)
    result = orient_gel(image, rectangle, workflow_orientation="wells_top")
    output_y, output_x = np.mgrid[:40, :30]
    theta = np.deg2rad(angle)
    sx = 50 + (output_x + .5 - 15) * np.cos(theta) - (output_y + .5 - 20) * np.sin(theta)
    sy = 50 + (output_x + .5 - 15) * np.sin(theta) + (output_y + .5 - 20) * np.cos(theta)
    np.testing.assert_allclose(np.asarray(result.image), sx + sy * 100 - 50.5, atol=1)
    assert result.image.size == (30, 40)


def test_top_pipeline_stores_setting_without_mutating_tiff(monkeypatch):
    from gel_analyzer import image_io
    monkeypatch.setattr(image_io, "find_gel_crop", lambda im: (0, 0, *im.size))
    source = BytesIO()
    Image.new("L", (60, 80), 120).save(source, format="TIFF")
    initial = replace(load_tiff(source.getvalue(), "top.tif"), workflow_orientation="wells_top")
    rectangle = rectangle_from_selection(dict(cx=30, cy=40, width=50, height=70, angle_degrees=0), (60, 80))
    result = orient_gel_image(initial, rectangle)
    assert result.source_bytes == source.getvalue()
    assert result.workflow_orientation == "wells_top"
    assert (result.preview_width, result.preview_height) == (50, 70)
    assert initial.orientation is None
