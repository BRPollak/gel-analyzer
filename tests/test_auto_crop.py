"""Generated gels check conservative crop geometry independently of TIFF I/O."""

from numbers import Integral

import numpy as np
from PIL import Image, ImageDraw
import pytest

from gel_analyzer.auto_crop import find_gel_crop


def make_gel(size=(800, 600), bounds=(200, 70, 610, 535), gradient=False):
    """Return an image and a mask of every physical gel pixel, including wells."""
    width, height = size
    background = np.full((height, width), 220.0)
    if gradient:
        y, x = np.mgrid[:height, :width]
        background -= 30 * x / width + 20 * y / height
    mask = np.zeros((height, width), dtype=bool)
    left, top, right, bottom = bounds
    mask[top:bottom, left:right] = True
    background[mask] -= 80
    return Image.fromarray(background.astype(np.uint8)), mask


def assert_contains_gel(image, mask, crop_box):
    assert len(crop_box) == 4
    assert all(isinstance(coordinate, Integral) for coordinate in crop_box)
    left, top, right, bottom = crop_box
    assert 0 <= left < right <= image.width
    assert 0 <= top < bottom <= image.height
    y, x = np.nonzero(mask)
    assert left <= x.min() and x.max() < right
    assert top <= y.min() and y.max() < bottom


def assert_small_margin(image, mask, crop_box):
    assert_contains_gel(image, mask, crop_box)
    y, x = np.nonzero(mask)
    left, top, right, bottom = crop_box
    margins = (x.min() - left, y.min() - top, right - x.max() - 1, bottom - y.max() - 1)
    # Each side must retain visible background, without treating most of the
    # original surrounding frame as a successful crop.
    assert min(margins) > 0
    short_side = min(x.max() - x.min() + 1, y.max() - y.min() + 1)
    assert max(margins) <= 0.08 * short_side + 8


@pytest.mark.parametrize(
    "size,bounds",
    [
        ((800, 600), (200, 70, 610, 535)),
        ((600, 800), (95, 140, 510, 660)),
        ((700, 700), (170, 150, 545, 520)),
        ((2400, 1800), (620, 220, 1860, 1620)),
    ],
)
def test_unambiguous_rectangle_is_cropped_with_small_margin(size, bounds):
    image, mask = make_gel(size, bounds)
    original = image.tobytes()

    crop_box = find_gel_crop(image)

    assert_small_margin(image, mask, crop_box)
    assert image.tobytes() == original


def test_lighting_gradient_does_not_pull_crop_inside_gel():
    image, mask = make_gel(gradient=True)

    assert_small_margin(image, mask, find_gel_crop(image))


def test_bright_wells_and_dark_bands_are_not_mistaken_for_outer_edges():
    image, mask = make_gel()
    draw = ImageDraw.Draw(image)
    for lane_x in range(225, 590, 55):
        draw.rounded_rectangle((lane_x, 90, lane_x + 30, 106), radius=6, fill=190)
        for band_y in (220, 265, 345):
            draw.rectangle((lane_x, band_y, lane_x + 30, band_y + 5), fill=15)
    for band_y in range(190, 410, 30):
        draw.rectangle((225, band_y, 255, band_y + 4), fill=20)

    assert_small_margin(image, mask, find_gel_crop(image))


@pytest.mark.parametrize("angle", [-3, -1.5, 1.5, 3])
def test_mild_tilt_never_removes_any_gel_corner(angle):
    image, mask = make_gel()
    image = image.rotate(angle, resample=Image.Resampling.BILINEAR, fillcolor=220)
    mask_image = Image.fromarray(mask).rotate(angle, resample=Image.Resampling.NEAREST)

    assert_contains_gel(image, np.asarray(mask_image), find_gel_crop(image))


def test_dark_peripheral_object_cannot_make_crop_cut_the_gel():
    image, mask = make_gel()
    ImageDraw.Draw(image).rectangle((20, 140, 105, 440), fill=5)

    assert_contains_gel(image, mask, find_gel_crop(image))


def test_local_outward_edge_irregularity_is_not_discarded_as_a_line_fit_outlier():
    image, mask = make_gel()
    ImageDraw.Draw(image).rectangle((174, 290, 200, 312), fill=140)
    mask[290:313, 174:201] = True

    assert_contains_gel(image, mask, find_gel_crop(image))


@pytest.mark.parametrize(
    "bounds",
    [
        (0, 70, 610, 535),
        (200, 0, 610, 535),
        (200, 70, 800, 535),
        (200, 70, 610, 600),
    ],
)
def test_missing_outer_edge_keeps_full_frame(bounds):
    image, mask = make_gel(bounds=bounds)

    crop_box = find_gel_crop(image)

    assert_contains_gel(image, mask, crop_box)
    assert crop_box == (0, 0, image.width, image.height)


def test_stronger_inner_rectangle_never_truncates_fainter_physical_gel():
    image, mask = make_gel()
    ImageDraw.Draw(image).rectangle((285, 160, 544, 449), fill=25)

    assert_contains_gel(image, mask, find_gel_crop(image))


@pytest.mark.parametrize("mode", ["L", "RGB", "RGBA", "P"])
def test_supported_color_modes_use_luminance_for_boundary_detection(mode):
    image, mask = make_gel()
    if mode == "P":
        # Deliberately reverse palette-index ordering relative to brightness.
        index_array = np.where(mask, 230, 10).astype(np.uint8)
        image = Image.fromarray(index_array).convert("P")
        palette = [0] * 768
        palette[10 * 3 : 10 * 3 + 3] = [220, 220, 220]
        palette[230 * 3 : 230 * 3 + 3] = [140, 140, 140]
        image.putpalette(palette)
    else:
        image = image.convert(mode)

    assert_small_margin(image, mask, find_gel_crop(image))


@pytest.mark.parametrize("byte_order", ["<u2", ">u2"])
def test_16_bit_analysis_does_not_clip_all_intensities_to_white(byte_order):
    _, mask = make_gel()
    # Every value is above 255: a direct conversion to L destroys both edges.
    values = np.where(mask, 18000, 47000).astype(byte_order)
    image = Image.fromarray(values)
    original = image.tobytes()

    assert_small_margin(image, mask, find_gel_crop(image))
    assert image.tobytes() == original


@pytest.mark.parametrize("value", [0, 127, 255])
def test_constant_image_keeps_full_frame(value):
    image = Image.new("L", (500, 400), value)

    assert find_gel_crop(image) == (0, 0, 500, 400)


def test_gradient_without_gel_keeps_full_frame():
    y, x = np.mgrid[:500, :700]
    image = Image.fromarray((230 - 100 * x / 700 - 40 * y / 500).astype(np.uint8))

    assert find_gel_crop(image) == (0, 0, 700, 500)


def test_noise_without_gel_keeps_full_frame():
    values = np.random.default_rng(7).normal(150, 30, (500, 700))
    image = Image.fromarray(np.clip(values, 0, 255).astype(np.uint8))

    assert find_gel_crop(image) == (0, 0, 700, 500)


def test_faint_rectangle_keeps_full_frame():
    image = Image.new("L", (800, 600), 160)
    ImageDraw.Draw(image).rectangle((200, 70, 609, 534), fill=157)

    assert find_gel_crop(image) == (0, 0, 800, 600)


@pytest.mark.parametrize("size", [(1, 1), (2, 9), (16, 16), (31, 9), (100, 3000), (3000, 100)])
def test_tiny_image_keeps_full_frame(size):
    width, height = size
    image = Image.new("L", size, 220)
    ImageDraw.Draw(image).rectangle(
        (width // 4, height // 4, width * 3 // 4, height * 3 // 4), fill=20
    )

    assert find_gel_crop(image) == (0, 0, width, height)
