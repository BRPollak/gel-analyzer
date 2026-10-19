"""Progress navigation retains drafts and invalidates changed geometry safely."""

from copy import deepcopy
from io import BytesIO
from types import SimpleNamespace

import numpy as np
from PIL import Image
import pytest

from gel_analyzer import image_io
from gel_analyzer.orientation import OrientationError
from test_annotation_app import annotated, annotation_event, crop_gel
from test_lane_app import REVIEWED_LANES, lane_event, start_review, upload, workflow
from test_ladder_app import confirm_ladder, ladder_snapshot, open_ladder


def progress(app):
    return [app.button(key=f"workflow_step_{index}") for index in range(4)]


def go(app, index):
    app.button(key=f"workflow_step_{index}").click().run()
    assert not app.exception


def test_progress_only_enables_reached_stages(annotated):
    app = annotated.app
    assert all(button.disabled for button in progress(app))
    upload(annotated.workflow)
    assert [button.disabled for button in progress(app)] == [False, True, True, True]
    app.button(key="rotate_and_orient").click().run()
    assert [button.disabled for button in progress(app)] == [False, True, True, True]
    app.button(key="confirm_orientation").click().run()
    assert [button.disabled for button in progress(app)] == [False, False, True, True]
    crop_gel(annotated)
    assert [button.disabled for button in progress(app)] == [False, False, False, True]
    annotation_event(annotated, action="confirm")
    app.button(key="skip_ladder").click().run()
    assert not any(button.disabled for button in progress(app))


def test_define_lanes_opens_guide_without_a_previous_detection(workflow):
    upload(workflow)
    app = workflow.app
    app.button(key="rotate_and_orient").click().run()
    app.button(key="confirm_orientation").click().run()
    go(app, 1)
    assert app.session_state["well_editing"]
    assert app.button(key="confirm_well_line").disabled


def test_return_to_lanes_captures_pending_labels_and_rejects_removed_editor_events(annotated):
    crop_gel(annotated)
    app = annotated.app
    pending = annotation_event(annotated, run=False)
    token = app.session_state["annotation_token"]
    go(app, 1)
    assert app.session_state["lane_stage"] == "borders"
    assert app.session_state["lane_crop"] is None
    assert app.session_state["annotation_data"]["labels"] == pending["annotations"]["labels"]
    assert app.session_state["annotation_token"] != token
    saved = deepcopy(app.session_state["annotation_data"])
    annotated.event = {**pending, "revision": 999, "annotations": {}}
    app.button(key="confirm_lane_borders").click().run()
    app.button(key="confirm_lane_crop").click().run()
    assert not app.exception
    assert app.session_state["annotation_data"] == saved


def test_return_to_borders_captures_pending_extent(workflow):
    start_review(workflow)
    app = workflow.app
    lane_event(workflow)
    app.button(key="confirm_lane_borders").click().run()
    token = app.session_state["lane_token"]
    lanes = tuple((left, top, 235, bottom) for left, top, _, bottom in REVIEWED_LANES)
    lane_event(workflow, lanes=lanes, right_edge=235, run=False)
    go(app, 1)
    assert app.session_state["lane_stage"] == "borders"
    assert app.session_state["lane_right"] == 235
    assert app.session_state["lane_token"] != token


def test_export_to_annotations_preserves_ladder_and_invalidates_confirmed_output(annotated):
    crop = confirm_ladder(annotated)
    app = annotated.app
    ladder = deepcopy(app.session_state["ladder_data"])
    labels = deepcopy(app.session_state["annotation_data"])
    go(app, 2)
    assert app.session_state["annotation_stage"] == "lanes"
    assert app.session_state["annotation_png"] is None
    assert app.session_state["ladder_data"] == ladder
    assert app.session_state["annotation_data"] == labels
    assert app.session_state["lane_crop"] is crop
    assert progress(app)[3].disabled


def test_annotation_progress_preserves_pending_ladder_draft_for_resuming(annotated):
    open_ladder(annotated)
    app = annotated.app
    token = app.session_state["annotation_token"]
    draft = ladder_snapshot(99.25)
    event = {
        "kind": "ladder", "action": "edit", "token": token, "revision": 1,
        "ladder": draft, "ladder_step": "markers",
    }
    app.session_state[f"annotation_editor_{token}"] = event
    go(app, 2)
    assert app.session_state["annotation_stage"] == "lanes"
    assert app.session_state["ladder_draft"] == draft
    assert app.session_state["ladder_data"] is None
    assert app.session_state["annotation_token"] != token
    annotation_event(annotated, action="confirm")
    app.button(key="annotate_ladder").click().run()
    assert not app.exception
    assert annotated.renders[-1][1]["ladder"] == draft
    assert annotated.renders[-1][1]["ladder_step"] == "markers"


@pytest.mark.parametrize("resume", ["confirm_orientation", "keep_previous_orientation", "automatic"])
def test_orient_restores_original_pixels_and_unchanged_orientation_retains_analysis(annotated, resume):
    crop = confirm_ladder(annotated)
    app = annotated.app
    gel = app.session_state["gel_image"]
    output = app.session_state["annotation_png"]
    labels = deepcopy(app.session_state["annotation_data"])
    old_tokens = {kind: app.session_state[f"{kind}_token"] for kind in ("well", "lane", "annotation")}
    go(app, 0)
    source = app.session_state["gel_image"]
    assert source.orientation is None
    assert source.source_bytes == gel.source_bytes
    assert [button.disabled for button in progress(app)] == [False, True, True, True]
    with Image.open(BytesIO(source.source_bytes)) as original, Image.open(BytesIO(source.preview_png)) as preview:
        original.load()
        assert np.array_equal(np.asarray(preview), np.asarray(original.crop(source.crop_box)))
        assert np.asarray(preview).dtype == np.uint16
    for kind, old_token in old_tokens.items():
        assert app.session_state[f"{kind}_token"] != old_token
    if resume == "automatic":
        app.button(key="rotate_and_orient").click().run()
        resume = "confirm_orientation"
    app.button(key=resume).click().run()
    assert not app.exception
    assert app.session_state["gel_image"] is gel
    assert app.session_state["lane_source"] is gel
    assert app.session_state["lane_crop"] is crop
    assert app.session_state["annotation_data"] == labels
    assert app.session_state["annotation_png"] == output
    assert app.session_state["annotation_stage"] == "final"


def test_changed_orientation_invalidates_downstream_only_on_confirmation(annotated, monkeypatch):
    crop = confirm_ladder(annotated)
    app = annotated.app
    go(app, 0)

    def changed(image):
        return SimpleNamespace(
            image=image.transpose(Image.Transpose.ROTATE_90),
            rectangle=SimpleNamespace(corners=((0, 0), (image.width, 0), image.size, (0, image.height))),
            counterclockwise_degrees=90.0,
            outline_complete=True,
            supported_edges=(),
        )

    monkeypatch.setattr(image_io, "orient_gel", changed)
    app.button(key="rotate_and_orient").click().run()
    assert app.session_state["lane_crop"] is crop
    assert app.session_state["annotation_png"] is not None
    app.button(key="confirm_orientation").click().run()
    assert not app.exception
    assert app.session_state["well_points"] == ()
    assert app.session_state["lane_crop"] is None
    assert app.session_state["annotation_data"] is None
    assert app.session_state["ladder_data"] is None
    assert [button.disabled for button in progress(app)] == [False, False, True, True]


def test_failed_orientation_revision_can_return_to_saved_analysis(annotated, monkeypatch):
    crop = crop_gel(annotated)
    app = annotated.app
    pending = annotation_event(annotated, run=False)
    go(app, 0)

    def fail(image):
        raise OrientationError("No reliable boundary.")

    monkeypatch.setattr(image_io, "orient_gel", fail)
    app.button(key="rotate_and_orient").click().run()
    assert app.session_state["orientation_manual"]
    app.button(key="keep_previous_orientation").click().run()
    assert not app.exception
    assert app.session_state["lane_crop"] is crop
    assert app.session_state["annotation_data"]["labels"] == pending["annotations"]["labels"]
    assert app.session_state["orientation_error"] is None


def test_upload_replacement_discards_suspended_orientation_and_analysis(annotated):
    crop_gel(annotated)
    app = annotated.app
    go(app, 0)
    upload(annotated.workflow, offset=10)
    assert not app.exception
    assert app.session_state["orientation_previous_gel"] is None
    assert app.session_state["lane_crop"] is None
    assert app.session_state["annotation_data"] is None
    assert app.session_state["gel_image"].orientation is None


def test_orientation_return_restores_exact_initial_crop_without_redetection(workflow, monkeypatch):
    crops = []

    def detect_crop(image):
        crops.append(image.size)
        return (2, 3, image.width - 2, image.height - 1)

    monkeypatch.setattr(image_io, "find_gel_crop", detect_crop)
    upload(workflow)
    app = workflow.app
    source = app.session_state["gel_image"]
    app.button(key="rotate_and_orient").click().run()
    app.button(key="confirm_orientation").click().run()
    go(app, 0)
    restored = app.session_state["gel_image"]
    assert restored == source
    assert crops == [(200, 300)]
    assert restored.crop_box == (2, 3, 198, 299)


def test_orientation_return_preserves_last_pointer_edit_in_well_guide(workflow):
    upload(workflow)
    app = workflow.app
    app.button(key="rotate_and_orient").click().run()
    app.button(key="confirm_orientation").click().run()
    app.button(key="define_wells").click().run()
    token = app.session_state["well_token"]
    pending = {"token": token, "revision": 1, "points": [[38, 20], [38, 112]]}
    app.session_state[f"well_overlay_{token}"] = pending
    go(app, 0)
    app.button(key="keep_previous_orientation").click().run()
    assert not app.exception
    assert app.session_state["well_points"] == ((38, 20), (38, 112))
    assert app.session_state["well_editing"]
    workflow.event = {**pending, "revision": 999, "points": [[45, 30], [45, 100]]}
    app.run()
    assert app.session_state["well_points"] == ((38, 20), (38, 112))
