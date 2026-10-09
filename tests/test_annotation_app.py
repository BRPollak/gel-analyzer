"""Exercise annotations through the existing orientation/lane/crop workflow."""

from copy import deepcopy
from types import SimpleNamespace

import pytest

from gel_analyzer.annotations import default_annotations
from test_annotations import composition, styled_annotations
from test_lane_app import bounds, finish_review, keys, lane_event, start_review, upload, workflow


@pytest.fixture
def annotated(workflow, monkeypatch):
    from gel_analyzer import annotation_component

    harness = SimpleNamespace(event=None, renders=[], workflow=workflow, app=workflow.app)

    def component(crop, **kwargs):
        harness.renders.append((crop, deepcopy(kwargs)))
        return harness.event

    monkeypatch.setattr(annotation_component, "render_annotation_component", component)
    return harness


def crop_gel(annotated):
    start_review(annotated.workflow)
    finish_review(annotated.workflow)
    return annotated.app.session_state["lane_crop"]


def annotation_event(annotated, *, data=None, revision=1, action="edit", run=True, **overrides):
    app = annotated.app
    event = {
        "kind": "annotations", "action": action,
        "token": app.session_state["annotation_token"], "revision": revision,
        "annotations": styled_annotations() if data is None else data,
    }
    if action == "confirm":
        image_event, _ = composition(app.session_state["lane_crop"])
        event.update(image_event)
    event.update(overrides)
    annotated.event = event
    if run:
        app.run()
        assert not app.exception
    else:
        app.session_state[f"annotation_editor_{app.session_state['annotation_token']}"] = event
    return event


def test_crop_automatically_opens_editor_with_translated_lane_coordinates(annotated):
    assert annotated.renders == []
    crop = crop_gel(annotated)
    rendered_crop, args = annotated.renders[-1]
    assert rendered_crop is crop
    assert crop.lanes == ((3, 3, 203, 41), (5, 61, 203, 104))
    assert args["annotations"] == default_annotations(2, lanes=crop.lanes)
    # This fixture's lanes are 38 and 43 pixels high. Their crop-relative
    # coordinates retain native scale, giving a 32-pixel initial label size.
    assert args["annotations"]["fontSize"] == 32
    assert args["revision"] == 0
    assert args["token"] == annotated.app.session_state["annotation_token"]
    assert "revise_lane_crop" in keys(annotated.app)


def test_edit_and_confirm_preserve_styles_groups_and_original_crop(annotated):
    crop = crop_gel(annotated)
    original_bytes = crop.preview_png
    original_source = annotated.app.session_state["gel_image"].source_bytes
    annotation_event(annotated)
    app = annotated.app
    draft = deepcopy(app.session_state["annotation_data"])
    assert draft["labels"][0]["bold"] and draft["labels"][0]["italic"]
    assert {group["set"] for group in draft["groups"]} == {0, 1}
    assert app.session_state["annotation_png"] is None
    assert annotated.renders[-1][1]["annotations"] == draft
    image_event, expected_png = composition(crop)

    annotation_event(annotated, data=draft, action="confirm", revision=2, **image_event)

    assert app.session_state["annotation_png"] == expected_png
    assert app.session_state["annotation_dimensions"] == (383, 131)
    assert "Edit annotations" == app.button(key="edit_annotations").label
    assert any("Annotations confirmed" in success.value for success in app.success)
    assert app.session_state["lane_crop"] is crop
    assert crop.preview_png == original_bytes
    assert app.session_state["gel_image"].source_bytes == original_source


def test_return_to_editing_preserves_complete_snapshot_and_rejects_old_confirmation(annotated):
    crop_gel(annotated)
    old_event = annotation_event(annotated, action="confirm")
    app = annotated.app
    confirmed = deepcopy(app.session_state["annotation_data"])
    old_token = app.session_state["annotation_token"]
    app.button(key="edit_annotations").click().run()
    assert not app.exception
    assert app.session_state["annotation_png"] is None
    assert app.session_state["annotation_token"] != old_token
    assert app.session_state["annotation_data"] == confirmed
    assert annotated.renders[-1][1]["annotations"] == confirmed
    annotated.event = {**old_event, "revision": 999}
    app.run()
    assert app.session_state["annotation_png"] is None
    assert app.session_state["annotation_data"] == confirmed
    annotation_event(annotated, data=confirmed, revision=1, action="confirm")
    assert app.session_state["annotation_png"] is not None


def test_user_font_size_survives_reruns_confirmation_reediting_and_changed_crop(annotated):
    crop_gel(annotated)
    app = annotated.app
    data = deepcopy(app.session_state["annotation_data"])
    data["fontSize"] = 72
    annotation_event(annotated, data=data)
    app.run()
    assert not app.exception
    assert annotated.renders[-1][1]["annotations"]["fontSize"] == 72
    annotation_event(annotated, data=data, action="confirm", revision=2)
    assert app.session_state["annotation_data"]["fontSize"] == 72
    app.button(key="edit_annotations").click().run()
    assert annotated.renders[-1][1]["annotations"]["fontSize"] == 72
    app.button(key="revise_lane_crop").click().run()
    changed_lanes = ((30, 15, 230, 60), (32, 70, 230, 140))
    lane_event(annotated.workflow, lanes=changed_lanes, right_edge=230)
    app.button(key="confirm_lane_borders").click().run()
    app.button(key="confirm_lane_crop").click().run()
    assert not app.exception
    new_crop = app.session_state["lane_crop"]
    assert [lane[3] - lane[1] for lane in new_crop.lanes] == [45, 70]
    assert app.session_state["annotation_data"] == data
    assert annotated.renders[-1][1]["annotations"]["fontSize"] == 72


def test_confirmation_freezes_snapshot_against_delayed_browser_edits(annotated):
    crop_gel(annotated)
    event = annotation_event(annotated, action="confirm")
    app = annotated.app
    frozen = deepcopy(app.session_state["annotation_data"])
    png = app.session_state["annotation_png"]
    annotated.event = {**event, "action": "edit", "revision": 999, "annotations": default_annotations(2)}
    app.run()
    assert app.session_state["annotation_data"] == frozen
    assert app.session_state["annotation_png"] == png


def test_group_edit_membership_change_and_delete_are_saved_independently(annotated):
    crop_gel(annotated)
    annotation_event(annotated)
    data = deepcopy(annotated.app.session_state["annotation_data"])
    data["groups"][0].update(label="Only the treated lane", lanes=[1], color="#ff1234")
    data["groups"][1].update(lanes=[0, 1], bold=True)
    annotation_event(annotated, data=data, revision=2)
    assert annotated.app.session_state["annotation_data"] == data
    data = deepcopy(data)
    data["groups"].pop(0)
    annotation_event(annotated, data=data, revision=3)
    assert annotated.app.session_state["annotation_data"] == data
    assert data["groups"][0]["set"] == 1
    assert data["groups"][0]["lanes"] == [0, 1]


def test_invalid_or_out_of_order_edit_cannot_replace_last_valid_draft(annotated):
    crop_gel(annotated)
    annotation_event(annotated, revision=2)
    app = annotated.app
    accepted = deepcopy(app.session_state["annotation_data"])
    annotation_event(annotated, data=default_annotations(2), revision=1)
    assert app.session_state["annotation_data"] == accepted
    invalid = deepcopy(accepted)
    invalid["groups"][0]["lanes"] = [2]
    annotation_event(annotated, data=invalid, revision=3)
    assert app.session_state["annotation_data"] == accepted
    assert app.session_state["annotation_png"] is None
    assert app.error


@pytest.mark.parametrize("overrides", [
    {"token": "previous-crop"}, {"revision": 0}, {"revision": True},
    {"kind": "lane_review"}, {"action": "delete"},
])
def test_stale_or_unrelated_events_cannot_change_annotations(annotated, overrides):
    crop_gel(annotated)
    before = deepcopy(annotated.app.session_state["annotation_data"])
    annotation_event(annotated, **overrides)
    assert annotated.app.session_state["annotation_data"] == before
    assert annotated.app.session_state["annotation_png"] is None


def test_failed_image_confirmation_keeps_valid_draft_for_retry(annotated):
    crop_gel(annotated)
    annotation_event(annotated, action="confirm", png="data:image/png;base64,broken!")
    app = annotated.app
    assert app.session_state["annotation_png"] is None
    assert app.session_state["annotation_data"]["labels"][0]["text"] == "α control"
    assert app.error
    annotation_event(annotated, revision=2, action="confirm")
    assert app.session_state["annotation_png"] is not None
    assert app.session_state["annotation_error"] is None


def test_revise_crop_consumes_pending_annotation_edit_and_preserves_it(annotated):
    first_crop = crop_gel(annotated)
    pending = annotation_event(annotated, run=False)
    app = annotated.app
    app.button(key="revise_lane_crop").click().run()
    assert not app.exception
    assert app.session_state["annotation_data"]["labels"][0]["text"] == "α control"
    expected = deepcopy(app.session_state["annotation_data"])
    assert app.session_state["annotation_png"] is None
    app.button(key="confirm_lane_borders").click().run()
    app.button(key="confirm_lane_crop").click().run()
    assert not app.exception
    assert app.session_state["lane_crop"] is not first_crop
    assert app.session_state["annotation_data"] == expected
    annotated.event = {**pending, "revision": 999, "annotations": default_annotations(2)}
    app.run()
    assert app.session_state["annotation_data"] == expected


def test_lane_deletion_and_addition_remap_labels_and_both_group_sets(annotated):
    crop_gel(annotated)
    data = styled_annotations()
    data["groups"].append({**data["groups"][0], "id": "deleted-only", "lanes": [0]})
    annotation_event(annotated, data=data, action="confirm")
    app = annotated.app
    app.button(key="revise_lane_crop").click().run()
    lanes = tuple((left, top, 230, bottom) for left, top, _, bottom in bounds(annotated.workflow))
    lane_event(annotated.workflow, lanes=lanes, right_edge=230, action="delete", lane_index=0)
    current = app.session_state["annotation_data"]
    assert current["labels"] == [data["labels"][1]]
    assert {group["id"]: group["lanes"] for group in current["groups"]} == {
        "group-1": [0], "group-2": [0],
    }
    assert {group["set"] for group in current["groups"]} == {0, 1}
    app.button(key="add_lane").click().run()
    assert not app.exception
    assert app.session_state["annotation_data"]["labels"] == [data["labels"][1], default_annotations(2)["labels"][1]]
    app.button(key="confirm_lane_borders").click().run()
    app.button(key="confirm_lane_crop").click().run()
    assert not app.exception
    assert annotated.renders[-1][1]["annotations"] == app.session_state["annotation_data"]
    assert app.session_state["annotation_png"] is None


@pytest.mark.parametrize("clear_upload", [False, True])
def test_changed_or_cleared_upload_discards_annotations_and_stale_events(annotated, clear_upload):
    crop_gel(annotated)
    old_event = annotation_event(annotated, action="confirm")
    app = annotated.app
    if clear_upload:
        app.file_uploader[0].set_value(None).run()
    else:
        upload(annotated.workflow, offset=1000)
    assert not app.exception
    assert app.session_state["annotation_data"] is None
    assert app.session_state["annotation_png"] is None
    assert app.session_state["annotation_token"] != old_event["token"]
    annotated.event = {**old_event, "revision": 999}
    crop = crop_gel(annotated)
    assert app.session_state["annotation_data"] == default_annotations(2, lanes=crop.lanes)
    assert app.session_state["annotation_png"] is None
