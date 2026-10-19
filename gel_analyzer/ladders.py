"""Load ladder presets and validate crop-relative preset and manual markers.

Preset snapshots travel with annotations so editing the configuration cannot
change the labels in an existing session. Coordinates are native crop pixels;
they are never snapped, rounded, or scaled to the displayed image.
"""

import json
import math
from pathlib import Path
import re

from .annotations import AnnotationError


class LadderError(AnnotationError):
    """A ladder preset or manual marker placement is invalid."""


PRESETS_PATH = Path(__file__).with_name("ladder_presets.json")


def _text(value: object, description: str, limit: int) -> str:
    if (
        not isinstance(value, str) or not value.strip() or len(value) > limit
        or any(ord(char) < 32 or ord(char) == 127 or char in "\u2028\u2029" for char in value)
    ):
        raise LadderError(f"{description} must be a nonempty single line of up to {limit} characters.")
    return value


def _preset(value: object) -> dict:
    if not isinstance(value, dict):
        raise LadderError("Each ladder preset must contain an id, name, and labels.")
    identifier = value.get("id")
    if not isinstance(identifier, str) or re.fullmatch(r"[a-zA-Z0-9_-]{1,80}", identifier) is None:
        raise LadderError("Each ladder preset needs an id of 1–80 letters, numbers, hyphens, or underscores.")
    name = _text(value.get("name"), "The ladder preset name", 200)
    labels = value.get("labels")
    if not isinstance(labels, list) or not 1 <= len(labels) <= 200:
        raise LadderError("Each ladder preset must contain between 1 and 200 size labels.")
    checked_labels = [_text(label, "Each ladder size label", 200) for label in labels]
    if len({label.strip() for label in checked_labels}) != len(checked_labels):
        raise LadderError("Size labels within a ladder preset must be unique.")
    checked = {"id": identifier, "name": name, "labels": checked_labels}
    if "referenceImage" in value:
        reference_image = value["referenceImage"]
        if (
            not isinstance(reference_image, str)
            or re.fullmatch(
                r"ladder_references/[a-zA-Z0-9_-]{1,80}\.(?:webp|gif|png|jpe?g)", reference_image,
            ) is None
        ):
            raise LadderError("The ladder reference image must be a local image in ladder_references/.")
        checked["referenceImage"] = reference_image
    if "referenceNote" in value:
        checked["referenceNote"] = _text(value["referenceNote"], "The ladder reference note", 500)
    return checked


def load_presets(path: str | Path | None = None) -> list[dict]:
    """Read a fresh preset configuration, or report why none can be offered."""
    location = PRESETS_PATH if path is None else Path(path)
    try:
        value = json.loads(location.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise LadderError(
            "No usable ladder presets are configured. Check ladder_presets.json and reload the app. "
            "Choose Manual ladder or skip ladder annotations."
        ) from exc
    try:
        if not isinstance(value, list) or not 1 <= len(value) <= 100:
            raise LadderError("Configure between 1 and 100 ladder presets.")
        presets = [_preset(preset) for preset in value]
        if len({preset["id"] for preset in presets}) != len(presets):
            raise LadderError("Ladder preset ids must be unique.")
        return presets
    except LadderError as exc:
        raise LadderError(
            f"No usable ladder presets are configured. {exc} Choose Manual ladder or skip ladder annotations."
        ) from exc


def _coordinate(value: object) -> float:
    if type(value) not in (int, float):
        raise LadderError("Marker positions must be finite image coordinates.")
    try:
        coordinate = float(value)
    except (ValueError, OverflowError) as exc:
        raise LadderError("Marker positions must be finite image coordinates.") from exc
    if not math.isfinite(coordinate):
        raise LadderError("Marker positions must be finite image coordinates.")
    return coordinate


def _manual_ladder(value: dict, crop, *, complete: bool) -> dict:
    placements = value.get("placements", [])
    if not isinstance(placements, list) or len(placements) > 200:
        raise LadderError("Manual ladder annotations must contain a list of up to 200 markers.")
    if complete and not placements:
        raise LadderError("Place at least one ladder marker before confirming.")
    checked = []
    identifiers = set()
    for placement in placements:
        if not isinstance(placement, dict):
            raise LadderError("Each manual ladder marker needs an id, label, and image coordinates.")
        identifier = placement.get("id")
        if (
            not isinstance(identifier, str)
            or re.fullmatch(r"[a-zA-Z0-9_-]{1,80}", identifier) is None
            or identifier in identifiers
        ):
            raise LadderError(
                "Each manual ladder marker needs a unique id of 1–80 letters, numbers, hyphens, or underscores."
            )
        label = _text(placement.get("label"), "Each manual ladder label", 200)
        x, y = _coordinate(placement.get("x")), _coordinate(placement.get("y"))
        if not (0 <= x < crop.width and 0 <= y < crop.height):
            raise LadderError("Click a ladder band inside the gel image.")
        identifiers.add(identifier)
        checked.append({"id": identifier, "label": label, "x": x, "y": y})
    return {"mode": "manual", "placements": checked}


def validate_ladder(value: object, crop, *, complete: bool = False) -> dict | None:
    """Return a detached snapshot with markers at native image coordinates.

    ``None`` and unselected preset/lane fields are allowed in working drafts.
    Preset markers belong to their selected lane; manual labels can be anywhere
    in the crop. Complete snapshots require at least one placement. Image and
    lane membership use half-open bounds, matching crop and lane geometry.
    """
    if value is None:
        if complete:
            raise LadderError("Place at least one ladder marker before confirming.")
        return None
    if not isinstance(value, dict):
        raise LadderError("Review the ladder annotations and try again.")

    mode = value.get("mode", "preset")
    if mode == "manual":
        return _manual_ladder(value, crop, complete=complete)
    if mode != "preset":
        raise LadderError("Choose a ladder preset or Manual ladder.")

    preset_value = value.get("preset")
    preset = _preset(preset_value) if preset_value is not None else None
    lane_index = value.get("laneIndex")
    placements = value.get("placements", [])
    if not isinstance(placements, list):
        raise LadderError("Ladder placements must be a list of selected size markers.")
    if lane_index is not None and (type(lane_index) is not int or not 0 <= lane_index < len(crop.lanes)):
        raise LadderError("Choose one of the current ladder lanes.")
    if preset is None and (lane_index is not None or placements):
        raise LadderError("Choose a ladder preset before selecting its lane or placing markers.")
    if placements and lane_index is None:
        raise LadderError("Choose the ladder lane before placing markers.")
    if complete and (preset is None or lane_index is None or not placements):
        raise LadderError("Choose a preset and lane, then place at least one ladder marker before confirming.")
    if preset is not None and len(placements) > len(preset["labels"]):
        raise LadderError("Place each ladder size marker at most once.")

    checked = []
    marker_indices = set()
    for placement in placements:
        if not isinstance(placement, dict):
            raise LadderError("Each ladder marker needs a size label and image coordinates.")
        marker_index = placement.get("markerIndex")
        if (
            type(marker_index) is not int or not 0 <= marker_index < len(preset["labels"])
            or marker_index in marker_indices
        ):
            raise LadderError("Choose each ladder size marker at most once from the selected preset.")
        x, y = _coordinate(placement.get("x")), _coordinate(placement.get("y"))
        left, top, right, bottom = crop.lanes[lane_index]
        if not (0 <= x < crop.width and 0 <= y < crop.height and left <= x < right and top <= y < bottom):
            raise LadderError("Click inside the highlighted ladder lane.")
        marker_indices.add(marker_index)
        checked.append({"markerIndex": marker_index, "x": x, "y": y})

    return {"preset": preset, "laneIndex": lane_index, "placements": checked}
