"""Validate extracted-band outlines in native gel crop coordinates."""

import math

from .annotations import AnnotationError


def validate_extracted_bands(value: object, crop) -> list[dict]:
    """Return detached rectangles, each wholly contained in the current crop."""
    if not isinstance(value, list) or len(value) > 500:
        raise AnnotationError("Use at most 500 extracted-band rectangles.")
    rectangles = []
    for rectangle in value:
        if (not isinstance(rectangle, dict)
                or set(rectangle) != {"x", "y", "width", "height"}
                or any(type(number) not in (int, float)
                       or type(number) is float and not math.isfinite(number)
                       for number in rectangle.values())):
            raise AnnotationError("Each extracted-band rectangle needs valid coordinates and dimensions.")
        x, y, width, height = (rectangle[key] for key in ("x", "y", "width", "height"))
        if not (0 <= x < crop.width and 0 <= y < crop.height
                and 0 < width <= crop.width and 0 < height <= crop.height
                and x + width <= crop.width and y + height <= crop.height):
            raise AnnotationError("Keep extracted-band rectangles inside the gel image.")
        rectangles.append({"x": x, "y": y, "width": width, "height": height})
    return rectangles
