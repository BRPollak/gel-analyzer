"""Reachable project controls snapshot current edits and restore usable workflows."""

from copy import deepcopy

import pytest

from gel_analyzer import project_ui
from gel_analyzer.projects import load_project, save_project
from test_annotation_app import annotated, annotation_event, crop_gel
from test_lane_app import REVIEWED_LANES, lane_event, start_review, upload, workflow
from test_ladder_app import confirm_ladder, ladder_snapshot
from test_projects import project_state


@pytest.fixture
def snapshots(monkeypatch):
    saved = []

    def capture(state):
        result = save_project(state)
        saved.append(result)
        return result

    monkeypatch.setattr(project_ui, "save_project", capture)
    return saved


def reopen(app, payload):
    app.file_uploader(key="project_upload").set_value(
        ("saved.gel.json", payload, "application/json"),
    ).run()
    assert not app.exception


def test_first_image_upload_immediately_offers_a_valid_project(workflow, snapshots):
    original = upload(workflow)
    assert any(button.key == "save_project" for button in workflow.app.get("download_button"))
    assert load_project(snapshots[-1])["gel_image"].source_bytes == original


def test_save_captures_pending_outline_and_well_events(workflow, snapshots):
    upload(workflow)
    app = workflow.app
    app.button(key="adjust_orientation_manually").click().run()
    token = app.session_state["orientation_token"]
    selection = dict(cx=100.0, cy=150.0, width=180.0, height=270.0, angle_degrees=0.0)
    app.session_state[f"orientation_overlay_{token}"] = dict(token=token, revision=1, selection=selection)
    app.run()
    assert load_project(snapshots[-1])["orientation_selection"] == selection
    app.button(key="rotate_and_orient").click().run()
    app.button(key="confirm_orientation").click().run()
    app.button(key="define_wells").click().run()
    token = app.session_state["well_token"]
    app.session_state[f"well_overlay_{token}"] = dict(token=token, revision=1, points=[[38, 20], [40, 112]])
    app.run()
    assert load_project(snapshots[-1])["well_points"] == ((38.0, 20.0), (38.0, 112.0))


def test_save_captures_pending_lane_extent(workflow, snapshots):
    start_review(workflow)
    app = workflow.app
    lane_event(workflow)
    app.button(key="confirm_lane_borders").click().run()
    lanes = tuple((left, top, 235, bottom) for left, top, _, bottom in REVIEWED_LANES)
    lane_event(workflow, lanes=lanes, right_edge=235, run=False)
    app.run()
    restored = load_project(snapshots[-1])
    assert restored["lane_right"] == 235
    assert restored["lane_stage"] == "extent"


def test_save_captures_pending_annotations_and_ladder_draft(annotated, snapshots):
    crop_gel(annotated)
    app = annotated.app
    pending = annotation_event(annotated, run=False)
    app.run()
    assert load_project(snapshots[-1])["annotation_data"]["labels"] == pending["annotations"]["labels"]
    annotation_event(annotated, action="confirm", revision=2)
    app.button(key="annotate_ladder").click().run()
    token = app.session_state["annotation_token"]
    draft = ladder_snapshot(99.25)
    app.session_state[f"annotation_editor_{token}"] = {
        "kind": "ladder", "action": "edit", "token": token, "revision": 1,
        "ladder": draft, "ladder_step": "markers",
    }
    app.run()
    restored = load_project(snapshots[-1])
    assert restored["ladder_draft"] == draft
    assert restored["annotation_stage"] == "ladder"


def test_reopening_export_keeps_pixels_and_allows_further_edits(annotated, snapshots):
    confirm_ladder(annotated)
    app = annotated.app
    app.run()  # Component harness events become semantic state during rendering.
    saved = snapshots[-1]
    png = app.session_state["annotation_png"]
    old_token = app.session_state["annotation_token"]
    old_uploader = app.session_state["uploader_generation"]
    reopen(app, saved)
    assert not app.error
    assert app.session_state["annotation_png"] == png
    assert app.session_state["annotation_stage"] == "final"
    assert app.session_state["annotation_token"] != old_token
    assert app.session_state["uploader_generation"] == old_uploader + 1
    assert not app.button(key="workflow_step_3").disabled
    assert any(button.key == "download_annotations" for button in app.get("download_button"))
    app.button(key="edit_annotations").click().run()
    assert not app.exception
    assert app.session_state["annotation_stage"] == "lanes"
    assert app.session_state["annotation_png"] is None


def test_invalid_project_upload_preserves_current_analysis(workflow):
    app = workflow.app
    state = project_state("wells_top", 45)
    reopen(app, save_project(state))
    before = deepcopy(app.session_state["annotation_data"])
    gel = app.session_state["gel_image"]
    reopen(app, b"not a valid project")
    assert app.error
    assert app.session_state["gel_image"] is gel
    assert app.session_state["annotation_data"] == before
    assert app.session_state["lane_stage"] == "cropped"
