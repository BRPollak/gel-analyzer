"""Versioned, data-only project snapshots for the complete gel workflow.

JSON contains only explicitly supported records; loading never executes code
or follows paths/URLs. Validate an entire snapshot before replacing a session.
Editor identities and transient requests are deliberately regenerated.
"""

from base64 import b64decode, b64encode
from binascii import Error as Base64Error
from dataclasses import fields, is_dataclass
from hashlib import sha256
from io import BytesIO
import json
import math
import re
from types import SimpleNamespace
from uuid import uuid4
import warnings
import xml.etree.ElementTree as ET

from PIL import Image

from .annotation_exports import validate_svg_composition
from .annotations import validate_annotations
from .image_io import GelImage, GelOrientation
from .lane_crop import LaneCrop, validate_lane_adjustments
from .ladders import validate_ladder
from .orientation import rectangle_from_selection
from .wells import DetectionResult, Well


class ProjectError(ValueError):
    """A project cannot safely restore a consistent workflow."""


FORMAT = "gel-analyzer-project"
VERSION = 1
MAX_PROJECT_BYTES = 256_000_000
_RECORDS = {cls.__name__: cls for cls in (GelImage, GelOrientation, LaneCrop, Well, DetectionResult)}
_DEFAULTS = {
    "gel_image": None,
    "orientation_preview": None, "orientation_previous_gel": None,
    "orientation_preview_method": None, "orientation_manual": False,
    "orientation_selection": None,
    "well_points": (), "well_result": None, "well_editing": False,
    "well_expected_count": None,
    "lane_stage": None, "lane_wells": (), "lane_right": None, "lane_crop": None,
    "annotation_stage": "lanes", "annotation_data": None,
    "annotation_geometry": None, "annotation_completed": False,
    "annotation_png": None, "annotation_svg": None, "annotation_dimensions": None,
    "annotation_base_png": None, "annotation_base_svg": None,
    "annotation_base_dimensions": None,
    "ladder_data": None, "ladder_draft": None, "ladder_step": "preset",
    "band_data": None, "band_geometry": None,
}


def _encode(value):
    if isinstance(value, bytes):
        return {"$bytes": b64encode(value).decode("ascii")}
    if is_dataclass(value) and type(value).__name__ in _RECORDS:
        return {"$record": type(value).__name__, "fields": {
            field.name: _encode(getattr(value, field.name)) for field in fields(value)
        }}
    if isinstance(value, tuple):
        return {"$tuple": [_encode(item) for item in value]}
    if isinstance(value, list):
        return [_encode(item) for item in value]
    if isinstance(value, dict):
        return {key: _encode(item) for key, item in value.items()}
    if value is None or type(value) in (str, bool, int, float):
        return value
    raise ProjectError("The project contains an unsupported value.")


def _decode(value, depth=0):
    if depth > 30:
        raise ProjectError("The project is nested too deeply.")
    if isinstance(value, list):
        return [_decode(item, depth + 1) for item in value]
    if not isinstance(value, dict):
        return value
    if set(value) == {"$bytes"}:
        try:
            return b64decode(value["$bytes"], validate=True)
        except (Base64Error, ValueError, TypeError) as exc:
            raise ProjectError("The project contains damaged image data.") from exc
    if set(value) == {"$tuple"}:
        if not isinstance(value["$tuple"], list):
            raise ProjectError("The project contains invalid coordinates.")
        return tuple(_decode(item, depth + 1) for item in value["$tuple"])
    if "$record" in value:
        cls = _RECORDS.get(value.get("$record"))
        supplied = value.get("fields")
        if (set(value) != {"$record", "fields"} or cls is None
                or not isinstance(supplied, dict)
                or set(supplied) - {field.name for field in fields(cls)}):
            raise ProjectError("The project contains an unsupported record.")
        try:
            return cls(**{key: _decode(item, depth + 1) for key, item in supplied.items()})
        except TypeError as exc:
            raise ProjectError("The project is missing required image or geometry data.") from exc
    if any(key.startswith("$") for key in value):
        raise ProjectError("The project contains an unsupported value.")
    return {key: _decode(item, depth + 1) for key, item in value.items()}


def save_project(state) -> bytes:
    """Capture semantic state and exact confirmed exports, without widget events."""
    if state.get("gel_image") is None:
        raise ProjectError("Open a gel image before saving a project.")
    value = {"format": FORMAT, "version": VERSION,
             "state": _encode({key: state.get(key, default) for key, default in _DEFAULTS.items()})}
    try:
        encoded = json.dumps(value, ensure_ascii=False, separators=(",", ":"), allow_nan=False).encode("utf-8")
    except (TypeError, ValueError, RecursionError) as exc:
        raise ProjectError("The current project contains invalid data.") from exc
    if len(encoded) > MAX_PROJECT_BYTES:
        raise ProjectError("The project is too large to save (maximum 256 MB).")
    return encoded


def _size(value):
    if (not isinstance(value, (tuple, list)) or len(value) != 2
            or any(type(number) is not int or not 1 <= number <= 32767 for number in value)
            or value[0] * value[1] > 64_000_000):
        raise ProjectError("The project contains invalid image dimensions.")
    return tuple(value)


def _bounds(value, size):
    if (not isinstance(value, (tuple, list)) or len(value) != 4
            or any(type(number) is not int for number in value)):
        raise ProjectError("The project contains invalid image bounds.")
    left, top, right, bottom = value
    if not (0 <= left < right <= size[0] and 0 <= top < bottom <= size[1]):
        raise ProjectError("Project geometry falls outside its image.")
    return tuple(value)


def _image(data, size, image_format):
    if not isinstance(data, bytes) or not data:
        raise ProjectError("The project is missing image data.")
    with warnings.catch_warnings():
        warnings.simplefilter("error", Image.DecompressionBombWarning)
        with Image.open(BytesIO(data)) as image:
            if image.format != image_format or getattr(image, "n_frames", 1) != 1:
                raise ProjectError("The project's image format is invalid.")
            image.load()
            if image.size != tuple(size):
                raise ProjectError("The project's image dimensions do not match its geometry.")


def _orientation(value):
    if value not in ("wells_left", "wells_top"):
        raise ProjectError("The project has an unknown workflow orientation.")
    return value


def _gel(value):
    if not isinstance(value, GelImage):
        raise ProjectError("The project is missing its source gel.")
    size = _size((value.width, value.height))
    _orientation(value.workflow_orientation)
    if not isinstance(value.filename, str) or len(value.filename) > 1000:
        raise ProjectError("The project has an invalid source filename.")
    _bounds(value.crop_box, size)
    _image(value.source_bytes, size, "TIFF")
    if value.orientation is not None:
        geometry = value.orientation
        if not isinstance(geometry, GelOrientation):
            raise ProjectError("The project has invalid orientation geometry.")
        _size(geometry.size)
        if (type(geometry.counterclockwise_degrees) not in (int, float)
                or not math.isfinite(geometry.counterclockwise_degrees)
                or not isinstance(geometry.corners, tuple) or len(geometry.corners) != 4):
            raise ProjectError("The project has invalid orientation geometry.")
        if (type(geometry.outline_complete) is not bool
                or not isinstance(geometry.supported_edges, tuple)
                or any(edge not in ("left", "right", "top", "bottom") for edge in geometry.supported_edges)
                or len(set(geometry.supported_edges)) != len(geometry.supported_edges)):
            raise ProjectError("The project has invalid outline support metadata.")
        for point in geometry.corners:
            if (not isinstance(point, tuple) or len(point) != 2
                    or any(type(number) not in (int, float) or not math.isfinite(number) for number in point)):
                raise ProjectError("The project has invalid orientation geometry.")
    _image(value.preview_png, _size((value.preview_width, value.preview_height)), "PNG")
    return value


def _wells(values, size):
    if not isinstance(values, tuple) or len(values) > 10000:
        raise ProjectError("The project has invalid wells.")
    for well in values:
        if not isinstance(well, Well):
            raise ProjectError("The project has invalid well geometry.")
        left, top, right, bottom = _bounds(well.bounds, size)
        if well.center != ((left + right) / 2, (top + bottom) / 2):
            raise ProjectError("A well center does not match its bounds.")


def _lanes(wells, lanes, size, orientation):
    _wells(wells, size)
    if not isinstance(lanes, tuple) or len(lanes) != len(wells):
        raise ProjectError("The project must retain one lane for every well.")
    for lane in lanes:
        _bounds(lane, size)
    if wells:
        extent = lanes[0][3 if orientation == "wells_top" else 2]
        validate_lane_adjustments(wells, lanes, extent, size, workflow_orientation=orientation)


def _checked_svg(data, dimensions, crop):
    """Revalidate saved vectors and replace embedded data with the saved crop."""
    if data is None:
        return None
    if not isinstance(data, bytes) or len(data) > 100_000_000 or b"<!" in data:
        raise ProjectError("The project has invalid vector output.")
    root = ET.fromstring(data)
    images = list(root.iter("{http://www.w3.org/2000/svg}image"))
    if len(images) != 1:
        raise ProjectError("The project has invalid vector output.")
    image = images[0]
    image.attrib.pop("{http://www.w3.org/1999/xlink}href", None)
    event = {"width": dimensions[0], "height": dimensions[1],
             "gel_x": int(image.attrib["x"]), "gel_y": int(image.attrib["y"]),
             "svg": ET.tostring(root, encoding="unicode")}
    return validate_svg_composition(event, crop)


def _validate(state):
    gel = _gel(state["gel_image"])
    for key in ("orientation_preview", "orientation_previous_gel"):
        other = state[key]
        if other is not None:
            _gel(other)
            if (other.source_bytes != gel.source_bytes or other.crop_box != gel.crop_box
                    or key == "orientation_preview" and other.workflow_orientation != gel.workflow_orientation):
                raise ProjectError("The project's orientation previews do not share the same source.")
    previous = state["orientation_previous_gel"]
    if previous is not None and state["orientation_preview"] == previous:
        state["orientation_preview"] = previous
    analysis_source = previous or gel
    size = (analysis_source.preview_width, analysis_source.preview_height)
    orientation = analysis_source.workflow_orientation
    for key in ("orientation_manual", "well_editing", "annotation_completed"):
        if type(state[key]) is not bool:
            raise ProjectError("The project contains an invalid workflow state.")
    if state["orientation_preview_method"] not in (None, "manual", "automatic", "confirmed", "unchanged"):
        raise ProjectError("The project contains an unknown orientation step.")
    if state["orientation_selection"] is not None:
        rectangle_from_selection(state["orientation_selection"], (gel.preview_width, gel.preview_height))
    points = state["well_points"]
    if not isinstance(points, tuple) or len(points) > 2:
        raise ProjectError("The project has an invalid well guide.")
    for point in points:
        if (not isinstance(point, tuple) or len(point) != 2
                or any(type(number) not in (int, float) or not math.isfinite(number) for number in point)
                or not (0 <= point[0] <= size[0] and 0 <= point[1] <= size[1])):
            raise ProjectError("The project has an invalid well guide.")
    count = state["well_expected_count"]
    if count is not None and (type(count) is not int or count < 1):
        raise ProjectError("The project has an invalid expected well count.")
    result = state["well_result"]
    if result is not None:
        if not isinstance(result, DetectionResult):
            raise ProjectError("The project has an invalid detection result.")
        _lanes(result.wells, result.lanes, size, orientation)
        if not isinstance(result.warnings, tuple) or any(not isinstance(item, str) for item in result.warnings):
            raise ProjectError("The project has invalid detection notes.")
    if state["lane_stage"] not in (None, "borders", "extent", "cropped"):
        raise ProjectError("The project contains an unknown lane step.")
    _wells(state["lane_wells"], size)
    if state["lane_stage"] is not None:
        if analysis_source.orientation is None:
            raise ProjectError("The project's lanes require a confirmed orientation.")
        right = state["lane_right"]
        if type(right) is not int or not 1 <= right <= size[1 if orientation == "wells_top" else 0]:
            raise ProjectError("The project has an invalid lane migration extent.")
        lanes = tuple((well.bounds[0], well.bounds[1], well.bounds[2], right)
                      if orientation == "wells_top" else
                      (well.bounds[0], well.bounds[1], right, well.bounds[3])
                      for well in state["lane_wells"])
        _lanes(state["lane_wells"], lanes, size, orientation)
    crop = state["lane_crop"]
    if crop is not None:
        if not isinstance(crop, LaneCrop) or crop.workflow_orientation != orientation:
            raise ProjectError("The project's crop orientation does not match its gel.")
        crop_size = _size((crop.width, crop.height))
        left, top, right, bottom = _bounds(crop.crop_box, size)
        if crop_size != (right - left, bottom - top):
            raise ProjectError("The project's crop dimensions are inconsistent.")
        _image(crop.preview_png, crop_size, "PNG")
        _lanes(crop.wells, crop.lanes, crop_size, orientation)
        if len(crop.lanes) != len(state["lane_wells"]):
            raise ProjectError("The project's crop does not match its reviewed lanes.")
    if state["lane_stage"] == "cropped" and (crop is None or not crop.lanes):
        raise ProjectError("The project's cropped stage is missing its crop.")
    if state["annotation_stage"] not in ("lanes", "ladder_offer", "ladder", "final"):
        raise ProjectError("The project contains an unknown annotation step.")
    if state["ladder_step"] not in ("preset", "lane", "markers"):
        raise ProjectError("The project contains an unknown ladder step.")
    data = state["annotation_data"]
    if data is not None:
        state["annotation_data"] = validate_annotations(data, len(state["lane_wells"]))
    # Revision navigation retains marker drafts while hiding the final crop.
    annotation_crop = crop
    geometry = state["annotation_geometry"]
    if annotation_crop is None and geometry is not None:
        if not isinstance(geometry, tuple) or len(geometry) not in (4, 5):
            raise ProjectError("The project has invalid annotation geometry.")
        _, width, height, lanes, *_ = geometry
        _size((width, height))
        if not isinstance(lanes, tuple):
            raise ProjectError("The project has invalid annotation lanes.")
        for lane in lanes:
            _bounds(lane, (width, height))
        annotation_crop = SimpleNamespace(width=width, height=height, lanes=lanes)
    for key in ("ladder_data", "ladder_draft"):
        if state[key] is not None:
            if annotation_crop is None:
                raise ProjectError("The project's ladder is missing its crop geometry.")
            state[key] = validate_ladder(state[key], annotation_crop)
    bands = state["band_data"]
    if bands is not None:
        if annotation_crop is None or not isinstance(bands, list) or len(bands) != len(annotation_crop.lanes):
            raise ProjectError("The project's bands do not match its cropped lanes.")
        for lane, candidates in zip(annotation_crop.lanes, bands):
            if not isinstance(candidates, list) or len(candidates) > 10000:
                raise ProjectError("The project has invalid band candidates.")
            for band in candidates:
                if (not isinstance(band, dict) or set(band) != {"x", "y", "position", "signal"}
                        or any(type(band[key]) not in (int, float) or not math.isfinite(band[key]) for key in ("x", "y", "position"))
                        or band["signal"] is not None and (type(band["signal"]) not in (int, float) or not math.isfinite(band["signal"]))
                        or not (lane[0] <= band["x"] < lane[2] and lane[1] <= band["y"] < lane[3])
                        or band["position"] != band["y" if orientation == "wells_top" else "x"]):
                    raise ProjectError("The project has an invalid band position.")
        if crop is not None:
            state["band_geometry"] = (sha256(crop.preview_png).hexdigest(), tuple(crop.lanes), orientation)
        else:
            geometry = state["band_geometry"]
            if (not isinstance(geometry, tuple) or len(geometry) != 3
                    or not isinstance(geometry[0], str) or re.fullmatch("[0-9a-f]{64}", geometry[0]) is None
                    or geometry[1] != tuple(annotation_crop.lanes) or geometry[2] != orientation):
                raise ProjectError("The project's bands are missing their original crop geometry.")
    for prefix in ("annotation", "annotation_base"):
        png, dimensions = state[f"{prefix}_png"], state[f"{prefix}_dimensions"]
        if png is not None:
            dimensions = _size(dimensions)
            _image(png, dimensions, "PNG")
            if crop is None or dimensions[0] < crop.width or dimensions[1] < crop.height:
                raise ProjectError("The project's output is missing its complete gel crop.")
            state[f"{prefix}_svg"] = _checked_svg(state[f"{prefix}_svg"], dimensions, crop)
        elif dimensions is not None or state[f"{prefix}_svg"] is not None:
            raise ProjectError("The project's output is incomplete.")
    if state["annotation_stage"] != "lanes" and (crop is None or state["annotation_png"] is None or data is None):
        raise ProjectError("The project's annotation step is missing its confirmed image.")
    state["lane_source"] = analysis_source if state["lane_stage"] is not None else None
    # Reestablish geometry through the editor's shared normalization on render.
    if crop is not None:
        state["annotation_geometry"] = None


def load_project(data: bytes) -> dict:
    """Return a validated detached session snapshot; missing orientation is legacy."""
    if not isinstance(data, bytes) or not data or len(data) > MAX_PROJECT_BYTES:
        raise ProjectError("Choose a valid Gel Analyzer project no larger than 256 MB.")
    try:
        payload = json.loads(data, parse_constant=lambda value: (_ for _ in ()).throw(ValueError(value)))
        if (not isinstance(payload, dict) or payload.get("format") != FORMAT
                or type(payload.get("version")) is not int or payload["version"] != VERSION):
            raise ProjectError("This file is not a supported Gel Analyzer project (version 1).")
        values = _decode(payload.get("state"))
        if not isinstance(values, dict) or set(values) - set(_DEFAULTS):
            raise ProjectError("The project contains unsupported workflow fields.")
        state = {**_DEFAULTS, **values}
        _validate(state)
    except ProjectError:
        raise
    except (TypeError, ValueError, KeyError, AttributeError, IndexError, OSError, SyntaxError,
            OverflowError, RecursionError, Image.DecompressionBombError, Image.DecompressionBombWarning) as exc:
        raise ProjectError("The project is damaged or contains inconsistent image or annotation data.") from exc
    for editor in ("orientation", "well", "lane", "annotation"):
        state[f"{editor}_token"] = uuid4().hex
        state[f"{editor}_revision"] = 0
        state[f"{editor}_error"] = None
    state.update(orientation_requested=False, orientation_manual_error=None,
                 well_detection_request=None, pending_upload=None, upload_error=None,
                 ladder_notice=None, band_editor_generation=int(uuid4().hex[:8], 16))
    return state
