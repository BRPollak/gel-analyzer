"""Orientation consumes the first lossless crop and preserves source metadata."""

from dataclasses import FrozenInstanceError
from io import BytesIO
from types import SimpleNamespace

from PIL import Image
import pytest

from gel_analyzer import image_io


def pixels(image):
    return [
        image.getpixel((x, y))
        for y in range(image.height)
        for x in range(image.width)
    ]


@pytest.mark.parametrize("mode", ["L", "RGBA", "I;16", "I;16B"])
@pytest.mark.parametrize("tiff_orientation", [1, 6])
def test_orientation_uses_first_crop_pixels_and_keeps_tiff_source(
    monkeypatch, mode, tiff_orientation
):
    original = Image.new(mode, (13, 9))
    original.putdata([
        (x * 17, y * 23, (x + y) * 11, 30 + x + y)
        if mode == "RGBA"
        else ((x * 4096 + y * 1031) % 65536 if mode.startswith("I;") else x * 13 + y)
        for y in range(original.height)
        for x in range(original.width)
    ])
    source = BytesIO()
    original.save(source, format="TIFF", tiffinfo={274: tiff_orientation})
    decoded = (
        original.transpose(Image.Transpose.ROTATE_270)
        if tiff_orientation == 6 else original
    )
    crop_box = (1, 2, decoded.width - 1, decoded.height - 1)
    first_crop = decoded.crop(crop_box)
    monkeypatch.setattr(image_io, "find_gel_crop", lambda image: crop_box)
    calls = []
    corners = ((1.0, 1.0), (5.0, 1.0), (5.0, 4.0), (1.0, 4.0))

    def orient(cropped):
        calls.append((cropped.size, pixels(cropped)))
        return SimpleNamespace(
            # The engine has its own geometry tests. This asymmetric transform
            # additionally crops the result to expose stale preview dimensions.
            image=cropped.transpose(Image.Transpose.TRANSPOSE).crop((1, 1, 4, 5)),
            rectangle=SimpleNamespace(corners=corners),
            counterclockwise_degrees=87.25,
            outline_complete=True,
            supported_edges=(),
        )

    monkeypatch.setattr(image_io, "orient_gel", orient)
    initial = image_io.load_tiff(source.getvalue(), "original.tiff")
    initial_preview = initial.preview_png

    oriented = image_io.orient_gel_image(initial)

    assert calls == [(first_crop.size, pixels(first_crop))]
    assert initial.orientation is None
    assert initial.preview_png == initial_preview
    assert oriented is not initial
    assert oriented.source_bytes == source.getvalue()
    assert oriented.filename == initial.filename
    assert (oriented.width, oriented.height, oriented.mode) == (
        initial.width, initial.height, initial.mode
    )
    assert oriented.crop_box == crop_box
    assert oriented.orientation.corners == corners
    assert oriented.orientation.counterclockwise_degrees == 87.25
    assert oriented.orientation.size == (3, 4)
    assert (oriented.preview_width, oriented.preview_height) == (3, 4)
    with Image.open(BytesIO(oriented.preview_png)) as result:
        expected = first_crop.transpose(Image.Transpose.TRANSPOSE).crop((1, 1, 4, 5))
        assert result.size == expected.size
        assert pixels(result) == pixels(expected)
        assert result.getexif().get(274, 1) == 1
        if mode.startswith("I;"):
            assert max(pixels(result)) > 255
    with pytest.raises(FrozenInstanceError):
        oriented.orientation.counterclockwise_degrees = 90

    # Calling the integration entry point with an already accepted image must
    # also avoid rotating and flipping it a second time.
    assert image_io.orient_gel_image(oriented) is oriented
    assert len(calls) == 1
