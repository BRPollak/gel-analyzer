"""Keep partial-edge previews explicit and stable through workflow navigation."""

from io import BytesIO
from pathlib import Path
from types import SimpleNamespace

import numpy as np
from PIL import Image
import pytest
from streamlit.testing.v1 import AppTest

from gel_analyzer import image_io, orientation_ui, orientation
from test_partial_orientation import partial_gel


@pytest.fixture
def partial_workflow(monkeypatch):
    harness = SimpleNamespace(event=None, calls=[])
    real_orient = image_io.orient_gel

    def orient(image, **kwargs):
        harness.calls.append(kwargs.copy())
        # Detection is covered by the partial-edge image tests. Exercise actual
        # sampling and all app callbacks with a known supported tilt here.
        if "rectangle" not in kwargs:
            kwargs.setdefault("fallback_angle_degrees", 8.0)
            kwargs.setdefault("supported_edges", ("left", "top", "right"))
        return real_orient(image, **kwargs)

    monkeypatch.setattr(image_io, "orient_gel", orient)
    monkeypatch.setattr(image_io, "find_gel_crop", lambda image: (0, 0, *image.size))
    monkeypatch.setattr(orientation_ui, "render_orientation_component", lambda *args, **kwargs: harness.event)
    app = harness.app = AppTest.from_file(Path(__file__).parents[1] / "app.py").run()
    source = BytesIO()
    pixels = (np.arange(100 * 120).reshape(120, 100) * 5).astype(np.uint16)
    Image.fromarray(pixels).save(source, format="TIFF")
    app.file_uploader[0].set_value(("partial.tif", source.getvalue(), "image/tiff")).run()
    assert not app.exception
    return harness


@pytest.mark.parametrize("mode", ["wells_left", "wells_top"])
def test_partial_preview_requires_confirmation_and_retains_metadata(partial_workflow, mode):
    app = partial_workflow.app
    app.selectbox(key="workflow_orientation_choice").select(mode).run()
    initial = app.session_state["gel_image"]
    app.button(key="rotate_and_orient").click().run()
    assert not app.exception
    preview = app.session_state["orientation_preview"]
    assert app.session_state["gel_image"] is initial
    assert not preview.orientation.outline_complete
    assert preview.orientation.supported_edges == ("left", "top", "right")
    assert any("full initial crop is retained" in info.value for info in app.info)
    assert not app.session_state["orientation_manual"]
    app.button(key="confirm_orientation").click().run()
    assert not app.exception
    assert app.session_state["gel_image"] is preview
    assert app.button(key="define_wells")
    app.button(key="workflow_step_0").click().run()
    assert app.session_state["orientation_previous_gel"] is preview
    app.button(key="confirm_orientation").click().run()
    assert app.session_state["gel_image"] is preview


def test_switching_partial_orientation_reuses_tilt_without_cropping(partial_workflow):
    app = partial_workflow.app
    app.button(key="rotate_and_orient").click().run()
    left = app.session_state["orientation_preview"]
    app.selectbox(key="workflow_orientation_choice").select("wells_top").run()
    assert not app.exception
    top = app.session_state["orientation_preview"]
    assert partial_workflow.calls[-1] == {
        "workflow_orientation": "wells_top", "fallback_angle_degrees": 8.0,
        "supported_edges": ("left", "top", "right"),
    }
    assert top.orientation.counterclockwise_degrees == pytest.approx(8)
    assert not top.orientation.outline_complete
    assert top.orientation.size == left.orientation.size[::-1]
    with Image.open(BytesIO(left.preview_png)) as first, Image.open(BytesIO(top.preview_png)) as second:
        np.testing.assert_array_equal(np.asarray(first), np.asarray(second).T)
    app.selectbox(key="workflow_orientation_choice").select("wells_left").run()
    assert app.session_state["orientation_preview"] == left


def test_manual_crop_does_not_seed_missing_sides_and_can_cancel(partial_workflow):
    app = partial_workflow.app
    app.button(key="rotate_and_orient").click().run()
    partial = app.session_state["orientation_preview"]
    app.button(key="adjust_orientation_manually").click().run()
    assert not app.exception
    assert app.session_state["orientation_selection"] is None
    assert app.button(key="preview_manual_orientation").disabled
    app.button(key="cancel_manual_orientation").click().run()
    assert app.session_state["orientation_preview"] is partial
    app.button(key="adjust_orientation_manually").click().run()
    partial_workflow.event = {
        "token": app.session_state["orientation_token"], "revision": 1,
        "selection": dict(cx=50, cy=60, width=60, height=70, angle_degrees=8),
    }
    app.run()
    app.button(key="preview_manual_orientation").click().run()
    assert not app.exception
    assert app.session_state["orientation_preview"].orientation.outline_complete
    assert app.session_state["orientation_preview"].orientation.size == (70, 60)


@pytest.mark.parametrize("mode,other", [("wells_left", "wells_top"), ("wells_top", "wells_left")])
def test_real_detected_partial_mode_roundtrip_keeps_accepted_analysis(monkeypatch, mode, other):
    app = AppTest.from_file(Path(__file__).parents[1] / "app.py").run()
    source = BytesIO()
    partial_gel(13).save(source, format="TIFF")
    app.file_uploader[0].set_value(("partial.tif", source.getvalue(), "image/tiff")).run()
    app.selectbox(key="workflow_orientation_choice").select(mode).run()
    app.button(key="rotate_and_orient").click().run()
    assert not app.exception
    accepted = app.session_state["orientation_preview"]
    assert not accepted.orientation.outline_complete
    app.button(key="confirm_orientation").click().run()
    points = ((20, 30), (60, 30)) if mode == "wells_top" else ((30, 20), (30, 60))
    app.session_state["well_points"] = points
    app.button(key="workflow_step_0").click().run()

    def unexpected(*args, **kwargs):
        pytest.fail("Changing the workflow selector must reuse the accepted tilt.")

    monkeypatch.setattr(orientation, "fit_gel_rectangle", unexpected)
    monkeypatch.setattr(orientation, "fit_partial_gel_edges", unexpected)
    app.selectbox(key="workflow_orientation_choice").select(other).run()
    assert app.button(key="confirm_orientation").label == "Confirm orientation and reset analysis"
    app.selectbox(key="workflow_orientation_choice").select(mode).run()
    assert not app.exception
    assert app.session_state["orientation_preview"] is accepted
    assert app.button(key="confirm_orientation").label == "Confirm"
    app.button(key="confirm_orientation").click().run()
    assert app.session_state["gel_image"] is accepted
    assert app.session_state["well_points"] == points
