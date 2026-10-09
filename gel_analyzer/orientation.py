"""Fit a gel's tilted outline and orient its original left edge at the top.

Detection uses a reduced grayscale copy. The accepted source pixels are sampled
only once, with the rotation, vertical reflection, and rectangle crop composed
in that order; no intensity normalization is applied to the output image.
"""

from dataclasses import dataclass
import math

import numpy as np
from PIL import Image

from .auto_crop import _has_competing_outer_edge


class OrientationError(ValueError):
    """The image does not contain a sufficiently reliable rectangular outline."""


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


@dataclass(frozen=True)
class _Side:
    points: np.ndarray
    slope: float
    support: float


_ANALYSIS_LIMIT = 768
_UNCERTAIN = (
    "The gel outline could not be estimated reliably. Choose an image with all "
    "four gel edges visible and a small amount of surrounding background."
)


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
    if image.mode not in {"1", "L", "LA", "P", "RGB", "RGBA", "I;16", "I;16L", "I;16B"}:
        raise OrientationError("This image's pixel format is not supported for orientation.")
    if "A" in image.getbands() and image.getchannel("A").getextrema() != (255, 255):
        raise OrientationError("Orientation requires a gel image without transparent areas.")
    if image.mode == "P" and "transparency" in image.info:
        raise OrientationError("Orientation requires a gel image without transparent areas.")
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


def orient_gel(image: Image.Image) -> OrientationResult:
    """Rotate/straighten CCW, flip vertically, then crop to the fitted rectangle.

    The geometry is composed before sampling, avoiding cumulative interpolation
    from three separate image operations. The same matrices transform both the
    source image and its fitted rectangle. The source image is never mutated.
    """
    rectangle = fit_gel_rectangle(image)
    degrees = 90.0 + rectangle.angle_degrees
    radians = math.radians(degrees)
    cosine, sine = math.cos(radians), math.sin(radians)
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
    rotated_and_flipped = flip @ rotation
    fitted_corners = np.column_stack((np.asarray(rectangle.corners), np.ones(4)))
    transformed_corners = fitted_corners @ rotated_and_flipped.T
    crop_min = transformed_corners[:, :2].min(axis=0)
    crop_max = transformed_corners[:, :2].max(axis=0)
    extent = crop_max - crop_min
    # Round inward: the output pixel boundary never extends beyond the outline.
    output_size = tuple(max(1, int(math.floor(float(value) + 1e-7))) for value in extent)
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
        result = Image.fromarray(values)
        if result.mode != image.mode:
            result = result.convert(image.mode)
    else:
        source = image.convert("RGB") if image.mode == "P" else image
        resampling = Image.Resampling.NEAREST if source.mode == "1" else Image.Resampling.BILINEAR
        result = source.transform(output_size, Image.Transform.AFFINE, affine, resampling)
    return OrientationResult(result, rectangle, degrees)
