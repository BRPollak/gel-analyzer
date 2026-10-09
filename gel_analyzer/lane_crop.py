"""Validate manual lane bounds and copy their shared crop without resampling.

Inputs use confirmed-image pixel-boundary coordinates. Adjustments keep each
well's horizontal bounds and change its top/bottom independently; every lane
shares one right edge. The final crop adds 1% of the image width to the left
and 1% of its height above/below the outer lanes (at least three pixels each).
All margins are clipped to the available image pixels.
"""

from dataclasses import dataclass, is_dataclass
from io import BytesIO
import math
from numbers import Integral, Real

import numpy as np
from PIL import Image

from .wells import Bounds, Well


class LaneAdjustmentError(ValueError):
    """Lane geometry cannot be applied safely to the confirmed image."""


@dataclass(frozen=True, slots=True)
class LaneCrop:
    """Lossless crop plus geometry translated into its own coordinate system."""

    preview_png: bytes
    crop_box: Bounds
    width: int
    height: int
    wells: tuple[Well, ...]
    lanes: tuple[Bounds, ...]


def _pixel(value, label: str) -> int:
    """Accept numeric integer values without coercing text or boolean events."""
    if isinstance(value, (bool, np.bool_)) or not isinstance(value, Real):
        raise LaneAdjustmentError(f"{label} must be a finite whole-pixel number.")
    if isinstance(value, Integral):
        return int(value)
    try:
        if not math.isfinite(value) or value != math.floor(value):
            raise LaneAdjustmentError(f"{label} must be a finite whole-pixel number.")
        return int(value)
    except (TypeError, OverflowError, ValueError) as exc:
        raise LaneAdjustmentError(f"{label} must be a finite whole-pixel number.") from exc


def _sequence(value, label: str) -> tuple:
    if isinstance(value, (str, bytes, dict)):
        raise LaneAdjustmentError(f"{label} must contain the expected coordinate values.")
    try:
        return tuple(value)
    except TypeError as exc:
        raise LaneAdjustmentError(f"{label} must contain the expected coordinate values.") from exc


def _size(size) -> tuple[int, int]:
    dimensions = _sequence(size, "Image size")
    if len(dimensions) != 2:
        raise LaneAdjustmentError("The confirmed image must have a width and height.")
    width, height = (_pixel(value, "Image size") for value in dimensions)
    if min(width, height) < 1:
        raise LaneAdjustmentError("The confirmed image must have a positive width and height.")
    return width, height


def _bounds(bounds, label: str) -> Bounds:
    values = _sequence(bounds, label)
    if len(values) != 4:
        raise LaneAdjustmentError(f"{label} must contain left, top, right, and bottom bounds.")
    return tuple(_pixel(value, label) for value in values)


def _checked_wells(wells, size: tuple[int, int]) -> tuple[Well, ...]:
    originals = _sequence(wells, "Wells")
    if not originals:
        raise LaneAdjustmentError("Detect at least one well before adjusting or cropping lanes.")
    width, height = size
    checked = []
    for number, well in enumerate(originals, start=1):
        # Streamlit keeps session objects across source reloads. A retained
        # Well can belong to the previous definition of the same dataclass;
        # validate its coordinates and rebuild it with the current definition.
        retained_well = (
            is_dataclass(well)
            and type(well).__module__ == Well.__module__
            and type(well).__qualname__ == Well.__qualname__
        )
        if not isinstance(well, Well) and not retained_well:
            raise LaneAdjustmentError(f"Well {number} has invalid geometry. Detect the wells again.")
        left, top, right, bottom = _bounds(well.bounds, f"Well {number}")
        if not (0 <= left < right <= width and 0 <= top < bottom <= height):
            raise LaneAdjustmentError(f"Well {number} must have positive bounds inside the confirmed image.")
        checked.append(Well((left, top, right, bottom), ((left + right) / 2, (top + bottom) / 2)))
    return tuple(checked)


def validate_lane_adjustments(
    original_wells, lanes, right_edge, size: tuple[int, int]
) -> tuple[Well, ...]:
    """Return wells with accepted heights, or explain the invalid adjustment.

    Lane input is one ``(left, top, right, bottom)`` rectangle per original
    well, in the original top-to-bottom order. Left edges are fixed; every
    right bound must equal ``right_edge``. Bounds are finite integer pixel
    boundaries and may touch, but lanes may not overlap or cross. Invalid
    geometry is rejected, never silently rounded, reordered, or clamped.
    """
    width, height = _size(size)
    originals = _checked_wells(original_wells, (width, height))
    proposed = _sequence(lanes, "Lanes")
    if len(proposed) != len(originals):
        raise LaneAdjustmentError("Keep exactly one lane for each detected well.")
    shared_right = _pixel(right_edge, "The shared right edge")
    if not max(well.bounds[2] for well in originals) <= shared_right <= width:
        raise LaneAdjustmentError("Keep the shared right edge inside the image and at or beyond every well's right edge.")
    adjusted = []
    previous_bottom = 0
    for number, (well, lane) in enumerate(zip(originals, proposed), start=1):
        left, top, right, bottom = _bounds(lane, f"Lane {number}")
        if left != well.bounds[0]:
            raise LaneAdjustmentError(f"Lane {number}'s left edge must stay at its detected well's left edge.")
        if right != shared_right:
            raise LaneAdjustmentError("Every lane must use the same shared right edge.")
        if not (0 <= top < bottom <= height):
            raise LaneAdjustmentError(f"Lane {number} must be at least one pixel high and stay inside the image.")
        if adjusted and top < previous_bottom:
            raise LaneAdjustmentError("Keep lanes in top-to-bottom order without overlapping or crossing their neighbors.")
        bounds = (left, top, well.bounds[2], bottom)
        adjusted.append(Well(bounds, ((left + well.bounds[2]) / 2, (top + bottom) / 2)))
        previous_bottom = bottom
    return tuple(adjusted)


def crop_lanes(image: Image.Image, wells, right_edge) -> LaneCrop:
    """Copy one enclosing lane region and return translated overlay geometry.

    The crop includes the gaps between lanes, with a left margin of
    ``max(3, round(image.width * .01))`` and top/bottom margins of
    ``max(3, round(image.height * .01))`` pixels, clipped to the image edges.
    PNG encoding keeps grayscale/color values and 16-bit intensities exactly;
    big-endian 16-bit input is encoded with equivalent unsigned 16-bit values.
    The input image and the uploaded image model are never changed.
    """
    originals = _checked_wells(wells, _size(image.size))
    shared_right = _pixel(right_edge, "The shared right edge")
    proposed = tuple((well.bounds[0], well.bounds[1], shared_right, well.bounds[3]) for well in originals)
    accepted = validate_lane_adjustments(originals, proposed, shared_right, image.size)
    if image.mode not in {"1", "L", "LA", "P", "RGB", "RGBA", "I;16", "I;16L", "I;16B", "I"}:
        raise LaneAdjustmentError("This image's pixel format cannot be cropped into a lossless PNG preview.")
    margin = max(3, round(image.width * 0.01))
    vertical_margin = max(3, round(image.height * 0.01))
    left = max(0, min(well.bounds[0] for well in accepted) - margin)
    top = max(0, min(well.bounds[1] for well in accepted) - vertical_margin)
    bottom = min(image.height, max(well.bounds[3] for well in accepted) + vertical_margin)
    crop_box = (left, top, shared_right, bottom)
    copied = image.crop(crop_box)
    if copied.mode.startswith("I"):
        values = np.asarray(copied)
        if values.min() < 0 or values.max() > 65535:
            raise LaneAdjustmentError("The crop contains values outside the supported unsigned 16-bit range.")
        # PNG stores 16-bit samples, not an input array's byte order. Casting
        # endian representation preserves every numeric value and low bit.
        copied = Image.fromarray(values.astype(np.uint16))
    encoded = BytesIO()
    copied.save(encoded, format="PNG")
    translated = tuple(
        Well(
            (well.bounds[0] - left, well.bounds[1] - top, well.bounds[2] - left, well.bounds[3] - top),
            (well.center[0] - left, well.center[1] - top),
        )
        for well in accepted
    )
    lanes = tuple((well.bounds[0], well.bounds[1], copied.width, well.bounds[3]) for well in translated)
    return LaneCrop(encoded.getvalue(), crop_box, copied.width, copied.height, translated, lanes)
