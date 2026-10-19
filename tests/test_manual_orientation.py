"""Manual geometry bypasses uncertain outlines, never source-pixel safeguards."""

from io import BytesIO

import numpy as np
from PIL import Image
import pytest

from gel_analyzer import image_io, orientation
from gel_analyzer.orientation import OrientationError, orient_gel, rectangle_from_selection


def selection(**changes):
    return {"cx": 40, "cy": 40, "width": 30, "height": 40, "angle_degrees": 0, **changes}


@pytest.mark.parametrize("angle", [-720, -340, -180, -90, 0, 32.5, 90, 179, 250, 360, 720])
def test_manual_angle_preserves_side_identity_through_full_circle(angle):
    # A linear source gradient gives an independent expectation for each output
    # pixel after the single interpolation. The normal rotate + vertical flip
    # maps the selected left side to output top and selected top side to left.
    y, x = np.mgrid[:80, :80]
    image = Image.fromarray((x + 2 * y).astype(np.uint8))
    original = image.tobytes()
    rectangle = rectangle_from_selection(selection(angle_degrees=angle), image.size)

    result = orient_gel(image, rectangle=rectangle)

    theta = np.deg2rad(angle)
    u = np.array([np.cos(theta), np.sin(theta)])
    v = np.array([-np.sin(theta), np.cos(theta)])
    output_y, output_x = np.mgrid[:30, :40]
    source = (
        np.array([40, 40])
        + (output_y[..., None] + 0.5 - 15) * u
        + (output_x[..., None] + 0.5 - 20) * v
    )
    expected = source[..., 0] + 2 * source[..., 1] - 1.5
    assert result.image.size == (40, 30)
    np.testing.assert_allclose(np.asarray(result.image), expected, atol=1.01)
    assert result.rectangle is rectangle
    assert image.tobytes() == original


def test_manual_rectangle_bypasses_failed_detection(monkeypatch):
    image = Image.new("L", (80, 80), 127)
    with pytest.raises(OrientationError):
        orient_gel(image)

    def unexpected_detection(_image):
        pytest.fail("Manual orientation must bypass the outline detector.")

    monkeypatch.setattr(orientation, "fit_gel_rectangle", unexpected_detection)
    result = orient_gel(image, rectangle_from_selection(selection(), image.size))

    assert result.image.size == (40, 30)
    assert result.image.getextrema() == (127, 127)


@pytest.mark.parametrize("mode", ["1", "L", "LA", "RGB", "RGBA", "I;16", "I;16L", "I;16B"])
def test_manual_orientation_preserves_supported_modes_and_exact_axis_aligned_pixels(mode):
    image = Image.new(mode, (13, 11))
    bands = len(image.getbands())
    image.putdata([
        (x * 17, y * 19, (x + y) * 9, 255)[:bands]
        if mode in {"RGB", "RGBA"}
        else ((x * 13 + y, 255) if mode == "LA"
              else ((x + y) % 2 if mode == "1"
                    else (x * 4096 + y * 113 if mode.startswith("I;") else x * 13 + y)))
        for y in range(image.height)
        for x in range(image.width)
    ])
    rectangle = rectangle_from_selection(
        selection(cx=6, cy=5, width=8, height=6), image.size
    )

    result = orient_gel(image, rectangle)

    expected = image.crop((2, 2, 10, 8)).transpose(Image.Transpose.TRANSPOSE)
    assert result.image.mode == mode
    np.testing.assert_array_equal(np.asarray(result.image), np.asarray(expected))
    if mode.startswith("I;"):
        assert np.asarray(result.image).max() > 255


@pytest.mark.parametrize("mode", ["F", "I", "CMYK"])
def test_manual_rectangle_cannot_bypass_unsupported_pixel_format(mode):
    image = Image.new(mode, (80, 80))
    rectangle = rectangle_from_selection(selection(), image.size)
    with pytest.raises(OrientationError, match="image format"):
        orient_gel(image, rectangle)


@pytest.mark.parametrize("mode", ["LA", "RGBA", "P"])
def test_manual_rectangle_cannot_bypass_transparency(mode):
    image = Image.new(mode, (80, 80))
    if mode == "P":
        image.info["transparency"] = 0
    else:
        image.putalpha(127)
    rectangle = rectangle_from_selection(selection(), image.size)
    with pytest.raises(OrientationError, match="transparent"):
        orient_gel(image, rectangle)


@pytest.mark.parametrize("payload", [None, [], {}, {"cx": 1}])
def test_missing_selection_reports_draw_instruction(payload):
    with pytest.raises(OrientationError, match="Draw a rectangle"):
        rectangle_from_selection(payload, (80, 80))


@pytest.mark.parametrize("field,value", [
    # All fields share numeric validation: cover each rejection category once,
    # then ensure that every remaining field is actually validated.
    ("cx", None), ("cx", "40"), ("cx", True), ("cx", float("nan")),
    ("cx", float("inf")), ("cx", -float("inf")), ("cx", 10**1000),
    ("cy", float("nan")), ("width", float("nan")),
    ("height", float("nan")), ("angle_degrees", float("nan")),
])
def test_selection_rejects_invalid_numbers(field, value):
    with pytest.raises(OrientationError, match="could not be read"):
        rectangle_from_selection(selection(**{field: value}), (80, 80))


@pytest.mark.parametrize("changes", [{"width": 0}, {"height": 1.9}, {"height": -5}])
def test_selection_requires_two_pixel_sides(changes):
    with pytest.raises(OrientationError, match="too small"):
        rectangle_from_selection(selection(**changes), (80, 80))


@pytest.mark.parametrize("changes", [
    {"cx": -1}, {"cy": 90}, {"width": 100}, {"height": 100},
    {"width": 80, "height": 80, "angle_degrees": 45},
    {"cx": 1e308, "width": 1e308},
])
def test_selection_requires_all_four_rotated_corners_inside_image(changes):
    with pytest.raises(OrientationError, match="four corners"):
        rectangle_from_selection(selection(**changes), (80, 80))


@pytest.mark.parametrize("angle", [0, 90, 180, 270, 360])
def test_selection_can_touch_image_boundaries(angle):
    rectangle = rectangle_from_selection(
        selection(width=80, height=80, angle_degrees=angle), (80, 80)
    )
    corners = np.asarray(rectangle.corners)
    assert np.all(corners >= -1e-6)
    assert np.all(corners <= 80 + 1e-6)


def test_manual_pipeline_always_samples_initial_crop_and_keeps_tiff_source(monkeypatch):
    y, x = np.mgrid[:9, :13]
    image = Image.fromarray((1000 + x * 3500 + y * 113).astype(np.uint16))
    source = BytesIO()
    image.save(source, format="TIFF")
    monkeypatch.setattr(image_io, "find_gel_crop", lambda _image: (1, 1, 12, 8))
    initial = image_io.load_tiff(source.getvalue(), "manual.tiff")
    original_preview = initial.preview_png
    rectangle = rectangle_from_selection(
        selection(cx=5, cy=3, width=6, height=4),
        (initial.preview_width, initial.preview_height),
    )

    result = image_io.orient_gel_image(initial, rectangle)
    repeated = image_io.orient_gel_image(initial, rectangle)

    assert initial.orientation is None
    assert initial.preview_png == original_preview
    assert result.preview_png == repeated.preview_png
    assert result.source_bytes == initial.source_bytes == source.getvalue()
    assert result.crop_box == initial.crop_box
    assert (result.filename, result.width, result.height, result.mode) == (
        initial.filename, initial.width, initial.height, initial.mode
    )
    assert result.orientation.corners == rectangle.corners
    assert result.orientation.size == (4, 6)
    assert result.orientation.counterclockwise_degrees == 90
    expected = image.crop((3, 2, 9, 6)).transpose(Image.Transpose.TRANSPOSE)
    with Image.open(BytesIO(result.preview_png)) as preview:
        np.testing.assert_array_equal(np.asarray(preview), np.asarray(expected))
    assert image_io.orient_gel_image(result) is result
    with pytest.raises(OrientationError, match="original cropped image"):
        image_io.orient_gel_image(result, rectangle)
