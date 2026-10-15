"""Exercise the optional ladder workflow through Streamlit session transitions."""

from copy import deepcopy

import pytest

from gel_analyzer.ladders import LadderError, load_presets
from test_annotation_app import annotated, annotation_event, crop_gel
from test_annotations import composition
from test_lane_app import keys, lane_event, upload, workflow


def ladder_snapshot(x=143.625):
    return {
        "preset": load_presets()[0],
        "laneIndex": 0,
        "placements": [{"markerIndex": 0, "x": x, "y": 28.25}],
    }


def open_ladder(annotated):
    crop = crop_gel(annotated)
    annotation_event(annotated, action="confirm")
    annotated.app.button(key="annotate_ladder").click().run()
    assert not annotated.app.exception
    return crop


def ladder_event(annotated, *, data=None, revision=1, action="edit", step="markers", **overrides):
    app = annotated.app
    event = {
        "kind": "ladder", "action": action, "token": app.session_state["annotation_token"],
        "revision": revision, "ladder": ladder_snapshot() if data is None else data,
        "ladder_step": step,
    }
    if action == "confirm":
        image_event, _ = composition(app.session_state["lane_crop"], gutter=210)
        event.update(image_event)
    event.update(overrides)
    annotated.event = event
    app.run()
    assert not app.exception
    return event


def confirm_ladder(annotated):
    crop = open_ladder(annotated)
    ladder_event(annotated, action="confirm")
    return crop


def test_lane_confirmation_offers_ladder_and_skip_preserves_lane_only_image(annotated):
    crop = crop_gel(annotated)
    app = annotated.app
    original = crop.preview_png
    source = app.session_state["gel_image"].source_bytes
    annotation_event(annotated, action="confirm")
    _, expected_png = composition(crop)
    assert app.session_state["annotation_stage"] == "ladder_offer"
    assert app.session_state["annotation_png"] == expected_png
    assert app.session_state["annotation_base_png"] == expected_png
    assert "annotate_ladder" in keys(app) and "skip_ladder" in keys(app)
    assert not app.get("download_button")
    assert any("Would you like to annotate a ladder?" in item.value for item in app.markdown)

    app.button(key="skip_ladder").click().run()

    assert not app.exception
    assert app.session_state["annotation_stage"] == "final"
    assert app.session_state["annotation_completed"] is True
    assert app.session_state["annotation_png"] == expected_png
    assert app.session_state["ladder_data"] is None
    assert app.get("download_button")[0].label == "Download annotated PNG"
    assert crop.preview_png == original
    assert app.session_state["gel_image"].source_bytes == source


def test_opening_ladder_keeps_existing_annotations_and_starts_without_implicit_preset(annotated):
    crop = open_ladder(annotated)
    app = annotated.app
    render_crop, args = annotated.renders[-1]
    assert render_crop is crop
    assert args["mode"] == "ladder"
    assert args["ladder"] is None
    assert args["ladder_step"] == "preset"
    assert args["confirmed_ladder"] is False
    assert args["presets"] == load_presets()
    assert args["annotations"] == app.session_state["annotation_data"]
    assert app.session_state["annotation_stage"] == "ladder"
    assert app.session_state["annotation_png"] == app.session_state["annotation_base_png"]


@pytest.mark.parametrize("preset_index", [0, 1, 2])
def test_selected_reference_metadata_survives_confirmation_and_reopening(annotated, preset_index):
    open_ladder(annotated)
    data = {**ladder_snapshot(), "preset": load_presets()[preset_index]}
    ladder_event(annotated, data=data, action="confirm")
    assert annotated.app.session_state["ladder_data"] == data
    annotated.app.button(key="edit_ladder").click().run()
    assert not annotated.app.exception
    assert annotated.renders[-1][1]["ladder"] == data


def test_draft_and_step_survive_navigation_without_changing_committed_output(annotated):
    open_ladder(annotated)
    app = annotated.app
    original_png = app.session_state["annotation_png"]
    original_labels = deepcopy(app.session_state["annotation_data"])
    data = ladder_snapshot()
    ladder_event(annotated, data=data)
    assert app.session_state["ladder_draft"] == data
    assert app.session_state["ladder_data"] is None
    ladder_event(annotated, data=data, revision=2, step="lane")
    assert app.session_state["ladder_step"] == "lane"
    assert annotated.renders[-1][1]["ladder"] == data
    ladder_event(annotated, data=data, revision=3, step="preset")
    assert app.session_state["ladder_step"] == "preset"
    assert app.session_state["ladder_draft"] == data
    assert app.session_state["annotation_png"] == original_png
    assert app.session_state["annotation_data"] == original_labels


def test_immediate_confirmation_contains_latest_placement_and_only_commits_once(annotated):
    crop = open_ladder(annotated)
    app = annotated.app
    ladder_event(annotated, data=ladder_snapshot(90.125))
    latest = ladder_snapshot(160.875)
    latest["placements"].append({"markerIndex": 2, "x": 160.875, "y": 30.5})
    # Confirm carries its complete snapshot without needing a preceding edit.
    event = ladder_event(annotated, data=latest, revision=2, action="confirm")
    _, expected_png = composition(crop, gutter=210)
    assert app.session_state["ladder_data"] == latest
    assert app.session_state["ladder_draft"] is None
    assert app.session_state["annotation_stage"] == "final"
    assert app.session_state["annotation_png"] == expected_png
    assert app.session_state["annotation_dimensions"] == (413, 131)
    assert app.button(key="edit_ladder").label == "Edit ladder"
    assert app.get("download_button")[0].label == "Download annotated PNG"
    annotated.event = {**event, "action": "edit", "revision": 999, "ladder": ladder_snapshot(70)}
    app.run()
    assert app.session_state["ladder_data"] == latest
    assert app.session_state["annotation_png"] == expected_png


@pytest.mark.parametrize("committed", [False, True])
def test_cancel_discards_working_draft_and_keeps_last_confirmed_image(annotated, committed):
    if committed:
        confirm_ladder(annotated)
        annotated.app.button(key="edit_ladder").click().run()
    else:
        open_ladder(annotated)
    app = annotated.app
    png = app.session_state["annotation_png"]
    labels = deepcopy(app.session_state["annotation_data"])
    previous = deepcopy(app.session_state["ladder_data"])
    original_token = app.session_state["annotation_token"]
    ladder_event(annotated, data=ladder_snapshot(72.75))
    old_event = ladder_event(annotated, action="cancel", revision=2)
    assert app.session_state["annotation_stage"] == "final"
    assert app.session_state["ladder_draft"] is None
    assert app.session_state["ladder_data"] == previous
    assert app.session_state["annotation_png"] == png
    assert app.session_state["annotation_data"] == labels
    assert app.session_state["annotation_token"] != original_token
    # Reopen, then replay an obsolete editor's final event.
    app.button(key="edit_ladder").click().run()
    annotated.event = {**old_event, "action": "confirm", "revision": 999}
    app.run()
    assert app.session_state["annotation_stage"] == "ladder"
    assert app.session_state["ladder_data"] == previous
    assert app.session_state["annotation_png"] == png


@pytest.mark.parametrize("action", ["skip", "remove"])
def test_skip_or_remove_returns_to_lane_only_png(annotated, action):
    if action == "remove":
        confirm_ladder(annotated)
        annotated.app.button(key="edit_ladder").click().run()
    else:
        open_ladder(annotated)
    app = annotated.app
    lane_png = app.session_state["annotation_base_png"]
    lane_dimensions = app.session_state["annotation_base_dimensions"]
    labels = deepcopy(app.session_state["annotation_data"])
    ladder_event(annotated, data=ladder_snapshot(80))
    ladder_event(annotated, action=action, revision=2)
    assert app.session_state["annotation_stage"] == "final"
    assert app.session_state["ladder_data"] is None
    assert app.session_state["ladder_draft"] is None
    assert app.session_state["annotation_png"] == lane_png
    assert app.session_state["annotation_dimensions"] == lane_dimensions
    assert app.session_state["annotation_data"] == labels


def test_invalid_preset_configuration_keeps_skip_available(annotated, monkeypatch):
    from gel_analyzer import annotation_ui

    def missing_presets():
        raise LadderError("No usable ladder presets are configured. You can skip ladder annotations.")

    monkeypatch.setattr(annotation_ui, "load_presets", missing_presets)
    open_ladder(annotated)
    app = annotated.app
    assert app.warning
    assert annotated.renders[-1][1]["presets"] == []
    ladder_event(annotated, action="skip")
    assert app.session_state["annotation_stage"] == "final"
    assert app.session_state["annotation_png"] == app.session_state["annotation_base_png"]


@pytest.mark.parametrize("overrides", [
    {"token": "obsolete"}, {"revision": 0}, {"revision": True},
    {"kind": "annotations"}, {"action": "delete"},
])
def test_stale_and_unrelated_ladder_events_do_not_change_state(annotated, overrides):
    open_ladder(annotated)
    app = annotated.app
    png = app.session_state["annotation_png"]
    ladder_event(annotated, **overrides)
    assert app.session_state["ladder_draft"] is None
    assert app.session_state["ladder_data"] is None
    assert app.session_state["annotation_revision"] == 0
    assert app.session_state["annotation_png"] == png


def test_out_of_order_or_invalid_edit_preserves_last_valid_ladder_draft(annotated):
    open_ladder(annotated)
    app = annotated.app
    accepted = ladder_snapshot(100.125)
    ladder_event(annotated, data=accepted, revision=2)
    ladder_event(annotated, data=ladder_snapshot(120), revision=1)
    assert app.session_state["ladder_draft"] == accepted
    ladder_event(annotated, data=ladder_snapshot(203), revision=3)
    assert app.session_state["ladder_draft"] == accepted
    assert app.error
    ladder_event(annotated, data=ladder_snapshot(150), step="unknown", revision=4)
    assert app.session_state["ladder_draft"] == accepted
    assert app.session_state["ladder_step"] == "markers"


@pytest.mark.parametrize("committed", [False, True])
def test_encoding_failure_keeps_new_draft_and_old_confirmation_for_retry(annotated, committed):
    if committed:
        confirm_ladder(annotated)
        annotated.app.button(key="edit_ladder").click().run()
    else:
        open_ladder(annotated)
    app = annotated.app
    previous_png = app.session_state["annotation_png"]
    previous_data = deepcopy(app.session_state["ladder_data"])
    data = ladder_snapshot(120.375)
    ladder_event(annotated, data=data, action="confirm", png="data:image/png;base64,broken!")
    assert app.error
    assert app.session_state["annotation_stage"] == "ladder"
    assert app.session_state["ladder_draft"] == data
    assert app.session_state["ladder_data"] == previous_data
    assert app.session_state["annotation_png"] == previous_png
    ladder_event(annotated, data=data, action="confirm", revision=2)
    assert app.session_state["annotation_stage"] == "final"
    assert app.session_state["ladder_data"] == data
    assert app.session_state["annotation_error"] is None


def test_empty_subset_cannot_be_confirmed_but_stays_editable(annotated):
    open_ladder(annotated)
    data = ladder_snapshot()
    data["placements"] = []
    ladder_event(annotated, data=data, action="confirm")
    app = annotated.app
    assert app.error
    assert app.session_state["annotation_stage"] == "ladder"
    assert app.session_state["ladder_draft"] == data
    assert app.session_state["ladder_data"] is None


def test_reediting_lane_text_retains_ladder_and_requires_both_outputs_atomically(annotated):
    crop = confirm_ladder(annotated)
    app = annotated.app
    ladder = deepcopy(app.session_state["ladder_data"])
    app.button(key="edit_annotations").click().run()
    assert app.session_state["annotation_stage"] == "lanes"
    assert app.session_state["ladder_data"] == ladder
    assert annotated.renders[-1][1]["ladder"] == ladder
    data = deepcopy(app.session_state["annotation_data"])
    data["labels"][0]["text"] = "Renamed lane"
    annotation_event(annotated, data=data, action="confirm")
    assert app.error
    assert app.session_state["annotation_png"] is None
    assert app.session_state["annotation_base_png"] is None
    assert app.session_state["annotation_stage"] == "lanes"
    base_event, base_png = composition(crop, gutter=190)
    combined_event, combined_png = composition(crop, gutter=240)
    annotation_event(annotated, data=data, action="confirm", revision=2, base=base_event, **combined_event)
    assert app.session_state["annotation_stage"] == "final"
    assert app.session_state["annotation_png"] == combined_png
    assert app.session_state["annotation_base_png"] == base_png
    assert app.session_state["ladder_data"] == ladder
    assert app.session_state["annotation_data"] == data
    assert "skip_ladder" not in keys(app)
    app.button(key="edit_ladder").click().run()
    ladder_event(annotated, action="remove")
    assert app.session_state["annotation_png"] == base_png


@pytest.mark.parametrize("changed", [False, True])
def test_crop_geometry_changes_clear_ladder_but_same_geometry_retains_it(annotated, changed):
    first_crop = confirm_ladder(annotated)
    app = annotated.app
    data = deepcopy(app.session_state["ladder_data"])
    labels = deepcopy(app.session_state["annotation_data"])
    app.button(key="revise_lane_crop").click().run()
    if changed:
        lane_event(annotated.workflow, lanes=((30, 15, 230, 60), (32, 70, 230, 140)), right_edge=230)
    app.button(key="confirm_lane_borders").click().run()
    app.button(key="confirm_lane_crop").click().run()
    assert not app.exception
    assert app.session_state["lane_crop"] is not first_crop
    assert app.session_state["annotation_data"] == labels
    assert app.session_state["annotation_stage"] == "lanes"
    assert app.session_state["annotation_png"] is None
    if changed:
        assert app.session_state["ladder_data"] is None
        assert app.session_state["ladder_draft"] is None
        assert app.session_state["annotation_completed"] is False
        assert any("place your ladder markers again" in message.value for message in app.info)
    else:
        assert app.session_state["ladder_data"] == data
        assert app.session_state["annotation_completed"] is True
        assert annotated.renders[-1][1]["ladder"] == data


@pytest.mark.parametrize("clear", [False, True])
def test_changed_or_cleared_upload_discards_ladder_and_obsolete_events(annotated, clear):
    confirm_ladder(annotated)
    app = annotated.app
    old_token = app.session_state["annotation_token"]
    app.button(key="edit_ladder").click().run()
    old_event = ladder_event(annotated, data=ladder_snapshot(50.25))
    if clear:
        app.file_uploader[0].set_value(None).run()
    else:
        upload(annotated.workflow, offset=1000)
    assert not app.exception
    assert app.session_state["ladder_data"] is None
    assert app.session_state["ladder_draft"] is None
    assert app.session_state["annotation_png"] is None
    assert app.session_state["annotation_base_png"] is None
    assert app.session_state["annotation_completed"] is False
    assert app.session_state["annotation_geometry"] is None
    assert app.session_state["annotation_token"] != old_token
    annotated.event = {**old_event, "revision": 999}
    crop_gel(annotated)
    assert app.session_state["ladder_data"] is None
    assert app.session_state["ladder_draft"] is None
    assert app.session_state["annotation_stage"] == "lanes"
