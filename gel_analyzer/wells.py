"""Find visible well outlines near a user-confirmed guide, without editing pixels.

All geometry uses the confirmed image's pixel-boundary coordinates. Detection
only examines a narrow strip following the guide and a small adjacent margin;
it never searches the downstream lane for evidence or infers missing wells.
"""

from dataclasses import dataclass
import math

import numpy as np
from PIL import Image


Point = tuple[float, float]
Bounds = tuple[int, int, int, int]


class SelectionError(ValueError):
    """A guide cannot delimit a generally vertical selection of wells."""


@dataclass(frozen=True, slots=True)
class Well:
    bounds: Bounds
    center: Point


@dataclass(frozen=True, slots=True)
class DetectionResult:
    wells: tuple[Well, ...]
    lanes: tuple[Bounds, ...]
    warnings: tuple[str, ...] = ()


def validate_line(points, size: tuple[int, int]) -> tuple[Point, Point]:
    """Return top/bottom endpoints, accepting either click order.

    Endpoints describe pixel boundaries, including the image's right/bottom
    edge. The vertical span must be at least 8–24 pixels depending on image
    height, and at least as large as the horizontal span.
    """
    try:
        coordinates = np.asarray(points, dtype=float)
    except (TypeError, ValueError, OverflowError) as exc:
        raise SelectionError("Place two points on the gel to define the well line.") from exc
    if coordinates.shape != (2, 2):
        raise SelectionError("Place two points on the gel to define the well line.")
    if not np.isfinite(coordinates).all():
        raise SelectionError("Both endpoints must have finite image coordinates.")
    if min(size) <= 0 or (coordinates < 0).any() or (coordinates > size).any():
        raise SelectionError("Keep both endpoints inside the confirmed gel image.")
    coordinates = coordinates[np.argsort(coordinates[:, 1], kind="stable")]
    delta_x, delta_y = coordinates[1] - coordinates[0]
    if delta_x == delta_y == 0:
        raise SelectionError("The points coincide. Move them to the top and bottom of the selected wells.")
    if abs(delta_x) > delta_y:
        raise SelectionError("Make the line generally vertical, through the well centers, with one point above the other.")
    if delta_y < max(8, min(24, size[1] * 0.02)):
        raise SelectionError("The line is too short. Place the points at the outside top and bottom edges of the selected wells.")
    return tuple(tuple(float(value) for value in point) for point in coordinates)


def _smooth(values: np.ndarray, radius: int) -> np.ndarray:
    if radius <= 0:
        return values.copy()
    padded = np.pad(values, (radius, radius), mode="edge")
    sums = np.concatenate(([0.0], np.cumsum(padded, dtype=float)))
    return (sums[2 * radius + 1:] - sums[:-2 * radius - 1]) / (2 * radius + 1)


def _runs(mask: np.ndarray) -> list[tuple[int, int]]:
    transitions = np.diff(np.r_[False, mask, False].astype(np.int8))
    return [(int(start), int(end)) for start, end in zip(np.flatnonzero(transitions == 1), np.flatnonzero(transitions == -1))]


def _bridge(mask: np.ndarray, gap: int) -> np.ndarray:
    result = mask.copy()
    for start, end in _runs(~mask):
        if start > 0 and end < len(mask) and end - start <= gap:
            result[start:end] = True
    return result


def _analysis_pixels(image: Image.Image) -> np.ndarray:
    if image.mode not in {"1", "L", "LA", "P", "RGB", "RGBA", "I;16", "I;16L", "I;16B", "I"}:
        raise SelectionError("This image's pixel format is not supported for well detection.")
    if ("A" in image.getbands() and image.getchannel("A").getextrema() != (255, 255)) or (
        image.mode == "P" and "transparency" in image.info
    ):
        raise SelectionError("Well detection requires a gel image without transparent areas.")
    # Float conversion retains every uint16 intensity; it does not overwrite or
    # normalize the image, its encoded preview, or the uploaded TIFF bytes.
    gray = image.convert("F" if image.mode.startswith("I") else "L")
    return np.asarray(gray, dtype=np.float64)


def detect_wells(image: Image.Image, endpoints) -> DetectionResult:
    """Detect contrast-supported wells and horizontal lanes in a selected range.

    Local background subtraction supports bright, dark, and outlined wells.
    Independent contiguous evidence determines vertical heights and spacing.
    Borderline objects are omitted with a warning; a result never establishes
    whether a visible well contains sample. Bounds are clipped and half-open.
    """
    upper, lower = validate_line(endpoints, image.size)
    pixels = _analysis_pixels(image)
    height, width = pixels.shape
    top = max(0, int(math.floor(upper[1])))
    bottom = min(height, int(math.ceil(lower[1])))
    rows = np.arange(top, bottom)
    centers = upper[0] + (rows + 0.5 - upper[1]) * (lower[0] - upper[0]) / (lower[1] - upper[1])
    # About 3% of the short image side is the discovery strip. Its adjacent
    # margins provide background and bound the largest possible refinement.
    radius = max(7, min(40, int(round(min(width, height) * 0.016))))
    margin = radius * 3
    offsets = np.arange(-margin, margin + 1)
    columns = np.clip(np.rint(centers[:, None] + offsets).astype(int), 0, width - 1)
    stripe = pixels[rows[:, None], columns]
    noise = max(0.3, float(np.median(np.abs(np.diff(stripe, axis=1))) / 0.954))
    left_bg = np.median(stripe[:, :radius], axis=1)
    right_bg = np.median(stripe[:, -radius:], axis=1)
    # A nearby migrating band may occupy the right background margin. A
    # large one-sided contrast jump must not project a false boundary to the
    # *left* of the well. Prefer the upstream background in that situation.
    contaminated_right = (np.abs(right_bg - left_bg) > noise * 5) & (centers - margin >= 0)
    right_bg = np.where(contaminated_right, left_bg, right_bg)
    # At an image edge use the available outside background on both sides.
    left_bg = np.where(centers - margin < 0, right_bg, left_bg)
    right_bg = np.where(centers + margin >= width, left_bg, right_bg)
    blend = (offsets + margin - radius / 2) / (2 * margin - radius)
    baseline = left_bg[:, None] + (right_bg - left_bg)[:, None] * blend
    residual = stripe - baseline
    smoothing = max(1, min(7, int(round(len(rows) / 200))))
    # A short median filter rejects isolated hot pixels before averaging; a
    # bright speck otherwise spreads into several apparently supported rows.
    padded_median = np.pad(residual, ((1, 1), (0, 0)), mode="edge")
    filtered = np.median(np.stack((padded_median[:-2], padded_median[1:-1], padded_median[2:])), axis=0)
    padded = np.pad(filtered, ((smoothing, smoothing), (0, 0)), mode="edge")
    sums = np.vstack((np.zeros((1, padded.shape[1])), np.cumsum(padded, axis=0)))
    coherent = (sums[2 * smoothing + 1:] - sums[:-2 * smoothing - 1]) / (2 * smoothing + 1)
    # Remove broad illumination changes locally as well. Narrow well walls
    # remain even when their mean intensity matches the adjacent gel.
    padded_x = np.pad(coherent, ((0, 0), (radius, radius)), mode="edge")
    sums_x = np.hstack((np.zeros((len(rows), 1)), np.cumsum(padded_x, axis=1)))
    broad = (sums_x[:, 2 * radius + 1:] - sums_x[:, :-2 * radius - 1]) / (2 * radius + 1)
    coherent -= broad
    core = coherent[:, margin - radius:margin + radius + 1]
    # Spatial averaging keeps isolated hot pixels from creating well evidence.
    core = (core[:, :-2] + core[:, 1:-1] + core[:, 2:]) / 3
    evidence = np.quantile(np.abs(core), 0.8, axis=1)
    # Include the integer-pixel quantization floor; a staircase illumination
    # gradient must not become a high-confidence feature in a noiseless image.
    coherent_noise = noise / math.sqrt((2 * smoothing + 1) * 3)
    floor = min(float(np.percentile(evidence, 10)), noise * 1.2)
    numerical_floor = max(float(np.max(np.abs(stripe))) * 1e-9, 1e-9)
    # An intensity fraction of the strongest well would lose faint neighbors.
    # Use the measured noise and between-feature floor instead.
    threshold = max(coherent_noise * 2.5, floor * 1.7, numerical_floor)
    min_height = max(4, int(round(height * 0.006)))
    min_width = 4
    candidate_mask = _bridge(evidence > threshold, smoothing)
    raw_core = np.quantile(np.abs(filtered[:, margin-radius:margin+radius+1]), 0.8, axis=1)
    # Smoothing must not close a clear physical gap between two adjacent wells.
    for gap_start, gap_end in _runs(raw_core < max(noise * 0.5, numerical_floor)):
        if gap_end - gap_start >= 2:
            candidate_mask[gap_start:gap_end] = False
    candidates = _runs(candidate_mask)
    wells = []
    uncertain = False
    clipped = False
    cut_endpoint = False
    weak_boundary = False
    for start, end in candidates:
        if end - start < min_height or float(np.max(evidence[start:end])) < max(coherent_noise * 3.0, numerical_floor):
            continue
        # Taking the median of central rows rejects dirt confined to one row,
        # while retaining the outer rims of outlined (rather than filled) wells.
        inset = (end - start) // 5
        cross_section = np.median(residual[start + inset:end - inset], axis=0)
        cross_section = np.abs(_smooth(cross_section, 1))
        local_peak = float(np.max(cross_section[margin-radius:margin+radius+1]))
        weak_boundary |= local_peak < noise * 4
        horizontal_threshold = max(local_peak * 0.35, noise * 2 / math.sqrt(max(1, end - start)), numerical_floor)
        horizontal_mask = _bridge(cross_section > horizontal_threshold, max(2, radius // 2))
        all_parts = _runs(horizontal_mask)
        parts = [(a, b) for a, b in all_parts if b > margin - radius and a <= margin + radius]
        # An outlined well may have a background-colored center. Include a
        # nearby wall on either side of the guide rather than requiring the
        # wall itself to cross the central discovery strip.
        if not parts:
            before = [(a, b) for a, b in all_parts if margin - 2 * radius <= b <= margin]
            after = [(a, b) for a, b in all_parts if margin <= a <= margin + 2 * radius]
            if before and after:
                parts = [before[-1], after[0]]
        if not parts:
            uncertain = True
            continue
        first, last = min(a for a, _ in parts), max(b for _, b in parts)
        # Any boundary reaching the search margin is unsupported unless that
        # margin is the physical image boundary. Do not extend towards bands.
        x_center = float(np.median(centers[start:end]))
        left = max(0, int(round(x_center + offsets[first])))
        right = min(width, int(round(x_center + offsets[last - 1]))) + 1
        right = min(width, right)
        if (first == 0 and x_center - margin > 0) or (last == len(offsets) and x_center + margin < width - 1):
            uncertain = True
            continue
        if right - left < min_width or end - start < (right - left) * 0.35:
            uncertain = True
            continue
        weak_boundary |= right - left < radius * 0.75 and end - start > radius * 2
        # Refine vertical edges using the candidate's own contrast. This keeps
        # faint wells independent of a neighboring well's much stronger signal.
        local_height_peak = float(np.percentile(evidence[start:end], 75))
        vertical_threshold = max(threshold * 0.9, floor + (local_height_peak - floor) * 0.30, numerical_floor)
        a, b = start, end
        while a > 0 and evidence[a - 1] > vertical_threshold:
            a -= 1
        while b < len(rows) and evidence[b] > vertical_threshold:
            b += 1
        # Refine caps from nearby original contrast, including walls on both
        # sides. A filled cap can have *less* high-pass response than hollow
        # interior walls, so the discovery response alone would trim it away.
        vertical = _smooth(np.quantile(np.abs(filtered[:, first:last]), 0.7, axis=1), 1)
        raw_peak = float(np.percentile(vertical[start:end], 75))
        cut = max(noise * 1.5, raw_peak * 0.5, numerical_floor)
        lo, hi = max(0, start - radius), min(len(rows), end + radius)
        while a > lo and vertical[a - 1] > cut:
            a -= 1
        while b < hi and vertical[b] > cut:
            b += 1
        while a < b and vertical[a] < cut:
            a += 1
        while b > a and vertical[b - 1] < cut:
            b -= 1
        if b - a < min_height:
            uncertain = True
            continue
        # Endpoints restrict the requested range, but are not evidence of a
        # physical well edge. Examine only adjacent rows to identify a cut
        # through an existing well; do not invent a truncated boundary there.
        endpoint_continues = False
        for touches, outside_y in ((a == 0, top - 1), (b == len(rows), bottom)):
            if not touches or not 0 <= outside_y < height:
                continue
            edge_row = pixels[outside_y, columns[0 if outside_y < top else -1]]
            local = edge_row - _smooth(edge_row, radius)
            local = _smooth(local, 1)[margin-radius:margin+radius+1]
            outside_evidence = float(np.quantile(np.abs(local), 0.8))
            endpoint_continues |= outside_evidence > max(noise * 1.5, local_height_peak * 0.65, numerical_floor)
        if endpoint_continues:
            cut_endpoint = True
            continue
        well_top, well_bottom = top + a, top + b
        if wells and well_top < wells[-1].bounds[3]:
            uncertain = True
            continue
        bounds = (left, well_top, right, well_bottom)
        wells.append(Well(bounds, ((left + right) / 2, (well_top + well_bottom) / 2)))
        clipped |= left == 0 or right == width or well_top == 0 or well_bottom == height

    warnings = []
    if not wells:
        warnings.append("No wells could be identified reliably near this line. Move the guide through the well centers and place its ends at the outer well edges, then try again.")
    if uncertain:
        warnings.append("Some nearby features had uncertain boundaries and were omitted. Review the outlines and edit the well line; the detected set may be incomplete.")
    if cut_endpoint:
        warnings.append("The guide appears to end inside a well. That well was omitted because its outer boundary is outside the selection. Move the endpoint to its outside edge and try again.")
    if weak_boundary and wells:
        warnings.append("Low contrast makes some well boundaries uncertain. Review every outline and edit the guide if needed; faint or fragmented wells may be missed or split.")
    if clipped:
        warnings.append("A detected well touches an image edge; its bounds are clipped to the available pixels.")
    return DetectionResult(tuple(wells), tuple((well.bounds[0], well.bounds[1], width, well.bounds[3]) for well in wells), tuple(warnings))
