"""Download display compositions without resampling the scientific image."""

from base64 import b64encode
from io import BytesIO
import math
import re
import xml.etree.ElementTree as ET

from PIL import Image

from .annotations import AnnotationError


EXPORT_FORMATS = {
    "PNG": {"extension": "png", "mime": "image/png", "dpi": (72, 96, 150, 300, 600)},
    "JPEG": {"extension": "jpg", "mime": "image/jpeg", "dpi": (72, 96, 150, 300, 600)},
    "TIFF": {"extension": "tiff", "mime": "image/tiff", "dpi": (150, 300, 600, 1200)},
    "SVG": {"extension": "svg", "mime": "image/svg+xml", "dpi": ()},
}

_SVG = "http://www.w3.org/2000/svg"
_XLINK = "http://www.w3.org/1999/xlink"
_XML_SPACE = "{http://www.w3.org/XML/1998/namespace}space"
ET.register_namespace("", _SVG)
ET.register_namespace("xlink", _XLINK)
_NUMBER = r"-?(?:\d+(?:\.\d*)?|\.\d+)(?:e[+-]?\d+)?"
_PATH = re.compile(rf"(?:[ML]\s+{_NUMBER}\s+{_NUMBER}\s*)+")
_TRANSFORM = re.compile(rf"translate\(({_NUMBER})\s+({_NUMBER})\) rotate\((-90|0|45|90)\)")
_ATTRIBUTES = {
    "svg": {"width", "height", "viewBox"},
    "rect": {"x", "y", "width", "height", "fill"},
    "image": {"x", "y", "width", "height"},
    "path": {"d", "fill", "stroke", "stroke-width", "stroke-linecap"},
    "text": {"x", "y", "font-family", "font-size", "font-weight", "font-style",
             "fill", "text-anchor", "transform", _XML_SPACE},
}
_NUMERIC = {"x", "y", "width", "height", "font-size", "stroke-width"}


def _valid_number(value: str) -> bool:
    return (re.fullmatch(_NUMBER, value) is not None
            and math.isfinite(float(value)) and abs(float(value)) <= 1_000_000)


def validate_svg_composition(event: dict, crop) -> bytes | None:
    """Allow only the inert vector elements our renderer produces.

    Browser markup contains no image URL. Embed the current crop here so SVG
    downloads cannot refer to remote resources or substitute a different gel.
    Older component snapshots without SVG remain usable.
    """
    svg = event.get("svg")
    if svg is None:
        return None
    error = "The vector image could not be read. Try confirming the annotations again."
    if not isinstance(svg, str) or len(svg) > 5_000_000 or "<!" in svg or "<?" in svg:
        raise AnnotationError(error)
    try:
        root = ET.fromstring(svg)
    except (ET.ParseError, ValueError) as exc:
        raise AnnotationError(error) from exc
    width, height = event["width"], event["height"]
    if (root.tag != f"{{{_SVG}}}svg"
            or root.attrib != {"width": str(width), "height": str(height),
                               "viewBox": f"0 0 {width} {height}"}):
        raise AnnotationError(error)
    images = []
    elements = list(root.iter())
    if len(elements) > 100_000:
        raise AnnotationError(error)
    for element in elements:
        tag = element.tag.removeprefix(f"{{{_SVG}}}")
        if (element.tag != f"{{{_SVG}}}{tag}" or tag not in _ATTRIBUTES
                or set(element.attrib) - _ATTRIBUTES[tag]
                or element is not root and (tag == "svg" or len(element))):
            raise AnnotationError(error)
        if (element.tail and element.tail.strip()) or (tag != "text" and element.text and element.text.strip()):
            raise AnnotationError(error)
        if tag == "text" and len(element.text or "") > 500:
            raise AnnotationError(error)
        for name, value in element.attrib.items():
            valid = True
            if name in _NUMERIC:
                valid = _valid_number(value)
            elif name in ("fill", "stroke"):
                valid = value == "none" or re.fullmatch(r"#[\da-fA-F]{6}", value) is not None
            elif name == "d":
                valid = (_PATH.fullmatch(value) is not None
                         and all(_valid_number(number) for number in re.findall(_NUMBER, value)))
            elif name == "transform":
                match = _TRANSFORM.fullmatch(value)
                valid = match is not None and all(_valid_number(number) for number in match.groups())
            elif name == "font-family":
                valid = value == "Arial"
            elif name == "font-weight":
                valid = value in ("bold", "normal")
            elif name == "font-style":
                valid = value in ("italic", "normal")
            elif name == "text-anchor":
                valid = value in ("start", "end")
            elif name == "stroke-linecap":
                valid = value == "butt"
            elif name == _XML_SPACE:
                valid = value == "preserve"
            if not valid:
                raise AnnotationError(error)
        if tag == "image":
            images.append(element)
    if len(images) != 1 or images[0].attrib != {
        "x": str(event["gel_x"]), "y": str(event["gel_y"]),
        "width": str(crop.width), "height": str(crop.height),
    }:
        raise AnnotationError(error)
    images[0].set(f"{{{_XLINK}}}href", "data:image/png;base64," + b64encode(crop.preview_png).decode("ascii"))
    return ET.tostring(root, encoding="utf-8", xml_declaration=True)


def export_composition(png: bytes, image_format: str, dpi: int | None = None,
                       *, svg: bytes | None = None) -> bytes:
    """Set real print-resolution metadata while retaining native pixel counts."""
    specification = EXPORT_FORMATS.get(image_format)
    if specification is None or image_format != "SVG" and dpi not in specification["dpi"]:
        raise AnnotationError("Choose an available image format and resolution.")
    if image_format == "SVG":
        if svg is not None:
            return svg
        # Compatibility for a confirmed snapshot from an older open editor.
        with Image.open(BytesIO(png)) as image:
            width, height = image.size
        root = ET.Element(f"{{{_SVG}}}svg", {"width": str(width), "height": str(height),
                                            "viewBox": f"0 0 {width} {height}"})
        ET.SubElement(root, f"{{{_SVG}}}image", {"width": str(width), "height": str(height),
            f"{{{_XLINK}}}href": "data:image/png;base64," + b64encode(png).decode("ascii")})
        return ET.tostring(root, encoding="utf-8", xml_declaration=True)
    output = BytesIO()
    with Image.open(BytesIO(png)) as image:
        options = {"dpi": (dpi, dpi)}
        if image_format == "JPEG":
            if image.mode == "RGBA":
                background = Image.new("RGB", image.size, "white")
                background.paste(image, mask=image.getchannel("A"))
                image = background
            else:
                image = image.convert("RGB")
            options.update(quality=95, subsampling=0)
        elif image_format == "TIFF":
            options["compression"] = "tiff_deflate"
        image.save(output, format=image_format, **options)
    return output.getvalue()
