"""Independent downstream band positions for uncertain well geometry.

The evidence returned here is a list of candidate lane spans, not a count of
loaded samples. In particular, absent bands say nothing about an empty well.
Analysis uses temporary arrays and never modifies the source image pixels.
"""

import math

import numpy as np

from .wells import _bridge, _runs, _smooth


def well_depth_profile(
    pixels: np.ndarray, points, spans,
) -> tuple[int, int] | None:
    """Estimate both well rims relative to the guide from repeated outlines.

    Each well contributes one horizontal profile after subtracting neighboring
    inter-well background. Median aggregation rejects dirt confined to a few
    wells and can recover a weak second rim even when individual detections
    consistently include only the stronger first rim.
    """
    if len(spans) < 5:
        return None
    height, width = pixels.shape
    spans = sorted((float(top), float(bottom)) for top, bottom in spans if bottom > top)
    if len(spans) < 5:
        return None
    centers = np.array([(top + bottom) / 2 for top, bottom in spans])
    thickness = float(np.median([bottom - top for top, bottom in spans]))
    spacing = float(np.median(np.diff(centers)))
    if thickness < 4 or spacing <= 0:
        return None
    search_limit = max(10, int(math.ceil(max(thickness * 0.9, spacing * 0.60))))
    # Background margins extend past the allowed rim search, so a weak rim
    # or its shallow halo cannot itself raise the estimated noise floor.
    reach = search_limit + max(6, round(thickness * 0.25))
    offsets = np.arange(-reach, reach + 1)
    slope = (points[1][0] - points[0][0]) / (points[1][1] - points[0][1])

    def sample(rows):
        rows = np.asarray(rows, dtype=int)
        rows = rows[(rows >= 0) & (rows < height)]
        if not len(rows):
            return None
        guide = points[0][0] + (rows + 0.5 - points[0][1]) * slope
        columns = np.rint(guide[:, None] + offsets).astype(int)
        valid = (columns >= 0) & (columns < width)
        values = pixels[rows[:, None], np.clip(columns, 0, width - 1)].astype(float)
        values[~valid] = np.nan
        return values

    profiles = []
    gap_half = max(1, round(min(thickness * 0.10, spacing * 0.08)))
    for index, (top, bottom) in enumerate(spans):
        center = centers[index]
        inner_half = max(2, round((bottom - top) * 0.30))
        inner = sample(np.arange(round(center - inner_half), round(center + inner_half)))
        before = (centers[index - 1] + center) / 2 if index else center - spacing / 2
        after = (centers[index + 1] + center) / 2 if index + 1 < len(spans) else center + spacing / 2
        outside = sample(np.r_[np.arange(round(before) - gap_half, round(before) + gap_half + 1),
                               np.arange(round(after) - gap_half, round(after) + gap_half + 1)])
        if inner is None or outside is None:
            continue
        # Discard out-of-image offsets before taking medians, rather than
        # repeating an image-edge pixel into an apparent broad wall.
        valid = np.all(np.isfinite(inner), axis=0) & np.all(np.isfinite(outside), axis=0)
        if np.count_nonzero(valid) < 12:
            continue
        difference = np.median(inner[:, valid], axis=0) - np.median(outside[:, valid], axis=0)
        difference -= _smooth(difference, max(4, round(thickness * 0.25)))
        profile = np.full(len(offsets), np.nan)
        profile[valid] = np.abs(_smooth(difference, 1))
        profiles.append(profile)
    if len(profiles) < 5:
        return None
    profiles = np.asarray(profiles)
    valid = np.count_nonzero(np.isfinite(profiles), axis=0) >= max(5, math.ceil(len(profiles) * 0.75))
    indices = np.flatnonzero(valid)
    if len(indices) < 12:
        return None
    profile = np.nanmedian(profiles[:, valid], axis=0)
    # Noise is measured in the outside margins of this local profile. It is
    # intensity-scale independent, preserving native 16-bit image precision.
    margin = max(3, len(profile) // 6)
    floor = float(np.median(np.r_[profile[:margin], profile[-margin:]]))
    numerical_floor = max(float(np.max(np.abs(pixels))) * 1e-9, 1e-9)
    threshold = max(floor * 4, float(np.max(profile)) * 0.22, numerical_floor)
    supported = np.flatnonzero((profile > threshold) & (np.abs(offsets[indices]) <= search_limit))
    if len(supported) < 4:
        return None
    first, last = int(supported[0]), int(supported[-1])
    left, right = int(offsets[indices[first]]), int(offsets[indices[last]] + 1)
    # A guide should lie inside the aggregate well; a single edge or an
    # unbounded feature at the search margin cannot establish both borders.
    if (left >= 0 or right <= 0 or first < 2 or last >= len(profile) - 2
            or right - left < max(8, thickness * 0.35)
            or right - left > max(thickness * 1.45, spacing * 0.95)):
        return None
    return left, right


def downstream_spans(
    pixels: np.ndarray, points, depth: float, thickness: float,
) -> list[tuple[int, int]]:
    """Find coherent band spans across the downstream image in guide range.

    Bright and dark bands have equal weight. Multiple bands in a ladder lane
    collapse to one span; their intensity and number do not contribute extra
    votes to the lane-spacing model. Tall scratches and isolated pixels are
    rejected before spans from different columns are combined.
    """
    height, width = pixels.shape
    low = max(0, int(math.floor(points[0][1])))
    high = min(height, int(math.ceil(points[1][1])))
    thickness = max(4.0, float(thickness))
    depth = max(4.0, float(depth))
    # Leave the guide's well rims and their immediate shadows out of this
    # independent evidence. The final image columns often contain crop edges.
    start = max(0, int(math.ceil(max(point[0] for point in points) + depth * 2)))
    end = width - max(2, round(width * 0.01))
    if end - start < 15 or high - low < 5:
        return []
    stride = max(1, (end - start) // 1600)
    strip = np.asarray(pixels[low:high, start:end:stride], dtype=float)
    noise = max(0.3, float(np.median(np.abs(np.diff(strip, axis=1))) / 0.954))
    radius = max(5, min(strip.shape[1] // 4, round(depth * 1.5 / stride)))
    padded = np.pad(strip, ((0, 0), (radius, radius)), mode="edge")
    sums = np.pad(np.cumsum(padded, axis=1), ((0, 0), (1, 0)))
    background = (sums[:, 2 * radius + 1:] - sums[:, :-2 * radius - 1]) / (2 * radius + 1)
    residual = strip - background
    padded = np.pad(residual, ((1, 1), (1, 1)), mode="edge")
    coherent = sum(padded[dy:dy + strip.shape[0], dx:dx + strip.shape[1]]
                   for dy in range(3) for dx in range(3)) / 9
    threshold = max(noise * 4.5, float(np.max(np.abs(strip))) * 1e-9, 1e-9)
    signal = np.abs(coherent) > threshold
    adjacent = signal[:, :-2] & signal[:, 1:-1] & signal[:, 2:]
    minimum = max(5, round(thickness * 0.30))
    maximum = max(minimum, round(thickness * 1.65))
    gap = max(1, min(3, round(thickness * 0.025)))
    candidates = []
    for column in np.flatnonzero(np.count_nonzero(adjacent, axis=0) >= minimum):
        for a, b in _runs(_bridge(adjacent[:, column], gap)):
            if not minimum <= b - a <= maximum:
                continue
            # A cut through a continuing feature does not establish its size.
            if (a == 0 and low > 0) or (b == high - low and high < height):
                continue
            candidates.append((a, b, int(column)))
    if not candidates:
        return []

    # Cluster by vertical overlap and a bounded center displacement. Comparing
    # to the current median prevents a chain of slightly shifted specks from
    # joining two distinct lanes. Clustering is independent of band polarity.
    candidates.sort(key=lambda item: (item[0] + item[1], item[2]))
    groups = []
    tolerance = max(3.0, thickness * 0.30)
    for candidate in candidates:
        a, b, _ = candidate
        center = (a + b) / 2
        match = None
        for group in reversed(groups):
            group_center = (group["top"] + group["bottom"]) / 2
            if center - group_center > tolerance:
                break
            overlap = min(b, group["bottom"]) - max(a, group["top"])
            if abs(center - group_center) <= tolerance and overlap >= min(b - a, group["bottom"] - group["top"]) * 0.4:
                match = group
                break
        if match is None:
            groups.append({"members": [candidate], "top": float(a), "bottom": float(b)})
        else:
            match["members"].append(candidate)
            match["top"] = float(np.median([member[0] for member in match["members"]]))
            match["bottom"] = float(np.median([member[1] for member in match["members"]]))

    spans = []
    for group in groups:
        columns = sorted({member[2] for member in group["members"]})
        longest = run = 1
        for previous, current in zip(columns, columns[1:]):
            run = run + 1 if current == previous + 1 else 1
            longest = max(longest, run)
        if longest < 3:
            continue
        top = low + round(group["top"])
        bottom = low + round(group["bottom"])
        if top < bottom:
            spans.append((int(top), int(bottom)))
    return sorted(set(spans))
