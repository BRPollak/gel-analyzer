"""Verify the orientation preview is staged until the user confirms it."""

from io import BytesIO
from pathlib import Path
from types import SimpleNamespace

from PIL import Image
import pytest
from streamlit.testing.v1 import AppTest

from gel_analyzer import image_io
from gel_analyzer.orientation import OrientationError


@pytest.fixture
def app(monkeypatch):
    monkeypatch.setattr(
        image_io, "find_gel_crop", lambda image: (2, 3, image.width - 2, image.height - 1)
    )
    return AppTest.from_file(Path(__file__).parents[1] / "app.py").run()


@pytest.fixture
def orientation_calls(monkeypatch):
    calls = []

    def orient(image):
        calls.append((image.size, image.tobytes()))
        result = image.transpose(Image.Transpose.TRANSPOSE)
        return SimpleNamespace(
            image=result,
            rectangle=SimpleNamespace(
                corners=((0, 0), (image.width, 0), image.size, (0, image.height))
            ),
            counterclockwise_degrees=90.0,
            outline_complete=True,
            supported_edges=(),
        )

    monkeypatch.setattr(image_io, "orient_gel", orient)
    return calls


def upload(app, size=(19, 13), color=40):
    source = BytesIO()
    Image.new("L", size, color).save(source, format="TIFF")
    app.file_uploader[0].set_value(("gel.tif", source.getvalue(), "image/tiff")).run()


def button_keys(app):
    return {button.key for button in app.button}


def assert_orientation_reset(app):
    assert app.session_state["orientation_preview"] is None
    assert app.session_state["orientation_requested"] is False
    assert app.session_state["orientation_error"] is None
    assert app.session_state["orientation_manual"] is False
    assert app.session_state["orientation_selection"] is None
    assert app.session_state["orientation_revision"] == 0
    assert app.session_state["orientation_manual_error"] is None
    assert "confirm_orientation" not in button_keys(app)


def test_rotate_previews_without_accepting_and_confirm_keeps_result(app, orientation_calls):
    assert "rotate_and_orient" not in button_keys(app)
    upload(app)
    first_crop = app.session_state["gel_image"]
    first_preview = app.get("image")[0].proto
    assert first_crop.orientation is None
    assert "rotate_and_orient" in button_keys(app)
    assert "confirm_orientation" not in button_keys(app)

    app.button(key="rotate_and_orient").click().run()

    assert not app.exception
    assert not app.error
    candidate = app.session_state["orientation_preview"]
    assert candidate.orientation is not None
    assert app.session_state["gel_image"] is first_crop
    assert app.text[0].value == "gel.tif · 9 × 15 pixels"
    assert app.get("image")[0].proto != first_preview
    assert "confirm_orientation" in button_keys(app)
    assert "rotate_and_orient" not in button_keys(app)
    assert app.session_state["orientation_preview_method"] == "automatic"
    assert "adjust_orientation_manually" in button_keys(app)
    assert len(orientation_calls) == 1
    staged_preview = app.get("image")[0].proto

    app.run()
    assert len(orientation_calls) == 1
    assert app.session_state["orientation_preview"] is candidate

    app.button(key="confirm_orientation").click().run()

    assert not app.exception
    assert not app.error
    accepted = app.session_state["gel_image"]
    assert accepted.orientation is not None
    assert accepted.preview_png == candidate.preview_png
    assert accepted.source_bytes == first_crop.source_bytes
    assert app.get("image")[0].proto == staged_preview
    assert app.text[0].value == "gel.tif · 9 × 15 pixels"
    assert "rotate_and_orient" not in button_keys(app)
    assert_orientation_reset(app)
    app.run()
    assert app.session_state["gel_image"] is accepted
    assert app.get("image")[0].proto == staged_preview
    assert len(orientation_calls) == 1


def test_failed_orientation_restores_first_crop_and_can_be_retried(
    app, orientation_calls, monkeypatch
):
    upload(app)
    first_crop = app.session_state["gel_image"]
    real_orient = image_io.orient_gel
    app.button(key="rotate_and_orient").click().run()
    assert app.session_state["orientation_preview"] is not None

    def fail(image):
        raise OrientationError("The gel outline could not be fitted confidently.")

    monkeypatch.setattr(image_io, "orient_gel", fail)
    app.button(key="adjust_orientation_manually").click().run()
    assert app.button(key="rotate_and_orient").label == "Automatic orientation"
    app.button(key="rotate_and_orient").click().run()

    assert not app.exception
    assert not app.error
    assert len(app.warning) == 1
    assert "Draw the gel outline" in app.warning[0].value
    assert app.session_state["gel_image"] is first_crop
    assert app.session_state["orientation_preview"] is None
    assert app.session_state["orientation_manual"] is True
    assert app.session_state["orientation_selection"] is None
    assert not app.get("image")
    assert app.button(key="preview_manual_orientation").disabled
    assert "rotate_and_orient" in button_keys(app)
    assert "confirm_orientation" not in button_keys(app)

    monkeypatch.setattr(image_io, "orient_gel", real_orient)
    app.button(key="rotate_and_orient").click().run()
    assert not app.exception
    assert not app.error
    assert app.session_state["orientation_preview"] is not None
    assert app.session_state["orientation_error"] is None
    assert app.session_state["orientation_manual"] is False
    assert not app.warning
    assert "confirm_orientation" in button_keys(app)


@pytest.mark.parametrize("state", ["staged", "confirmed", "failed"])
@pytest.mark.parametrize("change", ["clear", "remove", "replace", "invalid"])
def test_changing_upload_resets_orientation_state(
    app, orientation_calls, monkeypatch, state, change
):
    upload(app)
    if state == "failed":
        def fail(image):
            raise OrientationError("Cannot fit the gel outline.")

        monkeypatch.setattr(image_io, "orient_gel", fail)
    app.button(key="rotate_and_orient").click().run()
    if state == "confirmed":
        app.button(key="confirm_orientation").click().run()

    if change == "clear":
        app.button(key="clear_image").click().run()
    elif change == "remove":
        app.file_uploader[0].set_value(None).run()
    elif change == "replace":
        upload(app, size=(23, 17), color=120)
    else:
        app.file_uploader[0].set_value(("gel.tif", b"not a TIFF", "image/tiff")).run()

    assert not app.exception
    assert_orientation_reset(app)
    if change == "replace":
        gel = app.session_state["gel_image"]
        assert gel.orientation is None
        assert (gel.preview_width, gel.preview_height) == (19, 13)
        assert len(app.get("image")) == 1
        assert "rotate_and_orient" in button_keys(app)
        assert not app.error
    else:
        assert app.session_state["gel_image"] is None
        assert not app.get("image")
        assert "rotate_and_orient" not in button_keys(app)
        assert len(app.error) == (1 if change == "invalid" else 0)
