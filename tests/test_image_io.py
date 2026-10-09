"""Generated images exercise real PNG parsing without storing gel fixtures."""

from dataclasses import FrozenInstanceError
from io import BytesIO
import zlib

from PIL import Image
import pytest

from gel_analyzer import ImageValidationError, load_png


def make_png(mode="L", size=(31, 9), color=0):
    output = BytesIO()
    Image.new(mode, size, color).save(output, format="PNG")
    return output.getvalue()


@pytest.mark.parametrize("mode", ["1", "L", "LA", "P", "RGB", "RGBA", "I;16"])
@pytest.mark.parametrize("size", [(31, 9), (9, 31), (12, 12)])
def test_load_preserves_original_bytes_and_metadata(mode, size):
    source = make_png(mode, size)

    gel = load_png(source, "my gel.png")

    assert gel.source_bytes == source
    assert gel.filename == "my gel.png"
    assert (gel.width, gel.height) == size
    assert gel.mode == mode
    with pytest.raises(FrozenInstanceError):
        gel.width = 999


def test_preserves_16_bit_grayscale_pixel_values():
    source_image = Image.new("I;16", (3, 1))
    source_image.putdata([0, 32768, 65535])
    output = BytesIO()
    source_image.save(output, format="PNG")

    gel = load_png(output.getvalue(), "high-bit-depth.png")

    with Image.open(BytesIO(gel.source_bytes)) as image:
        assert [image.getpixel((x, 0)) for x in range(3)] == [0, 32768, 65535]


def test_different_images_with_same_filename_are_loaded_independently():
    first = load_png(make_png(size=(7, 21)), "gel.png")
    second = load_png(make_png(size=(40, 5), color=255), "gel.png")

    assert (first.width, first.height) == (7, 21)
    assert (second.width, second.height) == (40, 5)
    assert first.source_bytes != second.source_bytes


@pytest.mark.parametrize("source", [b"", b"not an image", b"\x89PNG\r\n\x1a\n"])
def test_rejects_empty_or_invalid_data(source):
    with pytest.raises(ImageValidationError):
        load_png(source, "looks-valid.png")


def test_rejects_a_jpeg_disguised_as_png():
    output = BytesIO()
    Image.new("RGB", (8, 8)).save(output, format="JPEG")

    with pytest.raises(ImageValidationError, match="not a PNG"):
        load_png(output.getvalue(), "gel.png")


@pytest.mark.parametrize("removed_bytes", [1, 12, 20])
def test_rejects_truncated_png(removed_bytes):
    with pytest.raises(ImageValidationError, match="incomplete or damaged"):
        load_png(make_png()[:-removed_bytes], "truncated.png")


def test_rejects_bad_chunk_crc():
    source = bytearray(make_png())
    idat_offset = source.index(b"IDAT")
    source[idat_offset + 4] ^= 0xFF

    with pytest.raises(ImageValidationError, match="incomplete or damaged"):
        load_png(bytes(source), "corrupt.png")


def test_rejects_bad_iend_crc():
    source = bytearray(make_png())
    source[-1] ^= 0xFF

    with pytest.raises(ImageValidationError, match="incomplete or damaged"):
        load_png(bytes(source), "corrupt-end.png")


def test_fully_decodes_png_instead_of_only_checking_chunk_crcs():
    source = bytearray(make_png())
    idat_offset = source.index(b"IDAT")
    length = int.from_bytes(source[idat_offset - 4 : idat_offset], "big")
    payload_end = idat_offset + 4 + length
    source[idat_offset + 4 : payload_end] = b"\x00" * length
    crc = zlib.crc32(source[idat_offset:payload_end])
    source[payload_end : payload_end + 4] = crc.to_bytes(4, "big")

    with pytest.raises(ImageValidationError, match="incomplete or damaged"):
        load_png(bytes(source), "invalid-pixels.png")


def test_rejects_animated_png():
    output = BytesIO()
    first = Image.new("L", (8, 8), 0)
    second = Image.new("L", (8, 8), 255)
    first.save(output, format="PNG", save_all=True, append_images=[second], duration=100)

    with pytest.raises(ImageValidationError, match="Animated PNG"):
        load_png(output.getvalue(), "animated.png")


@pytest.mark.parametrize("limit", [100, 50])
def test_surfaces_pillow_decompression_protections_as_validation_errors(monkeypatch, limit):
    source = make_png(size=(11, 10))
    monkeypatch.setattr(Image, "MAX_IMAGE_PIXELS", limit)

    with pytest.raises(ImageValidationError, match="too large"):
        load_png(source, "large.png")
