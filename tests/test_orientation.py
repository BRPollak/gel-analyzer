"""Independent generated gels check fitted geometry and the order of operations."""

import numpy as np
from PIL import Image, ImageFilter
import pytest

from gel_analyzer.auto_crop import find_gel_crop
from gel_analyzer.orientation import (
    OrientationError,
    orient_gel,
)


_FRAME_SIZE = 520
_GEL_WIDTH = 210
_GEL_HEIGHT = 350
_CENTER = np.array([260.0, 260.0])
_MARKERS = {
    "left": (25, -0.36 * _GEL_WIDTH, 0, (0.5, 0.14)),
    "right": (55, 0.36 * _GEL_WIDTH, 0, (0.5, 0.86)),
    "top": (155, 0, -0.40 * _GEL_HEIGHT, (0.10, 0.5)),
    "bottom": (185, 0, 0.40 * _GEL_HEIGHT, (0.90, 0.5)),
}


def _synthetic_gel(clockwise_degrees=0, dtype=np.uint8, markers=True):
    """Rasterize from analytic gel coordinates, without image rotation helpers."""
    angle = np.deg2rad(clockwise_degrees)
    rotation = np.array(
        [[np.cos(angle), -np.sin(angle)], [np.sin(angle), np.cos(angle)]]
    )
    y, x = np.mgrid[:_FRAME_SIZE, :_FRAME_SIZE]
    points = np.stack([x + 0.5, y + 0.5], axis=-1) - _CENTER
    local = points @ rotation
    local_x, local_y = local[..., 0], local[..., 1]
    inside = (np.abs(local_x) < _GEL_WIDTH / 2) & (
        np.abs(local_y) < _GEL_HEIGHT / 2
    )
    values = np.where(inside, 110, 220)
    if markers:
        for value, marker_x, marker_y, _ in _MARKERS.values():
            marker = (local_x - marker_x) ** 2 + (local_y - marker_y) ** 2 < 11**2
            values[marker] = value
    if np.dtype(dtype).itemsize == 2:
        # Deliberately retain information below an 8-bit conversion step.
        values = values * 193 + 17
    corners = np.array(
        [
            [-_GEL_WIDTH / 2, -_GEL_HEIGHT / 2],
            [_GEL_WIDTH / 2, -_GEL_HEIGHT / 2],
            [_GEL_WIDTH / 2, _GEL_HEIGHT / 2],
            [-_GEL_WIDTH / 2, _GEL_HEIGHT / 2],
        ]
    ) @ rotation.T + _CENTER
    return Image.fromarray(values.astype(dtype)), corners


@pytest.mark.parametrize("clockwise_degrees", [-25, -14, 0, 11, 25])
def test_fitted_outline_and_straighten_then_flip_preserve_original_sides(
    clockwise_degrees,
):
    image, expected_corners = _synthetic_gel(clockwise_degrees)

    result = orient_gel(image)

    rectangle = result.rectangle
    assert rectangle.angle_degrees == pytest.approx(clockwise_degrees, abs=1)
    assert rectangle.width == pytest.approx(_GEL_WIDTH, abs=6)
    assert rectangle.height == pytest.approx(_GEL_HEIGHT, abs=6)
    np.testing.assert_allclose(rectangle.corners, expected_corners, atol=3)
    assert result.counterclockwise_degrees == pytest.approx(
        90 + clockwise_degrees, abs=1
    )
    width, height = result.image.size
    assert width == pytest.approx(_GEL_HEIGHT, abs=6)
    assert height == pytest.approx(_GEL_WIDTH, abs=6)
    values = np.asarray(result.image)
    for name, (value, _, _, expected_position) in _MARKERS.items():
        ys, xs = np.nonzero(values == value)
        assert len(xs) > 150, f"The original {name} marker was lost."
        position = ((xs.mean() + 0.5) / width, (ys.mean() + 0.5) / height)
        np.testing.assert_allclose(position, expected_position, atol=0.02)
    # A correct crop has gel at all four corners and no expanded-rotation
    # wedges. Ignore a few rasterization pixels exactly at the fitted edges.
    for corner in (
        values[4:14, 4:14],
        values[4:14, -14:-4],
        values[-14:-4, 4:14],
        values[-14:-4, -14:-4],
    ):
        assert np.median(corner) == pytest.approx(110, abs=1)
    assert np.mean(values >= 210) < 0.02


def test_repeated_orientation_uses_unchanged_source_pixels():
    image, _ = _synthetic_gel(11)
    original = image.tobytes()
    original_size = image.size

    first = orient_gel(image)
    second = orient_gel(image)

    assert image.tobytes() == original
    assert image.size == original_size
    assert first.image is not image
    assert first.image.size == second.image.size
    assert first.image.tobytes() == second.image.tobytes()


@pytest.mark.parametrize("dtype", ["<u2", ">u2"])
def test_orientation_keeps_16_bit_intensities(dtype):
    image, _ = _synthetic_gel(-14, dtype=dtype)
    original = image.tobytes()

    result = orient_gel(image)

    values = np.asarray(result.image)
    assert values.dtype.kind == "u"
    assert values.dtype.itemsize == 2
    assert result.image.getpixel((result.image.width // 2, result.image.height // 2)) == (
        110 * 193 + 17
    )
    for value, _, _, _ in _MARKERS.values():
        assert np.count_nonzero(values == value * 193 + 17) > 150
    assert image.tobytes() == original


@pytest.mark.parametrize(
    "mode,gel_color,background",
    [
        ("RGB", (70, 90, 120), (220, 220, 220)),
        ("RGBA", (70, 90, 120, 255), (220, 220, 220, 255)),
        ("LA", (110, 255), (220, 255)),
    ],
)
def test_orientation_keeps_color_channels_and_alpha(mode, gel_color, background):
    mask_image, _ = _synthetic_gel(11, markers=False)
    mask = np.asarray(mask_image) == 110
    values = np.empty((_FRAME_SIZE, _FRAME_SIZE, len(gel_color)), dtype=np.uint8)
    values[:] = background
    values[mask] = gel_color
    image = Image.fromarray(values)
    assert image.mode == mode

    result = orient_gel(image)

    assert result.image.mode == mode
    assert result.image.getpixel((result.image.width // 2, result.image.height // 2)) == (
        gel_color
    )


def test_landscape_gel_retains_original_side_meaning():
    image, _ = _synthetic_gel(11)
    image = image.transpose(Image.Transpose.TRANSPOSE)

    result = orient_gel(image)

    assert result.rectangle.width == pytest.approx(_GEL_HEIGHT, abs=6)
    assert result.rectangle.height == pytest.approx(_GEL_WIDTH, abs=6)
    assert result.counterclockwise_degrees == pytest.approx(79, abs=1)
    assert result.image.width == pytest.approx(_GEL_WIDTH, abs=6)
    assert result.image.height == pytest.approx(_GEL_HEIGHT, abs=6)
    values = np.asarray(result.image)
    # Transposing the fixture exchanges its source axes. The operation still
    # puts this landscape source's own left edge at the top.
    for value, expected_position in (
        (25, (0.14, 0.5)),
        (55, (0.86, 0.5)),
        (155, (0.5, 0.10)),
        (185, (0.5, 0.90)),
    ):
        ys, xs = np.nonzero(values == value)
        assert len(xs) > 150
        position = (
            (xs.mean() + 0.5) / result.image.width,
            (ys.mean() + 0.5) / result.image.height,
        )
        np.testing.assert_allclose(position, expected_position, atol=0.02)


@pytest.mark.parametrize("mode", ["LA", "RGBA"])
def test_transparent_gel_outline_is_rejected(mode):
    image, _ = _synthetic_gel(11)
    image = image.convert(mode)
    image.putalpha(123)

    with pytest.raises(OrientationError, match="transparent"):
        orient_gel(image)


@pytest.mark.parametrize("value", [0, 127, 255])
def test_featureless_image_does_not_invent_a_gel_outline(value):
    image = Image.new("L", (_FRAME_SIZE, _FRAME_SIZE), value)

    with pytest.raises(OrientationError):
        orient_gel(image)


def test_smooth_illumination_gradient_is_not_a_gel_outline():
    y, x = np.mgrid[:_FRAME_SIZE, :_FRAME_SIZE]
    image = Image.fromarray((80 + x * 0.1 + y * 0.05).astype(np.uint8))

    with pytest.raises(OrientationError):
        orient_gel(image)


def _assert_orientation_preserves_physical_outline_or_declines(image, bounds):
    """Cover crop enclosure and orientation together for the same physical edge."""
    first_crop = find_gel_crop(image)
    left, top, right, bottom = bounds
    assert first_crop[0] <= left < right <= first_crop[2]
    assert first_crop[1] <= top < bottom <= first_crop[3]
    cropped = image.crop(first_crop)
    source = cropped.tobytes()
    try:
        result = orient_gel(cropped)
    except OrientationError:
        # Uncertain edges must leave the first-step crop available unchanged.
        assert cropped.tobytes() == source
        return

    assert cropped.tobytes() == source
    corners = np.asarray(result.rectangle.corners)
    physical_corners = np.asarray(
        [[left, top], [right, top], [right, bottom], [left, bottom]],
        dtype=float,
    ) - np.asarray(first_crop[:2])
    # Projection onto the fitted rectangle's own axes catches any corner
    # excluded by tilt; a bounding-box-only check could miss those cuts.
    horizontal = corners[1] - corners[0]
    vertical = corners[3] - corners[0]
    width = np.linalg.norm(horizontal)
    height = np.linalg.norm(vertical)
    coordinates = (physical_corners - corners[0]) @ np.stack(
        [horizontal / width, vertical / height], axis=1
    )
    assert np.all(coordinates >= -3), "Orientation removed a physical outer side."
    assert np.all(coordinates <= np.array([width, height]) + 3), (
        "Orientation removed a physical outer side."
    )


@pytest.mark.parametrize("side", ["left", "right", "top", "bottom"])
def test_orientation_preserves_faint_blurred_physical_extension(side):
    # The brighter strip is physically gel, even though an inner sharp step
    # creates a much stronger edge. This is also a first-crop safety regression.
    bounds = (200, 70, 610, 535)
    values = np.full((600, 800), 210, dtype=np.uint8)
    left, top, right, bottom = bounds
    values[top:bottom, left:right] -= 20
    outer = Image.fromarray(values).filter(ImageFilter.GaussianBlur(radius=6))
    values = np.asarray(outer).copy()
    if side == "left":
        left += 85
    elif side == "right":
        right -= 85
    elif side == "top":
        top += 85
    else:
        bottom -= 85
    values[top:bottom, left:right] -= 100

    _assert_orientation_preserves_physical_outline_or_declines(
        Image.fromarray(values), bounds
    )


@pytest.mark.parametrize("outer_contrast", [5, 10, 20])
def test_orientation_does_not_replace_faint_outer_outline_with_inner_rectangle(
    outer_contrast,
):
    bounds = (200, 70, 610, 535)
    values = np.full((600, 800), 210, dtype=np.uint8)
    left, top, right, bottom = bounds
    values[top:bottom, left:right] -= outer_contrast
    values[160:450, 285:545] -= 100

    _assert_orientation_preserves_physical_outline_or_declines(
        Image.fromarray(values), bounds
    )


@pytest.mark.parametrize("long_axis", ["horizontal", "vertical"])
def test_extreme_aspect_ratio_reports_uncertain_outline(long_axis):
    # These are valid TIFF dimensions, but reducing the long axis for analysis
    # leaves too few scan lines to estimate all four physical edges reliably.
    values = np.full((48, 20000), 220, dtype=np.uint8)
    values[:, 4000:16000] = 80
    if long_axis == "vertical":
        values = values.T

    with pytest.raises(OrientationError):
        orient_gel(Image.fromarray(values))
