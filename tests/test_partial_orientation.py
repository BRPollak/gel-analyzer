"""Partial outlines determine tilt without inventing absent gel crop edges."""

import math
from dataclasses import replace
from io import BytesIO

import numpy as np
from PIL import Image
import pytest

from gel_analyzer.orientation import OrientationError, fit_gel_rectangle, fit_partial_gel_edges, orient_gel
from gel_analyzer.image_io import load_tiff, orient_gel_image


def partial_gel(angle=13, *, missing="top", dtype=np.uint8, bright=False):
    y, x = np.mgrid[:520, :520]
    theta = math.radians(angle)
    local_x = (x + .5 - 260) * math.cos(theta) + (y + .5 - 260) * math.sin(theta)
    local_y = -(x + .5 - 260) * math.sin(theta) + (y + .5 - 260) * math.cos(theta)
    bounds = {"top": (-140, -500, 140, 180), "left": (-500, -160, 150, 160),
              "ends": (-140, -500, 140, 500)}[missing]
    left, top, right, bottom = bounds
    inside = (local_x > left) & (local_x < right) & (local_y > top) & (local_y < bottom)
    values = np.where(inside, 90, 220)
    if bright:
        values = 255 - values
    if np.dtype(dtype).itemsize == 2:
        values = values * 193 + 17
    return Image.fromarray(values.astype(dtype))


CLIPPED_SCENES = {
    # Both long side edges lie in the right half of the photograph. The bottom
    # edge spans only 30% of its width, so central scan lines cannot find it.
    "off_center": ((600, 500), (430, 100), (180, 600), 8, ("left", "right", "bottom")),
    # One side has only a few pixels of visible background near the bottom.
    "near_left_frame": ((600, 520), (255, 100), (480, 600), 2, ("left", "right", "bottom")),
    "near_both_sides": ((600, 520), (300, 100), (480, 600), 10, ("left", "right", "bottom")),
    "bottom_corners_cut": ((600, 520), (300, 420), (480, 600), -10, ("left", "right", "top")),
    # The visible vertical segments are 95–150px high, entirely outside most
    # of the previous central 20–80% scan range. Two bottom corners remain.
    "short_side_segments": ((600, 520), (300, -150), (400, 550), 8, ("left", "right", "bottom")),
    # Only two pixels separate the left side and the frame; demanding a fixed
    # 7%-image-width outside-background window rejects this clear boundary.
    "two_pixel_background": ((600, 520), (242, 100), (480, 600), 0, ("left", "right", "bottom")),
}


def clipped_scene(name, *, bright=False, dtype=np.uint8, clutter=False):
    size, center, gel_size, angle, _ = CLIPPED_SCENES[name]
    y, x = np.mgrid[:size[1], :size[0]]
    theta = math.radians(angle)
    local_x = (x + .5 - center[0]) * math.cos(theta) + (y + .5 - center[1]) * math.sin(theta)
    local_y = -(x + .5 - center[0]) * math.sin(theta) + (y + .5 - center[1]) * math.cos(theta)
    inside = (abs(local_x) < gel_size[0] / 2) & (abs(local_y) < gel_size[1] / 2)
    values = np.where(inside, 90., 220.)
    if clutter:
        # Realistic internal bands and mild sensor noise cannot substitute for
        # the physical sides or hide a short side beside the image boundary.
        for row in (40, 130, 220):
            values[inside & (abs(local_y - row) < 5) & (abs(local_x) < gel_size[0] * .3)] = 170
        values += np.random.default_rng(12).normal(0, .8, values.shape)
    if bright:
        values = 255 - values
    if np.dtype(dtype).itemsize == 2:
        values = values * 193 + 17
    return Image.fromarray(values.astype(dtype))


@pytest.mark.parametrize("angle", [-18, 0, 13])
@pytest.mark.parametrize("missing,supported", [("top", ("left", "right", "bottom")),
                                                ("left", ("right", "top", "bottom"))])
@pytest.mark.parametrize("orientation", ["wells_left", "wells_top"])
def test_three_sides_and_two_visible_corners_use_partial_tilt_and_preserve_full_frame(angle, missing, supported, orientation):
    image = partial_gel(angle, missing=missing)
    original = image.tobytes()
    with pytest.raises(OrientationError):
        fit_gel_rectangle(image)

    result = orient_gel(image, workflow_orientation=orientation)

    assert result.outline_complete is False
    assert result.supported_edges == supported
    assert result.rectangle.angle_degrees == pytest.approx(angle, abs=.2)
    assert result.counterclockwise_degrees == pytest.approx(angle + (90 if orientation == "wells_left" else 0), abs=.2)
    # Project every source corner into the returned envelope. All four must
    # remain inside, even though the gel's missing side has no inferred bound.
    corners = np.asarray(result.rectangle.corners)
    u = (corners[1] - corners[0]) / result.rectangle.width
    v = (corners[3] - corners[0]) / result.rectangle.height
    source_corners = np.asarray(((0, 0), (520, 0), (520, 520), (0, 520)))
    mapped = (source_corners - corners[0]) @ np.stack((u, v), axis=1)
    assert np.min(mapped) >= -1e-7
    assert np.max(mapped[:, 0]) <= result.rectangle.width + 1e-7
    assert np.max(mapped[:, 1]) <= result.rectangle.height + 1e-7
    assert result.image.width >= 520 and result.image.height >= 520
    assert image.tobytes() == original


@pytest.mark.parametrize("scene", CLIPPED_SCENES)
@pytest.mark.parametrize("orientation", ["wells_left", "wells_top"])
def test_three_visible_side_segments_work_off_center_and_at_frame_edges(scene, orientation):
    image = clipped_scene(scene)
    size, center, gel_size, expected_angle, expected_edges = CLIPPED_SCENES[scene]
    # Verify the fixture really has two adjacent corners outside the frame,
    # while the two other corners and three distinct side segments are visible.
    theta = math.radians(expected_angle)
    rotation = np.asarray(((math.cos(theta), -math.sin(theta)), (math.sin(theta), math.cos(theta))))
    corners = np.asarray(((-1, -1), (1, -1), (1, 1), (-1, 1))) * (np.asarray(gel_size) / 2)
    corners = corners @ rotation.T + center
    assert sum((corners >= 0).all(axis=1) & (corners <= size).all(axis=1)) == 2
    with pytest.raises(OrientationError):
        fit_gel_rectangle(image)

    result = orient_gel(image, workflow_orientation=orientation)

    assert not result.outline_complete
    assert result.supported_edges == expected_edges
    assert result.rectangle.angle_degrees == pytest.approx(expected_angle, abs=.25)
    envelope = np.asarray(result.rectangle.corners)
    axes = np.stack(((envelope[1] - envelope[0]) / result.rectangle.width,
                     (envelope[3] - envelope[0]) / result.rectangle.height), axis=1)
    source_corners = np.asarray(((0, 0), (size[0], 0), size, (0, size[1])))
    positions = (source_corners - envelope[0]) @ axes
    assert np.min(positions) >= -1e-7
    assert np.all(positions <= (result.rectangle.width + 1e-7, result.rectangle.height + 1e-7))


@pytest.mark.parametrize("scene", ["off_center", "near_left_frame", "short_side_segments"])
@pytest.mark.parametrize("bright", [False, True])
def test_clipped_side_segments_survive_bands_noise_and_either_contrast_polarity(scene, bright):
    image = clipped_scene(scene, bright=bright, clutter=True)
    angle, sides = fit_partial_gel_edges(image)
    assert angle == pytest.approx(CLIPPED_SCENES[scene][3], abs=.3)
    assert sides == CLIPPED_SCENES[scene][4]


@pytest.mark.parametrize("bright", [False, True])
def test_two_long_opposite_boundaries_can_supply_tilt_when_both_end_edges_are_outside_frame(bright):
    image = partial_gel(-18, missing="ends", bright=bright)
    angle, sides = fit_partial_gel_edges(image)
    assert angle == pytest.approx(-18, abs=.2)
    assert sides == ("left", "right")


@pytest.mark.parametrize("dtype", ["<u2", ">u2"])
@pytest.mark.parametrize("orientation", ["wells_left", "wells_top"])
def test_upright_partial_outline_preserves_every_uint16_pixel_without_rescaling(dtype, orientation):
    image = partial_gel(0, dtype=dtype)
    result = orient_gel(image, workflow_orientation=orientation)
    expected = np.asarray(image)
    if orientation == "wells_left":
        expected = expected.T
    np.testing.assert_array_equal(np.asarray(result.image), expected)
    assert np.asarray(result.image).dtype.itemsize == 2
    assert result.image.mode == image.mode


@pytest.mark.parametrize("dtype", ["<u2", ">u2"])
def test_tilted_partial_outline_keeps_uint16_low_bits_in_unmixed_regions(dtype):
    image = partial_gel(13, dtype=dtype)
    result = orient_gel(image, workflow_orientation="wells_top")
    values = np.asarray(result.image)
    assert result.image.mode == image.mode
    assert values.dtype.itemsize == 2
    assert np.count_nonzero(values == 90 * 193 + 17) > 10000
    assert np.count_nonzero(values == 220 * 193 + 17) > 10000


@pytest.mark.parametrize("mode", ["RGB", "RGBA", "LA"])
def test_expanded_color_canvas_preserves_mode_and_opaque_alpha(mode):
    image = partial_gel(13).convert(mode)
    result = orient_gel(image, workflow_orientation="wells_top")
    assert result.image.mode == mode
    if "A" in result.image.getbands():
        assert result.image.getchannel("A").getextrema() == (255, 255)


def test_retained_partial_angle_changes_workflow_without_refitting_or_cropping(monkeypatch):
    image = partial_gel(13)
    first = orient_gel(image, workflow_orientation="wells_top")

    def unexpected(*args, **kwargs):
        pytest.fail("An accepted partial angle must not be detected again.")

    monkeypatch.setattr("gel_analyzer.orientation.fit_gel_rectangle", unexpected)
    monkeypatch.setattr("gel_analyzer.orientation.fit_partial_gel_edges", unexpected)
    second = orient_gel(image, fallback_angle_degrees=first.rectangle.angle_degrees,
                        supported_edges=first.supported_edges)
    assert second.outline_complete is False
    assert second.supported_edges == first.supported_edges
    assert second.rectangle == first.rectangle
    assert second.counterclockwise_degrees == first.counterclockwise_degrees + 90
    np.testing.assert_array_equal(np.asarray(second.image), np.asarray(first.image).T)


@pytest.mark.parametrize("orientation", ["wells_left", "wells_top"])
def test_real_tiff_load_and_initial_crop_retain_partial_source_for_orientation(orientation):
    source = partial_gel(-18, missing="left", dtype=np.uint16)
    stream = BytesIO()
    source.save(stream, format="TIFF")
    initial = replace(load_tiff(stream.getvalue(), "partial.tif"), workflow_orientation=orientation)
    before = initial.preview_png
    assert initial.crop_box == (0, 0, 520, 520)
    with Image.open(BytesIO(before)) as copied:
        np.testing.assert_array_equal(np.asarray(copied), np.asarray(source))

    result = orient_gel_image(initial)

    assert result.orientation.outline_complete is False
    assert result.orientation.supported_edges == ("right", "top", "bottom")
    assert result.orientation.counterclockwise_degrees == pytest.approx(-18 + (90 if orientation == "wells_left" else 0), abs=.2)
    assert result.preview_width >= 520 and result.preview_height >= 520
    assert result.source_bytes == stream.getvalue()
    assert initial.preview_png == before
    assert initial.orientation is None


@pytest.mark.parametrize("scene", ["off_center", "near_left_frame", "short_side_segments"])
@pytest.mark.parametrize("orientation", ["wells_left", "wells_top"])
def test_real_tiff_pipeline_can_orient_three_off_center_side_segments(scene, orientation):
    image = clipped_scene(scene, dtype=np.uint16)
    stream = BytesIO()
    image.save(stream, format="TIFF")
    gel = replace(load_tiff(stream.getvalue(), f"{scene}.tif"), workflow_orientation=orientation)
    assert gel.crop_box == (0, 0, *image.size)

    result = orient_gel_image(gel)

    assert result.orientation.outline_complete is False
    assert result.orientation.supported_edges == CLIPPED_SCENES[scene][4]
    assert result.orientation.counterclockwise_degrees == pytest.approx(
        CLIPPED_SCENES[scene][3] + (90 if orientation == "wells_left" else 0), abs=.25)
    assert result.source_bytes == stream.getvalue()
    with Image.open(BytesIO(result.preview_png)) as output:
        values = np.asarray(output)
        assert values.dtype.itemsize == 2
        assert np.count_nonzero(values == 90 * 193 + 17) > 1000
        assert np.count_nonzero(values == 220 * 193 + 17) > 1000


@pytest.mark.parametrize("scene", ["blank", "gradient", "single_side", "stripe", "trapezoid", "noise"])
def test_ambiguous_or_insufficient_partial_evidence_still_requires_manual_outline(scene):
    y, x = np.mgrid[:520, :520]
    if scene == "blank":
        pixels = np.full((520, 520), 150)
    elif scene == "gradient":
        pixels = 60 + x * .2 + y * .08
    elif scene == "single_side":
        pixels = np.where(x + .2 * y < 300, 90, 220)
    elif scene == "stripe":
        pixels = np.where((x + .2 * y > 250) & (x + .2 * y < 270), 90, 220)
    elif scene == "trapezoid":
        pixels = np.where((x > 110 + .25 * y) & (x < 410) & (y < 450), 90, 220)
    else:
        pixels = np.random.default_rng(4).integers(0, 256, (520, 520))
    image = Image.fromarray(pixels.astype(np.uint8))
    with pytest.raises(OrientationError):
        orient_gel(image, workflow_orientation="wells_top")
