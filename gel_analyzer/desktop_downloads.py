"""Keep native download destinations consistent with the encoded image format.

pywebview 6's download dialogs accept arbitrary filenames. Install adapters
after its GUI imports, but before it constructs the native download delegates.
Browser downloads continue to use Streamlit's filename and content type.
"""

from pathlib import PurePath

from .annotation_exports import EXPORT_FORMATS


def export_extensions(image_format: str) -> tuple[str, ...]:
    extension = EXPORT_FORMATS[image_format]["extension"]
    aliases = {"JPEG": ("jpeg",), "TIFF": ("tif",)}
    return (extension, *aliases.get(image_format, ()))


def valid_export_path(filename: str, image_format: str) -> bool:
    return PurePath(filename).suffix.lower().removeprefix(".") in export_extensions(image_format)


def download_format(mime_type: str | None, suggested_filename: str) -> str | None:
    """Prefer the response type; use the suggestion only for untyped downloads."""
    mime = (mime_type or "").partition(";")[0].strip().lower()
    for name, specification in EXPORT_FORMATS.items():
        if mime == specification["mime"]:
            return name
    if mime in ("", "application/octet-stream"):
        return next((name for name in EXPORT_FORMATS
                     if valid_export_path(suggested_filename, name)), None)
    return None


def configure_downloads(renderer: str) -> None:
    """Called by the blocking initialized event before native window creation."""
    import webview

    # An adapter import/installation failure must not enable unrestricted saves.
    webview.settings["ALLOW_DOWNLOADS"] = False
    if renderer == "wkwebview":
        from webview.platforms import cocoa
        from .desktop_downloads_macos import install_macos_downloads

        install_macos_downloads(cocoa)
    elif renderer == "edgechromium":
        from webview.platforms import edgechromium
        from .desktop_downloads_windows import install_windows_downloads

        install_windows_downloads(edgechromium)
    else:
        raise RuntimeError(f"Unsupported desktop download renderer: {renderer}")
    webview.settings["ALLOW_DOWNLOADS"] = True
