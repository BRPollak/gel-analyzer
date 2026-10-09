"""Validate session annotations and the browser's clean, composed PNG.

The browser uses the same Arial canvas renderer for preview and confirmation.
The source crop remains lossless; the composition is a separate display PNG.
"""

from base64 import b64decode
from binascii import Error as Base64Error
from io import BytesIO
import math
import re

from PIL import Image, UnidentifiedImageError


class AnnotationError(ValueError):
    """An annotation edit or composed image is invalid."""


def default_label(number: int) -> dict:
    return {"text": f"Lane {number}", "bold": False, "italic": False, "color": "#202020"}


def default_font_size(lanes) -> int:
    """Start labels at 80% of mean lane height, in native crop pixels."""
    heights = [lane[3] - lane[1] for lane in lanes if lane[3] > lane[1]]
    if not heights:
        return 18
    return max(1, min(4096, math.floor(0.8 * sum(heights) / len(heights) + 0.5)))


def default_annotations(count: int, lanes=()) -> dict:
    return {
        "labels": [default_label(i + 1) for i in range(count)], "groups": [],
        "fontSize": default_font_size(lanes),
    }


def _style(value: object, text_key: str) -> dict:
    if not isinstance(value, dict):
        raise AnnotationError("Each label must include text and formatting.")
    text = value.get(text_key)
    if (
        not isinstance(text, str) or len(text) > 500
        or any(ord(char) < 32 or ord(char) == 127 for char in text)
    ):
        raise AnnotationError("Use a single line of up to 500 characters for each label.")
    if any(type(value.get(key)) is not bool for key in ("bold", "italic")):
        raise AnnotationError("Bold and italic must be independent on/off values.")
    color = value.get("color")
    if not isinstance(color, str) or re.fullmatch(r"#[0-9a-fA-F]{6}", color) is None:
        raise AnnotationError("Choose a valid text color.")
    return {text_key: text, "bold": value["bold"], "italic": value["italic"], "color": color}


def validate_annotations(value: object, count: int) -> dict:
    """Return a detached, normalized snapshot with valid lane membership."""
    if not isinstance(value, dict):
        raise AnnotationError("Review the lane annotations and try again.")
    labels, groups, size = value.get("labels"), value.get("groups"), value.get("fontSize")
    if not isinstance(labels, list) or len(labels) != count:
        raise AnnotationError("Keep one label for each cropped lane.")
    if type(size) is not int or not 1 <= size <= 4096:
        raise AnnotationError("Choose a font size from 1 to 4096 pixels.")
    if not isinstance(groups, list) or len(groups) > 100:
        raise AnnotationError("Use at most 100 groups across the two sets.")
    checked_groups = []
    identifiers = set()
    for group in groups:
        style = _style(group, "label")
        identifier, column, members = group.get("id"), group.get("set"), group.get("lanes")
        if (
            not isinstance(identifier, str)
            or re.fullmatch(r"[a-zA-Z0-9_-]{1,80}", identifier) is None
            or identifier in identifiers
        ):
            raise AnnotationError("Each group must have a unique identifier.")
        if type(column) is not int or column not in (0, 1):
            raise AnnotationError("Choose group set 1 or 2.")
        if (
            not isinstance(members, list) or not members
            or any(type(index) is not int or not 0 <= index < count for index in members)
            or len(set(members)) != len(members)
        ):
            raise AnnotationError("Select at least one current lane for every group.")
        identifiers.add(identifier)
        checked_groups.append({"id": identifier, "set": column, "lanes": sorted(members), **style})
    return {"labels": [_style(label, "text") for label in labels], "groups": checked_groups, "fontSize": size}


def validate_composition(event: dict, crop) -> bytes:
    """Decode only a bounded PNG that encloses the crop at its native size."""
    width, height = event.get("width"), event.get("height")
    x, y = event.get("gel_x"), event.get("gel_y")
    if (
        any(type(value) is not int for value in (width, height, x, y))
        or not 1 <= width <= 32767 or not 1 <= height <= 32767
        or width * height > 64_000_000 or x < 0 or y < 0
        or x + crop.width > width or y + crop.height > height
    ):
        raise AnnotationError("The composed image must contain the full crop at its original size.")
    encoded = event.get("png")
    prefix = "data:image/png;base64,"
    if (
        not isinstance(encoded, str) or not encoded.startswith(prefix)
        or len(encoded) > 100_000_000 or not encoded.isascii()
    ):
        raise AnnotationError("The browser could not create the annotated PNG. Try confirming again.")
    try:
        png = b64decode(encoded[len(prefix):], validate=True)
        with Image.open(BytesIO(png)) as image:
            if image.format != "PNG" or image.size != (width, height) or image.mode not in ("RGB", "RGBA"):
                raise AnnotationError("The annotated PNG does not match its preview dimensions.")
            image.verify()
    except (Base64Error, UnidentifiedImageError, OSError, SyntaxError, Image.DecompressionBombError) as exc:
        raise AnnotationError("The annotated PNG could not be read. Try confirming again.") from exc
    return png
