"""Load gel images without changing the uploaded source data."""

from dataclasses import dataclass
from io import BytesIO
import warnings
import zlib

from PIL import Image


class ImageValidationError(ValueError):
    """An uploaded file cannot be used as a static PNG gel image."""


@dataclass(frozen=True, slots=True)
class GelImage:
    """An immutable original PNG and the metadata of its decoded image."""

    source_bytes: bytes
    filename: str
    width: int
    height: int
    mode: str


_PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
_IEND_CRC = b"\xaeB`\x82"
_CORRUPT_MESSAGE = "This PNG is incomplete or damaged. Please choose another image."


def _validate_container(data: bytes) -> None:
    """Check chunk completeness, including the IEND CRC that Pillow skips."""
    if not data.startswith(_PNG_SIGNATURE):
        raise ImageValidationError("Please choose a PNG image. This file is not a PNG.")

    offset = len(_PNG_SIGNATURE)
    while offset + 12 <= len(data):
        length = int.from_bytes(data[offset : offset + 4], "big")
        chunk_type = data[offset + 4 : offset + 8]
        chunk_end = offset + length + 12
        if chunk_end > len(data):
            break
        if chunk_type == b"acTL":
            raise ImageValidationError(
                "Animated PNGs are not supported. Please choose a static PNG image."
            )
        if chunk_type == b"IEND":
            if length == 0 and data[offset + 8 : chunk_end] == _IEND_CRC:
                return
            break
        offset = chunk_end

    raise ImageValidationError(_CORRUPT_MESSAGE)


def load_png(data: bytes, filename: str) -> GelImage:
    """Validate and fully decode one static PNG while preserving its bytes.

    No image transformations, display adjustments, or filesystem writes occur.
    The filename is metadata only; actual file contents determine acceptance.
    """
    _validate_container(data)

    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(BytesIO(data)) as image:
                if image.format != "PNG":
                    raise ImageValidationError("Please choose a PNG image.")
                image.verify()

            # verify() consumes the stream; reopen it to actually decode pixels.
            with Image.open(BytesIO(data)) as image:
                image.load()
                width, height = image.size
                mode = image.mode
    except ImageValidationError:
        raise
    except (Image.DecompressionBombError, Image.DecompressionBombWarning) as exc:
        raise ImageValidationError(
            "This PNG is too large to open safely. Please choose a smaller image."
        ) from exc
    except (OSError, SyntaxError, ValueError, EOFError, zlib.error) as exc:
        raise ImageValidationError(_CORRUPT_MESSAGE) from exc

    return GelImage(
        source_bytes=data,
        filename=filename,
        width=width,
        height=height,
        mode=mode,
    )
