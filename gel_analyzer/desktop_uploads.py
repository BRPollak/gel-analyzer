"""Use a remembered native folder while keeping Streamlit's normal upload pipeline."""

import base64
import logging
from pathlib import Path
from threading import Lock

from .desktop_preferences import last_directory, remember_directory


LOGGER = logging.getLogger("gel_analyzer.desktop")
IMAGE_TYPES = {".tif": "image/tiff", ".tiff": "image/tiff", ".png": "image/png",
               ".jpg": "image/jpeg", ".jpeg": "image/jpeg"}
MAX_IMAGE_BYTES = 200 * 1024 * 1024  # Streamlit's default per-file upload limit.


class ImagePicker:
    def __init__(self):
        self.window = None
        self._lock = Lock()

    def choose_image(self):
        """Expose a user-controlled picker, never an arbitrary-path file reader."""
        import webview

        if self.window is None or not self._lock.acquire(blocking=False):
            return None
        try:
            selected = self.window.create_file_dialog(
                webview.FileDialog.OPEN,
                directory=last_directory("upload", str(Path.home())),
                allow_multiple=False,
                file_types=("Gel images (*.tif;*.tiff;*.png;*.jpeg;*.jpg)",),
            )
            if not selected:
                return None
            path = Path(selected[0])
            image_type = IMAGE_TYPES.get(path.suffix.lower())
            if image_type is None:
                return {"error": "Choose a TIFF, PNG, or JPEG image."}
            with path.open("rb") as source:
                if path.stat().st_size > MAX_IMAGE_BYTES:
                    return {"error": "Choose an image smaller than 200 MB."}
                data = source.read(MAX_IMAGE_BYTES + 1)
            if len(data) > MAX_IMAGE_BYTES:
                return {"error": "Choose an image smaller than 200 MB."}
            remember_directory("upload", path.parent)
            return {"name": path.name, "type": image_type,
                    "data": base64.b64encode(data).decode("ascii")}
        except OSError:
            LOGGER.exception("Unable to open the selected image")
            return {"error": "The image could not be opened. Please choose it again."}
        finally:
            self._lock.release()


def install_upload_picker(window) -> None:
    """Install after pywebview's API is ready, including after a page reload."""
    script = Path(__file__).with_name("desktop_uploads.js").read_text(encoding="utf-8")
    window.run_js(script)
