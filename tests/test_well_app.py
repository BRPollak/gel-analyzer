"""Exercise confirmation, stale-event protection, and well-session lifecycle.

The interaction component is replaced with its event boundary here; real
pointer, resize, and drawing behavior is verified separately in a browser.
"""

from io import BytesIO
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import numpy as np
from PIL import Image
import pytest
from streamlit.testing.v1 import AppTest

from gel_analyzer import image_io, well_component, wells


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
    harness = SimpleNamespace(event=None, renders=[], calls=[], result=None)

    def component(*args, **kwargs):
        harness.renders.append((args, kwargs))
        return harness.event

    def detect(image, points):
        harness.calls.append((image.copy(), points))
        return harness.result

    monkeypatch.setattr(well_component, "render_well_component", component)
    monkeypatch.setattr(wells, "detect_wells", detect)
    harness.app = AppTest.from_file(Path(__file__).parents[1] / "app.py").run()
    return harness


def upload(workflow, *, color=8000, mode="I;16"):
    # Different dimensions on each axis make accidental use of original
    # coordinates evident after the mocked transpose orientation.
    pixels = np.full((300, 200), color, dtype=np.uint16 if mode == "I;16" else np.uint8)
    pixels[20:40, 60:80] = color + 70
    source = BytesIO()
    Image.fromarray(pixels).save(source, format="TIFF")
    workflow.app.file_uploader[0].set_value(
        ("gel.tif", source.getvalue(), "image/tiff")
    ).run()
    return source.getvalue()


def confirm_orientation(workflow):
    workflow.app.button(key="rotate_and_orient").click().run()
    workflow.app.button(key="confirm_orientation").click().run()


def begin_selection(workflow):
    upload(workflow)
    confirm_orientation(workflow)
    workflow.app.button(key="define_wells").click().run()


def button_keys(app):
    return {button.key for button in app.button}


def event(workflow, points=((34, 20), (38, 180)), revision=1, **overrides):
    workflow.event = {
        "token": workflow.app.session_state["well_token"],
        "revision": revision,
        "points": [list(point) for point in points],
        **overrides,
    }
    workflow.app.run()
    assert not workflow.app.exception


def good_result():
    return wells.DetectionResult(
        wells=(wells.Well(center=(34.0, 40.0), bounds=(24, 30, 44, 50)),),
        lanes=((24, 30, 300, 50),),
        warnings=(),
    )


def assert_reset(app, previous_token):
    assert not app.exception
    assert app.session_state["well_points"] == ()
    assert app.session_state["well_result"] is None
    assert app.session_state["well_editing"] is False
    assert app.session_state["well_revision"] == 0
    assert app.session_state["well_token"] != previous_token


def test_selection_is_only_available_after_explicit_orientation_confirmation(workflow):
    app = workflow.app
    assert "define_wells" not in button_keys(app)
    upload(workflow)
    assert "define_wells" not in button_keys(app)
    app.button(key="rotate_and_orient").click().run()
    assert app.session_state["orientation_preview"].orientation is not None
    assert app.session_state["gel_image"].orientation is None
    assert "define_wells" not in button_keys(app)
    assert not workflow.renders
    assert not workflow.calls

    app.button(key="confirm_orientation").click().run()
    assert "define_wells" in button_keys(app)
    assert not workflow.renders
    app.button(key="define_wells").click().run()
    assert workflow.renders
    assert app.session_state["well_editing"] is True
    assert app.button(key="confirm_well_line").disabled


def test_clicks_drags_and_reruns_do_not_detect_until_confirmed(workflow):
    begin_selection(workflow)
    app = workflow.app
    gel = app.session_state["gel_image"]
    original_png = gel.preview_png
    original_source = gel.source_bytes
    event(workflow, points=((34, 20),))
    assert app.button(key="confirm_well_line").disabled
    event(workflow, revision=2)
    assert not app.button(key="confirm_well_line").disabled
    event(workflow, points=((38, 180), (34, 20)), revision=3)
    app.run()
    assert not workflow.calls
    workflow.result = good_result()

    app.button(key="confirm_well_line").click().run()

    assert not app.exception
    assert len(workflow.calls) == 1
    analyzed, selected = workflow.calls[0]
    assert analyzed.size == (300, 200)
    assert np.asarray(analyzed).dtype == np.uint16
    assert np.asarray(analyzed).max() > 255
    with Image.open(BytesIO(original_png)) as confirmed_pixels:
        np.testing.assert_array_equal(np.asarray(analyzed), np.asarray(confirmed_pixels))
    assert {tuple(point) for point in selected} == {(38, 180), (34, 20)}
    assert app.session_state["well_result"] is workflow.result
    assert app.session_state["well_editing"] is False
    assert "edit_well_line" in button_keys(app)
    assert any("1 well" in message.value and "1 horizontal lane" in message.value for message in app.success)
    rendered_args, rendered_kwargs = workflow.renders[-1]
    assert rendered_args[:3] == (original_png, 300, 200)
    assert rendered_kwargs["lanes"] == ((24, 30, 300, 50),)
    assert rendered_kwargs["wells"] == [{"bounds": (24, 30, 44, 50), "center": (34.0, 40.0)}]
    assert rendered_kwargs["editable"] is False
    assert app.session_state["gel_image"] is gel
    assert gel.preview_png == original_png
    assert gel.source_bytes == original_source
    # A late pointer event after confirmation cannot change frozen results.
    frozen_points = app.session_state["well_points"]
    event(workflow, points=((45, 25), (45, 185)), revision=4)
    assert app.session_state["well_points"] == frozen_points
    assert app.session_state["well_result"] is workflow.result
    app.run()
    assert len(workflow.calls) == 1


@pytest.mark.parametrize("warnings", [(), ("Review uncertain well boundaries.",)])
def test_immediate_confirmation_consumes_latest_pending_component_event(workflow, warnings):
    begin_selection(workflow)
    event(workflow)
    app = workflow.app
    token = app.session_state["well_token"]
    latest_points = ((45.0, 25.0), (45.0, 185.0))
    pending = {"token": token, "revision": 2, "points": [list(point) for point in latest_points]}
    # Pointer-up can update the component widget and confirmation can arrive
    # before another script run has copied that widget into well_points.
    app.session_state[f"well_overlay_{token}"] = pending
    workflow.event = pending
    workflow.result = replace(good_result(), warnings=warnings)

    app.button(key="confirm_well_line").click().run()

    assert not app.exception
    assert len(workflow.calls) == 1
    assert workflow.calls[0][1] == latest_points
    assert app.session_state["well_points"] == latest_points
    assert app.session_state["well_result"] is workflow.result
    assert workflow.renders[-1][1]["lanes"] == workflow.result.lanes
    app.run()
    assert app.session_state["well_result"] is workflow.result
    assert len(workflow.calls) == 1


@pytest.mark.parametrize(
    "overrides",
    [
        {"token": "previous-image"},
        {"revision": 1},
        {"points": [[float("nan"), 25], [45, 185]]},
    ],
)
def test_immediate_confirmation_ignores_stale_or_malformed_pending_event(workflow, overrides):
    begin_selection(workflow)
    event(workflow)
    app = workflow.app
    token = app.session_state["well_token"]
    accepted_points = app.session_state["well_points"]
    pending = {"token": token, "revision": 2, "points": [[45, 25], [45, 185]], **overrides}
    app.session_state[f"well_overlay_{token}"] = pending
    workflow.event = pending
    workflow.result = good_result()

    app.button(key="confirm_well_line").click().run()

    assert not app.exception
    assert len(workflow.calls) == 1
    assert workflow.calls[0][1] == accepted_points
    assert app.session_state["well_points"] == accepted_points
    assert app.session_state["well_result"] is workflow.result


def test_immediate_confirmation_does_not_detect_a_new_invalid_pending_line(workflow):
    begin_selection(workflow)
    event(workflow)
    app = workflow.app
    token = app.session_state["well_token"]
    pending = {"token": token, "revision": 2, "points": [[20, 50], [180, 50]]}
    app.session_state[f"well_overlay_{token}"] = pending
    workflow.event = pending

    app.button(key="confirm_well_line").click().run()

    assert not app.exception
    assert not workflow.calls
    assert app.session_state["well_points"] == ((20.0, 50.0), (180.0, 50.0))
    assert app.session_state["well_result"] is None
    assert app.button(key="confirm_well_line").disabled


@pytest.mark.parametrize(
    "points", [((40, 50), (40, 50)), ((40, 50), (40, 51)), ((10, 80), (180, 83))]
)
def test_invalid_line_geometry_is_editable_but_cannot_be_confirmed(workflow, points):
    begin_selection(workflow)
    event(workflow, points=points)
    assert workflow.app.button(key="confirm_well_line").disabled
    assert workflow.app.session_state["well_editing"] is True
    assert workflow.app.warning or workflow.app.info or workflow.app.error
    assert not workflow.calls


@pytest.mark.parametrize(
    "payload",
    [
        {"points": [[float("nan"), 20], [38, 180]]},
        {"points": [[34, float("inf")], [38, 180]]},
        {"points": [["34", 20], [38, 180]]},
        {"points": [[True, 20], [38, 180]]},
        {"points": [[34, 20, 99], [38, 180]]},
        {"points": [[34, 20], [38, 180], [50, 190]]},
        {"points": [[-1, 20], [38, 180]]},
        {"points": [[34, 20], [301, 180]]},
        {"points": [[34, 20], [38, 201]]},
        {"revision": "2"},
        {"revision": True},
        {"revision": 1.5},
        {"token": "event-from-another-image"},
    ],
)
def test_malformed_component_event_cannot_replace_good_geometry(workflow, payload):
    begin_selection(workflow)
    event(workflow)
    previous = workflow.app.session_state["well_points"]
    event(workflow, **({"points": ((45, 25), (45, 185)), "revision": 2} | payload))
    assert workflow.app.session_state["well_points"] == previous
    assert not workflow.calls


def test_out_of_order_event_cannot_restore_older_endpoints(workflow):
    begin_selection(workflow)
    event(workflow, revision=3)
    latest = workflow.app.session_state["well_points"]
    event(workflow, points=((70, 20), (70, 180)), revision=2)
    assert workflow.app.session_state["well_points"] == latest
    event(workflow, points=((80, 20), (80, 180)), revision=3)
    assert workflow.app.session_state["well_points"] == latest


def test_edit_invalidates_detection_and_stale_event_but_preserves_line(workflow):
    begin_selection(workflow)
    event(workflow)
    app = workflow.app
    workflow.result = good_result()
    app.button(key="confirm_well_line").click().run()
    previous_points = app.session_state["well_points"]
    old_token = app.session_state["well_token"]

    app.button(key="edit_well_line").click().run()

    assert not app.exception
    assert app.session_state["well_result"] is None
    assert app.session_state["well_points"] == previous_points
    assert app.session_state["well_token"] != old_token
    assert app.session_state["well_editing"] is True
    event(workflow, points=((80, 20), (80, 180)), revision=50, token=old_token)
    assert app.session_state["well_points"] == previous_points
    event(workflow, points=((45, 25), (45, 185)), revision=1)
    assert app.session_state["well_points"] != previous_points
    assert len(workflow.calls) == 1
    app.button(key="confirm_well_line").click().run()
    assert len(workflow.calls) == 2


@pytest.mark.parametrize("uncertain", [False, True])
def test_no_wells_or_uncertain_boundaries_preserve_editable_guide(workflow, uncertain):
    begin_selection(workflow)
    event(workflow)
    workflow.result = good_result()
    if not uncertain:
        workflow.result = replace(workflow.result, wells=(), lanes=())
    workflow.result = replace(
        workflow.result, warnings=("Well boundaries are uncertain; reposition the guide.",)
    )
    app = workflow.app
    previous_points = app.session_state["well_points"]

    app.button(key="confirm_well_line").click().run()

    assert not app.exception
    assert app.session_state["well_editing"] is True
    assert app.session_state["well_points"] == previous_points
    assert not app.button(key="confirm_well_line").disabled
    assert any("uncertain" in message.value.lower() for message in app.warning)
    assert not app.success
    assert len(workflow.calls) == 1


def test_detection_failure_explains_problem_and_preserves_retry(workflow, monkeypatch):
    begin_selection(workflow)
    event(workflow)
    previous_points = workflow.app.session_state["well_points"]

    def fail(image, points):
        raise wells.SelectionError("The selected well boundaries are too faint to estimate.")

    monkeypatch.setattr(wells, "detect_wells", fail)
    workflow.app.button(key="confirm_well_line").click().run()

    assert not workflow.app.exception
    assert workflow.app.session_state["well_points"] == previous_points
    assert workflow.app.session_state["well_result"] is None
    assert workflow.app.session_state["well_editing"] is True
    assert not workflow.app.button(key="confirm_well_line").disabled
    assert any("too faint" in warning.value for warning in workflow.app.warning)


def test_dragging_uncertain_result_removes_its_outlines_immediately(workflow):
    begin_selection(workflow)
    event(workflow)
    workflow.result = replace(good_result(), warnings=("Some well boundaries remain uncertain.",))
    app = workflow.app
    app.button(key="confirm_well_line").click().run()
    assert workflow.renders[-1][1]["lanes"]
    assert app.session_state["well_editing"] is True

    event(workflow, points=((45, 25), (45, 185)), revision=2)

    assert app.session_state["well_result"] is None
    assert workflow.renders[-1][1]["wells"] == []
    assert workflow.renders[-1][1]["lanes"] == []
    assert workflow.renders[-1][1]["editable"] is True
    assert len(workflow.calls) == 1


@pytest.mark.parametrize("action", ["request", "confirm"])
def test_orientation_changes_invalidate_any_existing_well_state(workflow, action):
    upload(workflow)
    app = workflow.app
    if action == "confirm":
        app.button(key="rotate_and_orient").click().run()
    # Defensive lifecycle check: geometry restored from earlier session state
    # must never survive a new orientation, even though controls are hidden.
    app.session_state["well_points"] = ((34.0, 20.0), (38.0, 180.0))
    app.session_state["well_result"] = good_result()
    app.session_state["well_editing"] = True
    app.session_state["well_revision"] = 9
    previous_token = app.session_state["well_token"]

    key = "rotate_and_orient" if action == "request" else "confirm_orientation"
    app.button(key=key).click().run()

    assert_reset(app, previous_token)
    assert not workflow.renders
    assert not workflow.calls


def test_reset_removes_points_and_result_without_changing_confirmed_image(workflow):
    begin_selection(workflow)
    event(workflow)
    app = workflow.app
    old_token = app.session_state["well_token"]
    gel = app.session_state["gel_image"]

    app.button(key="reset_well_line").click().run()

    assert not app.exception
    assert app.session_state["gel_image"] is gel
    assert app.session_state["well_points"] == ()
    assert app.session_state["well_result"] is None
    assert app.session_state["well_token"] != old_token
    assert app.session_state["well_editing"] is True
    assert app.button(key="confirm_well_line").disabled
    event(workflow, revision=500, token=old_token)
    assert app.session_state["well_points"] == ()
    assert not workflow.calls


@pytest.mark.parametrize("change", ["replace", "clear", "remove", "invalid"])
def test_upload_changes_clear_results_and_reject_previous_image_events(workflow, change):
    begin_selection(workflow)
    event(workflow)
    workflow.result = good_result()
    app = workflow.app
    app.button(key="confirm_well_line").click().run()
    old_token = app.session_state["well_token"]

    if change == "replace":
        upload(workflow, color=20000)
    elif change == "clear":
        app.button[0].click().run()
    elif change == "remove":
        app.file_uploader[0].set_value(None).run()
    else:
        app.file_uploader[0].set_value(("gel.tif", b"invalid", "image/tiff")).run()

    assert_reset(app, old_token)
    assert "define_wells" not in button_keys(app)
    if change == "replace":
        confirm_orientation(workflow)
        app.button(key="define_wells").click().run()
        event(workflow, revision=500, token=old_token)
        assert app.session_state["well_points"] == ()
        assert app.session_state["well_result"] is None
    assert len(workflow.calls) == 1
