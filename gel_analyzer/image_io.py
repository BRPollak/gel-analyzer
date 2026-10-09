"""Load gel images without changing the uploaded source data."""

from dataclasses import dataclass
from io import BytesIO
import warnings

from PIL import Image

from .auto_crop import find_gel_crop


class ImageValidationError(ValueError):
    """An uploaded file cannot be used as a single-image TIFF gel."""


@dataclass(frozen=True, slots=True)
class GelImage:
    """An original TIFF and a cropped, lossless PNG for browser display.

    Dimensions describe the decoded image, including TIFF orientation metadata.
    The original bytes remain the source for future processing and export.
    """

    source_bytes: bytes
    filename: str
    width: int
    height: int
    mode: str
    preview_png: bytes
    crop_box: tuple[int, int, int, int]

    @property
    def preview_width(self) -> int:
        return self.crop_box[2] - self.crop_box[0]

    @property
    def preview_height(self) -> int:
        return self.crop_box[3] - self.crop_box[1]

    @property
    def auto_cropped(self) -> bool:
        return self.crop_box != (0, 0, self.width, self.height)


_PREVIEW_MODES = {"1", "L", "LA", "P", "RGB", "RGBA", "I;16", "I;16B", "I;16L"}
_CORRUPT_MESSAGE = "This TIFF is incomplete or damaged, or cannot be decoded. Please choose another image."
_UNSUPPORTED_MESSAGE = (
    "This TIFF uses an unsupported pixel format. Please choose an unsigned "
    "8-bit grayscale/color or 16-bit grayscale TIFF."
)


def load_tiff(data: bytes, filename: str) -> GelImage:
    """Decode and safely crop one TIFF before encoding its first PNG preview.

    No contrast adjustment, normalization, resizing, or filesystem writes occur.
    Pillow honors TIFF orientation during decoding; do not transpose it again.
    """
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            # Pillow may otherwise keep reading after corrupt TIFF metadata.
            warnings.simplefilter("error", UserWarning)
            with Image.open(BytesIO(data)) as image:
                if image.format != "TIFF":
                    raise ImageValidationError(
                        "Please choose a TIFF image (.tif or .tiff). This file is not a TIFF."
                    )
                if image.n_frames != 1:
                    raise ImageValidationError(
                        "Multipage TIFFs are not supported yet. Please choose a single-image TIFF."
                    )

                # Pillow can reduce high-bit-depth color TIFFs to 8-bit on load.
                # Check the TIFF tags first rather than silently lose precision.
                bits = image.tag_v2.get(258, (1,))
                samples = image.tag_v2.get(339, (1,))
                if isinstance(bits, int):
                    bits = (bits,)
                if isinstance(samples, int):
                    samples = (samples,)
                if (
                    any(sample != 1 for sample in samples)
                    or max(bits) > 16
                    or (len(bits) > 1 and max(bits) > 8)
                    or image.mode not in _PREVIEW_MODES
                ):
                    raise ImageValidationError(_UNSUPPORTED_MESSAGE)

                # TIFF verify() does not decode the pixels. load() also applies
                # the file's orientation, so read size only after it completes.
                image.load()
                width, height = image.size
                mode = image.mode
                crop_box = find_gel_crop(image)
                preview = BytesIO()
                image.crop(crop_box).save(preview, format="PNG")
    except ImageValidationError:
        raise
    except (Image.DecompressionBombError, Image.DecompressionBombWarning) as exc:
        raise ImageValidationError(
            "This TIFF is too large to open safely. Please choose a smaller image."
        ) from exc
    except (OSError, SyntaxError, ValueError, EOFError, UserWarning) as exc:
        raise ImageValidationError(_CORRUPT_MESSAGE) from exc

    return GelImage(
        source_bytes=data,
        filename=filename,
        width=width,
        height=height,
        mode=mode,
        preview_png=preview.getvalue(),
        crop_box=crop_box,
    )
