"""Exercise the real uploader callbacks and rendered preview across reruns."""

from io import BytesIO
from pathlib import Path

from PIL import Image
import pytest
from streamlit.testing.v1 import AppTest

from gel_analyzer import image_io


@pytest.fixture
def app():
    return AppTest.from_file(Path(__file__).parents[1] / "app.py").run()


def image_bytes(image_format, size=(31, 9), mode="L", color=40):
    output = BytesIO()
    Image.new(mode, size, color).save(output, format=image_format)
    return output.getvalue()


def tiff_bytes(size=(31, 9), mode="L", color=40):
    return image_bytes("TIFF", size, mode, color)


def upload(app, source, filename="gel.tif"):
    suffix = Path(filename).suffix.lower()
    mime_type = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg"}.get(
        suffix, "image/tiff"
    )
    app.file_uploader[0].set_value((filename, source, mime_type)).run()


def assert_preview(app, source, size, filename="gel.tif"):
    assert not app.exception
    assert not app.error
    assert len(app.get("image")) == 1
    assert app.text[0].value == filename
    assert app.session_state["gel_image"].source_bytes == source
    gel = app.session_state["gel_image"]
    assert (gel.preview_width, gel.preview_height) == size
    with Image.open(BytesIO(app.session_state["gel_image"].preview_png)) as preview:
        assert preview.format == "PNG"
        assert preview.size == size
    assert not app.button(key="clear_image").disabled
    assert app.get("popover")[0].proto.popover.label == "Replace image"
    assert app.file_uploader[0].label == "Choose a replacement image"
    assert app.file_uploader[0].value is None
    assert any("discard the current analysis and start over with the new image" in item.value
               for item in app.markdown)
    assert "analysis will be discarded" in app.file_uploader[0].proto.help


def assert_empty(app):
    assert not app.exception
    assert not app.error
    assert not app.get("image")
    assert not app.text
    assert not app.info
    assert not app.expander
    assert app.file_uploader[0].label == "Open a gel image"
    assert app.file_uploader[0].value is None
    assert set(app.file_uploader[0].proto.type) == {".tif", ".tiff", ".png", ".jpeg", ".jpg"}
    assert app.session_state["gel_image"] is None
    assert all(button.disabled for button in app.button)


def test_upload_replacement_clear_removal_and_reupload(app):
    assert_empty(app)
    # Same-name replacements, all source formats, and case-insensitive suffixes
    # share one lifecycle. Pixel-mode validation belongs to test_image_io.py.
    uploads = [
        ("gel.tif", tiff_bytes(), (31, 9)),
        ("gel.tif", tiff_bytes(size=(9, 31), color=220), (9, 31)),
        ("gel.TIFF", tiff_bytes(size=(9, 31)), (9, 31)),
        ("gel.PNG", image_bytes("PNG", size=(19, 23), mode="RGBA", color=(13, 53, 103, 143)), (19, 23)),
        ("gel.JPG", image_bytes("JPEG", size=(25, 13), mode="RGB", color=(70, 80, 90)), (25, 13)),
    ]
    for filename, source, size in uploads:
        upload(app, source, filename)
        assert_preview(app, source, size, filename)
        app.run()
        assert_preview(app, source, size, filename)

    app.button(key="clear_image").click().run()
    assert_empty(app)
    upload(app, source, "gel.jpeg")
    assert_preview(app, source, size, "gel.jpeg")
    app.file_uploader[0].set_value(None).run()
    assert_preview(app, source, size, "gel.jpeg")
    app.button(key="clear_image").click().run()
    assert_empty(app)
    upload(app, source, "gel.jpeg")
    assert_preview(app, source, size, "gel.jpeg")


def test_invalid_replacement_removes_stale_preview_and_recovers(app):
    source = tiff_bytes()
    upload(app, source)

    upload(app, b"not an image", "gel.png")

    assert not app.exception
    assert len(app.error) == 1
    assert "TIFF, PNG, or JPEG" in app.error[0].value
    assert not app.get("image")
    assert not app.text
    assert app.session_state["gel_image"] is None

    upload(app, source)
    assert_preview(app, source, (31, 9))


@pytest.mark.parametrize("mode,size,color", [("I;16", (31, 9), 32768), ("L", (2000, 1), 100)])
def test_high_bit_depth_and_ultrawide_previews_preserve_source(app, mode, size, color):
    source = tiff_bytes(size=size, mode=mode, color=color)

    upload(app, source)

    assert_preview(app, source, size)


def test_only_completed_crop_is_stored_and_displayed_with_crop_dimensions(
    app, monkeypatch
):
    source = tiff_bytes(size=(31, 20), mode="RGBA", color=(13, 53, 103, 143))
    monkeypatch.setattr(image_io, "find_gel_crop", lambda image: (4, 3, 25, 15))

    upload(app, source)

    assert_preview(app, source, (21, 12))
    gel = app.session_state["gel_image"]
    assert (gel.width, gel.height) == (31, 20)
    assert gel.crop_box == (4, 3, 25, 15)
    assert gel.auto_cropped
    with Image.open(BytesIO(gel.preview_png)) as preview:
        assert preview.getpixel((0, 0)) == (13, 53, 103, 143)
    assert not app.slider
    assert not app.number_input


def test_crop_detection_runs_once_per_upload_and_not_on_reruns(app, monkeypatch):
    calls = []

    def detect(image):
        calls.append(image.size)
        return (2, 1, image.width - 2, image.height - 1)

    monkeypatch.setattr(image_io, "find_gel_crop", detect)
    first = tiff_bytes(size=(31, 20))
    replacement = tiff_bytes(size=(35, 23), color=85)

    upload(app, first)
    assert_preview(app, first, (27, 18))
    assert calls == [(31, 20)]

    app.run()
    assert_preview(app, first, (27, 18))
    assert calls == [(31, 20)]

    upload(app, replacement)
    assert_preview(app, replacement, (31, 21))
    assert calls == [(31, 20), (35, 23)]

    app.run()
    app.button(key="clear_image").click().run()
    assert_empty(app)
    assert calls == [(31, 20), (35, 23)]

    upload(app, replacement)
    assert_preview(app, replacement, (31, 21))
    assert calls == [(31, 20), (35, 23), (35, 23)]
