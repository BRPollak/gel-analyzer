"""Verify exported file formats, print metadata, and safe vector snapshots."""

from base64 import b64decode
from io import BytesIO
import json
from pathlib import Path
import shutil
import subprocess
from types import SimpleNamespace
import xml.etree.ElementTree as ET

from PIL import Image
import pytest

from gel_analyzer.annotation_exports import (
    EXPORT_FORMATS, export_composition, validate_svg_composition,
)
from gel_analyzer.annotations import AnnotationError
from test_annotations import composition


@pytest.fixture
def crop():
    output = BytesIO()
    image = Image.new("RGB", (30, 20), "#234567")
    image.putpixel((3, 4), (19, 47, 89))
    image.save(output, format="PNG")
    return SimpleNamespace(width=30, height=20, preview_png=output.getvalue())


@pytest.mark.parametrize("image_format,dpi", [
    (name, dpi) for name, specification in EXPORT_FORMATS.items() for dpi in specification["dpi"]
])
def test_raster_exports_keep_native_dimensions_and_write_real_dpi(crop, image_format, dpi):
    _, png = composition(crop)
    exported = export_composition(png, image_format, dpi)
    with Image.open(BytesIO(exported)) as image, Image.open(BytesIO(png)) as original:
        assert image.format == image_format
        assert image.size == original.size
        assert image.info["dpi"] == pytest.approx((dpi, dpi), abs=0.02)
        if image_format != "JPEG":
            assert image.tobytes() == original.tobytes()


def test_jpeg_flattens_alpha_onto_white(crop):
    output = BytesIO()
    Image.new("RGBA", (10, 10), (0, 0, 0, 0)).save(output, format="PNG")
    exported = export_composition(output.getvalue(), "JPEG", 300)
    with Image.open(BytesIO(exported)) as image:
        assert image.mode == "RGB"
        assert image.getpixel((4, 4)) == (255, 255, 255)


@pytest.mark.parametrize("image_format,dpi", [("PDF", 300), ("PNG", 999), ("TIFF", 72), ("JPEG", None)])
def test_unsupported_export_selections_fail(crop, image_format, dpi):
    _, png = composition(crop)
    with pytest.raises(AnnotationError):
        export_composition(png, image_format, dpi)


def vector_event(crop):
    event, _ = composition(crop)
    width, height, x, y = (event[key] for key in ("width", "height", "gel_x", "gel_y"))
    event["svg"] = (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">'
        f'<rect x="0" y="0" width="{width}" height="{height}" fill="#ffffff"/>'
        f'<image x="{x}" y="{y}" width="{crop.width}" height="{crop.height}"/>'
        '<text x="5" y="20" font-family="Arial" font-size="12" font-style="italic" '
        'font-weight="bold" fill="#1234ab" text-anchor="start" xml:space="preserve">α &amp; β</text>'
        '<path d="M 12 4 L 10 4 L 10 30 L 12 30" fill="none" stroke="#000000" stroke-width="1.5" stroke-linecap="butt"/>'
        '</svg>'
    )
    return event


def test_svg_preserves_vectors_and_embeds_the_current_lossless_crop(crop):
    event = vector_event(crop)
    svg = validate_svg_composition(event, crop)
    root = ET.fromstring(svg)
    image = root.find("{http://www.w3.org/2000/svg}image")
    url = image.attrib["{http://www.w3.org/1999/xlink}href"]
    assert b64decode(url.split(",", 1)[1]) == crop.preview_png
    label = root.find("{http://www.w3.org/2000/svg}text")
    assert label.text == "α & β"
    assert label.attrib["font-weight"] == "bold"
    assert label.attrib["font-style"] == "italic"
    assert root.find("{http://www.w3.org/2000/svg}path") is not None
    assert export_composition(b"not needed", "SVG", svg=svg) == svg


@pytest.mark.parametrize("old,new", [
    ('</svg>', '<script>alert(1)</script></svg>'),
    ('</svg>', '<foreignObject><div>HTML</div></foreignObject></svg>'),
    ('<image ', '<image onload="alert(1)" '),
    ('<image ', '<image href="https://example.com/image.png" '),
    ('fill="#1234ab"', 'fill="url(https://example.com)"'),
    ('x="5"', 'x="NaN"'),
    ('x="5"', 'x="1e99"'),
    ('font-family="Arial"', 'font-family="external"'),
    ('<svg ', '<!DOCTYPE svg><svg '),
    ('<svg ', '<?xml-stylesheet href="https://example.com"?><svg '),
    ('width="30"', 'width="29"'),
    ('viewBox="0 0 210 44"', 'viewBox="0 0 210 43"'),
    ('<text ', '<text transform="translate(1 2) rotate(10)" '),
    ('<text ', '<text style="background:url(https://example.com)" '),
    ('<text ', '<text xmlns="http://example.com" '),
])
def test_svg_rejects_active_content_external_resources_and_changed_crop(crop, old, new):
    event = vector_event(crop)
    assert old in event["svg"]
    event["svg"] = event["svg"].replace(old, new)
    with pytest.raises(AnnotationError):
        validate_svg_composition(event, crop)


def test_legacy_confirmation_still_exports_a_self_contained_svg(crop):
    event, png = composition(crop)
    assert validate_svg_composition(event, crop) is None
    root = ET.fromstring(export_composition(png, "SVG"))
    image = root.find("{http://www.w3.org/2000/svg}image")
    assert b64decode(image.attrib["{http://www.w3.org/1999/xlink}href"].split(",", 1)[1]) == png


def test_real_browser_serializer_is_accepted_with_rich_text_groups_and_ladder(crop):
    if not shutil.which("node"):
        pytest.skip("Node is required for the browser/server serialization contract.")
    script = """
import {layoutAnnotations} from './gel_analyzer/annotation_component_frontend/layout.mjs';
import {annotationSvg} from './gel_analyzer/annotation_component_frontend/svg.mjs';
const state = {width:30, height:20, lanes:[[0,0,30,20]], annotations:{fontSize:14,
  labels:[{text:'A & β',runs:[{text:'A ',bold:true,color:'#ff0000'},
    {text:'& β',italic:true,color:'#0000ff'}]}],
  groups:[{id:'g',set:0,label:'<Control>',lanes:[0]}]},
  ladder:{preset:{labels:['1 kb']},placements:[{markerIndex:0,x:20,y:10}]}};
const measure=(text,font)=>{const size=Number(font.match(/([\\d.]+)px/)[1]);
  return {width:text.length*size*.6,actualBoundingBoxAscent:size*.8,
    actualBoundingBoxDescent:size*.2,actualBoundingBoxLeft:0,
    actualBoundingBoxRight:text.length*size*.6};};
const layout=layoutAnnotations(state,measure);
process.stdout.write(JSON.stringify({svg:annotationSvg(layout),width:layout.width,
  height:layout.height,gel_x:layout.gelX,gel_y:layout.gelY}));
"""
    result = subprocess.run(["node", "--input-type=module", "-e", script], check=True,
                            capture_output=True, text=True, cwd=Path(__file__).parents[1])
    event = json.loads(result.stdout)
    root = ET.fromstring(validate_svg_composition(event, crop))
    labels = root.findall("{http://www.w3.org/2000/svg}text")
    assert [label.text for label in labels] == ["A ", "& β", "<Control>", "1 kb"]
    assert float(labels[-1].attrib["font-size"]) == pytest.approx(14 * 0.8)
    assert labels[-1].attrib["transform"].endswith("rotate(-90)")
