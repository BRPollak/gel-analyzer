"""Load gel images without changing the uploaded source data."""

from dataclasses import dataclass, replace
from io import BytesIO
import warnings

from PIL import Image, ImageOps

from .auto_crop import find_gel_crop
from .orientation import GelRectangle, OrientationError, orient_gel


class ImageValidationError(ValueError):
    """An uploaded file cannot be used as a single gel image."""


@dataclass(frozen=True, slots=True)
class GelOrientation:
    """Accepted transform geometry, relative to the initial cropped preview."""

    corners: tuple[tuple[float, float], ...]
    counterclockwise_degrees: float
    size: tuple[int, int]
    outline_complete: bool = True
    supported_edges: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class GelImage:
    """An original image and the current gel pixels in a lossless PNG.

    Source dimensions include orientation metadata. The first crop copies
    pixels exactly; orientation may resample them. The source stays unchanged.
    """

    source_bytes: bytes
    filename: str
    width: int
    height: int
    mode: str
    preview_png: bytes
    crop_box: tuple[int, int, int, int]
    orientation: GelOrientation | None = None
    workflow_orientation: str = "wells_left"

    @property
    def preview_width(self) -> int:
        if self.orientation is not None:
            return self.orientation.size[0]
        return self.crop_box[2] - self.crop_box[0]

    @property
    def preview_height(self) -> int:
        if self.orientation is not None:
            return self.orientation.size[1]
        return self.crop_box[3] - self.crop_box[1]

    @property
    def auto_cropped(self) -> bool:
        return self.crop_box != (0, 0, self.width, self.height)


def orient_gel_image(
    gel: GelImage, rectangle: GelRectangle | None = None, *,
    fallback_angle_degrees: float | None = None,
    supported_edges: tuple[str, ...] = (),
) -> GelImage:
    """Stage a reoriented first crop without changing the current gel or source.

    The first preview is a lossless copy of the decoded source crop, including its
    bit depth. Repeated requests therefore never resample an earlier result.
    """
    if gel.orientation is not None:
        if rectangle is not None or fallback_angle_degrees is not None:
            raise OrientationError(
                "Manual orientation must start from the original cropped image."
            )
        return gel
    with Image.open(BytesIO(gel.preview_png)) as cropped:
        cropped.load()
        options = {"workflow_orientation": gel.workflow_orientation} if gel.workflow_orientation != "wells_left" else {}
        if rectangle is not None:
            options["rectangle"] = rectangle
        if fallback_angle_degrees is not None:
            options["fallback_angle_degrees"] = fallback_angle_degrees
            options["supported_edges"] = supported_edges
        result = orient_gel(cropped, **options)
    preview = BytesIO()
    result.image.save(preview, format="PNG")
    return replace(
        gel,
        preview_png=preview.getvalue(),
        orientation=GelOrientation(
            corners=result.rectangle.corners,
            counterclockwise_degrees=result.counterclockwise_degrees,
            size=result.image.size,
            outline_complete=result.outline_complete,
            supported_edges=result.supported_edges,
        ),
    )


_PREVIEW_MODES = {"1", "L", "LA", "P", "RGB", "RGBA", "I;16", "I;16B", "I;16L"}
_CORRUPT_MESSAGE = "This image is incomplete or damaged, or cannot be decoded. Please choose another TIFF, PNG, or JPEG image."
_UNSUPPORTED_MESSAGE = (
    "This image uses an unsupported pixel format. Please choose an unsigned "
    "8-bit grayscale/color or 16-bit grayscale image."
)


def decode_source_image(image: Image.Image) -> Image.Image:
    """Decode source pixels and apply orientation metadata exactly once."""
    image_format = image.format
    # TIFF load() applies orientation itself; PNG EXIF may need load() first.
    image.load()
    if image_format != "TIFF":
        image = ImageOps.exif_transpose(image)
    if image_format == "JPEG" and image.mode == "CMYK":
        image = image.convert("RGB")
    return image


def load_image(data: bytes, filename: str) -> GelImage:
    """Decode and safely crop a TIFF, PNG, or JPEG for its first PNG preview.

    Source bytes remain unchanged. No contrast adjustment, normalization,
    resizing, or filesystem writes occur.
    """
    return _load_image(data, filename, formats={"TIFF", "PNG", "JPEG"})


def load_tiff(data: bytes, filename: str) -> GelImage:
    """Compatibility entry point for callers that require a TIFF source."""
    return _load_image(data, filename, formats={"TIFF"})


def _load_image(data: bytes, filename: str, *, formats: set[str]) -> GelImage:
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            # Pillow may otherwise keep reading after corrupt TIFF metadata.
            warnings.simplefilter("error", UserWarning)
            with Image.open(BytesIO(data)) as image:
                if image.format not in formats:
                    raise ImageValidationError(
                        "Please choose a TIFF image (.tif or .tiff). This file is not a TIFF."
                        if formats == {"TIFF"} else
                        "Please choose a TIFF, PNG, or JPEG image (.tif, .tiff, .png, .jpg, or .jpeg)."
                    )
                if getattr(image, "n_frames", 1) != 1:
                    raise ImageValidationError(
                        "Multipage TIFFs are not supported yet. Please choose a single-image TIFF."
                        if image.format == "TIFF" else
                        "Animated or multiframe images are not supported. Please choose a single-image PNG."
                    )

                # Pillow can reduce high-bit-depth color TIFFs to 8-bit on load.
                # Check the TIFF tags first rather than silently lose precision.
                if image.format == "TIFF":
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
                    ):
                        raise ImageValidationError(_UNSUPPORTED_MESSAGE)
                elif image.format == "PNG":
                    # IHDR stores bit depth and color type at bytes 24 and 25.
                    # Pillow also reduces 16-bit color PNGs to 8-bit on load.
                    if data[24] == 16 and data[25] != 0:
                        raise ImageValidationError(_UNSUPPORTED_MESSAGE)
                    # Check chunk checksums/end markers before decoding pixels.
                    with Image.open(BytesIO(data)) as check:
                        check.verify()
                if image.mode not in _PREVIEW_MODES and not (
                    image.format == "JPEG" and image.mode == "CMYK"
                ):
                    raise ImageValidationError(_UNSUPPORTED_MESSAGE)

                image = decode_source_image(image)
                width, height = image.size
                mode = image.mode
                crop_box = find_gel_crop(image)
                preview = BytesIO()
                image.crop(crop_box).save(preview, format="PNG")
    except ImageValidationError:
        raise
    except (Image.DecompressionBombError, Image.DecompressionBombWarning) as exc:
        raise ImageValidationError(
            "This image is too large to open safely. Please choose a smaller image."
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
