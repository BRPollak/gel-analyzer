"""Find supported well outlines and suggest lanes without editing image pixels.

All geometry uses the confirmed image's pixel-boundary coordinates. Well
discovery stays close to the guide; a separate refinement step can use the
downstream image to estimate lane coverage without changing the well outlines.
"""

from dataclasses import dataclass
import heapq
from itertools import combinations
import math
from numbers import Integral

import numpy as np
from PIL import Image

from .workflow_orientation import is_top, orientation_text, swap_bounds, swap_point, swap_size


Point = tuple[float, float]
# Detected boundaries are integral; manually interpolated lanes may lie between
# pixels so equal center spacing survives editing, cropping, and persistence.
Bounds = tuple[float, float, float, float]


class SelectionError(ValueError):
    """A guide cannot delimit wells along the selected workflow's lane axis."""


@dataclass(frozen=True, slots=True)
class Well:
    bounds: Bounds
    center: Point


@dataclass(frozen=True, slots=True)
class DetectionResult:
    wells: tuple[Well, ...]
    lanes: tuple[Bounds, ...]
    warnings: tuple[str, ...] = ()


def validate_line(points, size: tuple[int, int], *, workflow_orientation="wells_left") -> tuple[Point, Point]:
    """Return top/bottom endpoints, accepting either click order.

    Endpoints describe pixel boundaries, including the image's right/bottom
    edge. The vertical span must be at least 8–24 pixels depending on image
    height, and at least as large as the horizontal span.
    Wells-at-top mode applies the same rules horizontally and returns the
    left/right endpoints in displayed XY coordinates.
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
    if is_top(workflow_orientation):
        try:
            ordered = validate_line(coordinates[:, ::-1], swap_size(size))
        except SelectionError as exc:
            raise SelectionError(orientation_text(str(exc), workflow_orientation)) from exc
        return tuple(swap_point(point) for point in ordered)
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


def _detect_wells(
    image: Image.Image, endpoints, *, sensitive: bool = False,
    pixels: np.ndarray | None = None,
) -> tuple[DetectionResult, bool]:
    """Detect contrast-supported wells and horizontal lanes in a selected range.

    Local background subtraction supports bright, dark, and outlined wells.
    Independent contiguous evidence determines vertical heights and spacing.
    Borderline objects are omitted with a warning; a result never establishes
    whether a visible well contains sample. Bounds are clipped and half-open.
    """
    upper, lower = validate_line(endpoints, image.size)
    if pixels is None:
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
    # The recovery pass integrates thin, fragmented walls over more rows.
    # Its output must still respect clear gaps and established well boundaries.
    smoothing = (max(1, min(10, int(round(len(rows) / 130)))) if sensitive
                 else max(1, min(7, int(round(len(rows) / 200)))))
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
    # Thin walls can occupy less than 20% of the discovery strip. A higher
    # quantile recovers their coherent signal without requiring a filled well.
    evidence = np.quantile(np.abs(core), 0.95 if sensitive else 0.8, axis=1)
    # Include the integer-pixel quantization floor; a staircase illumination
    # gradient must not become a high-confidence feature in a noiseless image.
    coherent_noise = noise / math.sqrt((2 * smoothing + 1) * 3)
    floor = min(float(np.percentile(evidence, 10)), noise * 1.2)
    numerical_floor = max(float(np.max(np.abs(stripe))) * 1e-9, 1e-9)
    # An intensity fraction of the strongest well would lose faint neighbors.
    # Use the measured noise and between-feature floor instead.
    threshold = max(coherent_noise * 2.5, floor * (1.1 if sensitive else 1.7), numerical_floor)
    min_height = max(4, int(round(height * 0.006)))
    min_width = 4
    gap_limit = max(smoothing, int(radius * 0.6)) if sensitive else smoothing
    candidate_mask = _bridge(evidence > threshold, gap_limit)
    if sensitive:
        # Bridge shallow interruptions in a faint wall, but retain even a short
        # gap whose contrast drops below the measured between-feature floor.
        for gap_start, gap_end in _runs(evidence <= threshold):
            if float(np.min(evidence[gap_start:gap_end])) < floor * 0.9:
                candidate_mask[gap_start:gap_end] = False
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
    recovery_support = 0
    for start, end in candidates:
        if end - start < min_height or float(np.max(evidence[start:end])) < max(coherent_noise * 3.0, numerical_floor):
            continue
        # A recovery feature must persist beyond the averaging window; a
        # chance noise excursion cannot acquire support simply by smoothing.
        if sensitive and end - start < 2 * smoothing + 1:
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
        # Raw contrast trims crisp caps precisely. For faint outlines on an
        # uneven background it instead follows the illumination and can cut
        # away half a lane, so retain their coherent discovery support.
        if not sensitive or local_peak >= noise * 4:
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
        recovery_support += local_peak >= noise * 2 and well_bottom - well_top >= radius * 2
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
    result = DetectionResult(
        tuple(wells),
        tuple((well.bounds[0], well.bounds[1], width, well.bounds[3]) for well in wells),
        tuple(warnings),
    )
    # Blurred random texture can itself produce weak apparent outlines. Do
    # not relax the noise floor unless at least two sustained features have
    # measurable original contrast; otherwise keep the conservative result.
    return result, weak_boundary and recovery_support >= 2


def _detect_supported_wells(image: Image.Image, endpoints) -> DetectionResult:
    """Find locally supported wells, then recover faint fragmented outlines.

    A conservative pass preserves crisp geometry. When it encounters low
    contrast, a second pass can join weak parts of the same outline. Recovery
    cannot merge multiple established wells or produce overlapping lanes.
    Neither pass uses downstream bands or modifies the source image.
    """
    strict, recover_faint = _detect_wells(image, endpoints)
    if not recover_faint:
        return strict
    recovered, _ = _detect_wells(image, endpoints, sensitive=True)
    if not recovered.wells:
        return strict

    def overlap(first: Well, second: Well) -> int:
        return min(first.bounds[3], second.bounds[3]) - max(first.bounds[1], second.bounds[1])

    # Use the substantial observed outlines only to protect existing geometry,
    # never to extrapolate positions, impose equal spacing, or invent a well.
    heights = sorted(well.bounds[3] - well.bounds[1] for well in strict.wells)
    substantial_height = float(np.median(heights[len(heights) // 2:])) * 0.65
    protected = set()
    for candidate in recovered.wells:
        associated = [
            well for well in strict.wells
            if overlap(candidate, well) > min(
                candidate.bounds[3] - candidate.bounds[1],
                well.bounds[3] - well.bounds[1],
            ) * 0.5
        ]
        substantial = [
            well for well in associated
            if well.bounds[3] - well.bounds[1] >= substantial_height
        ]
        separated_centers = (
            len(associated) > 1
            and associated[-1].center[1] - associated[0].center[1] > substantial_height
        )
        if len(substantial) > 1 or separated_centers:
            protected.update(associated)

    # Resolve all protected intervals first. Otherwise two recovered fragments
    # could select the same old outline or overlap an adjacent protected lane.
    selected = list(protected)
    selected.extend(
        candidate for candidate in recovered.wells
        if not any(overlap(candidate, well) > 0 for well in protected)
    )
    for well in strict.wells:
        if not any(overlap(well, other) > 0 for other in selected):
            selected.append(well)
    selected.sort(key=lambda well: well.center[1])
    warnings = tuple(dict.fromkeys((*strict.warnings, *recovered.warnings)))
    return DetectionResult(
        tuple(selected),
        tuple((well.bounds[0], well.bounds[1], image.width, well.bounds[3]) for well in selected),
        warnings,
    )


def _overlap(first: Well, second: Well) -> int:
    return min(first.bounds[3], second.bounds[3]) - max(first.bounds[1], second.bounds[1])


def _well(bounds: Bounds) -> Well:
    left, top, right, bottom = bounds
    return Well(bounds, ((left + right) / 2, (top + bottom) / 2))


def _nearby_guides(points, size: tuple[int, int], radius: int):
    """Small translations sample either side of the user's intended well line."""
    shift = max(2, min(5, int(round(radius / 4))))
    return tuple(dict.fromkeys(
        tuple((min(size[0], max(0, x + offset)), y) for x, y in points)
        for offset in (-2 * shift, -shift, shift, 2 * shift)
    ))


def _extended_guide(points, size: tuple[int, int], margin: int):
    """Continue the same line, bounded by nearby pixels and the image edges."""
    upper, lower = points
    slope = (lower[0] - upper[0]) / (lower[1] - upper[1])
    top, bottom = max(0, upper[1] - margin), min(size[1], lower[1] + margin)
    if slope:
        y_at_left = upper[1] - upper[0] / slope
        y_at_right = upper[1] + (size[0] - upper[0]) / slope
        top = max(top, min(y_at_left, y_at_right))
        bottom = min(bottom, max(y_at_left, y_at_right))
    return tuple((min(size[0], max(0, upper[0] + (y - upper[1]) * slope)), y) for y in (top, bottom))


def _agreed_wells(first: DetectionResult, second: DetectionResult) -> tuple[Well, ...]:
    """Require comparable independent outlines on both neighboring guides."""
    agreed = []
    used = set()
    for well in first.wells:
        matches = [
            (index, other) for index, other in enumerate(second.wells)
            if index not in used
            and _overlap(well, other) >= 0.65 * max(well.bounds[3] - well.bounds[1], other.bounds[3] - other.bounds[1])
            and min(well.bounds[2], other.bounds[2]) > max(well.bounds[0], other.bounds[0])
        ]
        if not matches:
            continue
        index, other = max(matches, key=lambda item: _overlap(well, item[1]))
        used.add(index)
        agreed.append(_well(tuple(int(round((a + b) / 2)) for a, b in zip(well.bounds, other.bounds))))
    return tuple(agreed)


def _consensus_wells(results) -> tuple[Well, ...]:
    candidates = [well for first, second in combinations(results, 2) for well in _agreed_wells(first, second)]
    # Prefer the fuller repeatedly supported outline. Distinct neighbors still
    # require separate intervals, and an existing well may not be swallowed.
    candidates.sort(key=lambda well: well.bounds[3] - well.bounds[1], reverse=True)
    selected = []
    for candidate in candidates:
        if not any(_overlap(candidate, other) > 0 for other in selected):
            selected.append(candidate)
    return tuple(selected)


def _sustained_support(pixels: np.ndarray, well: Well, radius: int) -> bool:
    """Reject repeated tiny texture peaks before adding a consensus candidate."""
    left, top, right, bottom = well.bounds
    if bottom - top < max(6, radius * 1.5):
        return False
    return _contrast_support(pixels, well)


def _contrast_support(pixels: np.ndarray, well: Well) -> bool:
    """Require original contrast across most rows, not only one bright cap."""
    left, top, right, bottom = well.bounds
    reach = max(4, right - left)
    outside = np.hstack((pixels[top:bottom, max(0, left - reach):left],
                         pixels[top:bottom, right:min(pixels.shape[1], right + reach)]))
    if not outside.size:
        return False
    background = np.median(outside, axis=1)
    noise = max(0.3, float(np.median(np.abs(np.diff(outside, axis=1))) / 0.954)) if outside.shape[1] > 1 else 0.3
    contrast = np.quantile(np.abs(pixels[top:bottom, left:right] - background[:, None]), 0.9, axis=1)
    return float(np.percentile(contrast, 25)) > noise * 2.5


def _supported_extension(pixels: np.ndarray, candidate: Well, original: Well) -> bool:
    left, top, right, bottom = candidate.bounds
    for a, b in ((top, original.bounds[1]), (original.bounds[3], bottom)):
        if b - a >= 3 and not _contrast_support(pixels, _well((left, a, right, b))):
            return False
    return True


def _complete_endpoints(image: Image.Image, points, result: DetectionResult, radius: int) -> DetectionResult:
    """Only recover wells that actually cross an original selection endpoint."""
    extended = _extended_guide(points, image.size, min(80, radius * 3))
    if extended == points:
        return result
    # Most guides already include complete wells. Avoid perturbing their
    # smoothing scale or their deliberately selected first and last lanes.
    if not any("end inside a well" in warning for warning in result.warnings):
        return result
    nearby = _detect_supported_wells(image, extended)
    selected = list(result.wells)
    completed = 0
    for candidate in nearby.wells:
        if not any(candidate.bounds[1] < endpoint[1] < candidate.bounds[3] for endpoint in points):
            continue
        associated = [well for well in selected if _overlap(candidate, well) > 0]
        if len(associated) > 1:
            continue
        if associated and _overlap(candidate, associated[0]) < 0.75 * (associated[0].bounds[3] - associated[0].bounds[1]):
            continue
        selected = [well for well in selected if well not in associated]
        selected.append(candidate)
        completed += 1
    if not completed:
        return result
    warnings = tuple(warning for warning in result.warnings if "end inside a well" not in warning and "No wells" not in warning)
    warnings += ("Completed supported well boundaries just beyond a guide endpoint. Review the first and last lane; wells farther outside the selection remain excluded.",)
    return _result(selected, image.width, warnings)


def _result(wells, width: int, warnings=()) -> DetectionResult:
    wells = tuple(sorted(wells, key=lambda well: well.center[1]))
    return DetectionResult(wells, tuple((well.bounds[0], well.bounds[1], width, well.bounds[3]) for well in wells), tuple(dict.fromkeys(warnings)))


def _join_count_fragments(wells, expected_count: int):
    """Join compatible nearby fragments before enforcing the requested count."""
    selected = sorted(wells, key=lambda well: well.center[1])
    joined = False
    while len(selected) > expected_count:
        heights = sorted(well.bounds[3] - well.bounds[1] for well in selected)
        typical = float(np.median(heights[len(heights) // 2:]))
        proposals = []
        for index, (first, second) in enumerate(zip(selected, selected[1:])):
            a, b = first.bounds, second.bounds
            gap = b[1] - a[3]
            horizontal_overlap = min(a[2], b[2]) - max(a[0], b[0])
            if (a[3] - a[1] < typical * 0.8 and b[3] - b[1] < typical * 0.8
                    and 0 <= gap <= max(3, typical * 0.3)
                    and b[3] - a[1] <= typical * 1.35
                    and horizontal_overlap >= min(a[2] - a[0], b[2] - b[0]) * 0.65):
                proposals.append((gap, index))
        if not proposals:
            break
        _, index = min(proposals)
        a, b = selected[index].bounds, selected[index + 1].bounds
        selected[index:index + 2] = [_well((min(a[0], b[0]), a[1], max(a[2], b[2]), b[3]))]
        joined = True
    return selected, joined


def _well_evidence(pixels: np.ndarray, well: Well) -> float:
    """Rank competing outlines using sustained original-image contrast."""
    left, top, right, bottom = well.bounds
    reach = max(4, right - left)
    outside = np.hstack((pixels[top:bottom, max(0, left - reach):left],
                         pixels[top:bottom, right:min(pixels.shape[1], right + reach)]))
    if not outside.size:
        return 0.0
    noise = max(0.3, float(np.median(np.abs(np.diff(outside, axis=1))) / 0.954)) if outside.shape[1] > 1 else 0.3
    background = np.median(outside, axis=1)
    contrast = np.quantile(np.abs(pixels[top:bottom, left:right] - background[:, None]), 0.9, axis=1)
    return float(np.percentile(contrast, 25)) / noise * math.sqrt(bottom - top)


def _fit_well_count(pixels: np.ndarray, points, wells, count: int, radius: int):
    """Keep supported outlines and allocate exactly the requested number of slots.

    Count-derived positions are proposals, not image detections. Allocate
    missing slots to the largest remaining spacing intervals, including the
    guide endpoints. Integer cells then guarantee positive, disjoint bounds,
    even when a dense requested count requires narrowing existing outlines.
    """
    height, width = pixels.shape
    start = max(0, math.floor(points[0][1]))
    end = min(height, math.ceil(points[1][1]))
    selected = sorted(wells, key=lambda well: well.center[1])
    warnings = []
    if len(selected) > count:
        typical = float(np.median([well.bounds[3] - well.bounds[1] for well in selected]))
        targets = np.linspace(start + typical / 2, end - typical / 2, count) if count > 1 else [(start + end) / 2]
        selected.sort(key=lambda well: (-_well_evidence(pixels, well),
                                        min(abs(well.center[1] - target) for target in targets), well.center[1]))
        omitted = len(selected) - count
        selected = sorted(selected[:count], key=lambda well: well.center[1])
        warnings.append(f"Kept {count} wells to match the requested count and omitted {omitted} detected candidate(s), prioritizing stronger image evidence. Review the retained wells and lane boundaries.")
    if len(selected) == count:
        return selected, warnings

    # Preserve the existing small endpoint-completion allowance. Inferred
    # positions otherwise stay within the selected guide range.
    if selected:
        start = min(start, selected[0].bounds[1])
        end = max(end, selected[-1].bounds[3])
    typical = float(np.median([well.bounds[3] - well.bounds[1] for well in selected])) if selected else max(1.0, (end - start) / count * 0.6)
    depth = float(np.median([well.bounds[2] - well.bounds[0] for well in selected])) if selected else radius * 2
    entries = []
    if not selected:
        entries = [(start + (index + 0.5) * (end - start) / count, None) for index in range(count)]
    else:
        centers = [well.center[1] for well in selected]
        anchors = [math.floor(center) for center in centers]
        nominal = max(1.0, (end - start - typical) / max(1, count - 1))
        distances = np.diff(centers)
        spacing = float(np.median([distance / max(1, round(distance / nominal)) for distance in distances])) if len(distances) else nominal
        # One heap entry per gap. Interior gaps are bounded by two observed
        # centers; endpoint gaps are bounded by one center and half a well.
        gaps = [(start, selected[0].bounds[1]),
                *((first.bounds[3], second.bounds[1]) for first, second in zip(selected, selected[1:])),
                (selected[-1].bounds[3], end)]
        # Unequal well sizes can put a center midpoint inside a wide outline.
        # Use its actual free border gaps first, preserving every supported
        # rectangle whenever enough unoccupied pixels exist for the count.
        if sum(high - low for low, high in gaps) < count - len(selected):
            gaps = [(start, anchors[0]), *((a + 1, b) for a, b in zip(anchors, anchors[1:])),
                    (anchors[-1] + 1, end)]
        capacities = [high - low for low, high in gaps]
        spans = [max(0.0, centers[0] - start - typical / 2), *distances,
                 max(0.0, end - centers[-1] - typical / 2)]
        allocations = [0] * len(capacities)
        heap = []
        for index, capacity in enumerate(capacities):
            if capacity:
                divisor = 0.5 if index in (0, len(capacities) - 1) else 1.0
                heapq.heappush(heap, (-spans[index] / divisor, index, divisor))
        for _ in range(count - len(selected)):
            _, index, divisor = heapq.heappop(heap)
            allocations[index] += 1
            if allocations[index] < capacities[index]:
                heapq.heappush(heap, (-spans[index] / (allocations[index] + divisor), index, divisor))
        for index, amount in enumerate(allocations):
            if amount:
                if index == 0:
                    extent = max(amount, min(amount * spacing, spans[index]))
                    proposed = [centers[0] - extent * step / amount for step in range(amount, 0, -1)]
                elif index == len(selected):
                    extent = max(amount, min(amount * spacing, spans[index]))
                    proposed = [centers[-1] + extent * step / amount for step in range(1, amount + 1)]
                else:
                    proposed = [centers[index - 1] + (centers[index] - centers[index - 1]) * step / (amount + 1)
                                for step in range(1, amount + 1)]
                low, end_gap = gaps[index]
                high = end_gap - 1
                # Reserve one integer pixel for every remaining proposal.
                for number, center in enumerate(proposed):
                    anchor = max(low, min(high - (amount - number - 1), math.floor(center)))
                    entries.append((center if math.floor(center) == anchor else anchor + 0.5, None))
                    low = anchor + 1
            if index < len(selected):
                entries.append((centers[index], selected[index]))

    anchors = [math.floor(center) for center, _ in entries]
    boundaries = [start]
    for index, (a, b) in enumerate(zip(anchors, anchors[1:])):
        first, second = entries[index][1], entries[index + 1][1]
        low = first.bounds[3] if first is not None else a + 1
        high = second.bounds[1] if second is not None else b
        midpoint = (a + b + 1) // 2
        boundaries.append(max(low, min(high, midpoint)) if low <= high
                          else max(a + 1, min(b, midpoint)))
    boundaries.append(end)
    result = []
    inferred = []
    narrowed = False
    slope = (points[1][0] - points[0][0]) / (points[1][1] - points[0][1])
    for index, (center, well) in enumerate(entries):
        low, high = boundaries[index:index + 2]
        if well is not None:
            left, top, right, bottom = well.bounds
            bounds = (left, max(low, top), right, min(high, bottom))
            narrowed |= bounds != well.bounds
        else:
            thickness = max(1, min(high - low, round(typical)))
            top = max(low, min(high - thickness, round(center - thickness / 2)))
            x = points[0][0] + (center - points[0][1]) * slope
            well_depth = max(1, min(width, round(depth)))
            left = max(0, min(width - well_depth, round(x - well_depth / 2)))
            bounds = (left, top, left + well_depth, top + thickness)
            inferred.append(index + 1)
        result.append(_well(bounds))
    numbers = ", ".join(map(str, inferred[:12])) + (", …" if len(inferred) > 12 else "")
    warnings.append(f"To match the requested {count} wells, {len(inferred)} position(s) were inferred from guide spacing (wells {numbers}). These positions are not confirmed by image evidence. Review every inferred well and its lane boundaries.")
    if narrowed:
        warnings.append("Some detected well boundaries were narrowed to fit the requested count without overlap. Review all well and lane boundaries.")
    return result, warnings


def detect_wells(image: Image.Image, endpoints, *, expected_count: int | None = None,
                 workflow_orientation="wells_left") -> DetectionResult:
    """Locate wells, tolerate small guide errors, and independently fit lanes.

    An entered count is an exact constraint. Supported outlines and faint
    recovery take priority; missing positions are inferred from the guide and
    spacing with an explicit review warning. Without a count, only supported
    outlines are returned. Source image pixels are never altered.
    """
    if expected_count is not None and (isinstance(expected_count, bool) or not isinstance(expected_count, Integral) or expected_count <= 0):
        raise SelectionError("The number of wells must be a positive integer.")
    if is_top(workflow_orientation):
        points = validate_line(endpoints, image.size, workflow_orientation=workflow_orientation)
        # Only the computational view swaps axes. The displayed/source image
        # is untouched, and every detected rectangle is returned in display XY.
        result = detect_wells(image.transpose(Image.Transpose.TRANSPOSE),
                              tuple(swap_point(point) for point in points), expected_count=expected_count)
        return DetectionResult(
            tuple(Well(swap_bounds(well.bounds), swap_point(well.center)) for well in result.wells),
            tuple(swap_bounds(lane) for lane in result.lanes),
            tuple(orientation_text(warning, workflow_orientation) for warning in result.warnings),
        )
    points = validate_line(endpoints, image.size)
    if expected_count is not None:
        expected_count = int(expected_count)
        available = min(image.height, math.ceil(points[1][1])) - max(0, math.floor(points[0][1]))
        if expected_count > available:
            raise SelectionError(f"The requested {expected_count} wells cannot fit in this {available}-pixel guide span: each well needs at least one pixel across the lanes. Extend the guide or reduce the number of wells.")
    radius = max(7, min(40, int(round(min(image.size) * 0.016))))
    original = _detect_supported_wells(image, points)
    result = _complete_endpoints(image, points, original, radius)
    guides = _nearby_guides(points, image.size, radius)
    neighbors = tuple(_detect_supported_wells(image, guide) for guide in guides)
    pixels = _analysis_pixels(image)
    selected = list(result.wells)
    warnings = list(result.warnings)
    additions = []
    uncertain = any("Low contrast" in warning or "uncertain" in warning for warning in warnings)
    repaired = False
    for candidate in _consensus_wells(neighbors):
        associated = [well for well in selected if _overlap(candidate, well) > 0]
        supported = _sustained_support(pixels, candidate, radius)
        if not associated and supported:
            selected.append(candidate)
            additions.append(candidate)
        elif uncertain and len(associated) == 1 and supported:
            original_well = associated[0]
            old_height = original_well.bounds[3] - original_well.bounds[1]
            new_height = candidate.bounds[3] - candidate.bounds[1]
            if (new_height >= max(old_height * 1.35, old_height + 6)
                    and _overlap(candidate, original_well) >= old_height * 0.9
                    and _supported_extension(pixels, candidate, original_well)):
                selected[selected.index(original_well)] = candidate
                repaired = True
    if additions:
        warnings = [warning for warning in warnings if "No wells" not in warning]
        warnings.append("Nearby guide positions recovered additional supported wells. Review their lane boundaries.")
    if repaired:
        warnings.append("Nearby guide positions recovered fuller well outlines. Review the adjusted lane boundaries.")
    if expected_count is not None:
        selected, joined = _join_count_fragments(selected, int(expected_count))
        if joined:
            warnings.append("The expected lane count helped join short well fragments. Review the inferred boundaries of the joined lanes.")
        if len(selected) < expected_count and len(selected) >= 2:
            # An entered count permits a faint search, but candidates still need
            # coherent contrast on both nearby guides and in the original data.
            faint = tuple(_detect_wells(image, guide, sensitive=True, pixels=pixels)[0] for guide in guides)
            candidates = [candidate for candidate in _consensus_wells(faint)
                          if not any(_overlap(candidate, well) > 0 for well in selected)
                          and _sustained_support(pixels, candidate, radius)]
            if candidates:
                centers = sorted(well.center[1] for well in selected)
                spacing = float(np.median(np.diff(centers)))
                # Rank observed candidates by a soft spacing preference only;
                # their actual centers and independent heights are retained.
                candidates.sort(key=lambda candidate: abs(min(abs(candidate.center[1] - center) for center in centers) - spacing))
                accepted = 0
                for candidate in candidates:
                    if len(selected) >= expected_count:
                        break
                    if not any(_overlap(candidate, well) > 0 for well in selected):
                        selected.append(candidate)
                        accepted += 1
                if accepted:
                    warnings.append("The expected lane count helped recover faint well outlines. Review the inferred lane boundaries.")
        selected, count_warnings = _fit_well_count(pixels, points, selected, expected_count, radius)
        if count_warnings:
            warnings = [warning for warning in warnings if "No wells" not in warning]
            warnings.extend(count_warnings)
    result = _result(selected, image.width, warnings)
    from .lane_refinement import refine_lanes

    return refine_lanes(image, result, pixels=pixels)
