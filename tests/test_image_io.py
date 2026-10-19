"""Generated images exercise source preservation and the separate PNG preview."""

from dataclasses import FrozenInstanceError
from io import BytesIO
import struct
import zlib

from PIL import Image, TiffImagePlugin
import pytest

from gel_analyzer import ImageValidationError, load_image, load_tiff


def make_tiff(mode="L", size=(31, 9), color=0, **save_options):
    output = BytesIO()
    Image.new(mode, size, color).save(output, format="TIFF", **save_options)
    return output.getvalue()


@pytest.mark.parametrize("mode", ["1", "L", "LA", "P", "RGB", "RGBA", "I;16", "I;16B"])
@pytest.mark.parametrize("size", [(31, 9), (9, 31), (12, 12)])
def test_load_preserves_original_bytes_and_metadata(mode, size):
    source = make_tiff(mode, size)

    gel = load_tiff(source, "my gel.tif")

    assert gel.source_bytes == source
    assert gel.filename == "my gel.tif"
    assert (gel.width, gel.height) == size
    assert gel.mode == mode
    assert gel.preview_png.startswith(b"\x89PNG\r\n\x1a\n")
    with Image.open(BytesIO(gel.preview_png)) as preview:
        preview.load()
        assert preview.format == "PNG"
        assert preview.size == size
    with pytest.raises(FrozenInstanceError):
        gel.width = 999


@pytest.mark.parametrize("mode", ["I;16", "I;16B", "I;16L"])
@pytest.mark.parametrize("compression", ["raw", "tiff_lzw", "tiff_adobe_deflate"])
def test_preserves_16_bit_grayscale_values_in_source_and_preview(mode, compression):
    values = [0, 256, 32768, 65535]
    source_image = Image.new(mode, (len(values), 1))
    source_image.putdata(values)
    output = BytesIO()
    source_image.save(output, format="TIFF", compression=compression)

    gel = load_tiff(output.getvalue(), "high-bit-depth.tiff")

    assert gel.source_bytes == output.getvalue()
    for encoded_image in [gel.source_bytes, gel.preview_png]:
        with Image.open(BytesIO(encoded_image)) as image:
            assert [image.getpixel((x, 0)) for x in range(len(values))] == values


@pytest.mark.parametrize(
    "mode,color",
    [("RGB", (37, 124, 211)), ("RGBA", (37, 124, 211, 42)), ("LA", (124, 42))],
)
def test_color_and_alpha_are_preserved_in_preview(mode, color):
    gel = load_tiff(make_tiff(mode=mode, color=color), "color.tif")

    with Image.open(BytesIO(gel.preview_png)) as preview:
        assert preview.mode == mode
        assert preview.getpixel((0, 0)) == color


@pytest.mark.parametrize("compression", ["raw", "tiff_lzw", "tiff_adobe_deflate"])
def test_tiff_orientation_is_applied_once_to_preview_and_dimensions(compression):
    image = Image.new("L", (3, 2))
    image.putdata([1, 2, 3, 4, 5, 6])
    output = BytesIO()
    image.save(output, format="TIFF", tiffinfo={274: 6}, compression=compression)
    source = output.getvalue()

    gel = load_tiff(source, "oriented.tif")
    assert gel.source_bytes == source
    assert (gel.width, gel.height) == (2, 3)
    with Image.open(BytesIO(gel.preview_png)) as preview:
        assert preview.size == (2, 3)
        pixels = [preview.getpixel((x, y)) for y in range(3) for x in range(2)]
        assert pixels == [4, 1, 5, 2, 6, 3]
        assert preview.getexif().get(274, 1) == 1


def test_different_images_with_same_filename_are_loaded_independently():
    first = load_tiff(make_tiff(size=(7, 21)), "gel.tif")
    second = load_tiff(make_tiff(size=(40, 5), color=255), "gel.tif")

    assert (first.width, first.height) == (7, 21)
    assert (second.width, second.height) == (40, 5)
    assert first.source_bytes != second.source_bytes
    assert first.preview_png != second.preview_png


@pytest.mark.parametrize("source", [b"", b"not an image", b"II*\x00", b"MM\x00*"])
def test_rejects_empty_or_invalid_data(source):
    with pytest.raises(ImageValidationError):
        load_tiff(source, "looks-valid.tif")


@pytest.mark.parametrize("format", ["PNG", "JPEG"])
def test_rejects_other_formats_disguised_as_tiff(format):
    output = BytesIO()
    Image.new("RGB", (8, 8)).save(output, format=format)

    with pytest.raises(ImageValidationError, match="TIFF"):
        load_tiff(output.getvalue(), "gel.tif")


@pytest.mark.parametrize("compression", ["raw", "tiff_lzw", "tiff_adobe_deflate"])
@pytest.mark.parametrize("removed_bytes", [1, 10, 20])
def test_rejects_truncated_tiff(compression, removed_bytes):
    source = make_tiff(compression=compression)

    with pytest.raises(ImageValidationError, match="incomplete or damaged"):
        load_tiff(source[:-removed_bytes], "truncated.tif")


def test_fully_decodes_compressed_tiff_instead_of_only_checking_metadata():
    source = bytearray(make_tiff(compression="tiff_adobe_deflate"))
    with Image.open(BytesIO(source)) as image:
        offset = image.tag_v2[273][0]
        count = image.tag_v2[279][0]
    source[offset : offset + count] = b"\x00" * count

    with pytest.raises(ImageValidationError, match="incomplete or damaged"):
        load_tiff(bytes(source), "invalid-pixels.tif")


def test_rejects_multipage_tiff_instead_of_silently_using_first_page():
    output = BytesIO()
    first = Image.new("L", (8, 8), 0)
    second = Image.new("L", (8, 8), 255)
    first.save(output, format="TIFF", save_all=True, append_images=[second])

    with pytest.raises(ImageValidationError, match="(?i)page"):
        load_tiff(output.getvalue(), "stack.tif")


@pytest.mark.parametrize("mode", ["I", "F", "CMYK"])
def test_rejects_unsupported_modes_instead_of_clipping_or_reinterpreting_pixels(mode):
    with pytest.raises(ImageValidationError, match="(?i)support|8-bit|16-bit"):
        load_tiff(make_tiff(mode=mode), "unsupported.tif")


def test_rejects_high_bit_depth_color_before_pillow_silently_reduces_precision():
    # Pillow writes RGB TIFFs at 8 bits, so build this small 16-bit RGB fixture
    # with its TIFF directory writer. StripOffsets=0 means immediately after IFD.
    directory = TiffImagePlugin.ImageFileDirectory_v2()
    for tag, value in {
        256: 2, 257: 1, 258: (16, 16, 16), 259: 1, 262: 2,
        273: 0, 277: 3, 278: 1, 279: 12, 284: 1,
    }.items():
        directory[tag] = value
    source = (
        b"II" + struct.pack("<HI", 42, 8) + directory.tobytes(offset=8)
        + struct.pack("<6H", 0, 32768, 65535, 65535, 32768, 0)
    )

    with Image.open(BytesIO(source)) as image:
        image.load()
        assert image.mode == "RGB"
    with pytest.raises(ImageValidationError, match="(?i)support|8-bit|16-bit"):
        load_tiff(source, "16-bit-rgb.tif")


@pytest.mark.parametrize("limit", [100, 50])
def test_surfaces_pillow_decompression_protections_as_validation_errors(monkeypatch, limit):
    source = make_tiff(size=(11, 10))
    monkeypatch.setattr(Image, "MAX_IMAGE_PIXELS", limit)

    with pytest.raises(ImageValidationError, match="too large"):
        load_tiff(source, "large.tif")


@pytest.mark.parametrize(
    "image_format,mode",
    [("PNG", mode) for mode in ("1", "L", "LA", "P", "RGB", "RGBA", "I;16")]
    + [("JPEG", mode) for mode in ("L", "RGB", "CMYK")]
    + [("TIFF", "I;16")],
)
def test_supported_inputs_preserve_source_and_decoded_pixels(image_format, mode):
    original = Image.new(mode, (31, 9), 42)
    output = BytesIO()
    original.save(output, format=image_format)
    source = output.getvalue()
    filename = f"gel.{image_format.lower()}"

    gel = load_image(source, filename)

    assert gel.source_bytes == source
    assert gel.filename == filename
    assert (gel.width, gel.height) == original.size
    with Image.open(BytesIO(source)) as decoded, Image.open(BytesIO(gel.preview_png)) as preview:
        expected = decoded.convert("RGB") if mode == "CMYK" else decoded
        assert preview.mode == expected.mode
        assert preview.tobytes() == expected.tobytes()


def test_png_preserves_16_bit_grayscale_values():
    original = Image.new("I;16", (4, 1))
    original.putdata([0, 256, 32768, 65535])
    output = BytesIO()
    original.save(output, format="PNG")

    gel = load_image(output.getvalue(), "16-bit.png")

    with Image.open(BytesIO(gel.preview_png)) as preview:
        assert preview.mode == "I;16"
        assert [preview.getpixel((x, 0)) for x in range(4)] == [0, 256, 32768, 65535]


@pytest.mark.parametrize("image_format", ["PNG", "JPEG"])
@pytest.mark.parametrize(
    "orientation,transpose",
    [(2, Image.Transpose.FLIP_LEFT_RIGHT), (6, Image.Transpose.ROTATE_270)],
)
def test_png_jpeg_exif_orientation_is_applied_once(image_format, orientation, transpose):
    original = Image.new("L", (3, 2))
    original.putdata([0, 40, 80, 120, 160, 200])
    exif = Image.Exif()
    exif[274] = orientation
    output = BytesIO()
    original.save(output, format=image_format, exif=exif)
    source = output.getvalue()

    gel = load_image(source, f"oriented.{image_format.lower()}")

    assert gel.source_bytes == source
    with Image.open(BytesIO(source)) as decoded, Image.open(BytesIO(gel.preview_png)) as preview:
        expected = decoded.transpose(transpose)
        assert (gel.width, gel.height) == expected.size
        assert preview.size == expected.size
        assert preview.tobytes() == expected.tobytes()
        assert preview.getexif().get(274, 1) == 1


@pytest.mark.parametrize("image_format", ["PNG", "JPEG"])
def test_new_formats_use_the_same_crop_pipeline(monkeypatch, image_format):
    from gel_analyzer import image_io

    output = BytesIO()
    Image.new("RGB", (31, 20), (37, 124, 211)).save(output, format=image_format)
    source = output.getvalue()
    monkeypatch.setattr(image_io, "find_gel_crop", lambda image: (4, 3, 25, 15))

    gel = load_image(source, f"gel.{image_format.lower()}")

    assert gel.crop_box == (4, 3, 25, 15)
    assert gel.auto_cropped
    with Image.open(BytesIO(source)) as decoded, Image.open(BytesIO(gel.preview_png)) as preview:
        assert preview.size == (21, 12)
        assert preview.tobytes() == decoded.crop(gel.crop_box).tobytes()


@pytest.mark.parametrize("image_format", ["BMP", "GIF", "WEBP"])
def test_generic_loader_rejects_unsupported_formats_with_allowed_extension(image_format):
    output = BytesIO()
    Image.new("RGB", (8, 8)).save(output, format=image_format)

    with pytest.raises(ImageValidationError, match="TIFF, PNG, or JPEG"):
        load_image(output.getvalue(), "disguised.png")


def test_rejects_animated_png_instead_of_silently_selecting_a_frame():
    output = BytesIO()
    first = Image.new("RGB", (8, 8), "black")
    second = Image.new("RGB", (8, 8), "white")
    first.save(output, format="PNG", save_all=True, append_images=[second])

    with pytest.raises(ImageValidationError, match="Animated or multiframe"):
        load_image(output.getvalue(), "animated.png")


@pytest.mark.parametrize("image_format", ["PNG", "JPEG"])
def test_rejects_truncated_png_and_jpeg(image_format):
    output = BytesIO()
    Image.new("RGB", (8, 8)).save(output, format=image_format)

    with pytest.raises(ImageValidationError, match="incomplete or damaged"):
        load_image(output.getvalue()[:-20], f"damaged.{image_format.lower()}")


@pytest.mark.parametrize("color_type,channels", [(2, 3), (4, 2), (6, 4)])
def test_rejects_16_bit_color_png_before_precision_is_lost(color_type, channels):
    def chunk(kind, data):
        return (struct.pack(">I", len(data)) + kind + data
                + struct.pack(">I", zlib.crc32(kind + data)))

    source = (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", 2, 1, 16, color_type, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(b"\x00" + b"\x80\x00" * (2 * channels)))
        + chunk(b"IEND", b"")
    )
    with Image.open(BytesIO(source)) as image:
        image.load()
        assert image.mode in ("RGB", "RGBA")

    with pytest.raises(ImageValidationError, match="unsupported pixel format"):
        load_image(source, "16-bit-color.png")


@pytest.mark.parametrize("image_format", ["PNG", "JPEG"])
def test_new_formats_retain_decompression_protection(monkeypatch, image_format):
    output = BytesIO()
    Image.new("L", (11, 10)).save(output, format=image_format)
    monkeypatch.setattr(Image, "MAX_IMAGE_PIXELS", 100)

    with pytest.raises(ImageValidationError, match="too large"):
        load_image(output.getvalue(), "large.png")
