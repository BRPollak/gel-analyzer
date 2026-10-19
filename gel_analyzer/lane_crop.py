"""Validate manual lane bounds and copy their shared crop without resampling.

Inputs use displayed-image pixel-boundary coordinates. Adjustments keep each
well's depth and change its cross-lane bounds independently; every lane shares
one downstream edge. The crop adds 1% margins upstream and on both outer lane
sides (at least three pixels), clipped to the available source pixels.
"""

from dataclasses import dataclass, is_dataclass
from io import BytesIO
import math
from numbers import Integral, Real

import numpy as np
from PIL import Image

from .wells import Bounds, SelectionError, Well, validate_line
from .workflow_orientation import is_top, lane_bounds, orientation_text, swap_bounds, swap_point, swap_size


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
    workflow_orientation: str = "wells_left"


def _pixel(value, label: str) -> int:
    """Accept numeric integer values without coercing text or boolean events."""
    if isinstance(value, (bool, np.bool_)) or not isinstance(value, Real):
        raise LaneAdjustmentError(f"{label} could not be read. Adjust the selection and try again.")
    if isinstance(value, Integral):
        return int(value)
    try:
        if not math.isfinite(value) or value != math.floor(value):
            raise LaneAdjustmentError(f"{label} could not be read. Adjust the selection and try again.")
        return int(value)
    except (TypeError, OverflowError, ValueError) as exc:
        raise LaneAdjustmentError(f"{label} could not be read. Adjust the selection and try again.") from exc


def _sequence(value, label: str) -> tuple:
    if isinstance(value, (str, bytes, dict)):
        raise LaneAdjustmentError(f"{label} must contain the expected coordinate values.")
    try:
        return tuple(value)
    except TypeError as exc:
        raise LaneAdjustmentError(f"{label} must contain the expected coordinate values.") from exc


def _coordinate(value, label: str) -> int | float:
    """Keep subpixel geometry; raster sampling is rounded only at its boundary."""
    if isinstance(value, (bool, np.bool_)) or not isinstance(value, Real):
        raise LaneAdjustmentError(f"{label} could not be read. Adjust the selection and try again.")
    if isinstance(value, Integral):
        return int(value)
    if not math.isfinite(value):
        raise LaneAdjustmentError(f"{label} could not be read. Adjust the selection and try again.")
    return int(value) if value == math.floor(value) else float(value)


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
    return tuple(_coordinate(value, label) for value in values)


def _checked_wells(wells, size: tuple[int, int], *, allow_empty: bool = False) -> tuple[Well, ...]:
    originals = _sequence(wells, "Wells")
    if not originals and not allow_empty:
        raise LaneAdjustmentError("Add or detect at least one lane before adjusting or cropping lanes.")
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
            raise LaneAdjustmentError(f"Well {number} has invalid geometry. Review the lanes again.")
        left, top, right, bottom = _bounds(well.bounds, f"Well {number}")
        if not (0 <= left < right <= width and 0 <= top < bottom <= height):
            raise LaneAdjustmentError(f"Well {number} must have positive bounds inside the confirmed image.")
        checked.append(Well((left, top, right, bottom), ((left + right) / 2, (top + bottom) / 2)))
    return tuple(checked)


def validate_lane_adjustments(
    original_wells, lanes, right_edge, size: tuple[int, int], *, workflow_orientation="wells_left",
) -> tuple[Well, ...]:
    """Return wells with accepted cross-lane bounds, or explain invalid edits.

    Lane input is one ``(left, top, right, bottom)`` rectangle per original
    well, in the original top-to-bottom order. Left edges are fixed; every
    right bound must equal ``right_edge``. Bounds are finite image
    boundaries and may touch, but lanes must be at least one pixel wide along
    the cross-lane axis and may not overlap or cross. Invalid
    geometry is rejected, never silently rounded, reordered, or clamped.
    In wells-at-top mode the same rules use left-to-right order, fixed top
    edges and a shared bottom extent (the legacy ``right_edge`` argument).
    """
    width, height = _size(size)
    originals = _checked_wells(original_wells, (width, height))
    proposed = _sequence(lanes, "Lanes")
    if is_top(workflow_orientation):
        try:
            transformed = validate_lane_adjustments(
                tuple(Well(swap_bounds(well.bounds), swap_point(well.center)) for well in originals),
                tuple(swap_bounds(_bounds(lane, f"Lane {number}")) for number, lane in enumerate(proposed, 1)),
                right_edge, swap_size((width, height)),
            )
        except LaneAdjustmentError as exc:
            raise LaneAdjustmentError(orientation_text(str(exc), workflow_orientation)) from exc
        return tuple(Well(swap_bounds(well.bounds), swap_point(well.center)) for well in transformed)
    if len(proposed) != len(originals):
        raise LaneAdjustmentError("Keep exactly one lane for each reviewed well.")
    shared_right = _pixel(right_edge, "The shared right edge")
    if not max(well.bounds[2] for well in originals) <= shared_right <= width:
        raise LaneAdjustmentError("Keep the shared right edge inside the image and at or beyond every well's right edge.")
    adjusted = []
    previous_bottom = 0
    for number, (well, lane) in enumerate(zip(originals, proposed), start=1):
        left, top, right, bottom = _bounds(lane, f"Lane {number}")
        if left != well.bounds[0]:
            raise LaneAdjustmentError(f"Lane {number}'s left edge must stay at its reviewed well's left edge.")
        if right != shared_right:
            raise LaneAdjustmentError("Every lane must use the same shared right edge.")
        lane_height = bottom - top
        if (not (0 <= top < bottom <= height)
                or (lane_height < 1 and not math.isclose(lane_height, 1, rel_tol=0, abs_tol=1e-10))):
            raise LaneAdjustmentError(f"Lane {number} is too narrow or extends outside the image. Adjust its edges to enclose a lane inside the image.")
        if adjusted and top < previous_bottom and not math.isclose(top, previous_bottom, rel_tol=0, abs_tol=1e-10):
            raise LaneAdjustmentError("Keep lanes in top-to-bottom order without overlapping or crossing their neighbors.")
        bounds = (left, top, well.bounds[2], bottom)
        adjusted.append(Well(bounds, ((left + well.bounds[2]) / 2, (top + bottom) / 2)))
        previous_bottom = bottom
    return tuple(adjusted)


def seed_boundary_well(wells, points, right_edge, size, *, workflow_orientation="wells_left") -> Well:
    """Reuse the first reviewed well, or place a manual seed at the guide start."""
    dimensions = _size(size)
    originals = _checked_wells(wells, dimensions, allow_empty=True)
    top_mode = is_top(workflow_orientation)
    if originals:
        first = min(originals, key=lambda well: well.center[0 if top_mode else 1])
        return validate_lane_adjustments(
            (first,), (lane_bounds(first.bounds, right_edge, workflow_orientation),),
            right_edge, dimensions, workflow_orientation=workflow_orientation,
        )[0]
    try:
        ordered = validate_line(points, dimensions, workflow_orientation=workflow_orientation)
    except SelectionError as exc:
        raise LaneAdjustmentError(str(exc)) from exc
    # append_lane supplies the same conservative dimensions as ordinary manual
    # recovery. Translate its seed to the first guide endpoint, in displayed XY.
    seed = append_lane((), ordered, right_edge, dimensions, workflow_orientation=workflow_orientation)[0]
    width, height = seed.bounds[2] - seed.bounds[0], seed.bounds[3] - seed.bounds[1]
    maximum_x = dimensions[0] if top_mode else right_edge
    maximum_y = right_edge if top_mode else dimensions[1]
    left = min(max(0, round(ordered[0][0] - width / 2)), maximum_x - width)
    top = min(max(0, round(ordered[0][1] - height / 2)), maximum_y - height)
    return Well((left, top, left + width, top + height), (left + width / 2, top + height / 2))


def validate_boundary_adjustments(
    original_wells, lanes, right_edge, size, stage, *, workflow_orientation="wells_left",
) -> tuple[Well, ...]:
    """Apply existing lane edits, keeping the confirmed first boundary fixed.

    The last boundary may be moved across the first while editing; generation
    separately checks their order. Its width is linked to the first boundary.
    """
    expected = {"boundary_first": 1, "boundary_last": 2}.get(stage)
    if expected is None:
        raise LaneAdjustmentError("Choose the first or last boundary well to adjust.")
    originals = _checked_wells(original_wells, _size(size))
    proposed = _sequence(lanes, "Boundary wells")
    if len(originals) != expected or len(proposed) != expected:
        raise LaneAdjustmentError(f"Keep exactly {expected} boundary well{'s' if expected == 2 else ''} in this step.")
    adjusted = tuple(
        validate_lane_adjustments((well,), (lane,), right_edge, size,
                                  workflow_orientation=workflow_orientation)[0]
        for well, lane in zip(originals, proposed)
    )
    if stage == "boundary_last":
        if adjusted[0] != originals[0]:
            raise LaneAdjustmentError("The first well is fixed. Use Back to revise it.")
        _matching_boundary_geometry(*adjusted, workflow_orientation)
    return adjusted


def _matching_boundary_geometry(first, last, workflow_orientation):
    a, b = first.bounds, last.bounds
    if is_top(workflow_orientation):
        a, b = swap_bounds(a), swap_bounds(b)
    if a[0] != b[0] or a[2] != b[2]:
        raise LaneAdjustmentError("Keep both boundary wells at the same upstream position and depth.")
    if not math.isclose(a[3] - a[1], b[3] - b[1], rel_tol=0, abs_tol=1e-10):
        raise LaneAdjustmentError("Keep the last well's width linked to the first well.")


def generate_boundary_lanes(
    first, last, count, right_edge, size, *, workflow_orientation="wells_left",
) -> tuple[Well, ...]:
    """Interpolate N total lanes, preserving both confirmed bounds exactly."""
    if isinstance(count, (bool, np.bool_)) or not isinstance(count, Integral) or count < 2:
        raise LaneAdjustmentError("Enter a whole-number total lane count of at least 2, including both boundary wells.")
    endpoints = _checked_wells((first, last), _size(size))
    first, last = validate_boundary_adjustments(
        endpoints, tuple(lane_bounds(well.bounds, right_edge, workflow_orientation) for well in endpoints),
        right_edge, size, "boundary_last", workflow_orientation=workflow_orientation,
    )
    axis = 0 if is_top(workflow_orientation) else 1
    distance = last.center[axis] - first.center[axis]
    if distance <= 0:
        side = "right of" if axis == 0 else "below"
        raise LaneAdjustmentError(f"Place the last well {side} the first well, at a distinct position.")
    lane_width = first.bounds[axis + 2] - first.bounds[axis]
    # Compare before division by the count (or allocating interiors), including
    # Python integers too large to convert into a floating-point denominator.
    if count - 1 > distance / lane_width + 1e-10:
        raise LaneAdjustmentError("The lanes would overlap. Reduce the first well's width or move the boundaries farther apart.")
    spacing = distance / (count - 1)
    if spacing < lane_width and not math.isclose(spacing, lane_width, rel_tol=0, abs_tol=1e-10):
        raise LaneAdjustmentError("The lanes would overlap. Reduce the first well's width or move the boundaries farther apart.")
    interiors = []
    for index in range(1, count - 1):
        fraction = index / (count - 1)
        bounds = tuple(start + (end - start) * fraction for start, end in zip(first.bounds, last.bounds))
        interiors.append(Well(bounds, ((bounds[0] + bounds[2]) / 2, (bounds[1] + bounds[3]) / 2)))
    return (first, *interiors, last)


def append_lane(wells, points, right_edge, size: tuple[int, int], *, workflow_orientation="wells_left") -> tuple[Well, ...]:
    """Append an editable lane at the guide's bottom, fitting available rows.

    Existing lanes supply the median height, width, and gap. With no lanes,
    conservative image/guide-scaled dimensions seed manual recovery. Prefer a
    center at the lower endpoint; continue below the final lane when needed.
    A smaller new rectangle uses any remaining space without moving existing
    lanes. With less than one row left, reserve one by trimming the last lane, moving
    a contiguous one-pixel tail upward only if needed. Every lane stays at
    least one pixel high, ordered, and inside the image.
    """
    width, height = _size(size)
    originals = _checked_wells(wells, (width, height), allow_empty=True)
    if is_top(workflow_orientation):
        try:
            ordered = validate_line(points, (width, height), workflow_orientation=workflow_orientation)
            transformed = append_lane(
                tuple(Well(swap_bounds(well.bounds), swap_point(well.center)) for well in originals),
                tuple(swap_point(point) for point in ordered), right_edge, swap_size((width, height)),
            )
        except SelectionError as exc:
            raise LaneAdjustmentError(str(exc)) from exc
        except LaneAdjustmentError as exc:
            raise LaneAdjustmentError(orientation_text(str(exc), workflow_orientation)) from exc
        return tuple(Well(swap_bounds(well.bounds), swap_point(well.center)) for well in transformed)
    try:
        upper, lower = validate_line(points, (width, height))
    except SelectionError as exc:
        raise LaneAdjustmentError(str(exc)) from exc
    shared_right = _pixel(right_edge, "The shared right edge")
    minimum_right = max((well.bounds[2] for well in originals), default=1)
    if not minimum_right <= shared_right <= width:
        raise LaneAdjustmentError("Keep the shared right edge inside the image and at or beyond every well's right edge.")
    if originals:
        # Reuse adjustment validation so invalid order/overlap never becomes
        # accepted simply because the next action is adding a lane.
        lanes = tuple((well.bounds[0], well.bounds[1], shared_right, well.bounds[3]) for well in originals)
        originals = validate_lane_adjustments(originals, lanes, shared_right, (width, height))
        lane_height = max(1, int(round(float(np.median([well.bounds[3] - well.bounds[1] for well in originals])))))
        lane_width = max(1, int(round(float(np.median([well.bounds[2] - well.bounds[0] for well in originals])))))
        gaps = [following.bounds[1] - previous.bounds[3] for previous, following in zip(originals, originals[1:])]
        gap = max(1, int(round(float(np.median(gaps))))) if gaps else max(1, round(lane_height / 4))
        previous_bottom = originals[-1].bounds[3]
    else:
        lane_height = min(height, max(4, round(min(height * 0.035, (lower[1] - upper[1]) * 0.12))))
        lane_width = max(4, round(min(width, height) * 0.025))
        gap, previous_bottom = 0, 0
    if height - previous_bottom < 1:
        if len(originals) >= height:
            raise LaneAdjustmentError("There is no room for another lane. Delete a lane before adding another.")
        # Reserve one bottom row with the smallest possible boundary change.
        # A one-pixel lane cannot shrink, so move that trailing lane upward
        # until a gap or a taller lane supplies the required row.
        adjusted = list(originals)
        ceiling = height - 1
        for index in range(len(adjusted) - 1, -1, -1):
            left, top, right, bottom = adjusted[index].bounds
            if bottom <= ceiling:
                break
            bottom = ceiling
            top = min(top, bottom - 1)
            adjusted[index] = Well((left, top, right, bottom), ((left + right) / 2, (top + bottom) / 2))
            ceiling = top
        originals = tuple(adjusted)
        previous_bottom = originals[-1].bounds[3]
    lane_height = min(lane_height, height - previous_bottom)

    top = int(round(lower[1] - lane_height / 2))
    if originals and top < previous_bottom:
        top = previous_bottom + gap
    top = min(max(previous_bottom, top, 0), height - lane_height)
    bottom = top + lane_height
    center_y = (top + bottom) / 2
    center_x = upper[0] + (center_y - upper[1]) * (lower[0] - upper[0]) / (lower[1] - upper[1])
    lane_width = min(lane_width, shared_right)
    left = min(max(0, int(round(center_x - lane_width / 2))), shared_right - lane_width)
    right = left + lane_width
    new_well = Well((left, top, right, bottom), ((left + right) / 2, center_y))
    result = (*originals, new_well)
    return validate_lane_adjustments(
        result, tuple(lane_bounds(well.bounds, shared_right) for well in result), shared_right, (width, height),
    )


def crop_lanes(image: Image.Image, wells, right_edge, *, workflow_orientation="wells_left") -> LaneCrop:
    """Copy one enclosing lane region and return translated overlay geometry.

    The crop includes the gaps between lanes, with a left margin of
    ``max(3, round(image.width * .01))`` and top/bottom margins of
    ``max(3, round(image.height * .01))`` pixels, clipped to the image edges.
    PNG encoding keeps grayscale/color values and 16-bit intensities exactly;
    big-endian 16-bit input is encoded with equivalent unsigned 16-bit values.
    The input image and the uploaded image model are never changed.
    Wells-at-top mode adds the upstream margin above and cross-lane margins
    left/right, then crops directly from the displayed image without rotation.
    """
    originals = _checked_wells(wells, _size(image.size))
    shared_right = _pixel(right_edge, "The shared right edge")
    proposed = tuple(lane_bounds(well.bounds, shared_right, workflow_orientation) for well in originals)
    accepted = validate_lane_adjustments(originals, proposed, shared_right, image.size,
                                         workflow_orientation=workflow_orientation)
    if image.mode not in {"1", "L", "LA", "P", "RGB", "RGBA", "I;16", "I;16L", "I;16B", "I"}:
        raise LaneAdjustmentError("This image format cannot be cropped here. Open a standard PNG or JPEG copy.")
    margin = max(3, round(image.width * 0.01))
    vertical_margin = max(3, round(image.height * 0.01))
    left = max(0, math.floor(min(well.bounds[0] for well in accepted) - margin))
    top = max(0, math.floor(min(well.bounds[1] for well in accepted) - vertical_margin))
    bottom = min(image.height, math.ceil(max(well.bounds[3] for well in accepted) + vertical_margin))
    if is_top(workflow_orientation):
        right = min(image.width, math.ceil(max(well.bounds[2] for well in accepted) + margin))
        crop_box = (left, top, right, shared_right)
    else:
        crop_box = (left, top, shared_right, bottom)
    copied = image.crop(crop_box)
    if copied.mode.startswith("I"):
        values = np.asarray(copied)
        if values.min() < 0 or values.max() > 65535:
            raise LaneAdjustmentError("This image cannot be cropped here. Open a standard PNG or JPEG copy.")
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
    extent = copied.height if is_top(workflow_orientation) else copied.width
    lanes = tuple(lane_bounds(well.bounds, extent, workflow_orientation) for well in translated)
    return LaneCrop(encoded.getvalue(), crop_box, copied.width, copied.height, translated, lanes,
                    workflow_orientation)
