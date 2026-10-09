"""Estimate lane coverage independently of the visible well outlines.

Wells remain the anchors: downstream contrast can enlarge their lanes, but
cannot add/delete a well or erase a lane with no visible bands. All analysis
uses temporary floating point arrays; source pixels are never modified.
"""

import math

import numpy as np
from PIL import Image

from .wells import DetectionResult, Well, _analysis_pixels, _bridge, _runs


def _typical_height(wells: tuple[Well, ...]) -> float | None:
    """Require several mutually consistent wells before borrowing their height."""
    if len(wells) < 3:
        return None
    heights = np.array([well.bounds[3] - well.bounds[1] for well in wells])
    # A lower median can be dominated by partial outlines. Look for the
    # largest consistent group, breaking ties in favor of substantial wells.
    groups = [heights[np.abs(heights - height) <= height * 0.20] for height in heights]
    group = max(groups, key=lambda values: (len(values), float(np.median(values))))
    if len(group) < max(2, math.ceil(len(wells) * 0.6)):
        return None
    return float(np.median(group))


def _crisp_caps(pixels: np.ndarray, well: Well) -> bool:
    """Keep genuinely short, sharply bounded wells out of thickness repair."""
    left, top, right, bottom = well.bounds
    height, width = pixels.shape
    if top < 3 or bottom > height - 3:
        return True
    padding = max(3, (right - left) // 2)
    lo, hi = max(0, left - padding), min(width, right + padding)
    strip = pixels[top - 3:bottom + 3, lo:hi]
    noise = max(0.3, float(np.median(np.abs(np.diff(strip, axis=1))) / 0.954))
    # Compare the cap with immediately adjacent rows at the same x positions;
    # this cancels horizontal background gradients without rescaling pixels.
    inner_top = np.median(pixels[top:min(top + 3, bottom), left:right], axis=0)
    outer_top = np.median(pixels[top - 3:top, left:right], axis=0)
    inner_bottom = np.median(pixels[max(top, bottom - 3):bottom, left:right], axis=0)
    outer_bottom = np.median(pixels[bottom:bottom + 3, left:right], axis=0)
    return all(float(np.quantile(np.abs(delta), 0.7)) >= noise * 5
               for delta in (inner_top - outer_top, inner_bottom - outer_bottom))


def _band_span(
    pixels: np.ndarray, well: Well, low: int, high: int, typical: float,
) -> tuple[int, int] | None:
    """Find sustained downstream contrast overlapping this well's lane.

    Horizontal background subtraction handles bright and dark bands. A row
    must contain multiple adjacent signal pixels, and a run must persist over
    several rows. Features continuing through the whole search window (e.g.
    vertical scratches) do not establish lane borders.
    """
    left, top, right, bottom = well.bounds
    height, width = pixels.shape
    start_x = right + max(4, round(min(height, width) * 0.012))
    end_x = width - max(2, round(width * 0.01))
    if end_x - start_x < 12 or high - low < 5:
        return None
    # Bounded horizontal sampling keeps large TIFFs responsive while retaining
    # vertical pixel precision. The input image itself is never resampled.
    stride = max(1, (end_x - start_x) // 1600)
    strip = pixels[low:high, start_x:end_x:stride]
    noise = max(0.3, float(np.median(np.abs(np.diff(strip, axis=1))) / 0.954))
    radius = max(5, min(strip.shape[1] // 4, round((right - left) * 1.5 / stride)))
    padded = np.pad(strip, ((0, 0), (radius, radius)), mode="edge")
    sums = np.pad(np.cumsum(padded, axis=1), ((0, 0), (1, 0)))
    background = (sums[:, 2 * radius + 1:] - sums[:, :-2 * radius - 1]) / (2 * radius + 1)
    residual = strip - background
    # Smooth before testing contrast so single hot pixels cannot acquire the
    # same influence as a band extending through a substantial part of a lane.
    padded = np.pad(residual, ((1, 1), (1, 1)), mode="edge")
    coherent = sum(padded[dy:dy + strip.shape[0], dx:dx + strip.shape[1]]
                   for dy in range(3) for dx in range(3)) / 9
    threshold = max(noise * 3.5, float(np.max(np.abs(strip))) * 1e-9, 1e-9)
    signal = np.abs(coherent) > threshold
    adjacent = signal[:, :-2] & signal[:, 1:-1] & signal[:, 2:]
    minimum = max(5, round(min(bottom - top, typical) * 0.25))
    gap = max(1, min(3, round(typical * 0.025)))
    supported_rows = np.zeros(high - low, dtype=bool)
    # Test vertical support separately at each x position. A tall scratch in
    # one column must not join otherwise separate bands into an all-row run.
    for column in np.flatnonzero(np.count_nonzero(adjacent, axis=0) >= minimum):
        for a, b in _runs(_bridge(adjacent[:, column], gap)):
            if b - a < minimum or b - a > typical * 1.8:
                continue
            if (a == 0 and low > 0) or (b == high - low and high < height):
                continue
            overlap = min(low + b, bottom) - max(low + a, top)
            if overlap >= max(3, min(bottom - top, b - a) * 0.25):
                supported_rows[a:b] = True
    active = _bridge(supported_rows, gap)
    candidates = []
    for a, b in _runs(active):
        a, b = low + a, low + b
        if b - a < minimum or b - a > typical * 1.8:
            continue
        if (a <= low and low > 0) or (b >= high and high < height):
            continue
        overlap = min(b, bottom) - max(a, top)
        if overlap < max(3, min(bottom - top, b - a) * 0.25):
            continue
        candidates.append((a, b))
    if not candidates:
        return None
    return min(a for a, _ in candidates), max(b for _, b in candidates)


def refine_lanes(
    image: Image.Image, result: DetectionResult, *, pixels: np.ndarray | None = None,
) -> DetectionResult:
    """Retain well geometry and expand only supported, nonoverlapping lanes."""
    wells = result.wells
    if not wells:
        return result
    if pixels is None:
        pixels = _analysis_pixels(image)
    height, width = pixels.shape
    typical = _typical_height(wells)
    # Separators stay in the actual gaps between wells, even for unequal well
    # heights. Neither the typical-height prior nor bands can cross a neighbor.
    separators = [0]
    for first, second in zip(wells, wells[1:]):
        midpoint = round((first.center[1] + second.center[1]) / 2)
        separators.append(max(first.bounds[3], min(second.bounds[1], midpoint)))
    separators.append(height)
    lanes = []
    repaired = False
    uncertain = any("Low contrast" in warning for warning in result.warnings)
    for index, well in enumerate(wells):
        left, top, right, bottom = well.bounds
        reference = typical or float(bottom - top)
        allowance = max(4, round(reference * 0.65))
        low = max(separators[index], top - allowance)
        high = min(separators[index + 1], bottom + allowance)
        span = _band_span(pixels, well, low, high, reference)
        lane_top, lane_bottom = top, bottom
        if span is not None:
            lane_top, lane_bottom = min(top, span[0]), max(bottom, span[1])
        if (typical is not None and uncertain and bottom - top < typical * 0.65
                and not _crisp_caps(pixels, well)):
            center = (span[0] + span[1]) / 2 if span is not None else well.center[1]
            lane_top = min(lane_top, max(low, math.floor(center - typical / 2)))
            lane_bottom = max(lane_bottom, min(high, math.ceil(center + typical / 2)))
            repaired = True
        lanes.append((left, int(lane_top), width, int(lane_bottom)))
    warnings = result.warnings
    if repaired:
        warnings = (*warnings, "Unusually thin lane borders were expanded using nearby lane thickness; review their coverage.")
    return DetectionResult(wells, tuple(lanes), warnings)
