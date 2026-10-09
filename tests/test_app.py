"""Exercise the real uploader callbacks and rendered preview across reruns."""

from io import BytesIO
from pathlib import Path

from PIL import Image
import pytest
from streamlit.testing.v1 import AppTest


@pytest.fixture
def app():
    return AppTest.from_file(Path(__file__).parents[1] / "app.py").run()


def png_bytes(size=(31, 9), mode="L", color=40):
    output = BytesIO()
    Image.new(mode, size, color).save(output, format="PNG")
    return output.getvalue()


def upload(app, source, filename="gel.png"):
    app.file_uploader[0].set_value((filename, source, "image/png")).run()


def assert_preview(app, source, size, filename="gel.png"):
    assert not app.exception
    assert not app.error
    assert len(app.get("image")) == 1
    assert app.text[0].value == f"{filename} · {size[0]:,} × {size[1]:,} pixels"
    assert app.session_state["gel_image"].source_bytes == source
    assert not app.button[0].disabled


def assert_empty(app):
    assert not app.exception
    assert not app.error
    assert not app.get("image")
    assert not app.text
    assert app.info[0].value == "Your gel preview will appear here."
    assert app.file_uploader[0].value is None
    assert app.session_state["gel_image"] is None
    assert app.button[0].disabled


def test_upload_same_name_replacement_clear_and_same_file_reupload(app):
    first = png_bytes(size=(31, 9))
    replacement = png_bytes(size=(9, 31), color=220)
    assert_empty(app)

    upload(app, first)
    assert_preview(app, first, (31, 9))
    upload(app, replacement)
    assert_preview(app, replacement, (9, 31))
    app.run()
    assert_preview(app, replacement, (9, 31))

    app.button[0].click().run()
    assert_empty(app)
    upload(app, replacement)
    assert_preview(app, replacement, (9, 31))


def test_removing_upload_clears_preview_and_metadata(app):
    upload(app, png_bytes())

    app.file_uploader[0].set_value(None).run()

    assert_empty(app)


def test_invalid_replacement_removes_stale_preview_and_recovers(app):
    source = png_bytes()
    upload(app, source)

    upload(app, b"not a PNG")

    assert not app.exception
    assert len(app.error) == 1
    assert "PNG" in app.error[0].value
    assert not app.get("image")
    assert not app.text
    assert app.session_state["gel_image"] is None

    upload(app, source)
    assert_preview(app, source, (31, 9))


@pytest.mark.parametrize("mode,size,color", [("I;16", (31, 9), 32768), ("L", (2000, 1), 100)])
def test_high_bit_depth_and_ultrawide_previews_preserve_source(app, mode, size, color):
    source = png_bytes(size=size, mode=mode, color=color)

    upload(app, source)

    assert_preview(app, source, size)
