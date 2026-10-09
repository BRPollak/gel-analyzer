"""Sensitivity regressions distinguish lighting artifacts from physical borders.

These scenes are generated independently of the real gels used for tuning, so
they check enclosure and robustness without embedding private image fixtures.
"""

import numpy as np
from PIL import Image, ImageFilter
import pytest

from gel_analyzer.auto_crop import find_gel_crop


_SIZE = (800, 600)
_BOUNDS = (200, 70, 610, 535)


def _scene():
    width, height = _SIZE
    y, x = np.mgrid[:height, :width]
    values = np.full((height, width), 210.0)
    left, top, right, bottom = _BOUNDS
    values[top:bottom, left:right] -= 80
    return values, x, y


def _assert_encloses(crop, bounds=_BOUNDS):
    left, top, right, bottom = crop
    gel_left, gel_top, gel_right, gel_bottom = bounds
    assert 0 <= left <= gel_left < gel_right <= right <= _SIZE[0]
    assert 0 <= top <= gel_top < gel_bottom <= bottom <= _SIZE[1]


def _assert_useful_crop(crop):
    _assert_encloses(crop)
    left, top, right, bottom = crop
    margins = (
        _BOUNDS[0] - left,
        _BOUNDS[1] - top,
        right - _BOUNDS[2],
        bottom - _BOUNDS[3],
    )
    assert min(margins) > 0
    assert max(margins) <= 40


@pytest.mark.parametrize("axis", ["horizontal", "vertical"])
def test_gradual_background_shading_does_not_block_clear_gel_edges(axis):
    values, x, y = _scene()
    # Curved illumination has a modest derivative outside the gel, but no
    # physical discontinuity and no second rectangle enclosing the center.
    if axis == "horizontal":
        values += 20 * (1 + np.tanh((x - 695) / 32)) / 2
    else:
        values += 20 * (1 + np.tanh((y - 570) / 20)) / 2
    image = Image.fromarray(values.astype(np.uint8))

    _assert_useful_crop(find_gel_crop(image))


@pytest.mark.parametrize("side", ["left", "right", "top", "bottom"])
def test_local_exterior_artifact_is_not_a_competing_gel_rectangle(side):
    values, _, _ = _scene()
    # The central projection sees this faint exterior step, but it does not
    # continue along most of the corresponding gel side.
    if side == "left":
        values[210:390, 110:200] -= 6
    elif side == "right":
        values[210:390, 610:700] -= 6
    elif side == "top":
        values[20:70, 320:480] -= 6
    else:
        values[535:580, 320:480] -= 6
    image = Image.fromarray(values.astype(np.uint8))

    _assert_useful_crop(find_gel_crop(image))


@pytest.mark.parametrize("outer_contrast", [5, 10, 20])
def test_faint_physical_outer_rectangle_is_not_replaced_by_stronger_inner(
    outer_contrast,
):
    values = np.full((_SIZE[1], _SIZE[0]), 210.0)
    left, top, right, bottom = _BOUNDS
    values[top:bottom, left:right] -= outer_contrast
    values[160:450, 285:545] -= 100
    image = Image.fromarray(values.astype(np.uint8))

    # Either the complete frame or a crop around the physical outer rectangle
    # is acceptable. Cutting to the attractive inner rectangle is never safe.
    _assert_encloses(find_gel_crop(image))


@pytest.mark.parametrize("obscured_top", [False, True])
def test_blurred_outer_rectangle_is_not_discarded_as_smooth_illumination(
    obscured_top,
):
    values = np.full((_SIZE[1], _SIZE[0]), 210, dtype=np.uint8)
    left, top, right, bottom = _BOUNDS
    values[top:bottom, left:right] -= 20
    if obscured_top:
        # A bright patch obscures about one third of the upper border. The
        # remaining three enclosing borders must still protect the outer gel.
        values[45:100, 310:455] = 210
    # Imaging blur can soften a physical border. Its four consistent outer
    # sides still enclose the gel even if a sharper inner region looks clearer.
    outer = Image.fromarray(values).filter(ImageFilter.GaussianBlur(radius=6))
    values = np.asarray(outer).copy()
    values[160:450, 285:545] -= 100
    image = Image.fromarray(values)

    _assert_encloses(find_gel_crop(image))


@pytest.mark.parametrize("side", ["left", "right", "top", "bottom"])
def test_blurred_physical_extension_on_one_side_is_not_discarded(side):
    values = np.full((_SIZE[1], _SIZE[0]), 210, dtype=np.uint8)
    left, top, right, bottom = _BOUNDS
    values[top:bottom, left:right] -= 20
    outer = Image.fromarray(values).filter(ImageFilter.GaussianBlur(radius=6))
    values = np.asarray(outer).copy()
    # A stronger inner region can share three real gel boundaries while one
    # faint, blurred strip remains physically part of the gel on the fourth.
    if side == "left":
        left += 85
    elif side == "right":
        right -= 85
    elif side == "top":
        top += 85
    else:
        bottom -= 85
    values[top:bottom, left:right] -= 100
    image = Image.fromarray(values)

    _assert_encloses(find_gel_crop(image))


@pytest.mark.parametrize(
    "dtype,gain,offset",
    [("u1", 1, 0), ("u1", 0.5, 35), ("<u2", 128, 14000), (">u2", 256, 4000)],
)
def test_intensity_rescaling_and_bit_depth_keep_gel_enclosed(dtype, gain, offset):
    values, x, y = _scene()
    values -= 35 * x / _SIZE[0] + 25 * y / _SIZE[1]
    image = Image.fromarray((values * gain + offset).astype(dtype))
    source = image.tobytes()

    _assert_useful_crop(find_gel_crop(image))
    assert image.tobytes() == source


@pytest.mark.parametrize("side", ["left", "right", "top", "bottom"])
def test_dark_rim_inside_gel_cannot_truncate_physical_edge(side):
    values, _, _ = _scene()
    left, top, right, bottom = _BOUNDS
    if side == "left":
        values[top:bottom, left:left + 18] -= 70
    elif side == "right":
        values[top:bottom, right - 18:right] -= 70
    elif side == "top":
        values[top:top + 18, left:right] -= 70
    else:
        values[bottom - 18:bottom, left:right] -= 70
    image = Image.fromarray(values.astype(np.uint8))

    _assert_encloses(find_gel_crop(image))


def test_broad_exterior_shadow_cannot_move_crop_inside_gel():
    values, x, y = _scene()
    # A shadow spans the physical right side and broadens the observed edge.
    # Its varying strength is a plausible lighting change, not extra gel.
    values -= 45 * np.exp(-((x - 610) / 28) ** 2) * (
        0.6 + 0.4 * np.sin(np.pi * y / _SIZE[1]) ** 2
    )
    image = Image.fromarray(values.astype(np.uint8))

    _assert_encloses(find_gel_crop(image))
