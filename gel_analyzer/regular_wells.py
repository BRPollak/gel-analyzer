"""Recover weak outlines at the requested number of positions along a guide.

The count fixes the spacing model; image evidence refines its phase and pitch.
Recovered outlines still need local contrast. Slots without it are left to the
exact-count fitter, which explicitly labels them as inferred positions.
"""

import math

import numpy as np

from .wells import _bridge, _contrast_support, _runs, _smooth, _well


def _guide_x(points, rows):
    return points[0][0] + (rows - points[0][1]) * (points[1][0] - points[0][0]) / (points[1][1] - points[0][1])


def _count_model(wells, start, end, count):
    """Fit one known-count grid; never search over possible lane counts."""
    nominal = (end - start) / count
    anchors = [well for well in wells if nominal * 0.3 <= well.bounds[3] - well.bounds[1] <= nominal * 0.9]
    if len(anchors) < 2:
        return None
    thickness = float(np.median([well.bounds[3] - well.bounds[1] for well in anchors]))
    anchors = [well for well in anchors if thickness * 0.72 <= well.bounds[3] - well.bounds[1] <= thickness * 1.3]
    if len(anchors) < 2:
        return None
    pitch = (end - start - thickness) / (count - 1)
    phase = start + thickness / 2
    centers = np.array([well.center[1] for well in anchors])
    slots = np.rint((centers - phase) / pitch).astype(int)
    inliers = (slots >= 0) & (slots < count) & (np.abs(centers - phase - slots * pitch) < pitch * 0.3)
    if np.count_nonzero(inliers) >= 2 and len(np.unique(slots[inliers])) >= 2:
        fitted_phase, fitted_pitch = np.linalg.lstsq(
            np.column_stack((np.ones(np.count_nonzero(inliers)), slots[inliers])), centers[inliers], rcond=None,
        )[0]
        # The guide delimits exactly N wells. Evidence may refine that grid,
        # but cannot shift the first/last slot onto an additional neighbor.
        if abs(fitted_phase - phase) < pitch * 0.3 and abs(fitted_phase + (count - 1) * fitted_pitch - (phase + (count - 1) * pitch)) < pitch * 0.3:
            phase, pitch = float(fitted_phase), float(fitted_pitch)
    return thickness, anchors, phase, pitch


def _rim_profile(pixels, points, offset, depth, thickness):
    """Measure coherent wall contrast on both sides of the guide.

    Subtract the slowly varying background in the migration direction, then
    use a per-cell floor below. This retains faint rims under uneven lighting
    without a threshold set by the brightest well or by a nearby DNA band.
    """
    height, width = pixels.shape
    reach = max(6, round(depth * 1.2))
    offsets = np.arange(-reach, reach + 1)
    xs = _guide_x(points, np.arange(height) + 0.5) + offset
    columns = np.clip(np.rint(xs[:, None] + offsets).astype(int), 0, width - 1)
    strip = pixels[np.arange(height)[:, None], columns]
    noise = max(0.3, float(np.median(np.abs(np.diff(strip, axis=1))) / 0.954))
    ry = max(1, min(5, round(thickness * 0.08)))
    # Arrays are limited to the narrow well strip, including for large TIFFs.
    padded = np.pad(strip, ((ry, ry), (0, 0)), mode="edge")
    sums = np.pad(np.cumsum(padded, axis=0), ((1, 0), (0, 0)))
    smooth = (sums[2 * ry + 1:] - sums[:-2 * ry - 1]) / (2 * ry + 1)
    smooth = np.apply_along_axis(_smooth, 1, smooth, 1)
    broad = np.apply_along_axis(_smooth, 1, smooth, max(4, round(depth / 3)))
    core = np.abs(smooth - broad)[:, np.abs(offsets) <= depth * 0.6]
    return np.quantile(core, 0.85, axis=1), noise / math.sqrt(2 * ry + 1)


def recover_regular_wells(pixels, points, wells, expected_count: int):
    """Remeasure merged/partial outlines inside the known-count guide cells."""
    from .lane_refinement import _crisp_caps

    wells = tuple(sorted(wells, key=lambda well: well.center[1]))
    # One/two wells need no comb model. Dense one-pixel requests use the exact
    # geometry allocator, avoiding contrast analysis below image resolution.
    if expected_count < 3 or not wells:
        return wells, ()
    start, end = max(0, math.floor(points[0][1])), min(pixels.shape[0], math.ceil(points[1][1]))
    # Respect the earlier, evidence-based completion of a cut end well.
    start, end = min(start, wells[0].bounds[1]), max(end, wells[-1].bounds[3])
    if (end - start) / expected_count < 8:
        return wells, ()
    model = _count_model(wells, start, end, expected_count)
    if model is None:
        return wells, ()
    thickness, anchors, phase, pitch = model
    # Estimate depth from the fuller cluster: seeing only one wall should not
    # cause every recovered well to inherit a half-width rectangle.
    depths = np.array([well.bounds[2] - well.bounds[0] for well in anchors])
    depth = float(np.median(depths[depths >= np.median(depths)]))
    full = [well for well in anchors if depth * 0.75 <= well.bounds[2] - well.bounds[0] <= depth * 1.3]
    offset = float(np.median([well.center[0] - _guide_x(points, well.center[1]) for well in full]))
    from .lane_evidence import downstream_spans, well_depth_profile

    measured_depth = well_depth_profile(pixels, points, [well.bounds[1::2] for well in anchors])
    if measured_depth is not None:
        left_offset, right_offset = measured_depth
        depth = right_offset - left_offset
        offset = (left_offset + right_offset) / 2
    profile, noise = _rim_profile(pixels, points, offset, depth, thickness)
    bands = downstream_spans(pixels, points, depth, thickness)
    selected = []
    used_bands = False
    changed = False
    for slot in range(expected_count):
        target = phase + slot * pitch
        lo = max(start, round(target - pitch / 2))
        hi = min(end, round(target + pitch / 2))
        if hi - lo < 5:
            continue
        associated = [well for well in wells if well.bounds[1] < hi and well.bounds[3] > lo]
        matching = [well for well in associated if abs(well.center[1] - target) < pitch * 0.23
                    and thickness * 0.72 <= well.bounds[3] - well.bounds[1] <= thickness * 1.3
                    and depth * 0.8 <= well.bounds[2] - well.bounds[0] <= depth * 1.25
                    and abs(well.center[0] - _guide_x(points, well.center[1]) - offset) <= depth * 0.2]
        if len(matching) == 1:
            selected.append(matching[0])
            continue
        # Clearly bounded unequal wells retain their measured dimensions.
        protected = [well for well in associated
                     if well.bounds[1] >= 3 and well.bounds[3] <= pixels.shape[0] - 3
                     and _crisp_caps(pixels, well)]
        if protected:
            for well in protected:
                left, top, right, bottom = well.bounds
                x = _guide_x(points, well.center[1])
                if measured_depth is not None and right - left < depth * 0.7 and not left + 1 < x < right - 1:
                    new_left = max(0, round(x + measured_depth[0]))
                    new_right = min(pixels.shape[1], round(x + measured_depth[1]))
                    extensions = [(new_left, left), (right, new_right)]
                    extensions = [(a, b) for a, b in extensions if b - a >= 4]
                    # Crisp caps establish height, but a narrow single wall
                    # can have crisp caps too. Require the other rim itself
                    # before restoring the aggregate depth around the guide.
                    if extensions and all(_contrast_support(pixels, _well((a, top, b, bottom))) for a, b in extensions):
                        well = _well((new_left, top, new_right, bottom))
                        changed = True
                if well not in selected:
                    selected.append(well)
            continue
        cell = profile[lo:hi]
        floor = float(np.percentile(cell, 15))
        peak = float(np.percentile(cell, 75))
        # Local contrast is mandatory, including for an unloaded end well.
        if peak - floor < max(noise * 1.2, 1e-9):
            selected.extend(well for well in associated if well not in selected)
            continue
        nearby_bands = [(a, b) for a, b in bands if abs((a + b) / 2 - target) < pitch * 0.22]
        center = target
        if nearby_bands:
            band_center = float(np.median([(a + b) / 2 for a, b in nearby_bands]))
            # Migration can curve slightly: band evidence is a soft positional
            # cue, not permission to move a well onto the downstream band.
            center += float(np.clip(band_center - target, -pitch * 0.08, pitch * 0.08)) * 0.5
            used_bands = True
        active = _bridge(cell > floor + (peak - floor) * 0.35, max(1, round(thickness * 0.06)))
        runs = [(a + lo, b + lo) for a, b in _runs(active)
                if b - a >= thickness * 0.4 and a + lo < center + thickness * 0.2 and b + lo > center - thickness * 0.2]
        if not runs:
            selected.extend(well for well in associated if well not in selected)
            continue
        a, b = min(runs, key=lambda span: abs((span[0] + span[1]) / 2 - center))
        # Bound size variation in weak proposals. The fitted center limits the
        # influence of dirt extending one rim into the neighboring cell.
        measured_center = float(np.clip((a + b) / 2, center - pitch * 0.10, center + pitch * 0.10))
        size = max(round(thickness * 0.8), min(round(thickness * 1.2), b - a))
        top = max(lo, min(hi - size, round(measured_center - size / 2)))
        x = _guide_x(points, measured_center) + offset
        left = max(0, min(pixels.shape[1] - round(depth), round(x - depth / 2)))
        candidate = _well((int(left), int(top), int(left + round(depth)), int(top + size)))
        # A relative threshold always has a strongest patch, even in a blank
        # cell. Require sustained original-pixel contrast as well, so a comb
        # and a downstream band cannot turn correlated noise into a well.
        if not _contrast_support(pixels, candidate):
            selected.extend(well for well in associated if well not in selected)
            continue
        selected.append(candidate)
        changed |= candidate not in wells
    # Never silently remove a supported well away from the recovered comb.
    for well in wells:
        if not any(min(well.bounds[3], other.bounds[3]) > max(well.bounds[1], other.bounds[1]) for other in selected):
            selected.append(well)
    selected = sorted(set(selected), key=lambda well: well.center[1])
    if not changed or any(a.bounds[3] > b.bounds[1] for a, b in zip(selected, selected[1:])):
        return wells, ()
    warning = "The requested well count and local rim contrast repaired merged or partial outlines with consistent well sizes. Review the recovered wells and lane boundaries."
    if used_bands:
        warning += " Downstream bands also supported the recovered lane positions."
    return tuple(selected), (warning,)
