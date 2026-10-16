"""Verify staged manual lane review and cropping without changing source data."""

from io import BytesIO
from pathlib import Path
from types import SimpleNamespace

import numpy as np
from PIL import Image
import pytest
from streamlit.testing.v1 import AppTest

from gel_analyzer import image_io, well_component, wells


DETECTED_BOUNDS = ((30, 20, 46, 50), (32, 80, 49, 112))
REVIEWED_LANES = ((30, 17, 300, 55), (32, 75, 300, 118))


@pytest.fixture
def workflow(monkeypatch):
    monkeypatch.setattr(
        image_io, "find_gel_crop", lambda image: (0, 0, image.width, image.height)
    )

    def orient(image):
        return SimpleNamespace(
            image=image.transpose(Image.Transpose.TRANSPOSE),
            rectangle=SimpleNamespace(
                corners=((0, 0), (image.width, 0), image.size, (0, image.height))
            ),
            counterclockwise_degrees=90.0,
        )

    monkeypatch.setattr(image_io, "orient_gel", orient)
    detected_wells = tuple(
        wells.Well(bounds, ((bounds[0] + bounds[2]) / 2, (bounds[1] + bounds[3]) / 2))
        for bounds in DETECTED_BOUNDS
    )
    result = wells.DetectionResult(
        detected_wells, tuple((left, top, 300, bottom) for left, top, _, bottom in DETECTED_BOUNDS)
    )
    harness = SimpleNamespace(event=None, renders=[], detections=[], expected_counts=[], result=result)

    def component(*args, **kwargs):
        harness.renders.append((args, kwargs))
        return harness.event

    def detect(image, points, *, expected_count=None):
        harness.detections.append((image.copy(), points))
        harness.expected_counts.append(expected_count)
        return harness.result

    monkeypatch.setattr(well_component, "render_well_component", component)
    monkeypatch.setattr(wells, "detect_wells", detect)
    harness.app = AppTest.from_file(Path(__file__).parents[1] / "app.py").run()
    return harness


def upload(workflow, offset=0):
    # Every pixel differs from its neighbors, including below the high byte,
    # so a crop/resampling/uint8 conversion error cannot hide behind flat data.
    pixels = (np.arange(300 * 200, dtype=np.uint16).reshape(300, 200) + offset).astype(np.uint16)
    output = BytesIO()
    Image.fromarray(pixels).save(output, format="TIFF")
    workflow.app.file_uploader[0].set_value(("gel.tif", output.getvalue(), "image/tiff")).run()
    return output.getvalue()


def detect_lanes(workflow):
    upload(workflow)
    app = workflow.app
    app.button(key="rotate_and_orient").click().run()
    app.button(key="confirm_orientation").click().run()
    app.button(key="define_wells").click().run()
    workflow.event = {
        "token": app.session_state["well_token"], "revision": 1,
        "points": [[38, 20], [40, 112]],
    }
    app.run()
    app.button(key="confirm_well_line").click().run()
    assert not app.exception


def start_review(workflow):
    detect_lanes(workflow)
    workflow.app.button(key="adjust_lane_borders").click().run()
    assert not workflow.app.exception


def lane_event(workflow, *, lanes=REVIEWED_LANES, right_edge=300, revision=1, run=True, **overrides):
    app = workflow.app
    payload = {
        "token": app.session_state["lane_token"],
        "revision": revision,
        "kind": "lane_review",
        "mode": app.session_state["lane_stage"],
        "lanes": [list(lane) for lane in lanes],
        "right_edge": right_edge,
        **overrides,
    }
    workflow.event = payload
    if run:
        app.run()
        assert not app.exception
    else:
        app.session_state[f"lane_overlay_{app.session_state['lane_token']}"] = payload
    return payload


def bounds(workflow):
    return tuple(well.bounds for well in workflow.app.session_state["lane_wells"])


def keys(app):
    return {button.key for button in app.button}


def finish_review(workflow, right_edge=230):
    lane_event(workflow)
    workflow.app.button(key="confirm_lane_borders").click().run()
    lanes = tuple((left, top, right_edge, bottom) for left, top, _, bottom in REVIEWED_LANES)
    lane_event(workflow, lanes=lanes, right_edge=right_edge)
    workflow.app.button(key="confirm_lane_crop").click().run()
    assert not workflow.app.exception


def test_manual_review_is_available_after_detection(workflow):
    app = workflow.app
    assert "adjust_lane_borders" not in keys(app)
    upload(workflow)
    assert "adjust_lane_borders" not in keys(app)
    detect_lanes(workflow)
    assert "adjust_lane_borders" in keys(app)
    assert app.session_state["lane_stage"] is None
    assert app.session_state["lane_crop"] is None


@pytest.mark.parametrize("has_warning", [False, True])
def test_confirm_detected_lanes_goes_directly_to_right_edge_without_reanalysis(workflow, has_warning):
    if has_warning:
        workflow.result = wells.DetectionResult(
            workflow.result.wells, workflow.result.lanes, ("Review uncertain boundaries.",)
        )
    detect_lanes(workflow)
    app = workflow.app
    assert keys(app) - {"clear_image"} == {
        "confirm_detected_lanes", "adjust_lane_borders", "edit_well_line",
    }
    app.button(key="confirm_detected_lanes").click().run()

    assert not app.exception
    assert app.session_state["lane_stage"] == "extent"
    assert bounds(workflow) == DETECTED_BOUNDS
    assert app.session_state["lane_right"] == 300
    assert app.session_state["lane_crop"] is None
    assert workflow.renders[-1][1]["review_mode"] == "extent"
    assert "confirm_lane_crop" in keys(app)
    assert "confirm_lane_borders" not in keys(app)
    assert not app.warning
    assert len(workflow.detections) == 1


@pytest.mark.parametrize("has_warning", [False, True])
def test_detected_candidates_can_start_border_review_without_reanalysis(workflow, has_warning):
    if has_warning:
        workflow.result = wells.DetectionResult(
            workflow.result.wells, workflow.result.lanes, ("Review the uncertain boundaries.",)
        )
    start_review(workflow)
    app = workflow.app
    assert app.session_state["lane_stage"] == "borders"
    assert bounds(workflow) == DETECTED_BOUNDS
    assert app.session_state["lane_right"] == 300
    assert app.session_state["lane_crop"] is None
    assert app.session_state["well_editing"] is False
    assert "confirm_lane_borders" in keys(app)
    assert "confirm_lane_crop" not in keys(app)
    assert workflow.renders[-1][1]["review_mode"] == "borders"
    assert len(workflow.detections) == 1


def test_refined_lane_heights_survive_review_and_final_crop(workflow):
    workflow.result = wells.DetectionResult(workflow.result.wells, REVIEWED_LANES)
    start_review(workflow)
    app = workflow.app
    assert bounds(workflow) == ((30, 17, 46, 55), (32, 75, 49, 118))
    assert workflow.renders[-1][1]["lanes"] == REVIEWED_LANES
    app.button(key="confirm_lane_borders").click().run()
    app.button(key="confirm_lane_crop").click().run()

    assert not app.exception
    assert app.session_state["lane_crop"].crop_box == (27, 14, 300, 121)
    assert tuple(well.bounds for well in workflow.result.wells) == DETECTED_BOUNDS
    assert len(workflow.detections) == 1


@pytest.mark.parametrize("stage", ["borders", "extent", "cropped"])
def test_review_and_crop_do_not_show_expected_lane_count_control(workflow, stage):
    start_review(workflow)
    app = workflow.app
    if stage == "extent":
        app.button(key="confirm_lane_borders").click().run()
    elif stage == "cropped":
        finish_review(workflow)
    assert not any(control.key == "expected_lane_count" for control in app.number_input)
    assert not any("Expected number of lanes" in control.label for control in app.number_input)
    assert app.session_state["lane_stage"] == stage
    assert app.session_state["well_editing"] is False
    assert len(workflow.detections) == 1


def test_empty_detection_has_three_controls_and_adjust_can_start_manual_review(workflow):
    workflow.result = wells.DetectionResult((), (), ("No wells found.",))
    detect_lanes(workflow)
    app = workflow.app
    assert keys(app) - {"clear_image"} == {
        "confirm_detected_lanes", "adjust_lane_borders", "edit_well_line",
    }
    assert app.button(key="confirm_detected_lanes").disabled
    assert not app.warning
    app.button(key="adjust_lane_borders").click().run()
    assert app.session_state["lane_stage"] == "borders"
    assert bounds(workflow) == ()
    assert app.session_state["lane_crop"] is None
    assert app.button(key="confirm_lane_borders").disabled
    assert keys(app) - {"clear_image"} == {
        "confirm_lane_borders", "add_lane", "edit_well_line", "back_to_well_review",
    }


def test_empty_detection_can_add_adjust_and_crop_a_manual_lane(workflow):
    workflow.result = wells.DetectionResult((), (), ("No wells found.",))
    detect_lanes(workflow)
    app = workflow.app
    gel = app.session_state["gel_image"]
    app.button(key="adjust_lane_borders").click().run()
    app.button(key="add_lane").click().run()
    assert not app.exception
    assert app.session_state["lane_stage"] == "borders"
    assert len(bounds(workflow)) == 1
    left, top, right, bottom = bounds(workflow)[0]
    assert top <= 112 <= bottom
    lane_event(workflow, lanes=((left, 70, 300, 130),))
    app.button(key="confirm_lane_borders").click().run()
    app.button(key="confirm_lane_crop").click().run()
    assert not app.exception
    assert app.session_state["lane_stage"] == "cropped"
    assert len(app.session_state["lane_crop"].lanes) == 1
    assert app.session_state["gel_image"] is gel
    assert len(workflow.detections) == 1


def test_delete_renumbers_survivors_rejects_old_events_and_preserves_latest_drag(workflow):
    start_review(workflow)
    app = workflow.app
    original = app.session_state["well_result"]
    old_token = app.session_state["lane_token"]
    deleted = lane_event(workflow, action="delete", lane_index=0)
    assert bounds(workflow) == ((32, 75, 49, 118),)
    assert app.session_state["lane_token"] != old_token
    assert app.session_state["well_result"] is original
    assert tuple(well.bounds for well in original.wells) == DETECTED_BOUNDS
    workflow.event = {**deleted, "revision": 999}
    app.run()
    assert bounds(workflow) == ((32, 75, 49, 118),)
    # The remaining lane now owns index 0, and can still be edited/cropped.
    lane_event(workflow, lanes=((32, 72, 300, 120),))
    app.button(key="confirm_lane_borders").click().run()
    lane_event(workflow, lanes=((32, 72, 240, 120),), right_edge=240)
    app.button(key="confirm_lane_crop").click().run()
    assert not app.exception
    assert app.session_state["lane_crop"].crop_box == (29, 69, 240, 123)
    app.button(key="revise_lane_crop").click().run()
    assert bounds(workflow) == ((32, 72, 49, 120),)


def test_delete_all_blocks_confirmation_and_add_restores_review(workflow):
    start_review(workflow)
    app = workflow.app
    lane_event(workflow, action="delete", lane_index=1)
    lane_event(workflow, lanes=((30, 17, 300, 55),), action="delete", lane_index=0)
    assert bounds(workflow) == ()
    assert app.button(key="confirm_lane_borders").disabled
    app.button(key="add_lane").click().run()
    assert not app.exception
    assert len(bounds(workflow)) == 1
    assert not app.button(key="confirm_lane_borders").disabled
    assert len(workflow.detections) == 1


def test_add_consumes_pending_drag_and_invalidates_old_collection(workflow):
    start_review(workflow)
    app = workflow.app
    old_token = app.session_state["lane_token"]
    pending = lane_event(workflow, run=False)
    app.button(key="add_lane").click().run()
    assert not app.exception
    added = bounds(workflow)
    assert len(added) == 3
    assert added[:2] == ((30, 17, 46, 55), (32, 75, 49, 118))
    assert added[2][1] >= added[1][3]
    assert app.session_state["lane_token"] != old_token
    workflow.event = {**pending, "revision": 999}
    app.run()
    assert bounds(workflow) == added
    assert len(workflow.detections) == 1


def test_immediate_confirmation_consumes_pending_deletion(workflow):
    start_review(workflow)
    lane_event(workflow, action="delete", lane_index=0, run=False)
    app = workflow.app
    app.button(key="confirm_lane_borders").click().run()
    assert not app.exception
    assert app.session_state["lane_stage"] == "extent"
    assert bounds(workflow) == ((32, 75, 49, 118),)
    app.button(key="confirm_lane_crop").click().run()
    assert len(app.session_state["lane_crop"].lanes) == 1


def test_add_lane_ignores_late_guide_event_after_uncertain_detection_is_frozen(workflow):
    workflow.result = wells.DetectionResult(
        workflow.result.wells, workflow.result.lanes, ("Review the uncertain boundaries.",)
    )
    detect_lanes(workflow)
    app = workflow.app
    token = app.session_state["well_token"]
    pending = {"token": token, "revision": 2, "points": [[42, 18], [42, 115]]}
    app.session_state[f"well_overlay_{token}"] = pending
    workflow.event = pending
    points = app.session_state["well_points"]
    app.button(key="adjust_lane_borders").click().run()
    app.button(key="add_lane").click().run()
    assert not app.exception
    assert app.session_state["well_result"] is workflow.result
    assert app.session_state["well_points"] == points
    assert app.session_state["lane_stage"] == "borders"
    assert len(bounds(workflow)) == 3
    assert len(workflow.detections) == 1


@pytest.mark.parametrize("overrides", [
    {"lane_index": -1}, {"lane_index": 2}, {"lane_index": True},
    {"lane_index": "0"}, {"lane_index": None}, {"action": "replace"},
    {"mode": "extent"}, {"token": "old-image"},
    {"lanes": [[30, 17, 300, 55]]},
])
def test_delete_rejects_invalid_or_stale_requests(workflow, overrides):
    start_review(workflow)
    before = bounds(workflow)
    lane_event(workflow, **{"action": "delete", "lane_index": 0, **overrides})
    assert bounds(workflow) == before


def test_extent_stage_cannot_delete_lanes(workflow):
    start_review(workflow)
    app = workflow.app
    app.button(key="confirm_lane_borders").click().run()
    before = bounds(workflow)
    original_lanes = tuple((left, top, 300, bottom) for left, top, _, bottom in before)
    lane_event(workflow, lanes=original_lanes, action="delete", lane_index=0)
    assert bounds(workflow) == before
    assert app.session_state["lane_stage"] == "extent"


def test_pending_guide_event_cannot_change_frozen_detection_when_adjusting(workflow):
    workflow.result = wells.DetectionResult(
        workflow.result.wells, workflow.result.lanes, ("Review the uncertain boundaries.",)
    )
    detect_lanes(workflow)
    app = workflow.app
    token = app.session_state["well_token"]
    pending = {"token": token, "revision": 2, "points": [[42, 18], [42, 115]]}
    app.session_state[f"well_overlay_{token}"] = pending
    workflow.event = pending
    points = app.session_state["well_points"]

    app.button(key="adjust_lane_borders").click().run()

    assert not app.exception
    assert app.session_state["well_result"] is workflow.result
    assert app.session_state["well_points"] == points
    assert app.session_state["well_editing"] is False
    assert app.session_state["lane_stage"] == "borders"
    assert bounds(workflow) == DETECTED_BOUNDS
    assert app.session_state["lane_crop"] is None
    assert "adjust_lane_borders" not in keys(app)
    assert len(workflow.detections) == 1


def test_border_edits_are_separate_from_detected_wells_and_require_confirmation(workflow):
    start_review(workflow)
    app = workflow.app
    detected = app.session_state["well_result"]
    gel = app.session_state["gel_image"]
    lane_event(workflow)

    assert bounds(workflow) == ((30, 17, 46, 55), (32, 75, 49, 118))
    assert app.session_state["lane_stage"] == "borders"
    assert app.session_state["lane_crop"] is None
    assert app.session_state["gel_image"] is gel
    assert tuple(well.bounds for well in detected.wells) == DETECTED_BOUNDS
    assert len(workflow.detections) == 1
    old_token = app.session_state["lane_token"]

    app.button(key="confirm_lane_borders").click().run()

    assert not app.exception
    assert app.session_state["lane_stage"] == "extent"
    assert app.session_state["lane_token"] != old_token
    assert app.session_state["lane_crop"] is None
    assert "confirm_lane_crop" in keys(app)
    assert "confirm_lane_borders" not in keys(app)
    assert workflow.renders[-1][1]["review_mode"] == "extent"


@pytest.mark.parametrize(
    "overrides",
    [
        {"token": "previous-image"},
        {"revision": True},
        {"revision": 0},
        {"kind": "well_selection"},
        {"mode": "extent"},
        {"lanes": [[30, 17, 300, 90], [32, 75, 300, 118]]},
        {"lanes": [[30, -1, 300, 55], [32, 75, 300, 118]]},
        {"lanes": [[30, 17, 300, 55], [32, 75, 300, 201]]},
        {"lanes": [[30, 55, 300, 17], [32, 75, 300, 118]]},
        {"lanes": [[25, 17, 300, 55], [32, 75, 300, 118]]},
        {"lanes": [[30, 17, 230, 55], [32, 75, 230, 118]], "right_edge": 230},
        {"lanes": [[30, 17, 300, 55]]},
        {"lanes": [[30, float("nan"), 300, 55], [32, 75, 300, 118]]},
    ],
)
def test_border_stage_rejects_stale_malformed_or_disallowed_edits(workflow, overrides):
    start_review(workflow)
    before = bounds(workflow)
    lane_event(workflow, **overrides)
    assert bounds(workflow) == before
    assert workflow.app.session_state["lane_right"] == 300
    assert workflow.app.session_state["lane_crop"] is None


def test_extent_edits_change_only_the_shared_right_edge(workflow):
    start_review(workflow)
    lane_event(workflow)
    app = workflow.app
    app.button(key="confirm_lane_borders").click().run()
    before = bounds(workflow)
    lanes = tuple((left, top, 230, bottom) for left, top, _, bottom in REVIEWED_LANES)
    lane_event(workflow, lanes=lanes, right_edge=230)

    assert app.session_state["lane_right"] == 230
    assert bounds(workflow) == before
    assert app.session_state["lane_crop"] is None
    assert app.session_state["lane_stage"] == "extent"
    assert len(workflow.detections) == 1


@pytest.mark.parametrize(
    "overrides",
    [
        {"mode": "borders"},
        {"lanes": [[30, 16, 230, 55], [32, 75, 230, 118]]},
        {"lanes": [[29, 17, 230, 55], [32, 75, 230, 118]]},
        {"lanes": [[30, 17, 220, 55], [32, 75, 230, 118]]},
        {"lanes": [[30, 17, 301, 55], [32, 75, 301, 118]], "right_edge": 301},
        {"lanes": [[30, 17, 35, 55], [32, 75, 35, 118]], "right_edge": 35},
    ],
)
def test_extent_stage_rejects_vertical_changes_or_invalid_right_edges(workflow, overrides):
    start_review(workflow)
    lane_event(workflow)
    app = workflow.app
    app.button(key="confirm_lane_borders").click().run()
    before = bounds(workflow)
    payload = {
        "lanes": tuple((left, top, 230, bottom) for left, top, _, bottom in REVIEWED_LANES),
        "right_edge": 230,
        **overrides,
    }
    lane_event(workflow, **payload)
    assert bounds(workflow) == before
    assert app.session_state["lane_right"] == 300
    assert app.session_state["lane_crop"] is None


def test_back_to_borders_preserves_edits_and_discards_prior_stage_events(workflow):
    start_review(workflow)
    lane_event(workflow)
    app = workflow.app
    app.button(key="confirm_lane_borders").click().run()
    lanes = tuple((left, top, 230, bottom) for left, top, _, bottom in REVIEWED_LANES)
    prior_event = lane_event(workflow, lanes=lanes, right_edge=230)
    previous_token = app.session_state["lane_token"]

    app.button(key="back_to_lane_borders").click().run()

    assert app.session_state["lane_stage"] == "borders"
    assert app.session_state["lane_right"] == 230
    assert app.session_state["lane_token"] != previous_token
    assert bounds(workflow) == ((30, 17, 46, 55), (32, 75, 49, 118))
    workflow.event = {**prior_event, "revision": 999}
    app.run()
    assert app.session_state["lane_right"] == 230
    assert app.session_state["lane_stage"] == "borders"
    assert app.session_state["lane_crop"] is None


@pytest.mark.parametrize("resume", ["confirm_detected_lanes", "adjust_lane_borders"])
def test_adjust_back_preserves_pending_manual_edits_and_rejects_old_review_events(workflow, resume):
    start_review(workflow)
    app = workflow.app
    points = app.session_state["well_points"]
    old_token = app.session_state["lane_token"]
    pending = lane_event(workflow, run=False)

    app.button(key="back_to_well_review").click().run()

    assert not app.exception
    assert app.session_state["lane_stage"] is None
    assert app.session_state["lane_token"] != old_token
    assert app.session_state["well_editing"] is False
    assert app.session_state["well_points"] == points
    assert tuple(well.bounds for well in app.session_state["well_result"].wells) == (
        (30, 17, 46, 55), (32, 75, 49, 118),
    )
    assert app.session_state["well_result"].lanes == REVIEWED_LANES
    assert keys(app) - {"clear_image"} == {
        "confirm_detected_lanes", "adjust_lane_borders", "edit_well_line",
    }
    workflow.event = {**pending, "revision": 999}
    app.button(key=resume).click().run()
    assert not app.exception
    assert bounds(workflow) == ((30, 17, 46, 55), (32, 75, 49, 118))
    assert app.session_state["lane_stage"] == ("extent" if resume == "confirm_detected_lanes" else "borders")
    assert len(workflow.detections) == 1


def test_shortened_right_edge_survives_back_to_borders_summary_and_direct_confirm(workflow):
    start_review(workflow)
    lane_event(workflow)
    app = workflow.app
    app.button(key="confirm_lane_borders").click().run()
    shortened = tuple((left, top, 230, bottom) for left, top, _, bottom in REVIEWED_LANES)
    lane_event(workflow, lanes=shortened, right_edge=230)
    app.button(key="back_to_lane_borders").click().run()
    app.button(key="back_to_well_review").click().run()
    assert not app.exception
    assert app.session_state["well_result"].lanes == shortened

    app.button(key="confirm_detected_lanes").click().run()

    assert not app.exception
    assert not app.warning
    assert app.session_state["lane_stage"] == "extent"
    assert app.session_state["lane_right"] == 230
    assert bounds(workflow) == ((30, 17, 46, 55), (32, 75, 49, 118))
    app.button(key="confirm_lane_crop").click().run()
    assert app.session_state["lane_crop"].crop_box == (27, 14, 230, 121)
    assert len(workflow.detections) == 1


def test_immediate_border_confirmation_consumes_pending_drag(workflow):
    start_review(workflow)
    lane_event(workflow, run=False)

    workflow.app.button(key="confirm_lane_borders").click().run()

    assert not workflow.app.exception
    assert workflow.app.session_state["lane_stage"] == "extent"
    assert bounds(workflow) == ((30, 17, 46, 55), (32, 75, 49, 118))
    assert workflow.app.session_state["lane_crop"] is None


def test_immediate_crop_confirmation_uses_latest_extent_and_exact_16bit_pixels(workflow):
    start_review(workflow)
    app = workflow.app
    gel = app.session_state["gel_image"]
    original_png, source_bytes = gel.preview_png, gel.source_bytes
    with Image.open(BytesIO(original_png)) as image:
        original_pixels = np.asarray(image).copy()
    lane_event(workflow)
    app.button(key="confirm_lane_borders").click().run()
    pending_lanes = tuple((left, top, 230, bottom) for left, top, _, bottom in REVIEWED_LANES)
    pending = lane_event(workflow, lanes=pending_lanes, right_edge=230, run=False)
    assert app.session_state["lane_crop"] is None

    app.button(key="confirm_lane_crop").click().run()

    assert not app.exception
    assert app.session_state["lane_stage"] == "cropped"
    crop = app.session_state["lane_crop"]
    # The enclosing crop retains three-pixel margins left of the wells and
    # above/below the outer lanes, and includes the gap between both lanes.
    assert crop.crop_box == (27, 14, 230, 121)
    assert (crop.width, crop.height) == (203, 107)
    assert app.text[0].value == "gel.tif · 203 × 107 pixels"
    assert crop.lanes == ((3, 3, 203, 41), (5, 61, 203, 104))
    assert tuple(well.bounds for well in crop.wells) == ((3, 3, 19, 41), (5, 61, 22, 104))
    with Image.open(BytesIO(crop.preview_png)) as cropped:
        actual = np.asarray(cropped)
        assert actual.dtype == np.uint16
        np.testing.assert_array_equal(actual, original_pixels[14:121, 27:230])
    assert app.session_state["gel_image"] is gel
    assert gel.preview_png == original_png
    assert gel.source_bytes == source_bytes
    assert "revise_lane_crop" in keys(app)
    assert "confirm_lane_crop" not in keys(app)
    # A delayed event from the extent iframe cannot restore mutable geometry
    # or erase the explicitly confirmed crop.
    workflow.event = {**pending, "revision": 999, "right_edge": 280}
    app.run()
    assert app.session_state["lane_crop"] is crop
    assert app.session_state["lane_stage"] == "cropped"
    assert len(workflow.detections) == 1


def test_revising_crop_uses_original_confirmed_image_and_never_crops_cumulatively(workflow):
    start_review(workflow)
    app = workflow.app
    gel = app.session_state["gel_image"]
    finish_review(workflow)
    first_crop = app.session_state["lane_crop"]
    token = app.session_state["lane_token"]

    app.button(key="revise_lane_crop").click().run()

    assert not app.exception
    assert app.session_state["lane_stage"] == "borders"
    assert app.session_state["lane_crop"] is None
    assert app.session_state["lane_right"] == 230
    assert app.session_state["lane_token"] != token
    assert bounds(workflow) == ((30, 17, 46, 55), (32, 75, 49, 118))
    assert workflow.renders[-1][0][:3] == (gel.preview_png, 300, 200)
    expanded = ((30, 10, 230, 55), (32, 75, 230, 130))
    lane_event(workflow, lanes=expanded, right_edge=230)
    app.button(key="confirm_lane_borders").click().run()
    expanded = tuple((left, top, 250, bottom) for left, top, _, bottom in expanded)
    lane_event(workflow, lanes=expanded, right_edge=250)
    app.button(key="confirm_lane_crop").click().run()

    assert not app.exception
    second_crop = app.session_state["lane_crop"]
    assert second_crop is not first_crop
    assert second_crop.crop_box == (27, 7, 250, 133)
    assert (second_crop.width, second_crop.height) == (223, 126)
    assert second_crop.lanes == ((3, 3, 223, 48), (5, 68, 223, 123))
    assert tuple(well.bounds for well in second_crop.wells) == ((3, 3, 19, 48), (5, 68, 22, 123))
    with Image.open(BytesIO(gel.preview_png)) as original, Image.open(BytesIO(second_crop.preview_png)) as cropped:
        np.testing.assert_array_equal(np.asarray(cropped), np.asarray(original)[7:133, 27:250])
    assert app.session_state["gel_image"] is gel
    assert len(workflow.detections) == 1


@pytest.mark.parametrize("stage", ["borders", "extent", "cropped"])
def test_editing_original_well_line_discards_manual_review(workflow, stage):
    start_review(workflow)
    lane_event(workflow)
    app = workflow.app
    if stage == "cropped":
        finish_review(workflow)
    elif stage == "extent":
        app.button(key="confirm_lane_borders").click().run()
        app.button(key="back_to_lane_borders").click().run()
    original_points = app.session_state["well_points"]
    old_lane_token = app.session_state["lane_token"]
    old_well_token = app.session_state["well_token"]

    app.button(key="edit_well_line").click().run()

    assert not app.exception
    assert app.session_state["lane_stage"] is None
    assert app.session_state["lane_wells"] == ()
    assert app.session_state["lane_right"] is None
    assert app.session_state["lane_crop"] is None
    assert app.session_state["lane_token"] != old_lane_token
    assert app.session_state["well_token"] != old_well_token
    assert app.session_state["well_points"] == original_points
    assert app.session_state["well_result"] is None
    assert app.session_state["well_editing"] is True


@pytest.mark.parametrize("change", ["replace", "clear", "remove", "invalid"])
def test_upload_changes_clear_manual_review_and_confirmed_crop(workflow, change):
    start_review(workflow)
    finish_review(workflow)
    app = workflow.app
    old_token = app.session_state["lane_token"]

    if change == "replace":
        upload(workflow, offset=50)
    elif change == "clear":
        app.button[0].click().run()
    elif change == "remove":
        app.file_uploader[0].set_value(None).run()
    else:
        app.file_uploader[0].set_value(("gel.tif", b"invalid", "image/tiff")).run()

    assert not app.exception
    assert app.session_state["lane_stage"] is None
    assert app.session_state["lane_wells"] == ()
    assert app.session_state["lane_right"] is None
    assert app.session_state["lane_crop"] is None
    assert app.session_state["lane_revision"] == 0
    assert app.session_state["lane_token"] != old_token
    assert app.session_state["well_result"] is None
    assert "adjust_lane_borders" not in keys(app)
    assert "confirm_lane_crop" not in keys(app)
    assert "revise_lane_crop" not in keys(app)
    assert len(workflow.detections) == 1
