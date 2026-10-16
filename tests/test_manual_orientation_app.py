"""Exercise outline editing and staging through the real Streamlit workflow."""

from io import BytesIO
from pathlib import Path
from types import SimpleNamespace

import numpy as np
from PIL import Image
import pytest
from streamlit.testing.v1 import AppTest

from gel_analyzer import image_io, orientation, orientation_ui
from gel_analyzer.orientation import OrientationError, rectangle_from_selection


AUTO_SELECTION = dict(cx=50, cy=40, width=76, height=50, angle_degrees=8)
MANUAL_SELECTION = dict(cx=50, cy=40, width=60, height=35, angle_degrees=23)


@pytest.fixture
def editor(monkeypatch):
    """Supply browser events while retaining the actual app callbacks/backend."""
    harness = SimpleNamespace(event=None, calls=[])

    def render(png, width, height, **kwargs):
        harness.calls.append(dict(png=png, width=width, height=height, **kwargs))
        return harness.event

    monkeypatch.setattr(orientation_ui, "render_orientation_component", render)
    return harness


@pytest.fixture
def app(monkeypatch, editor):
    monkeypatch.setattr(
        image_io, "find_gel_crop", lambda image: (2, 3, image.width - 2, image.height - 1),
    )
    return AppTest.from_file(Path(__file__).parents[1] / "app.py").run()


@pytest.fixture
def auto_fit(monkeypatch):
    state = SimpleNamespace(fail=False, calls=[])

    def fit(image):
        state.calls.append(image.size)
        if state.fail:
            raise OrientationError("The four gel edges could not be detected.")
        return rectangle_from_selection(AUTO_SELECTION, image.size)

    monkeypatch.setattr(orientation, "fit_gel_rectangle", fit)
    return state


@pytest.fixture
def sampled_sources(monkeypatch):
    calls = []
    orient = image_io.orient_gel

    def record(image, rectangle=None):
        calls.append((image.size, image.tobytes(), rectangle))
        return orient(image, rectangle=rectangle)

    monkeypatch.setattr(image_io, "orient_gel", record)
    return calls


def upload(app, size=(104, 84)):
    # Distinct rows/columns expose accidentally reusing an oriented preview.
    pixels = np.arange(size[0] * size[1], dtype=np.uint16).reshape(size[1], size[0])
    source = BytesIO()
    Image.fromarray(pixels).save(source, format="TIFF")
    app.file_uploader[0].set_value(("gel.tif", source.getvalue(), "image/tiff")).run()


def send_selection(app, editor, selection=MANUAL_SELECTION, revision=1):
    editor.event = dict(
        token=app.session_state["orientation_token"],
        revision=revision,
        selection=selection,
    )
    app.run()
    assert not app.exception


def keys(app):
    return {button.key for button in app.button}


def test_failed_detection_can_draw_rotate_preview_and_confirm(app, editor, auto_fit):
    auto_fit.fail = True
    upload(app)
    source = app.session_state["gel_image"]

    app.button(key="rotate_and_orient").click().run()

    assert not app.exception
    assert not app.error
    assert "manually" in app.warning[0].value
    assert app.session_state["orientation_manual"]
    assert editor.calls[-1]["png"] == source.preview_png
    assert (editor.calls[-1]["width"], editor.calls[-1]["height"]) == (100, 80)
    assert app.button(key="preview_manual_orientation").disabled
    assert "confirm_orientation" not in keys(app)

    send_selection(app, editor)
    assert not app.button(key="preview_manual_orientation").disabled
    app.button(key="preview_manual_orientation").click().run()

    assert not app.exception
    assert not app.warning
    candidate = app.session_state["orientation_preview"]
    assert candidate.orientation is not None
    assert candidate.orientation.size == (35, 60)
    assert candidate.orientation.counterclockwise_degrees == 113
    assert app.session_state["gel_image"] is source
    assert app.session_state["orientation_error"] is None
    assert not app.session_state["orientation_manual"]
    assert len(auto_fit.calls) == 1  # Manual processing bypassed detection.
    assert {"confirm_orientation", "adjust_orientation_manually"} <= keys(app)
    assert "define_wells" not in keys(app)

    app.button(key="confirm_orientation").click().run()

    assert not app.exception
    assert app.session_state["gel_image"] is candidate
    assert candidate.source_bytes == source.source_bytes
    assert app.session_state["orientation_preview"] is None
    assert app.session_state["orientation_selection"] is None
    assert "define_wells" in keys(app)


def test_successful_detection_opens_original_crop_with_seed_and_cancel_keeps_preview(
    app, editor, auto_fit,
):
    upload(app)
    source = app.session_state["gel_image"]
    app.button(key="rotate_and_orient").click().run()
    automatic = app.session_state["orientation_preview"]
    displayed = app.get("image")[0].proto

    app.button(key="adjust_orientation_manually").click().run()

    assert not app.exception
    assert app.session_state["orientation_selection"] == pytest.approx(AUTO_SELECTION)
    assert editor.calls[-1]["selection"] == pytest.approx(AUTO_SELECTION)
    assert editor.calls[-1]["png"] == source.preview_png
    assert app.session_state["orientation_preview"] is automatic
    assert not app.get("image")
    assert "confirm_orientation" not in keys(app)
    assert not app.button(key="preview_manual_orientation").disabled

    send_selection(app, editor)
    app.button(key="cancel_manual_orientation").click().run()

    assert not app.exception
    assert app.session_state["orientation_preview"] is automatic
    assert app.session_state["gel_image"] is source
    assert app.get("image")[0].proto == displayed
    assert app.session_state["orientation_selection"] is None
    assert "confirm_orientation" in keys(app)


def test_reediting_manual_preview_always_samples_original_crop(
    app, editor, auto_fit, sampled_sources,
):
    upload(app)
    source = app.session_state["gel_image"]
    app.button(key="rotate_and_orient").click().run()
    app.button(key="adjust_orientation_manually").click().run()
    send_selection(app, editor)
    app.button(key="preview_manual_orientation").click().run()
    first_manual = app.session_state["orientation_preview"]

    # The last editor event belongs to its old token and must not override the
    # new editor's seed when the same component is opened a second time.
    app.button(key="adjust_orientation_manually").click().run()
    assert editor.calls[-1]["png"] == source.preview_png
    assert app.session_state["orientation_selection"] == pytest.approx(MANUAL_SELECTION)
    assert app.session_state["orientation_revision"] == 0
    edited = dict(cx=40, cy=30, width=30, height=25, angle_degrees=-15)
    send_selection(app, editor, edited)
    app.button(key="preview_manual_orientation").click().run()

    assert not app.exception
    assert app.session_state["gel_image"] is source
    assert app.session_state["orientation_preview"].orientation.size == (25, 30)
    assert app.session_state["orientation_preview"].preview_png != first_manual.preview_png
    assert len(sampled_sources) == 3
    assert all(call[:2] == sampled_sources[0][:2] for call in sampled_sources)
    assert len(auto_fit.calls) == 1


def test_automatic_retry_invalidates_manual_selection(app, editor, auto_fit):
    auto_fit.fail = True
    upload(app)
    app.button(key="rotate_and_orient").click().run()
    send_selection(app, editor)
    token = app.session_state["orientation_token"]
    auto_fit.fail = False

    app.button(key="rotate_and_orient").click().run()

    assert not app.exception
    assert app.session_state["orientation_token"] != token
    assert app.session_state["orientation_selection"] is None
    assert app.session_state["orientation_revision"] == 0
    assert not app.session_state["orientation_manual"]
    assert app.session_state["orientation_error"] is None
    assert app.session_state["orientation_preview"].orientation.size == (50, 76)


def test_bad_or_stale_browser_events_cannot_change_selected_outline(app, editor):
    upload(app)
    app.button(key="adjust_orientation_manually").click().run()
    send_selection(app, editor)
    token = app.session_state["orientation_token"]
    valid = dict(token=token, revision=2, selection=MANUAL_SELECTION)
    bad_events = [
        None, [], "invalid", {},
        {**valid, "token": "previous-image"},
        {**valid, "revision": 1},
        {**valid, "revision": True},
        {**valid, "revision": 2.5},
        {"token": token, "revision": 2},
        {**valid, "selection": {}},
        {**valid, "selection": {**MANUAL_SELECTION, "cx": float("nan")}},
        {**valid, "selection": {**MANUAL_SELECTION, "width": -5}},
        {**valid, "selection": {**MANUAL_SELECTION, "cx": 500}},
        {**valid, "selection": {**MANUAL_SELECTION, "angle_degrees": True}},
    ]
    for event in bad_events:
        editor.event = event
        app.run()
        assert not app.exception, event
        assert app.session_state["orientation_selection"] == pytest.approx(MANUAL_SELECTION)
        assert app.session_state["orientation_revision"] == 1
        assert not app.button(key="preview_manual_orientation").disabled

    send_selection(app, editor, None, revision=2)
    assert app.session_state["orientation_selection"] is None
    assert app.session_state["orientation_revision"] == 2
    assert app.button(key="preview_manual_orientation").disabled


def test_preview_click_consumes_latest_pointer_up_widget_value(app, editor):
    upload(app)
    app.button(key="adjust_orientation_manually").click().run()
    send_selection(app, editor)
    latest = dict(cx=50, cy=40, width=30, height=20, angle_degrees=45)
    token = app.session_state["orientation_token"]
    app.session_state[f"orientation_overlay_{token}"] = dict(
        token=token, revision=2, selection=latest,
    )

    app.button(key="preview_manual_orientation").click().run()

    assert not app.exception
    candidate = app.session_state["orientation_preview"]
    assert candidate.orientation.size == (20, 30)
    assert candidate.orientation.counterclockwise_degrees == 135
    assert np.asarray(candidate.orientation.corners) == pytest.approx(
        np.asarray(rectangle_from_selection(latest, (100, 80)).corners),
    )


@pytest.mark.parametrize("change", ["clear", "remove", "replace", "invalid"])
def test_upload_change_invalidates_outline_and_queued_events(app, editor, change):
    upload(app)
    app.button(key="adjust_orientation_manually").click().run()
    send_selection(app, editor)
    old_token = app.session_state["orientation_token"]

    if change == "clear":
        app.button(key="clear_image").click().run()
    elif change == "remove":
        app.file_uploader[0].set_value(None).run()
    elif change == "replace":
        upload(app, size=(124, 94))
    else:
        app.file_uploader[0].set_value(("gel.tif", b"bad TIFF", "image/tiff")).run()

    assert not app.exception
    assert app.session_state["orientation_token"] != old_token
    assert app.session_state["orientation_selection"] is None
    assert app.session_state["orientation_revision"] == 0
    assert not app.session_state["orientation_manual"]
    assert app.session_state["orientation_preview"] is None
    if change != "replace":
        upload(app, size=(124, 94))
    app.button(key="adjust_orientation_manually").click().run()

    assert not app.exception
    assert app.session_state["orientation_selection"] is None
    assert app.session_state["orientation_revision"] == 0
    assert app.button(key="preview_manual_orientation").disabled
    assert (editor.calls[-1]["width"], editor.calls[-1]["height"]) == (120, 90)
