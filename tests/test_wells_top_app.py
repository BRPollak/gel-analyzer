"""Real wells-at-top app workflow; only browser component events are simulated."""

from copy import deepcopy
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace

import numpy as np
from PIL import Image
import pytest
from streamlit.testing.v1 import AppTest

from gel_analyzer import annotation_component, orientation_ui, well_component
from gel_analyzer.projects import load_project, save_project


@pytest.fixture
def workflow(monkeypatch):
    harness = SimpleNamespace(well_event=None, orientation_event=None, annotation_event=None,
                              wells=[], orientations=[], annotations=[])

    def wells(*args, **kwargs):
        harness.wells.append((args, kwargs))
        return harness.well_event

    def orientation(*args, **kwargs):
        harness.orientations.append((args, kwargs))
        return harness.orientation_event

    def annotations(*args, **kwargs):
        harness.annotations.append((args, kwargs))
        return harness.annotation_event

    monkeypatch.setattr(well_component, "render_well_component", wells)
    monkeypatch.setattr(orientation_ui, "render_orientation_component", orientation)
    monkeypatch.setattr(annotation_component, "render_annotation_component", annotations)
    harness.app = AppTest.from_file(Path(__file__).parents[1] / "app.py").run()
    return harness


def upload(workflow):
    values = np.full((360, 310), 120, dtype=np.uint16)
    for left, right in ((30, 66), (100, 136), (170, 206), (240, 276)):
        values[36:54, left:right] = 200
        for top, bottom in ((136, 150), (230, 243)):
            values[top:bottom, left:right] = 40
    values = values * 193 + 17
    stream = BytesIO()
    Image.fromarray(values).save(stream, format="TIFF")
    workflow.app.file_uploader[0].set_value(("vertical.tif", stream.getvalue(), "image/tiff")).run()
    assert not workflow.app.exception
    assert not workflow.app.error
    assert workflow.app.session_state["gel_image"].crop_box == (0, 0, 310, 360)
    return values


def confirm_top(workflow):
    app = workflow.app
    pixels = upload(workflow)
    app.selectbox(key="workflow_orientation_choice").select("wells_top").run()
    assert not app.exception
    assert app.selectbox(key="workflow_orientation_choice").label == "Workflow orientation"
    app.button(key="keep_displayed_orientation").click().run()
    preview = app.session_state["orientation_preview"]
    assert preview.orientation.size == (310, 360)
    assert preview.orientation.counterclockwise_degrees == 0
    with Image.open(BytesIO(preview.preview_png)) as image:
        np.testing.assert_array_equal(np.asarray(image), pixels)
    app.button(key="confirm_orientation").click().run()
    assert not app.exception
    assert app.session_state["gel_image"] is preview
    return pixels


def detect_and_crop(workflow):
    app = workflow.app
    pixels = confirm_top(workflow)
    app.button(key="define_wells").click().run()
    workflow.well_event = {"token": app.session_state["well_token"], "revision": 1,
                           "points": [[26, 45], [280, 45]]}
    app.run()
    app.button(key="confirm_well_line").click().run()
    assert not app.exception
    result = app.session_state["well_result"]
    assert len(result.wells) == 4
    np.testing.assert_allclose([lane[::2] for lane in result.lanes],
                               [(30, 66), (100, 136), (170, 206), (240, 276)], atol=1)
    assert all(lane[3] == 360 for lane in result.lanes)
    assert workflow.wells[-1][1]["workflow_orientation"] == "wells_top"
    app.button(key="adjust_lane_borders").click().run()
    assert any("left and right borders" in caption.value for caption in app.caption)
    edited = [list(lane) for lane in result.lanes]
    edited[0][0], edited[0][2] = 25, 71
    workflow.well_event = {"token": app.session_state["lane_token"], "revision": 1,
                           "kind": "lane_review", "mode": "borders", "lanes": edited, "right_edge": 360}
    app.run()
    assert app.session_state["lane_wells"][0].bounds == (25, 36, 71, 54)
    app.button(key="confirm_lane_borders").click().run()
    edited = [[left, top, right, 310] for left, top, right, _ in edited]
    workflow.well_event = {"token": app.session_state["lane_token"], "revision": 1,
                           "kind": "lane_review", "mode": "extent", "lanes": edited, "right_edge": 310}
    app.run()
    assert app.subheader[0].value == "Define bottom of lanes"
    app.button(key="confirm_lane_crop").click().run()
    assert not app.exception
    crop = app.session_state["lane_crop"]
    assert crop.workflow_orientation == "wells_top"
    assert crop.crop_box == (22, 32, 280, 310)
    with Image.open(BytesIO(crop.preview_png)) as image:
        np.testing.assert_array_equal(np.asarray(image), pixels[32:310, 22:280])
    return crop


def edit_annotations(workflow, angle):
    app = workflow.app
    annotations = deepcopy(app.session_state["annotation_data"])
    annotations["laneLabelAngle"] = angle
    annotations["labels"][0]["text"] = "Control"
    annotations["labels"][1]["text"] = "Treatment"
    annotations["groups"] = [{"id": "experiment", "set": 0, "lanes": [0, 1],
                              "label": "Experiment", "bold": False, "italic": False, "color": "#123456"}]
    workflow.annotation_event = {"token": app.session_state["annotation_token"], "revision": 1,
                                 "kind": "annotations", "action": "edit", "annotations": annotations}
    app.run()
    assert not app.exception
    assert app.session_state["annotation_data"] == annotations
    return annotations


def test_selector_remains_available_during_manual_outline_and_keeps_the_live_rectangle(workflow):
    app = workflow.app
    pixels = upload(workflow)
    assert app.session_state["gel_image"].workflow_orientation == "wells_left"
    assert app.selectbox(key="workflow_orientation_choice").options == ["Wells at left", "Wells at top"]
    app.button(key="adjust_orientation_manually").click().run()
    selection = {"cx": 155., "cy": 180., "width": 280., "height": 320., "angle_degrees": 0.}
    workflow.orientation_event = {"token": app.session_state["orientation_token"], "revision": 1,
                                  "selection": selection}
    app.run()
    app.selectbox(key="workflow_orientation_choice").select("wells_top").run()
    assert not app.exception
    assert app.session_state["orientation_selection"] == selection
    assert app.session_state["orientation_manual"]
    assert workflow.orientations[-1][1]["workflow_orientation"] == "wells_top"
    app.button(key="preview_manual_orientation").click().run()
    preview = app.session_state["orientation_preview"]
    assert preview.workflow_orientation == "wells_top"
    assert preview.orientation.size == (280, 320)
    with Image.open(BytesIO(preview.preview_png)) as image:
        np.testing.assert_array_equal(np.asarray(image), pixels[20:340, 15:295])
    app.button(key="confirm_orientation").click().run()
    assert app.session_state["gel_image"] is preview
    assert not app.exception


@pytest.mark.parametrize("angle", [90, 45])
def test_real_detection_manual_crop_and_restored_state_keep_lane_group_associations(workflow, angle):
    crop = detect_and_crop(workflow)
    annotations = edit_annotations(workflow, angle)
    assert all(popover.proto.popover.label != "Project" for popover in workflow.app.get("popover"))
    assert all(button.label != "Save project" for button in workflow.app.get("download_button"))
    snapshot = save_project(workflow.app.session_state)
    reopened = AppTest.from_file(Path(__file__).parents[1] / "app.py").run()
    for key, value in load_project(snapshot).items():
        reopened.session_state[key] = value
    reopened.run()
    assert not reopened.exception
    assert not reopened.error
    assert reopened.session_state["gel_image"].workflow_orientation == "wells_top"
    assert reopened.session_state["lane_crop"] == crop
    assert reopened.session_state["annotation_data"] == annotations
    assert reopened.session_state["lane_source"] is reopened.session_state["gel_image"]
    reopened.button(key="revise_lane_crop").click().run()
    assert not reopened.exception
    assert reopened.session_state["lane_stage"] == "borders"
    assert reopened.session_state["annotation_data"]["groups"][0]["lanes"] == [0, 1]
    reopened.button(key="confirm_lane_borders").click().run()
    reopened.button(key="confirm_lane_crop").click().run()
    assert not reopened.exception
    assert reopened.session_state["lane_crop"] == crop
    assert reopened.session_state["annotation_data"] == annotations


def test_switching_stages_mode_until_explicit_reset_and_return_preserves_existing_analysis(workflow):
    crop = detect_and_crop(workflow)
    annotations = edit_annotations(workflow, 45)
    app = workflow.app
    gel = app.session_state["gel_image"]
    result = app.session_state["well_result"]
    points = app.session_state["well_points"]
    for confirm in (False, True):
        app.button(key="workflow_step_0").click().run()
        app.selectbox(key="workflow_orientation_choice").select("wells_left").run()
        assert not app.exception
        assert app.session_state["gel_image"].workflow_orientation == "wells_left"
        assert app.session_state["orientation_previous_gel"] is gel
        assert app.session_state["lane_crop"] is crop
        assert app.session_state["well_result"] is result
        assert app.session_state["well_points"] == points
        assert app.session_state["annotation_data"] == annotations
        assert any("resets the well selection" in warning.value for warning in app.warning)
        assert app.button(key="confirm_orientation").label == "Confirm orientation and reset analysis"
        if not confirm:
            app.button(key="keep_previous_orientation").click().run()
            assert app.session_state["gel_image"] is gel
            assert app.session_state["lane_crop"] is crop
            assert app.session_state["annotation_data"] == annotations
        else:
            app.button(key="confirm_orientation").click().run()
            assert app.session_state["gel_image"].workflow_orientation == "wells_left"
            assert app.session_state["well_points"] == ()
            assert app.session_state["well_result"] is None
            assert app.session_state["lane_crop"] is None
            assert app.session_state["annotation_data"] is None
            assert app.session_state["ladder_data"] is None
            assert app.session_state["band_data"] is None
        assert not app.exception
