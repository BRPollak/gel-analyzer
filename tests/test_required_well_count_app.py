"""The entered well count is an exact workflow constraint in both orientations.

These tests use real TIFF preparation, well detection, lane validation, and
cropping. Only browser component event boundaries are replaced.
"""

from io import BytesIO
from pathlib import Path
from types import SimpleNamespace

import numpy as np
from PIL import Image
import pytest
from streamlit.testing.v1 import AppTest

from gel_analyzer import annotation_component, orientation_ui, well_component


@pytest.fixture
def workflow(monkeypatch):
    harness = SimpleNamespace(orientation_event=None, well_event=None, well_renders=[])

    def well_editor(*args, **kwargs):
        harness.well_renders.append((args, kwargs))
        return harness.well_event

    monkeypatch.setattr(well_component, "render_well_component", well_editor)
    monkeypatch.setattr(orientation_ui, "render_orientation_component",
                        lambda *args, **kwargs: harness.orientation_event)
    monkeypatch.setattr(annotation_component, "render_annotation_component",
                        lambda *args, **kwargs: None)
    harness.app = AppTest.from_file(Path(__file__).parents[1] / "app.py").run()
    return harness


def _pixels(scene):
    pixels = np.full((360, 310), 120, dtype=np.uint8)
    wells = [(30, 66), (100, 136), (170, 206), (240, 276)]
    if scene == "missing":
        wells.pop(1)
    elif scene == "extra":
        wells.insert(1, (80, 92))
    elif scene == "noise":
        pixels = np.clip(np.random.default_rng(9).normal(120, 5, pixels.shape), 0, 255).astype(np.uint8)
        wells = [wells[0], wells[-1]]
    elif scene == "blank":
        wells = []
    for left, right in wells:
        pixels[36:54, left:right] = 200
        for top, bottom in ((136, 150), (230, 243)):
            pixels[top:bottom, left:right] = 40
    return pixels


def _start_selection(workflow, orientation, scene):
    app = workflow.app
    pixels = _pixels(scene)
    source = BytesIO()
    Image.fromarray(pixels).save(source, format="TIFF")
    app.file_uploader[0].set_value((f"{scene}.tif", source.getvalue(), "image/tiff")).run()
    assert not app.exception
    assert app.session_state["gel_image"].crop_box == (0, 0, 310, 360)
    app.selectbox(key="workflow_orientation_choice").select(orientation).run()
    app.button(key="adjust_orientation_manually").click().run()
    workflow.orientation_event = {
        "token": app.session_state["orientation_token"], "revision": 1,
        "selection": dict(cx=155., cy=180., width=310., height=360., angle_degrees=0.),
    }
    app.run()
    app.button(key="preview_manual_orientation").click().run()
    app.button(key="confirm_orientation").click().run()
    assert not app.exception
    expected = pixels if orientation == "wells_top" else pixels.T
    with Image.open(BytesIO(app.session_state["gel_image"].preview_png)) as preview:
        np.testing.assert_array_equal(np.asarray(preview), expected)
    app.button(key="define_wells").click().run()
    workflow.well_event = {
        "token": app.session_state["well_token"], "revision": 1,
        "points": [[26, 45], [280, 45]] if orientation == "wells_top" else [[45, 26], [45, 280]],
    }
    app.run()
    assert not app.exception
    assert app.number_input(key="expected_well_count").label == "Number of wells"
    assert app.number_input(key="expected_well_count").value is None
    assert app.button(key="confirm_well_line").disabled
    return expected


@pytest.mark.parametrize("orientation", ["wells_left", "wells_top"])
@pytest.mark.parametrize("scene", ["missing", "extra", "noise", "blank"])
def test_required_count_survives_review_crop_and_clearing_requires_new_input(workflow, orientation, scene):
    app = workflow.app
    expected_pixels = _start_selection(workflow, orientation, scene)
    app.number_input(key="expected_well_count").set_value(4).run()
    assert app.session_state["well_expected_count"] == 4
    assert app.session_state["well_result"] is None
    app.button(key="confirm_well_line").click().run()
    assert not app.exception
    assert app.session_state["well_error"] is None
    result = app.session_state["well_result"]
    assert len(result.wells) == len(result.lanes) == 4
    direction = "vertical" if orientation == "wells_top" else "horizontal"
    assert any(message.value == f"Prepared 4 wells and 4 {direction} lanes." for message in app.markdown)
    assert not any(message.value.startswith("Detected 4 wells") for message in app.markdown)
    assert result.warnings
    assert not app.warning  # Users judge well and lane quality from the preview.
    if scene != "extra":
        assert any("infer" in warning.lower() for warning in result.warnings)
    cross_axis = 0 if orientation == "wells_top" else 1
    assert all(first.bounds[cross_axis + 2] <= second.bounds[cross_axis]
               for first, second in zip(result.wells, result.wells[1:]))
    assert workflow.well_renders[-1][1]["lanes"] == result.lanes
    assert len(workflow.well_renders[-1][1]["wells"]) == 4
    app.button(key="adjust_lane_borders").click().run()
    assert not app.exception
    assert len(app.session_state["lane_wells"]) == 4
    app.button(key="confirm_lane_borders").click().run()
    assert not app.exception
    app.button(key="confirm_lane_crop").click().run()
    assert not app.exception
    crop = app.session_state["lane_crop"]
    assert crop.workflow_orientation == orientation
    assert len(crop.lanes) == len(crop.wells) == 4
    assert len(app.session_state["annotation_data"]["labels"]) == 4
    left, top, right, bottom = crop.crop_box
    with Image.open(BytesIO(crop.preview_png)) as preview:
        np.testing.assert_array_equal(np.asarray(preview), expected_pixels[top:bottom, left:right])
    assert app.session_state["well_expected_count"] == 4
    app.button(key="edit_well_line").click().run()
    assert app.number_input(key="expected_well_count").value == 4
    app.number_input(key="expected_well_count").set_value(None).run()
    app.run()
    assert not app.exception
    assert app.session_state["well_expected_count"] is None
    assert app.session_state["well_result"] is None
    assert app.session_state["well_detection_request"] is None
    assert app.button(key="confirm_well_line").disabled
    assert any("Enter the number of wells" in message.value for message in app.info)


@pytest.mark.parametrize("orientation", ["wells_left", "wells_top"])
def test_impossible_required_count_reports_error_instead_of_accepting_wrong_count(workflow, orientation):
    app = workflow.app
    _start_selection(workflow, orientation, "missing")
    app.number_input(key="expected_well_count").set_value(1000).run()
    app.button(key="confirm_well_line").click().run()
    assert not app.exception
    assert app.session_state["well_result"] is None
    assert app.session_state["well_editing"]
    assert app.session_state["well_error"]
    assert any(item.value == app.session_state["well_error"] for item in app.warning)
    assert "confirm_detected_lanes" not in {button.key for button in app.button}
    assert app.number_input(key="expected_well_count").value == 1000


@pytest.mark.parametrize("orientation", ["wells_left", "wells_top"])
def test_retained_old_hint_result_must_be_refitted_before_confirmation(workflow, orientation):
    app = workflow.app
    _start_selection(workflow, orientation, "missing")
    app.number_input(key="expected_well_count").set_value(3).run()
    app.button(key="confirm_well_line").click().run()
    assert len(app.session_state["well_result"].wells) == 3
    # Simulate a live session from before entered counts became mandatory.
    app.session_state["well_expected_count"] = 4
    app.run()
    assert not app.exception
    assert app.button(key="confirm_detected_lanes").disabled
    assert any("earlier result does not match the required 4 wells" in item.value for item in app.warning)
    app.button(key="edit_well_line").click().run()
    app.button(key="confirm_well_line").click().run()
    assert not app.exception
    assert len(app.session_state["well_result"].wells) == 4
    assert not app.button(key="confirm_detected_lanes").disabled


@pytest.mark.parametrize("orientation", ["wells_left", "wells_top"])
def test_missing_count_blocks_confirmation_and_injected_pending_request(workflow, orientation):
    app = workflow.app
    _start_selection(workflow, orientation, "missing")
    points = app.session_state["well_points"]
    assert app.button(key="confirm_well_line").disabled
    app.number_input(key="expected_well_count").set_value(3).run()
    # An event from the previously enabled button must still honor server state.
    app.session_state["well_expected_count"] = None
    app.button(key="confirm_well_line").click().run()
    assert not app.exception
    assert app.session_state["well_result"] is None
    assert app.session_state["well_detection_request"] is None
    app.session_state["well_detection_request"] = (app.session_state["well_token"], points, None)
    app.run()
    assert not app.exception
    assert app.session_state["well_result"] is None
    assert app.session_state["well_detection_request"] is None
    assert app.session_state["well_points"] == points
    assert app.button(key="confirm_well_line").disabled


@pytest.mark.parametrize("orientation", ["wells_left", "wells_top"])
@pytest.mark.parametrize("action", ["confirm_detected_lanes", "adjust_lane_borders"])
def test_live_legacy_result_without_count_cannot_enter_review(workflow, orientation, action):
    app = workflow.app
    _start_selection(workflow, orientation, "missing")
    app.number_input(key="expected_well_count").set_value(3).run()
    app.button(key="confirm_well_line").click().run()
    app.session_state["well_expected_count"] = None
    app.button(key=action).click().run()
    assert not app.exception
    assert app.button(key="confirm_detected_lanes").disabled
    assert app.button(key="adjust_lane_borders").disabled
    app.run()
    assert app.session_state["lane_stage"] is None
    assert any("no required well count" in message.value for message in app.warning)
    app.button(key="edit_well_line").click().run()
    assert app.button(key="confirm_well_line").disabled
