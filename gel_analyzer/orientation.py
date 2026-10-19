"""Fit a gel's tilted outline and prepare it for the selected workflow.

Detection uses a reduced grayscale copy. The accepted source pixels are sampled
only once, with the rotation, vertical reflection, and rectangle crop composed
in that order; no intensity normalization is applied to the output image.
"""

from dataclasses import dataclass
import math
from numbers import Real

import numpy as np
from PIL import Image

from .auto_crop import _has_competing_outer_edge


class OrientationError(ValueError):
    """The image or selected rectangle cannot be used for orientation."""


@dataclass(frozen=True, slots=True)
class GelRectangle:
    """Rectangle in source pixel-boundary coordinates, clockwise TL/TR/BR/BL.

    ``angle_degrees`` is the clockwise tilt of the original top edge relative
    to the source x axis. Width and height retain the source's original sides.
    """

    corners: tuple[tuple[float, float], ...]
    width: float
    height: float
    angle_degrees: float


@dataclass(frozen=True, slots=True)
class OrientationResult:
    image: Image.Image
    rectangle: GelRectangle
    counterclockwise_degrees: float
    outline_complete: bool = True
    supported_edges: tuple[str, ...] = ()


@dataclass(frozen=True)
class _Side:
    points: np.ndarray
    slope: float
    support: float


_ANALYSIS_LIMIT = 768
_UNCERTAIN = (
    "The four gel edges could not be detected reliably."
)


def _cosine_sine(degrees: float) -> tuple[float, float]:
    radians = math.radians(degrees)
    cosine, sine = math.cos(radians), math.sin(radians)
    if degrees % 90 == 0:
        # Exact quarter turns need no interpolation between adjacent pixels.
        # Tiny trig residuals otherwise round down some RGB channels in Pillow.
        return float(round(cosine)), float(round(sine))
    return cosine, sine


def rectangle_from_selection(selection: object, size: tuple[int, int]) -> GelRectangle:
    """Validate a manual rectangle in the initial crop's pixel coordinates.

    The angle is clockwise around the rectangle center. Keeping its original
    side identities across the full circle lets users correct any orientation,
    including an upside-down selection, before the normal rotate/flip step.
    """
    fields = ("cx", "cy", "width", "height", "angle_degrees")
    if not isinstance(selection, dict) or any(key not in selection for key in fields):
        raise OrientationError("Draw a rectangle around the gel before applying it.")
    values = [selection[key] for key in fields]
    if any(isinstance(value, bool) or not isinstance(value, Real) for value in values):
        raise OrientationError("The outline could not be read. Draw it again around the gel.")
    try:
        cx, cy, width, height, angle = map(float, values)
    except (OverflowError, ValueError) as exc:
        raise OrientationError(
            "The outline could not be read. Draw it again around the gel."
        ) from exc
    if not all(math.isfinite(value) for value in (cx, cy, width, height, angle)):
        raise OrientationError("The outline could not be read. Draw it again around the gel.")
    if min(width, height) < 2:
        raise OrientationError("The outline is too small. Draw a larger rectangle around the gel.")
    angle = (angle + 180) % 360 - 180
    cosine, sine = _cosine_sine(angle)
    u = np.asarray((cosine, sine))
    v = np.asarray((-sine, cosine))
    center = np.asarray((cx, cy))
    # Multiplying each side by one half first avoids overflowing intermediate
    # values in a malformed payload; the bounds check rejects oversized boxes.
    horizontal, vertical = (width / 2) * u, (height / 2) * v
    with np.errstate(over="ignore", invalid="ignore"):
        corners = np.asarray([
            center - horizontal - vertical,
            center + horizontal - vertical,
            center + horizontal + vertical,
            center - horizontal + vertical,
        ])
    tolerance = 1e-6
    if (
        not np.isfinite(corners).all()
        or (corners < -tolerance).any()
        or (corners > np.asarray(size) + tolerance).any()
    ):
        raise OrientationError("Keep all four corners of the rectangle inside the image.")
    return GelRectangle(
        corners=tuple((float(x), float(y)) for x, y in corners),
        width=width,
        height=height,
        angle_degrees=angle,
    )


def _validate_orientation_image(image: Image.Image) -> None:
    """Apply the same source-pixel requirements to manual and detected outlines."""
    if image.mode not in {"1", "L", "LA", "P", "RGB", "RGBA", "I;16", "I;16L", "I;16B"}:
        raise OrientationError("This image format cannot be rotated here. Open a standard PNG or JPEG copy.")
    if "A" in image.getbands() and image.getchannel("A").getextrema() != (255, 255):
        raise OrientationError("Orientation requires a gel image without transparent areas.")
    if image.mode == "P" and "transparency" in image.info:
        raise OrientationError("Orientation requires a gel image without transparent areas.")


def _step(profile: np.ndarray) -> np.ndarray:
    """Three-pixel means on either side of each pixel boundary."""
    padded = np.pad(profile, (3, 3), mode="edge")
    sums = np.concatenate(([0.0], np.cumsum(padded)))
    centers = np.arange(len(profile)) + 3
    return (sums[centers + 3] - 2 * sums[centers] + sums[centers - 3]) / 3


def _trace_side(pixels: np.ndarray, *, axis: int, near: bool) -> _Side:
    """Find a long, straight outer boundary despite bands and isolated debris."""
    size = pixels.shape[axis]
    across = pixels.shape[1 - axis]
    positions = np.linspace(across * 0.2, across * 0.8, 61)
    low, high = (1, int(size * 0.46)) if near else (int(size * 0.54), size - 1)
    if high <= low:
        raise OrientationError(_UNCERTAIN)
    candidates = []
    for group, position in enumerate(positions):
        center = int(position)
        if axis == 0:
            profile = np.median(pixels[:, max(0, center - 1) : center + 2], axis=1)
        else:
            profile = np.median(pixels[max(0, center - 1) : center + 2, :], axis=0)
        response = _step(profile) * (-1 if near else 1)
        scores = response[low:high].copy()
        # Keep several alternatives so a lane band cannot displace the edge.
        for _ in range(4):
            peak = int(np.argmax(scores))
            strength = scores[peak]
            if strength < 0.025:
                break
            candidates.append((position + 0.5, float(low + peak), group, strength))
            scores[max(0, peak - 5) : peak + 6] = 0
    if len(candidates) < 30:
        raise OrientationError(_UNCERTAIN)
    points = np.asarray(candidates)
    x, y, groups = points[:, 0], points[:, 1], points[:, 2].astype(int)
    # Reproducible robust line fitting. One vote per scan line prevents multiple
    # peaks in a dark band from outweighing a continuous physical outer edge.
    rng = np.random.default_rng(0)
    pairs = rng.integers(0, len(points), size=(800, 2))
    best_score, best = -1.0, None
    tolerance = max(1.8, size * 0.004)
    for first, second in pairs:
        delta = x[second] - x[first]
        if abs(delta) < across * 0.15:
            continue
        slope = (y[second] - y[first]) / delta
        if abs(slope) > 0.85:
            continue
        intercept = y[first] - slope * x[first]
        residual = np.abs(y - (slope * x + intercept))
        strengths = np.where(residual <= tolerance, np.minimum(points[:, 3], 0.5), 0)
        votes = np.zeros(len(positions))
        np.maximum.at(votes, groups, strengths)
        support = np.count_nonzero(votes)
        score = support + votes.sum() * 0.4
        if score > best_score:
            best_score, best = score, (slope, intercept)
    if best is None:
        raise OrientationError(_UNCERTAIN)
    line = np.asarray(best)
    chosen = np.empty(0, dtype=int)
    for _ in range(3):
        residual = np.abs(y - np.polyval(line, x))
        chosen = np.asarray([
            eligible[np.argmax(points[eligible, 3])]
            for group in range(len(positions))
            if (eligible := np.flatnonzero((groups == group) & (residual <= tolerance))).size
        ])
        if len(chosen) < len(positions) * 0.55:
            raise OrientationError(_UNCERTAIN)
        line = np.polyfit(x[chosen], y[chosen], 1)
    samples = points[chosen, :2]
    if axis == 1:
        samples = samples[:, ::-1]
    return _Side(samples, float(line[0]), len(chosen) / len(positions))


def _check_outer_boundaries(
    pixels: np.ndarray, corners: np.ndarray, degrees: float,
) -> None:
    """Keep the initial crop's protection against faint physical extensions.

    A strong inner boundary does not prove that the gel ends there. Deskew only
    the detection copy so the shared outer-edge checks can look for weaker,
    coherent enclosing edges, including blurred edges that end at gel corners.
    NaN fill excludes wedges outside the photographed image from that evidence.
    """
    height, width = pixels.shape
    upright_image = Image.fromarray(pixels.astype(np.float32)).rotate(
        degrees, resample=Image.Resampling.BILINEAR, expand=True, fillcolor=float("nan")
    )
    upright = np.asarray(upright_image, dtype=np.float64)
    radians = math.radians(degrees)
    cosine, sine = math.cos(radians), math.sin(radians)
    rotation = np.asarray(((cosine, sine), (-sine, cosine)))
    transformed = (corners - (width / 2, height / 2)) @ rotation.T
    transformed += np.asarray(upright_image.size) / 2
    left, top = np.rint(transformed.min(axis=0)).astype(int)
    right, bottom = np.rint(transformed.max(axis=0)).astype(int)
    horizontal = np.median(
        upright[top + int((bottom - top) * 0.35) : top + int((bottom - top) * 0.65), :],
        axis=0,
    )
    vertical = np.median(
        upright[:, left + int((right - left) * 0.35) : left + int((right - left) * 0.65)],
        axis=1,
    )
    sides = (
        (horizontal, left, top, bottom, 1, -1, True),
        (vertical, top, left, right, 0, -1, True),
        (horizontal, right, top, bottom, 1, 1, False),
        (vertical, bottom, left, right, 0, 1, False),
    )
    broad_sides = 0
    for side in sides:
        if _has_competing_outer_edge(upright, *side):
            raise OrientationError(_UNCERTAIN)
        if _has_competing_outer_edge(upright, *side, localized=False):
            broad_sides += 1
            if broad_sides >= 2 or _has_competing_outer_edge(
                upright, *side, localized=False, require_termination=True
            ):
                raise OrientationError(_UNCERTAIN)


def fit_gel_rectangle(image: Image.Image) -> GelRectangle:
    """Fit four supported outer edges to one tilted rectangle.

    The supported scene is one roughly centered dark gel on a lighter surround,
    with all four edges visible and a modest tilt. An ambiguous
    image raises ``OrientationError`` instead of silently rotating a full frame.
    """
    if min(image.size) < 48:
        raise OrientationError(_UNCERTAIN)
    _validate_orientation_image(image)
    # F avoids clipping uint16 pixels at 255. This normalization is detection-only.
    gray = image.convert("F" if image.mode.startswith("I") else "L")
    gray.thumbnail((_ANALYSIS_LIMIT, _ANALYSIS_LIMIT), Image.Resampling.BILINEAR)
    pixels = np.asarray(gray, dtype=np.float64)
    if min(pixels.shape) < 48:
        raise OrientationError(_UNCERTAIN)
    low, high = np.percentile(pixels, [1, 99])
    if not np.isfinite(pixels).all() or high - low < 4:
        raise OrientationError(_UNCERTAIN)
    pixels = (pixels - low) / (high - low)
    left = _trace_side(pixels, axis=1, near=True)
    right = _trace_side(pixels, axis=1, near=False)
    top = _trace_side(pixels, axis=0, near=True)
    bottom = _trace_side(pixels, axis=0, near=False)
    sides = (left, right, top, bottom)
    scale = np.asarray(image.size) / np.asarray(gray.size)
    # Work in original coordinates before imposing perpendicularity; rounding
    # during analysis resizing can give x and y slightly different scales.
    source_points = [side.points * scale for side in sides]
    angles = []
    weights = []
    for index, points in enumerate(source_points):
        if index < 2:
            slope = np.polyfit(points[:, 1], points[:, 0], 1)[0]
            angle = math.atan(-slope)
            span = np.ptp(points[:, 1])
        else:
            slope = np.polyfit(points[:, 0], points[:, 1], 1)[0]
            angle = math.atan(slope)
            span = np.ptp(points[:, 0])
        angles.append(angle)
        weights.append(span * span * sides[index].support)
    if np.ptp(angles) > math.radians(8):
        raise OrientationError(_UNCERTAIN)
    theta = float(np.average(angles, weights=weights))
    u = np.asarray((math.cos(theta), math.sin(theta)))
    v = np.asarray((-math.sin(theta), math.cos(theta)))
    left_bound, right_bound = [float(np.median(points @ u)) for points in source_points[:2]]
    top_bound, bottom_bound = [float(np.median(points @ v)) for points in source_points[2:]]
    width, height = right_bound - left_bound, bottom_bound - top_bound
    if min(width, height) < 24 or width * height < image.width * image.height * 0.12:
        raise OrientationError(_UNCERTAIN)
    corners = np.asarray([
        left_bound * u + top_bound * v,
        right_bound * u + top_bound * v,
        right_bound * u + bottom_bound * v,
        left_bound * u + bottom_bound * v,
    ])
    # A fitted edge beyond the source has no supporting visible image data.
    if (corners < -2).any() or (corners > np.asarray(image.size) + 2).any():
        raise OrientationError(_UNCERTAIN)
    _check_outer_boundaries(pixels, corners / scale, math.degrees(theta))
    return GelRectangle(
        corners=tuple((float(x), float(y)) for x, y in corners),
        width=width,
        height=height,
        angle_degrees=math.degrees(theta),
    )


def _full_frame_envelope(size: tuple[int, int], degrees: float) -> GelRectangle:
    """Enclose all source pixels in the tilted axes without claiming gel edges."""
    cosine, sine = _cosine_sine(degrees)
    u, v = np.asarray((cosine, sine)), np.asarray((-sine, cosine))
    width, height = size
    frame = np.asarray(((0, 0), (width, 0), (width, height), (0, height)))
    left, right = float(np.min(frame @ u)), float(np.max(frame @ u))
    top, bottom = float(np.min(frame @ v)), float(np.max(frame @ v))
    corners = (left * u + top * v, right * u + top * v,
               right * u + bottom * v, left * u + bottom * v)
    return GelRectangle(tuple(tuple(float(value) for value in point) for point in corners),
                        right - left, bottom - top, degrees)


def _broad_boundary(pixels: np.ndarray, side: _Side, *, axis: int, near: bool) -> bool:
    """An outer side separates broad regions, unlike a thin band or scratch.

    Test sustained interior contrast against the available outside background.
    A photographed side may sit only a few pixels from the frame boundary;
    shorten the outside sample in that case instead of requiring nonexistent
    background. Never clamp an out-of-frame coordinate onto the gel itself.
    """
    height, width = pixels.shape
    direction = 1 if near else -1
    # Array axes are y,x, whereas traced points are in displayed x,y.
    coordinate = 1 - axis
    distances = (max(4, min(pixels.shape) * 0.012),
                 max(8, min(pixels.shape) * 0.035),
                 max(12, min(pixels.shape) * 0.07))
    for distance in distances:
        inside, outside = side.points.copy(), side.points.copy()
        inside[:, coordinate] += direction * distance
        available = (outside[:, coordinate] if near else pixels.shape[axis] - outside[:, coordinate])
        outside_distance = np.minimum(distance, available * .75)
        outside[:, coordinate] -= direction * outside_distance
        inside, outside = np.floor(inside).astype(int), np.floor(outside).astype(int)
        valid = ((inside >= 0).all(axis=1) & (outside >= 0).all(axis=1)
                 & (inside < (width, height)).all(axis=1) & (outside < (width, height)).all(axis=1)
                 & (outside_distance >= 1))
        if np.count_nonzero(valid) < len(side.points) * 0.65:
            return False
        inner, outer = inside[valid], outside[valid]
        contrast = pixels[outer[:, 1], outer[:, 0]] - pixels[inner[:, 1], inner[:, 0]]
        if np.median(contrast) < 0.12 or np.mean(contrast > 0.06) < 0.75:
            return False
    return True


def _trace_partial_side(pixels: np.ndarray, *, axis: int, near: bool) -> _Side:
    """Trace an observed side segment anywhere in an incompletely framed gel.

    Unlike the complete-outline fitter, a partial photograph need not be
    centered: both side edges can occupy the same image half, and the third
    side can appear only near a corner. Scan the full frame and measure support
    within the observed segment, never extrapolating across missing evidence.
    """
    size, across = pixels.shape[axis], pixels.shape[1 - axis]
    positions = np.linspace(1, across - 2, min(121, across - 2))
    candidates = []
    for group, position in enumerate(positions):
        center = int(position)
        profile = (np.median(pixels[:, max(0, center - 1):center + 2], axis=1)
                   if axis == 0 else np.median(pixels[max(0, center - 1):center + 2, :], axis=0))
        scores = (_step(profile) * (-1 if near else 1))[1:size - 1].copy()
        for _ in range(5):
            peak = int(np.argmax(scores))
            if scores[peak] < .025:
                break
            candidates.append((position + .5, float(peak + 1), group, scores[peak]))
            scores[max(0, peak - 5):peak + 6] = 0
    if len(candidates) < 12:
        raise OrientationError(_UNCERTAIN)
    points = np.asarray(candidates)
    tolerance = max(1.8, size * .003)
    rng = np.random.default_rng(0)
    # A long interior band can be stronger than an outside side. Try the next
    # independent line when broad-region checks reject a thin band or scratch.
    for _ in range(5):
        if len(points) < 12:
            break
        x, y, groups = points[:, 0], points[:, 1], points[:, 2].astype(int)
        best_score, best = -1., None
        for first, second in rng.integers(0, len(points), size=(1000, 2)):
            delta = x[second] - x[first]
            if abs(delta) < max(16, across * .08):
                continue
            slope = (y[second] - y[first]) / delta
            if abs(slope) > .85:
                continue
            intercept = y[first] - slope * x[first]
            residual = np.abs(y - (slope * x + intercept))
            votes = np.zeros(len(positions))
            np.maximum.at(votes, groups, np.where(residual <= tolerance, np.minimum(points[:, 3], .5), 0))
            score = np.count_nonzero(votes) + votes.sum() * .4
            if score > best_score:
                best_score, best = score, (slope, intercept)
        if best is None:
            break
        line = np.asarray(best)
        chosen = np.empty(0, dtype=int)
        for _ in range(3):
            residual = np.abs(y - np.polyval(line, x))
            chosen = np.asarray([
                eligible[np.argmax(points[eligible, 3])]
                for group in np.unique(groups)
                if (eligible := np.flatnonzero((groups == group) & (residual <= tolerance))).size
            ], dtype=int)
            if len(chosen) < 12:
                break
            line = np.polyfit(x[chosen], y[chosen], 1)
        if len(chosen) >= 12:
            density = len(chosen) / (int(np.ptp(groups[chosen])) + 1)
            if density >= .75 and np.ptp(x[chosen]) >= max(24, across * .12):
                samples = points[chosen, :2]
                if axis == 1:
                    samples = samples[:, ::-1]
                side = _Side(samples, float(line[0]), density)
                if _broad_boundary(pixels, side, axis=axis, near=near):
                    return side
        points = points[np.abs(y - np.polyval(line, x)) > tolerance * 1.5]
    raise OrientationError(_UNCERTAIN)


def fit_partial_gel_edges(image: Image.Image) -> tuple[float, tuple[str, ...]]:
    """Estimate tilt only from multiple consistent, clearly visible sides.

    This is a fallback after four-edge fitting fails. It accepts broad dark or
    bright gel boundaries, requires independent sides rather than a lone line,
    and never estimates a missing cropping boundary. Conflicting side angles,
    weak evidence, gradients, small objects and thin bands remain unsupported.
    """
    uncertain = "The visible gel sides do not provide a reliable, consistent orientation. Draw the outline manually."
    _validate_orientation_image(image)
    gray = image.convert("F" if image.mode.startswith("I") else "L")
    gray.thumbnail((_ANALYSIS_LIMIT, _ANALYSIS_LIMIT), Image.Resampling.BILINEAR)
    pixels = np.asarray(gray, dtype=np.float64)
    if min(pixels.shape) < 48:
        raise OrientationError(uncertain)
    low, high = np.percentile(pixels, [1, 99])
    if not np.isfinite(pixels).all() or high - low < 4:
        raise OrientationError(uncertain)
    normalized = (pixels - low) / (high - low)
    scale = np.asarray(image.size) / np.asarray(gray.size)
    specifications = (("left", 1, True), ("right", 1, False),
                      ("top", 0, True), ("bottom", 0, False))
    candidates = []
    for values in (normalized, 1 - normalized):
        sides = []
        for name, axis, near in specifications:
            try:
                side = _trace_partial_side(values, axis=axis, near=near)
            except OrientationError:
                continue
            points = side.points * scale
            if axis == 1:
                angle = math.degrees(math.atan(-np.polyfit(points[:, 1], points[:, 0], 1)[0]))
                span = float(np.ptp(points[:, 1]))
            else:
                angle = math.degrees(math.atan(np.polyfit(points[:, 0], points[:, 1], 1)[0]))
                span = float(np.ptp(points[:, 0]))
            sides.append((name, axis, side, angle, span, points))
        if len(sides) < 2:
            continue
        angles = [side[3] for side in sides]
        theta = math.radians(float(np.median(angles)))
        axes = (np.asarray((-math.sin(theta), math.cos(theta))),
                np.asarray((math.cos(theta), math.sin(theta))))
        bounds = {side[0]: float(np.median(side[5] @ axes[side[1]])) for side in sides}
        # With a full-frame search the opposite contrast polarity also sees
        # these lines, but it reverses which side contains gel. Opposing sides
        # must bound the same interior, not the two disconnected outer margins.
        if ("left" in bounds and "right" in bounds and bounds["left"] >= bounds["right"]
                or "top" in bounds and "bottom" in bounds and bounds["top"] >= bounds["bottom"]):
            continue
        # Reject an impossible contrast polarity before considering its angle
        # disagreement: its interior is outside the gel, so it cannot veto the
        # supported physical boundary set from the other polarity.
        # Do not cherry-pick an agreeable subset of a physically valid set.
        if np.ptp(angles) > 5 or max(abs(angle) for angle in angles) > 35:
            raise OrientationError(uncertain)
        if len(sides) == 2:
            # Two opposing long sides can define tilt despite both end edges
            # being outside the frame. Reject narrow strips and partial specks.
            if any(side[2].support < 0.85 for side in sides):
                continue
            if sides[0][1] == sides[1][1]:
                axis = sides[0][1]
                separation = abs(float(np.median(sides[0][5][:, 1 - axis]))
                                 - float(np.median(sides[1][5][:, 1 - axis])))
                if separation < image.size[1 - axis] * 0.25:
                    continue
        weights = [side[4] ** 2 * side[2].support for side in sides]
        candidates.append((float(np.average(angles, weights=weights)),
                           tuple(side[0] for side in sides), sum(weights)))
    if not candidates or (len(candidates) > 1 and np.ptp([candidate[0] for candidate in candidates]) > 5):
        raise OrientationError(uncertain)
    angle, names, _ = max(candidates, key=lambda candidate: (len(candidate[1]), candidate[2]))
    # Pixel staircases around an exactly upright edge can produce tiny fitting
    # residuals. Retain exact quarter-turn/no-turn copies in that case.
    if abs(angle) < 0.05:
        angle = 0.0
    return angle, names


def orient_gel(
    image: Image.Image, rectangle: GelRectangle | None = None,
    *, workflow_orientation: str = "wells_left",
    fallback_angle_degrees: float | None = None,
    supported_edges: tuple[str, ...] = (),
) -> OrientationResult:
    """Prepare the chosen outline with a single composed image transform.

    The default rotates/straightens CCW and flips vertically. Wells at top
    only removes the chosen tilt, retaining the original top edge and handedness.

    The geometry is composed before sampling, avoiding cumulative interpolation
    from three separate image operations. The same matrices transform both the
    source image and its rectangle. With no manual rectangle, fit the source's
    outline automatically. If that fails, multiple clear sides can supply tilt
    without supplying a crop: the complete source is retained on an expanded
    canvas. ``fallback_angle_degrees`` reapplies that accepted partial estimate
    when changing workflow orientation. The source image is never mutated.
    """
    if workflow_orientation not in ("wells_left", "wells_top"):
        raise OrientationError("Choose a supported workflow orientation.")
    outline_complete = True
    if fallback_angle_degrees is not None:
        if (rectangle is not None or isinstance(fallback_angle_degrees, bool)
                or not isinstance(fallback_angle_degrees, Real)
                or not math.isfinite(fallback_angle_degrees) or abs(fallback_angle_degrees) > 35
                or not isinstance(supported_edges, tuple)
                or any(type(name) is not str or name not in {"left", "right", "top", "bottom"} for name in supported_edges)
                or len(set(supported_edges)) != len(supported_edges)):
            raise OrientationError("The retained partial-edge orientation is invalid.")
        _validate_orientation_image(image)
        rectangle = _full_frame_envelope(image.size, float(fallback_angle_degrees))
        outline_complete = False
    elif rectangle is None:
        try:
            rectangle = fit_gel_rectangle(image)
        except OrientationError:
            angle, supported_edges = fit_partial_gel_edges(image)
            rectangle = _full_frame_envelope(image.size, angle)
            outline_complete = False
    else:
        _validate_orientation_image(image)
    # Wells at top keeps the chosen top edge and migration direction. Only
    # the user's rectangle tilt is removed; no quarter-turn or reflection.
    degrees = rectangle.angle_degrees + (0.0 if workflow_orientation == "wells_top" else 90.0)
    cosine, sine = _cosine_sine(degrees)
    rotation = np.asarray(((cosine, sine, 0), (-sine, cosine, 0), (0, 0, 1)))
    image_corners = np.asarray(((0, 0, 1), (image.width, 0, 1),
                                (image.width, image.height, 1), (0, image.height, 1)))
    rotated_corners = image_corners @ rotation.T
    rotated_min = rotated_corners[:, :2].min(axis=0)
    rotated_max = rotated_corners[:, :2].max(axis=0)
    translation = np.eye(3)
    translation[:2, 2] = -rotated_min
    rotation = translation @ rotation
    # PowerPoint's Flip Vertical: reflect top to bottom on the rotated canvas.
    flip = np.asarray(((1, 0, 0), (0, -1, rotated_max[1] - rotated_min[1]), (0, 0, 1)))
    rotated_and_flipped = rotation if workflow_orientation == "wells_top" else flip @ rotation
    fitted_corners = np.column_stack((np.asarray(rectangle.corners), np.ones(4)))
    transformed_corners = fitted_corners @ rotated_and_flipped.T
    crop_min = transformed_corners[:, :2].min(axis=0)
    crop_max = transformed_corners[:, :2].max(axis=0)
    extent = crop_max - crop_min
    # Complete outlines round inward. Partial outlines round outward so the
    # rotated source keeps every original edge and corner, including low bits.
    output_size = tuple(max(1, int(math.floor(float(value) + 1e-7) if outline_complete
                                  else math.ceil(float(value) - 1e-7))) for value in extent)
    crop = np.eye(3)
    crop[:2, 2] = -crop_min
    inverse = np.linalg.inv(crop @ rotated_and_flipped)
    affine = tuple(float(value) for value in inverse[:2].reshape(-1))
    if image.mode.startswith("I;16"):
        # Pillow's direct I;16 interpolator operates on bytes. F preserves the
        # values during interpolation, then explicit conversion restores uint16.
        sampled = image.convert("F").transform(
            output_size, Image.Transform.AFFINE, affine, Image.Resampling.BILINEAR
        )
        dtype = np.asarray(image).dtype
        values = np.clip(np.rint(np.asarray(sampled)), 0, 65535).astype(dtype)
        # Preserve the original byte order explicitly; Pillow's I;16 -> I;16L
        # conversion otherwise takes an 8-bit path and clips values above 255.
        result = Image.frombytes(image.mode, output_size, values.tobytes())
    else:
        source = image.convert("RGB") if image.mode == "P" else image
        resampling = Image.Resampling.NEAREST if source.mode == "1" else Image.Resampling.BILINEAR
        # A full-frame rotation adds canvas wedges. Keep alpha opaque so those
        # added margins do not make later well/band analysis reject the image.
        fill = ((0, 0, 0, 255) if source.mode == "RGBA" else (0, 255)
                if source.mode == "LA" else 0) if not outline_complete else None
        result = source.transform(output_size, Image.Transform.AFFINE, affine, resampling, fillcolor=fill)
    return OrientationResult(result, rectangle, degrees, outline_complete, supported_edges)
