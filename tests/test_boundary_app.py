"""Boundary-well recovery uses real state, crop, and analysis paths in both axes.

Oriented fixture images, automatic candidates, and browser events are supplied
deterministically. Coordinates below use the app's displayed-image pixel axes.
"""

from copy import deepcopy
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace

import numpy as np
from PIL import Image
import pytest
from streamlit.testing.v1 import AppTest

from gel_analyzer import annotation_component, image_io, well_component, wells
from gel_analyzer.projects import load_project, save_project
from gel_analyzer.workflow_orientation import lane_bounds, swap_bounds
from test_annotations import composition


@pytest.fixture(params=["wells_left", "wells_top"])
def boundary_workflow(monkeypatch, request):
    orientation = request.param
    monkeypatch.setattr(image_io, "find_gel_crop", lambda image: (0, 0, image.width, image.height))

    def orient(image, **options):
        return SimpleNamespace(
            image=image.copy() if orientation == "wells_top" else image.transpose(Image.Transpose.TRANSPOSE),
            rectangle=SimpleNamespace(corners=((0, 0), (image.width, 0), image.size, (0, image.height))),
            counterclockwise_degrees=0.0 if orientation == "wells_top" else 90.0,
            outline_complete=True, supported_edges=(),
        )

    monkeypatch.setattr(image_io, "orient_gel", orient)
    harness = SimpleNamespace(orientation=orientation, event=None, annotation_event=None,
                              renders=[], detection_count=0)
    canonical_bounds = ((30, 20, 46, 50), (32, 80, 49, 112))
    geometry = tuple(swap_bounds(bounds) if orientation == "wells_top" else bounds
                     for bounds in canonical_bounds)
    originals = tuple(wells.Well(bounds, ((bounds[0] + bounds[2]) / 2,
                                        (bounds[1] + bounds[3]) / 2)) for bounds in geometry)
    harness.original = wells.DetectionResult(
        originals, tuple(lane_bounds(well.bounds, 300, orientation) for well in originals),
    )

    def detect(*args, **kwargs):
        harness.detection_count += 1
        return harness.original

    def component(*args, **kwargs):
        harness.renders.append((args, kwargs))
        return harness.event

    monkeypatch.setattr(wells, "detect_wells", detect)
    monkeypatch.setattr(well_component, "render_well_component", component)
    monkeypatch.setattr(annotation_component, "render_annotation_component",
                        lambda *args, **kwargs: harness.annotation_event)
    app = harness.app = AppTest.from_file(Path(__file__).parents[1] / "app.py").run()
    pixels = np.arange(300 * 200, dtype=np.uint16).reshape(300, 200)
    source = BytesIO()
    Image.fromarray(pixels).save(source, format="TIFF")
    app.file_uploader[0].set_value(("boundary.tif", source.getvalue(), "image/tiff")).run()
    if orientation == "wells_top":
        app.selectbox(key="workflow_orientation_choice").select(orientation).run()
        app.button(key="keep_displayed_orientation").click().run()
    else:
        app.button(key="rotate_and_orient").click().run()
    app.button(key="confirm_orientation").click().run()
    harness.pixels = pixels if orientation == "wells_top" else pixels.T
    app.button(key="define_wells").click().run()
    harness.event = {
        "token": app.session_state["well_token"], "revision": 1,
        "points": [[20, 38], [112, 40]] if orientation == "wells_top" else [[38, 20], [40, 112]],
    }
    app.run()
    app.button(key="confirm_well_line").click().run()
    app.button(key="adjust_lane_borders").click().run()
    assert not app.exception
    return harness


def _canonical(workflow):
    bounds = tuple(well.bounds for well in workflow.app.session_state["lane_wells"])
    return tuple(swap_bounds(item) for item in bounds) if workflow.orientation == "wells_top" else bounds


def _event(workflow, cross_bounds, *, revision=1, run=True, **overrides):
    app = workflow.app
    canonical = _canonical(workflow)
    lanes = [(well[0], cross[0], app.session_state["lane_right"], cross[1])
             for well, cross in zip(canonical, cross_bounds)]
    if workflow.orientation == "wells_top":
        lanes = [swap_bounds(lane) for lane in lanes]
    stage = app.session_state["lane_boundary_stage"]
    payload = {
        "token": app.session_state["lane_token"], "revision": revision,
        "kind": "lane_review", "mode": f"boundary_{stage}" if stage else app.session_state["lane_stage"],
        "lanes": [list(lane) for lane in lanes], "right_edge": app.session_state["lane_right"],
        **overrides,
    }
    workflow.event = payload
    if run:
        app.run()
        assert not app.exception
    else:
        app.session_state[f"lane_overlay_{app.session_state['lane_token']}"] = payload
    return payload


def _start(workflow, count=15):
    app = workflow.app
    app.session_state["well_expected_count"] = count
    app.button(key="define_boundary_wells").click().run()
    assert not app.exception
    assert app.session_state["lane_boundary_stage"] == "first"
    assert len(_canonical(workflow)) == 1
    assert workflow.renders[-1][1]["review_mode"] == "boundary_first"
    return app


def _first(workflow, cross=(10, 16)):
    app = workflow.app
    _event(workflow, [cross], run=False)
    app.button(key="confirm_first_well").click().run()
    assert not app.exception
    assert app.session_state["lane_boundary_stage"] == "last"
    assert workflow.renders[-1][1]["review_mode"] == "boundary_last"
    assert _canonical(workflow)[0][1::2] == cross
    return _canonical(workflow)[0]


@pytest.mark.parametrize("count", [2, 15])
def test_generate_exact_total_and_spacing_then_edit_crop_and_analyze(boundary_workflow, count):
    workflow = boundary_workflow
    app = _start(workflow, count)
    assert app.number_input(key="boundary_lane_count").value == count
    first = _first(workflow)
    assert len(_canonical(workflow)) == 2
    assert _canonical(workflow)[1][2] - _canonical(workflow)[1][0] == first[2] - first[0]
    _event(workflow, [(10, 16), (176, 182)])
    _event(workflow, [(10, 16), (177, 183)], revision=2, run=False)
    app.button(key="generate_boundary_lanes").click().run()
    assert not app.exception
    assert app.session_state["lane_boundary_stage"] is None
    assert app.session_state["lane_stage"] == "borders"
    assert workflow.renders[-1][1]["review_mode"] == "borders"
    generated = _canonical(workflow)
    assert len(generated) == count
    assert len(generated[1:-1]) == count - 2
    assert generated[0] == first
    assert generated[-1] == (first[0], 177, first[2], 183)
    np.testing.assert_allclose([bounds[3] - bounds[1] for bounds in generated], 6, atol=1e-12)
    centers = np.array([(bounds[1] + bounds[3]) / 2 for bounds in generated])
    np.testing.assert_allclose(centers, 13 + np.arange(count) / (count - 1) * 167, atol=1e-12)
    assert app.session_state["well_result"].wells == app.session_state["lane_wells"]
    assert len(app.session_state["well_result"].lanes) == count
    assert workflow.detection_count == 1

    # The completed collection is an ordinary manual review: adjust a lane,
    # crop the unchanged 16-bit source, and use all lanes in band analysis.
    adjusted = [(bounds[1], bounds[3]) for bounds in generated]
    adjusted[0] = (9, 17)
    _event(workflow, adjusted)
    assert _canonical(workflow)[0][1::2] == (9, 17)
    app.button(key="confirm_lane_borders").click().run()
    app.button(key="confirm_lane_crop").click().run()
    assert not app.exception
    crop = app.session_state["lane_crop"]
    assert len(crop.wells) == len(crop.lanes) == count
    assert crop.workflow_orientation == workflow.orientation
    assert len(app.session_state["annotation_data"]["labels"]) == count
    left, top, right, bottom = crop.crop_box
    with Image.open(BytesIO(crop.preview_png)) as image:
        np.testing.assert_array_equal(np.asarray(image), workflow.pixels[top:bottom, left:right])
    workflow.annotation_event = {
        "token": app.session_state["annotation_token"], "revision": 1, "kind": "annotations",
        "action": "confirm", "annotations": deepcopy(app.session_state["annotation_data"]),
        **composition(crop)[0],
    }
    app.run()
    app.button(key="skip_ladder").click().run()
    assert not app.exception
    assert len(app.session_state["band_data"]) == count
    assert app.session_state["band_geometry"][1] == tuple(crop.lanes)


def test_back_keeps_both_positions_and_relinks_width(boundary_workflow):
    workflow = boundary_workflow
    app = _start(workflow)
    _first(workflow)
    _event(workflow, [(10, 16), (177, 183)], run=False)
    app.button(key="back_to_first_well").click().run()
    assert not app.exception
    assert app.session_state["lane_boundary_stage"] == "first"
    assert _canonical(workflow)[0][1::2] == (10, 16)
    _event(workflow, [(9, 17)], run=False)
    app.button(key="confirm_first_well").click().run()
    assert not app.exception
    revised = _canonical(workflow)
    assert revised[0][1::2] == (9, 17)
    assert revised[1][1::2] == (176, 184)
    app.button(key="generate_boundary_lanes").click().run()
    assert not app.exception
    assert all(abs(bounds[3] - bounds[1] - 8) < 1e-10 for bounds in _canonical(workflow))


@pytest.mark.parametrize("cancel_stage", ["first", "last"])
def test_cancel_restores_pending_prior_arrangement_and_rejects_stale_events(boundary_workflow, cancel_stage):
    workflow = boundary_workflow
    app = workflow.app
    original_result = app.session_state["well_result"]
    _event(workflow, [(17, 55), (75, 118)], run=False)
    _start(workflow)
    if cancel_stage == "last":
        _first(workflow)
        draft = _event(workflow, [(10, 16), (177, 183)], run=False)
    else:
        draft = _event(workflow, [(10, 16)], run=False)
    app.button(key="cancel_boundary_wells").click().run()
    assert not app.exception
    assert app.session_state["lane_boundary_stage"] is None
    assert app.session_state["lane_stage"] == "borders"
    assert _canonical(workflow) == ((30, 17, 46, 55), (32, 75, 49, 118))
    assert app.session_state["well_result"] is original_result
    workflow.event = {**draft, "revision": 999}
    app.run()
    assert _canonical(workflow) == ((30, 17, 46, 55), (32, 75, 49, 118))
    assert workflow.detection_count == 1


@pytest.mark.parametrize("last_cross", [(60, 66), (30, 36)])
def test_coincident_or_reversed_boundaries_cannot_generate(boundary_workflow, last_cross):
    workflow = boundary_workflow
    app = _start(workflow, 2)
    _first(workflow, (60, 66))
    _event(workflow, [(60, 66), last_cross])
    assert app.button(key="generate_boundary_lanes").disabled
    assert app.session_state["lane_boundary_stage"] == "last"
    assert len(_canonical(workflow)) == 2
    assert app.session_state["well_result"] is workflow.original


def test_last_boundary_cannot_edit_fixed_first_or_unlink_width(boundary_workflow):
    workflow = boundary_workflow
    app = _start(workflow, 2)
    _first(workflow)
    _event(workflow, [(10, 16), (177, 183)])
    accepted = _canonical(workflow)
    _event(workflow, [(11, 17), (177, 183)], revision=2)
    assert _canonical(workflow) == accepted
    _event(workflow, [(10, 16), (176, 184)], revision=3)
    assert _canonical(workflow) == accepted
    assert not app.button(key="generate_boundary_lanes").disabled


def test_invalid_count_requires_valid_total_before_confirmation(boundary_workflow):
    workflow = boundary_workflow
    app = _start(workflow, 1)
    assert app.button(key="confirm_first_well").disabled
    app.number_input(key="boundary_lane_count").set_value(2).run()
    assert not app.exception
    assert not app.button(key="confirm_first_well").disabled
    _first(workflow)
    assert app.number_input(key="boundary_lane_count").value == 2
    for invalid in (None, 1):
        app.number_input(key="boundary_lane_count").set_value(invalid).run()
        assert not app.exception
        assert app.button(key="generate_boundary_lanes").disabled
    app.button(key="back_to_first_well").click().run()
    assert app.button(key="confirm_first_well").disabled
    assert _canonical(workflow)[0][1::2] == (10, 16)


def test_boundary_recovery_can_begin_when_detection_found_no_lanes(boundary_workflow):
    workflow = boundary_workflow
    app = workflow.app
    app.session_state["lane_wells"] = ()
    app.session_state["well_result"] = wells.DetectionResult((), ())
    app.run()
    _start(workflow, 15)
    first = _first(workflow)
    _event(workflow, [(10, 16), (177, 183)])
    app.button(key="generate_boundary_lanes").click().run()
    assert not app.exception
    assert len(_canonical(workflow)) == 15
    assert _canonical(workflow)[0] == first
    assert app.session_state["well_result"].wells == app.session_state["lane_wells"]
    assert workflow.detection_count == 1


def test_mode_and_collection_changes_invalidate_old_events(boundary_workflow):
    workflow = boundary_workflow
    app = _start(workflow, 2)
    first_event = _event(workflow, [(10, 16)])
    app.button(key="confirm_first_well").click().run()
    before = _canonical(workflow)
    workflow.event = {**first_event, "revision": 999}
    app.run()
    assert _canonical(workflow) == before
    _event(workflow, [(10, 16), (177, 183)], action="delete", lane_index=0)
    assert _canonical(workflow) == before
    _event(workflow, [(10, 16), (177, 183)], revision=2)
    app.button(key="generate_boundary_lanes").click().run()
    generated = _canonical(workflow)
    workflow.event = {**first_event, "token": app.session_state["lane_token"], "revision": 1000}
    app.run()
    assert _canonical(workflow) == generated


def _reopen(workflow, snapshot):
    restored = load_project(snapshot)
    app = AppTest.from_file(Path(__file__).parents[1] / "app.py").run()
    for key, value in restored.items():
        app.session_state[key] = value
    app.run()
    assert not app.exception
    assert not app.error
    workflow.app = app
    return app


@pytest.mark.parametrize("stage", ["first", "last"])
def test_project_saved_during_boundary_draft_restores_previous_arrangement(boundary_workflow, stage):
    workflow = boundary_workflow
    app = workflow.app
    _event(workflow, [(17, 55), (75, 118)])
    previous_wells = app.session_state["lane_wells"]
    previous_result = app.session_state["well_result"]
    _start(workflow)
    if stage == "last":
        _first(workflow)
        _event(workflow, [(10, 16), (177, 183)])
    else:
        _event(workflow, [(10, 16)])
    draft = app.session_state["lane_wells"]
    snapshot = save_project(app.session_state)
    # Saving is read-only and leaves the live guided interaction intact.
    assert app.session_state["lane_boundary_stage"] == stage
    assert app.session_state["lane_wells"] == draft
    reopened = _reopen(workflow, snapshot)
    assert reopened.session_state["lane_boundary_stage"] is None
    assert reopened.session_state["lane_boundary_backup"] is None
    assert reopened.session_state["lane_stage"] == "borders"
    assert reopened.session_state["lane_wells"] == previous_wells
    assert reopened.session_state["well_result"] == previous_result
    assert reopened.session_state["lane_source"] is reopened.session_state["gel_image"]
    assert workflow.renders[-1][1]["review_mode"] == "borders"
    _event(workflow, [(16, 54), (75, 118)])
    assert _canonical(workflow)[0][1::2] == (16, 54)


@pytest.mark.parametrize("stage", ["borders", "cropped"])
def test_generated_fractional_lanes_survive_project_round_trip_and_editing(boundary_workflow, stage):
    workflow = boundary_workflow
    app = _start(workflow, 15)
    _first(workflow)
    _event(workflow, [(10, 16), (177, 183)])
    app.button(key="generate_boundary_lanes").click().run()
    generated = app.session_state["lane_wells"]
    result = app.session_state["well_result"]
    assert any(float(value) != int(value) for value in generated[1].bounds)
    if stage == "cropped":
        app.button(key="confirm_lane_borders").click().run()
        app.button(key="confirm_lane_crop").click().run()
    assert not app.exception
    crop = app.session_state["lane_crop"]
    reopened = _reopen(workflow, save_project(app.session_state))
    assert reopened.session_state["lane_stage"] == stage
    assert reopened.session_state["lane_wells"] == generated
    assert reopened.session_state["well_result"] == result
    assert reopened.session_state["well_expected_count"] == 15
    assert reopened.session_state["lane_crop"] == crop
    if stage == "cropped":
        assert len(reopened.session_state["annotation_data"]["labels"]) == 15
        reopened.button(key="revise_lane_crop").click().run()
    before = _canonical(workflow)
    edited = [bounds[1::2] for bounds in before]
    edited[1] = tuple(value + 1 for value in edited[1])
    _event(workflow, edited)
    assert _canonical(workflow)[1][1::2] == edited[1]
    assert _canonical(workflow)[0] == before[0]
    assert _canonical(workflow)[-1] == before[-1]
    reopened.button(key="confirm_lane_borders").click().run()
    reopened.button(key="confirm_lane_crop").click().run()
    assert not reopened.exception
    assert len(reopened.session_state["lane_crop"].lanes) == 15


@pytest.mark.parametrize("stage", ["first", "last"])
@pytest.mark.parametrize("resume", ["confirm_orientation", "keep_previous_orientation", "cancel_changed"])
def test_orientation_navigation_retains_boundary_draft_and_refreshes_events(boundary_workflow, stage, resume):
    workflow = boundary_workflow
    app = _start(workflow, 15)
    gel = app.session_state["gel_image"]
    if stage == "last":
        _first(workflow)
        pending = _event(workflow, [(10, 16), (177, 183)], run=False)
        expected_cross = [(10, 16), (177, 183)]
    else:
        pending = _event(workflow, [(10, 16)], run=False)
        expected_cross = [(10, 16)]
    app.button(key="workflow_step_0").click().run()
    assert not app.exception
    assert app.session_state["lane_boundary_stage"] == stage
    assert [bounds[1::2] for bounds in _canonical(workflow)] == expected_cross
    assert app.session_state["lane_token"] != pending["token"]
    if resume == "cancel_changed":
        other = "wells_left" if workflow.orientation == "wells_top" else "wells_top"
        app.selectbox(key="workflow_orientation_choice").select(other).run()
        resume = "keep_previous_orientation"
    app.button(key=resume).click().run()
    assert not app.exception
    assert app.session_state["gel_image"] is gel
    assert app.session_state["lane_source"] is gel
    assert app.session_state["lane_boundary_stage"] == stage
    retained = _canonical(workflow)
    workflow.event = {**pending, "revision": 999}
    app.run()
    assert _canonical(workflow) == retained
    changed = [(10, 16), (178, 184)] if stage == "last" else [(11, 17)]
    _event(workflow, changed)
    assert [bounds[1::2] for bounds in _canonical(workflow)] == changed
    app.button(key="cancel_boundary_wells").click().run()
    assert _canonical(workflow) == ((30, 20, 46, 50), (32, 80, 49, 112))


def test_confirming_changed_orientation_clears_boundary_draft_safely(boundary_workflow):
    workflow = boundary_workflow
    app = _start(workflow)
    _first(workflow)
    draft = _event(workflow, [(10, 16), (177, 183)])
    app.button(key="workflow_step_0").click().run()
    other = "wells_left" if workflow.orientation == "wells_top" else "wells_top"
    app.selectbox(key="workflow_orientation_choice").select(other).run()
    app.button(key="confirm_orientation").click().run()
    assert not app.exception
    assert app.session_state["gel_image"].workflow_orientation == other
    assert app.session_state["lane_boundary_stage"] is None
    assert app.session_state["lane_boundary_backup"] is None
    assert app.session_state["lane_stage"] is None
    assert app.session_state["lane_wells"] == ()
    assert app.session_state["well_result"] is None
    workflow.event = {**draft, "revision": 999}
    app.run()
    assert app.session_state["lane_wells"] == ()
    assert app.session_state["well_result"] is None
