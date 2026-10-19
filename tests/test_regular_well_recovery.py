"""Outcome regressions for a faint, regular comb with one unloaded well.

The generated gel is independent of private image pixels. Set
GEL_ANALYZER_15_WELL_IMAGE and/or GEL_ANALYZER_15_WELL_CROP to run the
additional opt-in checks against the supplied full gel and well-strip images.
"""

import os

import numpy as np
from PIL import Image, ImageFilter
import pytest

from gel_analyzer.lane_evidence import downstream_spans
from gel_analyzer.regular_wells import recover_regular_wells
from gel_analyzer.wells import Well, _detect_supported_wells, detect_wells
from gel_analyzer.workflow_orientation import swap_bounds, swap_point


CENTERS = 21 + np.arange(15) * 34.7
GUIDE = ((20, 3), (20, 528))


def _regular_gel(*, band_polarity=-1, wells=True, seed=17):
    """Faint embossed rims, smooth illumination, dirt, and 14 loaded lanes."""
    ys, xs = np.mgrid[:536, :825]
    values = 165 + xs * 0.006 + ys * 0.003
    values += 3 * np.sin(ys / 94) - 5 * np.exp(-((xs - 26) / 42) ** 2)
    values += 2 * np.cos((xs + ys) / 160)
    band_bounds = []
    if wells:
        for index, center in enumerate(CENTERS):
            top, bottom = round(center - 12), round(center + 12)
            left, right = 11 + index % 2, 31 + index % 2
            strength = 6 + (index % 4) * 0.8
            # Opposite-polarity edges approximate a weak visible outline even
            # when the central line has nearly the same intensity as the gel.
            values[top:bottom, left:left + 2] -= strength
            values[top:bottom, right - 2:right] -= strength * 0.75
            values[top:top + 2, left:right] -= strength * 0.65
            values[bottom - 2:bottom, left:right] += strength * 0.65
            values[top + 2:bottom - 2, left + 3:left + 5] += strength * 0.7
        # A narrow smear bridges two rims, and a local spot competes with the
        # complete outline of another well. Neither should become a lane.
        values[round(CENTERS[3] - 7):round(CENTERS[4] + 7), 19:21] -= 3
        values[round(CENTERS[7] - 2):round(CENTERS[7] + 3), 15:25] -= 8
    for index, center in enumerate(CENTERS[:-1]):
        top, bottom = round(center - 11), round(center + 11)
        positions = (226, 252, 286, 316, 350, 370, 397, 430, 463) if index == 0 else ((444,) if index < 10 else (241,))
        for left in positions:
            values[top:bottom, left:left + 7] += band_polarity * (55 + 5 * (index % 3))
            band_bounds.append((index, (left, top, left + 7, bottom)))
    values += np.random.default_rng(seed).normal(0, 0.9, values.shape)
    image = Image.fromarray(values.clip(0, 255).astype(np.uint8))
    return image.filter(ImageFilter.GaussianBlur(0.65)), band_bounds


def _assert_comb(result, centers=CENTERS, *, tolerance=5, bounds=(825, 536)):
    assert len(result.wells) == len(result.lanes) == len(centers)
    np.testing.assert_allclose([well.center[1] for well in result.wells], centers, atol=tolerance)
    heights = np.array([well.bounds[3] - well.bounds[1] for well in result.wells])
    depths = np.array([well.bounds[2] - well.bounds[0] for well in result.wells])
    assert np.all((16 <= heights) & (heights <= 34))
    assert heights.max() / heights.min() < 1.75
    assert np.all((10 <= depths) & (depths <= 32))
    assert depths.max() / depths.min() < 2
    for well in result.wells:
        assert 7 <= well.bounds[0] <= 20
        assert 24 <= well.bounds[2] <= 40
    for first, second in zip(result.wells, result.wells[1:]):
        assert first.bounds[3] <= second.bounds[1]
    for first, second in zip(result.lanes, result.lanes[1:]):
        assert first[3] <= second[1]
    for left, top, right, bottom in result.lanes:
        assert 0 <= left < right <= bounds[0]
        assert 0 <= top < bottom <= bounds[1]


def _assert_band_coverage(result, bands):
    for index, (_, top, _, bottom) in bands:
        lane = result.lanes[index]
        covered = max(0, min(bottom, lane[3]) - max(top, lane[1]))
        assert covered / (bottom - top) >= 0.85


@pytest.mark.parametrize("missing", (None, 2), ids=("four-visible-wells", "one-absent-well"))
def test_known_four_well_count_recovers_faint_rims_from_only_two_supported_outlines(missing):
    rows = ((30, 66), (100, 136), (170, 206), (240, 276))
    values = np.full((310, 360), 120.0)
    for index, (top, bottom) in enumerate(rows):
        if index == missing:
            continue
        strength = 20 if index in (0, 3) else 6
        values[top:bottom, 36:38] += strength
        values[top:bottom, 52:54] += strength
        values[top:top + 2, 36:54] += strength * 0.5
        values[bottom - 2:bottom, 36:54] -= strength * 0.5
    values += np.random.default_rng(41).normal(0, 0.5, values.shape)
    image = Image.fromarray(values.clip(0, 255).astype(np.uint8)).filter(ImageFilter.GaussianBlur(0.5))
    pixels = np.asarray(image, dtype=float)
    before = pixels.copy()
    pixels.flags.writeable = False
    # Only the first and last outlines are established. The entered count
    # supplies the two interior slots without needing a larger consensus.
    anchors = tuple(Well((36, top, 54, bottom), (45, (top + bottom) / 2))
                    for top, bottom in (rows[0], rows[-1]))

    recovered, warnings = recover_regular_wells(pixels, ((45, 26), (45, 280)), anchors, expected_count=4)

    expected = [(36, top, 54, bottom) for index, (top, bottom) in enumerate(rows) if index != missing]
    np.testing.assert_allclose([well.bounds for well in recovered], expected, atol=1)
    assert recovered[0] == anchors[0]
    assert recovered[-1] == anchors[-1]
    assert warnings
    # An absent rim remains unconfirmed for the later count allocator to
    # disclose as inference; the known count alone is not image evidence.
    assert len(recovered) == (4 if missing is None else 3)
    np.testing.assert_array_equal(pixels, before)


@pytest.mark.parametrize("dx", (-3, 0, 3))
@pytest.mark.parametrize("crop", (False, True), ids=("full-gel", "well-strip"))
def test_fifteen_faint_wells_survive_dirt_and_small_guide_shifts(dx, crop):
    image, bands = _regular_gel()
    if crop:
        image = image.crop((0, 0, 46, image.height))
    before = image.tobytes(), image.mode, image.size
    guide = tuple((x + dx, y) for x, y in GUIDE)

    result = detect_wells(image, guide, expected_count=15)

    _assert_comb(result, bounds=image.size)
    if not crop:
        _assert_band_coverage(result, bands)
    # The bottom position must come from its visible empty well, not a band.
    assert abs(result.wells[-1].center[1] - CENTERS[-1]) <= 5
    assert (image.tobytes(), image.mode, image.size) == before


@pytest.mark.parametrize("band_polarity", (-1, 1), ids=("dark-bands", "bright-bands"))
def test_regular_comb_recovery_is_transpose_equivariant(band_polarity):
    image, bands = _regular_gel(band_polarity=band_polarity)
    top_image = image.transpose(Image.Transpose.TRANSPOSE)
    before = top_image.tobytes(), top_image.mode, top_image.size

    left = detect_wells(image, GUIDE, expected_count=15)
    top = detect_wells(top_image, tuple(swap_point(point) for point in GUIDE),
                       expected_count=15, workflow_orientation="wells_top")

    _assert_comb(left)
    _assert_band_coverage(left, bands)
    assert [well.bounds for well in top.wells] == [swap_bounds(well.bounds) for well in left.wells]
    assert [well.center for well in top.wells] == [swap_point(well.center) for well in left.wells]
    assert top.lanes == tuple(swap_bounds(lane) for lane in left.lanes)
    assert (top_image.tobytes(), top_image.mode, top_image.size) == before


@pytest.mark.parametrize("dtype", ("<u2", ">u2"))
def test_regular_comb_recovery_preserves_native_sixteen_bit_pixels(dtype):
    source, bands = _regular_gel()
    image = Image.fromarray((np.asarray(source).astype(np.uint16) * 193 + 17).astype(dtype))
    before = image.tobytes(), image.mode, image.size

    result = detect_wells(image, GUIDE, expected_count=15)

    _assert_comb(result)
    _assert_band_coverage(result, bands)
    assert (image.tobytes(), image.mode, image.size) == before


@pytest.mark.parametrize("band_polarity", (-1, 1))
def test_regular_downstream_bands_do_not_claim_supported_well_outlines(band_polarity):
    image, _ = _regular_gel(band_polarity=band_polarity, wells=False)

    result = detect_wells(image, GUIDE, expected_count=15)

    assert len(result.wells) == len(result.lanes) == 15
    assert any("15 position(s) were inferred" in warning for warning in result.warnings)


@pytest.mark.parametrize("seed,missing", ((43, 0), (43, 7), (71, 7)))
def test_regular_neighbors_and_a_band_infer_absent_well_with_review_warning(seed, missing):
    source, _ = _regular_gel(seed=seed)
    without_wells, _ = _regular_gel(wells=False, seed=seed)
    pixels = np.asarray(source).copy()
    center = CENTERS[missing]
    top, bottom = round(center - 17), round(center + 17)
    # Preserve the downstream band and the same image noise while removing
    # only this well. The count and remaining wells establish its position,
    # but regular spacing and a band do not establish a visible well outline.
    pixels[top:bottom, :100] = np.asarray(without_wells)[top:bottom, :100]

    result = detect_wells(Image.fromarray(pixels), GUIDE, expected_count=15)

    _assert_comb(result)
    assert abs(result.wells[missing].center[1] - center) <= 5
    assert any("inferred" in warning and "not confirmed by image evidence" in warning
               for warning in result.warnings)


@pytest.mark.parametrize("seed", (3, 17, 43))
def test_blurred_texture_is_not_promoted_to_a_regular_comb(seed):
    rng = np.random.default_rng(seed)
    ys, xs = np.mgrid[:536, :825]
    values = 165 + 3 * np.sin(ys / 94) + xs * 0.006 + rng.normal(0, 1.2, xs.shape)
    image = Image.fromarray(values.clip(0, 255).astype(np.uint8)).filter(ImageFilter.GaussianBlur(0.65))

    result = _detect_supported_wells(image, GUIDE)

    # Any isolated preexisting texture fragments must not be extrapolated to
    # a long, apparently complete regular comb.
    assert len(result.wells) <= 2


def test_crisp_irregular_wells_keep_their_independent_sizes_and_positions():
    values = np.full((536, 825), 130, dtype=np.uint8)
    rows = ((8, 34), (51, 69), (89, 123), (146, 168), (182, 223),
            (248, 266), (280, 310), (339, 360), (383, 425), (467, 491))
    for index, (top, bottom) in enumerate(rows):
        values[top:bottom, 10:31] = 195 if index % 2 else 65
    image = Image.fromarray(values)

    counted = detect_wells(image, GUIDE, expected_count=len(rows))

    assert [well.bounds for well in counted.wells] == [(10, top, 31, bottom) for top, bottom in rows]
    assert [lane[1::2] for lane in counted.lanes] == list(rows)


def test_partial_guide_recovers_only_the_selected_regular_wells():
    image, bands = _regular_gel()
    centers = CENTERS[3:12]
    guide = ((20, round(centers[0] - 16)), (20, round(centers[-1] + 16)))

    result = detect_wells(image, guide, expected_count=9)

    _assert_comb(result, centers, bounds=image.size)
    assert result.wells[0].bounds[1] >= guide[0][1]
    assert result.wells[-1].bounds[3] <= guide[1][1]
    selected_bands = [(index - 3, bounds) for index, bounds in bands if 3 <= index <= 11]
    _assert_band_coverage(result, selected_bands)


@pytest.mark.parametrize("band_polarity", (-1, 1), ids=("dark-bands", "bright-bands"))
def test_downstream_spans_find_fourteen_loaded_lanes_despite_a_tall_scratch(band_polarity):
    # These pixels contain no wells: the scanner must independently locate
    # lane positions, collapse the ladder's many bands, and ignore a scratch.
    ys, xs = np.mgrid[:536, :825]
    pixels = 135 + xs * 0.01 + ys * 0.002
    for index, center in enumerate(CENTERS[:-1]):
        positions = (155, 194, 233, 274, 315, 356, 397) if index == 0 else ((441,) if index < 10 else (243,))
        for left in positions:
            pixels[round(center - 11):round(center + 11), left:left + 7] += band_polarity * 65
    pixels[:, 521:526] += band_polarity * 60
    pixels += np.random.default_rng(71).normal(0, 0.6, pixels.shape)
    before = pixels.copy()
    pixels.flags.writeable = False

    spans = downstream_spans(pixels, GUIDE, depth=20, thickness=24)

    assert len(spans) == 14
    np.testing.assert_allclose([(top + bottom) / 2 for top, bottom in spans], CENTERS[:-1], atol=2)
    assert all(18 <= bottom - top <= 26 for top, bottom in spans)
    assert all(first[1] <= second[0] for first, second in zip(spans, spans[1:]))
    assert not any(top <= CENTERS[-1] <= bottom for top, bottom in spans)
    np.testing.assert_array_equal(pixels, before)


@pytest.mark.parametrize("background", ("gradient", "noise", "scratch"))
def test_downstream_spans_reject_background_and_full_height_scratches(background):
    ys, xs = np.mgrid[:536, :825]
    pixels = 135 + xs * 0.01 + ys * 0.002
    if background == "noise":
        pixels += np.random.default_rng(71).normal(0, 3, pixels.shape)
    elif background == "scratch":
        pixels[:, 210:215] -= 65
        pixels[:, 510:517] += 65
    before = pixels.copy()

    spans = downstream_spans(pixels, GUIDE, depth=20, thickness=24)

    assert spans == []
    np.testing.assert_array_equal(pixels, before)


@pytest.mark.parametrize("environment,first_center", (
    ("GEL_ANALYZER_15_WELL_IMAGE", 20),
    ("GEL_ANALYZER_15_WELL_CROP", 23),
))
@pytest.mark.parametrize("dx", (-3, 0, 3))
def test_private_fifteen_well_example(environment, first_center, dx):
    path = os.environ.get(environment)
    if not path:
        pytest.skip(f"Set {environment} to run the private-image regression.")
    with Image.open(path) as opened:
        image = opened.copy()
    before = image.tobytes(), image.mode, image.size
    guide = ((20 + dx, 3), (20 + dx, image.height - 8))

    result = detect_wells(image, guide, expected_count=15)

    _assert_comb(result, first_center + np.arange(15) * 34.7, tolerance=8, bounds=image.size)
    if environment == "GEL_ANALYZER_15_WELL_IMAGE":
        # The first ten loaded lanes migrate farther than the final four.
        # These interior band intervals are independently read from the image.
        for index, (top, bottom) in enumerate(((15, 33), (48, 68), (83, 103),
                (118, 137), (153, 171), (186, 206), (220, 240), (255, 275),
                (290, 310), (325, 344), (355, 375), (389, 409),
                (424, 444), (459, 479))):
            lane = result.lanes[index]
            assert max(0, min(bottom, lane[3]) - max(top, lane[1])) / (bottom - top) >= 0.8
    assert (image.tobytes(), image.mode, image.size) == before
