"""Conservative outer-gel detection; uncertainty keeps the complete image.

The supported scene is one approximately centered, nearly rectangular dark gel
on a lighter background. All analysis uses a temporary reduced grayscale copy.
Returned bounds use Pillow's half-open coordinates in the decoded source image.
"""

from dataclasses import dataclass
import math

import numpy as np
from PIL import Image


_ANALYSIS_LIMIT = 768
_MIN_STEP = 0.06
_MIN_SUPPORT = 0.90
_MARGIN_FRACTION = 0.03
_MIN_OUTER_STEP = 0.025
_MIN_EDGE_LOCALIZATION = 0.65
_MIN_OUTER_SUPPORT = 0.75


@dataclass(frozen=True)
class _Edge:
    low: float
    high: float
    slope: float


def _step_response(profile: np.ndarray, radius: int = 4) -> np.ndarray:
    """Measure a step across a chosen scale after mild noise smoothing."""
    smooth = np.convolve(np.pad(profile, 2, mode="edge"), np.ones(5) / 5, mode="valid")
    padded = np.pad(smooth, radius, mode="edge")
    return padded[2 * radius :] - padded[: -2 * radius]


def _edge_response(profile: np.ndarray, sign: int) -> np.ndarray:
    """Require a sustained brightness step rather than a thin band or dark rim."""
    size = len(profile)
    response = _step_response(profile) * sign
    padded = np.pad(profile, 14, mode="edge")
    before = np.median(
        [padded[14 - offset : 14 - offset + size] for offset in range(6, 14)], axis=0
    )
    after = np.median(
        [padded[14 + offset : 14 + offset + size] for offset in range(6, 14)], axis=0
    )
    return np.minimum(response, (after - before) * sign)


def _localized_response(profile: np.ndarray, sign: int) -> np.ndarray:
    """Separate localized boundaries from broad, smooth illumination changes.

    A sharp step has similar contrast across short and long windows. Gradual
    changes grow with window width; blurred physical edges are checked separately.
    """
    response = _edge_response(profile, sign)
    broad = _step_response(profile, radius=16) * sign
    return np.where(response >= _MIN_EDGE_LOCALIZATION * broad, response, 0)


def _initial_edge(profile: np.ndarray, sign: int, near: bool) -> int | None:
    size = len(profile)
    response = _edge_response(profile, sign)
    start, stop = (int(size * 0.02), int(size * 0.46)) if near else (
        int(size * 0.54), int(size * 0.98)
    )
    index = start + int(np.argmax(response[start:stop]))
    if response[index] < _MIN_STEP:
        return None

    return index


def _trace_edge(
    pixels: np.ndarray, base: int, start: int, stop: int, axis: int, sign: int,
    *, outer_range: tuple[int, int] | None = None, localized: bool = True,
) -> _Edge | None:
    """Require a sustained, nearly straight boundary along almost the whole side."""
    size = pixels.shape[axis]
    search = max(6, int(size * 0.07))
    # An alternative must be traced independently; never let its search window
    # jump inward to the already detected physical gel edge.
    if outer_range is not None:
        search = max(3, int(size * 0.02))
    minimum_step = _MIN_STEP if outer_range is None else _MIN_OUTER_STEP
    minimum_support = _MIN_SUPPORT if outer_range is None else _MIN_OUTER_SUPPORT
    traces = []
    positions = np.linspace(
        start + (stop - start) * 0.04, stop - (stop - start) * 0.04, 41
    )
    for position in positions:
        center = int(position)
        if axis == 0:
            profile = np.median(pixels[:, max(0, center - 2) : center + 3], axis=1)
        else:
            profile = np.median(pixels[max(0, center - 2) : center + 3, :], axis=0)
        response = (
            _step_response(profile) * sign
            if outer_range is None else (
                _localized_response(profile, sign) if localized
                else _edge_response(profile, sign)
            )
        )
        low, high = max(8, base - search), min(size - 8, base + search)
        if outer_range is not None:
            low, high = max(low, outer_range[0]), min(high, outer_range[1])
        if high <= low:
            return None
        index = low + int(np.argmax(response[low:high]))
        # A thin dark line alone is not a gel border: the interior must remain
        # darker after moving away from that line on both sides of the step.
        before = np.median(profile[max(0, index - 14) : index - 6])
        after = np.median(profile[index + 6 : min(size, index + 14)])
        sustained = (after - before) * sign
        traces.append((position, index, min(response[index], sustained)))

    samples = np.asarray(traces)
    strong = samples[:, 2] > minimum_step
    if np.mean(strong) < minimum_support:
        return None
    line = np.polyfit(samples[strong, 0], samples[strong, 1], 1)
    errors = np.abs(np.polyval(line, samples[:, 0]) - samples[:, 1])
    valid = strong & (errors < max(3, size * 0.01))
    if np.mean(valid) < minimum_support:
        return None
    line = np.polyfit(samples[valid, 0], samples[valid, 1], 1)
    # Include observed extrema and extrapolated corners; a tilted gel must not
    # be cropped to the narrower rectangle through the middle of its sides.
    # A small real protrusion can be an outlier to the straight-line fit. Keep
    # every strong observation in the enclosure, including those outliers.
    extents = np.concatenate((np.polyval(line, [start, stop]), samples[strong, 1]))
    return _Edge(float(extents.min()), float(extents.max()), float(line[0]))


def _has_competing_outer_edge(
    pixels: np.ndarray, profile: np.ndarray, base: int, start: int, stop: int,
    axis: int, sign: int, near: bool, *, localized: bool = True,
    require_termination: bool = False,
) -> bool:
    """Reject a smaller crop only for a supported alternative outer boundary."""
    size = len(profile)
    gap = max(10, int(size * 0.04))
    low, high = (
        (int(size * 0.02), base - gap)
        if near else (base + gap, int(size * 0.98))
    )
    if high <= low:
        return False
    response = (
        _localized_response(profile, sign) if localized else _edge_response(profile, sign)
    )
    candidates = np.flatnonzero(response[low:high] > _MIN_OUTER_STEP) + low
    if not candidates.size:
        return False
    groups = np.split(candidates, np.flatnonzero(np.diff(candidates) > 1) + 1)
    # Many competing structures are themselves a reason to keep the full frame.
    if len(groups) > 8:
        return True
    for group in groups:
        index = int(group[np.argmax(response[group])])
        if _trace_edge(
            pixels, index, start, stop, axis, sign, outer_range=(low, high),
            localized=localized,
        ) is not None:
            if not require_termination or not _continues_outside_gel(
                pixels, index, start, stop, axis, sign, low, high
            ):
                return True
    return False


def _continues_outside_gel(
    pixels: np.ndarray, index: int, start: int, stop: int, axis: int, sign: int,
    low: int, high: int,
) -> bool:
    """A broad lighting transition can continue beyond the gel's end corners.

    Check several strips beyond either end, clear of the edge-smoothing window.
    A broad alternative confined to the gel's span could be a blurred physical
    extension and must not be discarded. Missing exterior evidence stays unsafe.
    """
    across = pixels.shape[1 - axis]
    radius = max(3, int(pixels.shape[axis] * 0.01))
    low, high = max(low, index - radius), min(high, index + radius + 1)
    for positions in (
        [start - offset for offset in (20, 24, 28)],
        [stop + offset for offset in (20, 24, 28)],
    ):
        support = []
        for center in positions:
            if center < 2 or center >= across - 2:
                continue
            if axis == 0:
                profile = np.median(pixels[:, center - 2 : center + 3], axis=1)
            else:
                profile = np.median(pixels[center - 2 : center + 3, :], axis=0)
            response = _edge_response(profile, sign)
            support.append(np.max(response[low:high]) > _MIN_OUTER_STEP)
        if len(support) == 3 and all(support):
            return True
    return False


def find_gel_crop(image: Image.Image) -> tuple[int, int, int, int]:
    """Find four reliable gel edges plus a 3% margin, or retain the full frame.

    This intentionally favors leaving extra background over an uncertain crop.
    No user settings, image mutations, contrast changes, or coordinate rotation
    occur here. The caller crops the original decoded pixels with these bounds.
    """
    source_width, source_height = image.size
    full_frame = (0, 0, source_width, source_height)
    if min(image.size) < 96:
        return full_frame
    if "A" in image.getbands() and image.getchannel("A").getextrema() != (255, 255):
        return full_frame
    if image.mode == "P" and "transparency" in image.info:
        return full_frame

    # Converting 16-bit values to L would clip them at 255. F preserves values
    # for detection; normalization below never changes source or preview data.
    gray = image.convert("F" if image.mode.startswith("I") else "L")
    gray.thumbnail((_ANALYSIS_LIMIT, _ANALYSIS_LIMIT), Image.Resampling.BILINEAR)
    pixels = np.asarray(gray, dtype=np.float64)
    if min(pixels.shape) < 64:
        return full_frame
    low, high = np.percentile(pixels, [1, 99])
    if not np.isfinite(pixels).all() or high - low < 4:
        return full_frame
    pixels = (pixels - low) / (high - low)
    height, width = pixels.shape

    horizontal = np.median(pixels[int(height * 0.35) : int(height * 0.65), :], axis=0)
    vertical = np.median(pixels[:, int(width * 0.4) : int(width * 0.6)], axis=1)
    left = _initial_edge(horizontal, -1, True)
    right = _initial_edge(horizontal, 1, False)
    top = _initial_edge(vertical, -1, True)
    bottom = _initial_edge(vertical, 1, False)
    if any(edge is None for edge in (left, top, right, bottom)):
        return full_frame
    if right - left < width * 0.2 or bottom - top < height * 0.2:
        return full_frame

    edges = (
        _trace_edge(pixels, left, top, bottom, 1, -1),
        _trace_edge(pixels, top, left, right, 0, -1),
        _trace_edge(pixels, right, top, bottom, 1, 1),
        _trace_edge(pixels, bottom, left, right, 0, 1),
    )
    if any(edge is None for edge in edges):
        return full_frame
    left_edge, top_edge, right_edge, bottom_edge = edges
    # Opposing edges of a rectangle should be approximately parallel.
    if (
        abs(left_edge.slope - right_edge.slope) > 0.05
        or abs(top_edge.slope - bottom_edge.slope) > 0.05
    ):
        return full_frame

    # A weak projection alone can be background shading. Require an alternative
    # to look like an actual edge and persist along the side before rejecting.
    sides = (
        (horizontal, left, top, bottom, 1, -1, True),
        (vertical, top, left, right, 0, -1, True),
        (horizontal, right, top, bottom, 1, 1, False),
        (vertical, bottom, left, right, 0, 1, False),
    )
    for side in sides:
        if _has_competing_outer_edge(pixels, *side):
            return full_frame

    # Blur can soften a physical boundary too. Multiple broad outer sides, or a
    # single broad side that ends at the gel, may belong to a larger enclosure.
    # Keep the frame rather than trusting the sharper inner region in that case.
    broad_sides = 0
    for side in sides:
        if _has_competing_outer_edge(pixels, *side, localized=False):
            broad_sides += 1
            if broad_sides >= 2 or _has_competing_outer_edge(
                pixels, *side, localized=False, require_termination=True
            ):
                return full_frame

    bounds = (left_edge.low, top_edge.low, right_edge.high, bottom_edge.high)
    # A boundary at the frame edge has no supporting exterior; keep everything.
    if min(bounds[0], bounds[1], width - bounds[2], height - bounds[3]) < 8:
        return full_frame
    margin = max(7, _MARGIN_FRACTION * min(bounds[2] - bounds[0], bounds[3] - bounds[1]))
    scale_x, scale_y = source_width / width, source_height / height
    return (
        max(0, math.floor((bounds[0] - margin) * scale_x)),
        max(0, math.floor((bounds[1] - margin) * scale_y)),
        min(source_width, math.ceil((bounds[2] + margin) * scale_x)),
        min(source_height, math.ceil((bounds[3] + margin) * scale_y)),
    )
