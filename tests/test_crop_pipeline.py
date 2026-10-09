"""Check that automatic cropping changes only the completed browser preview."""

from io import BytesIO

from PIL import Image, ImageDraw
import pytest

from gel_analyzer import image_io


def encode_tiff(image, **save_options):
    output = BytesIO()
    image.save(output, format="TIFF", **save_options)
    return output.getvalue()


def pixels(image):
    return [
        image.getpixel((x, y))
        for y in range(image.height)
        for x in range(image.width)
    ]


@pytest.mark.parametrize("mode", ["RGBA", "I;16", "I;16B"])
@pytest.mark.parametrize("compression", ["raw", "tiff_lzw", "tiff_adobe_deflate"])
def test_cropped_preview_preserves_source_and_exact_pixel_values(
    monkeypatch, mode, compression
):
    original = Image.new(mode, (9, 7))
    original.putdata(
        [
            (x * 23, y * 29, (x + y) * 13, 30 + x * 20 + y)
            if mode == "RGBA"
            else (x * 4096 + y * 1031) % 65536
            for y in range(original.height)
            for x in range(original.width)
        ]
    )
    source = encode_tiff(original, compression=compression)
    # Pillow uses native byte order for compressed 16-bit TIFF decoding.
    with Image.open(BytesIO(source)) as decoded:
        decoded.load()
        decoded_mode = decoded.mode
    crop_box = (2, 1, 8, 6)
    detector_calls = []

    def detect(image):
        detector_calls.append((image.mode, image.size, pixels(image)))
        return crop_box

    monkeypatch.setattr(image_io, "find_gel_crop", detect)

    gel = image_io.load_tiff(source, "source.tif")

    assert detector_calls == [(decoded_mode, original.size, pixels(original))]
    assert gel.source_bytes == source
    assert (gel.width, gel.height) == original.size
    assert gel.mode == decoded_mode
    assert gel.crop_box == crop_box
    assert (gel.preview_width, gel.preview_height) == (6, 5)
    assert gel.auto_cropped
    with Image.open(BytesIO(gel.preview_png)) as preview:
        preview.load()
        assert preview.format == "PNG"
        # The only stored browser image is already cropped. It has neither
        # analysis normalization nor downsampling applied to its pixels.
        assert preview.size == (6, 5)
        assert pixels(preview) == pixels(original.crop(crop_box))
    with Image.open(BytesIO(gel.source_bytes)) as preserved_source:
        preserved_source.load()
        assert preserved_source.size == original.size
        assert pixels(preserved_source) == pixels(original)


@pytest.mark.parametrize(
    "orientation,transpose",
    [
        (2, Image.Transpose.FLIP_LEFT_RIGHT),
        (3, Image.Transpose.ROTATE_180),
        (4, Image.Transpose.FLIP_TOP_BOTTOM),
        (5, Image.Transpose.TRANSPOSE),
        (6, Image.Transpose.ROTATE_270),
        (7, Image.Transpose.TRANSVERSE),
        (8, Image.Transpose.ROTATE_90),
    ],
)
@pytest.mark.parametrize("compression", ["raw", "tiff_lzw"])
def test_crop_coordinates_follow_tiff_orientation_exactly_once(
    monkeypatch, orientation, transpose, compression
):
    original = Image.new("L", (5, 4))
    original.putdata(range(20))
    expected_oriented = original.transpose(transpose)
    crop_box = (1, 1, expected_oriented.width, expected_oriented.height)
    source = encode_tiff(
        original, tiffinfo={274: orientation}, compression=compression
    )
    detector_inputs = []

    def detect(image):
        detector_inputs.append((image.size, pixels(image)))
        return crop_box

    monkeypatch.setattr(image_io, "find_gel_crop", detect)

    gel = image_io.load_tiff(source, "oriented.tif")

    assert detector_inputs == [(expected_oriented.size, pixels(expected_oriented))]
    assert gel.source_bytes == source
    assert (gel.width, gel.height) == expected_oriented.size
    assert gel.crop_box == crop_box
    expected_crop = expected_oriented.crop(crop_box)
    assert (gel.preview_width, gel.preview_height) == expected_crop.size
    with Image.open(BytesIO(gel.preview_png)) as preview:
        assert preview.size == expected_crop.size
        assert pixels(preview) == pixels(expected_crop)
        assert preview.getexif().get(274, 1) == 1


def test_full_frame_fallback_retains_original_preview(monkeypatch):
    original = Image.new("RGB", (17, 13), (34, 91, 151))
    source = encode_tiff(original)
    monkeypatch.setattr(
        image_io, "find_gel_crop", lambda image: (0, 0, image.width, image.height)
    )

    gel = image_io.load_tiff(source, "uncertain.tif")

    assert gel.crop_box == (0, 0, 17, 13)
    assert not gel.auto_cropped
    assert (gel.preview_width, gel.preview_height) == original.size
    with Image.open(BytesIO(gel.preview_png)) as preview:
        assert pixels(preview) == pixels(original)


def test_centered_gel_upload_is_cropped_with_all_edges_and_margin_intact():
    original = Image.new("L", (480, 360), 190)
    draw = ImageDraw.Draw(original)
    gel_box = (75, 50, 405, 315)
    draw.rectangle((75, 50, 404, 314), fill=45)
    for lane_x in range(100, 390, 35):
        draw.rectangle((lane_x, 68, lane_x + 13, 77), fill=100)
        for band_y in (135, 177, 224):
            draw.rectangle((lane_x, band_y, lane_x + 13, band_y + 3), fill=225)
    source = encode_tiff(original, compression="tiff_lzw")

    gel = image_io.load_tiff(source, "centered-gel.tif")

    assert gel.auto_cropped
    left, top, right, bottom = gel.crop_box
    assert 0 <= left < gel_box[0]
    assert 0 <= top < gel_box[1]
    assert gel_box[2] < right <= original.width
    assert gel_box[3] < bottom <= original.height
    assert gel.source_bytes == source
    with Image.open(BytesIO(gel.preview_png)) as preview:
        assert pixels(preview) == pixels(original.crop(gel.crop_box))
