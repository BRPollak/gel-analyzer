"""Keep extracted-band drawing isolated from lane/ladder editing and exports."""

from base64 import b64encode
from copy import deepcopy
from dataclasses import replace
from io import BytesIO

from PIL import Image, ImageDraw
import pytest

from test_annotation_app import annotated, annotation_event, crop_gel
from test_annotations import composition
from test_ladder_app import confirm_ladder, ladder_event
from test_lane_app import keys, lane_event, upload, workflow


MARKS = [{"x": 20.125, "y": 10.5, "width": 9.875, "height": 12.25},
         {"x": 90, "y": 65.25, "width": 7.5, "height": 20}]


def marked_composition(crop, marks, *, gutter=180):
    event, png = composition(crop, gutter=gutter)
    with Image.open(BytesIO(png)) as image:
        draw = ImageDraw.Draw(image)
        for rectangle in marks:
            x, y = gutter + rectangle["x"], event["gel_y"] + rectangle["y"]
            draw.rectangle((x, y, x + rectangle["width"], y + rectangle["height"]),
                           outline="#e02020", width=1)
        output = BytesIO()
        image.save(output, format="PNG")
    png = output.getvalue()
    event["png"] = "data:image/png;base64," + b64encode(png).decode("ascii")
    return event, png


def open_extracted(annotated, *, ladder=False):
    if ladder:
        crop = confirm_ladder(annotated)
    else:
        crop = crop_gel(annotated)
        annotation_event(annotated, action="confirm")
        annotated.app.button(key="skip_ladder").click().run()
    annotated.app.button(key="mark_extracted_bands").click().run()
    assert not annotated.app.exception
    return crop


def extracted_event(annotated, *, marks=None, revision=1, action="edit", **overrides):
    app = annotated.app
    marks = deepcopy(MARKS if marks is None else marks)
    event = {"kind": "extracted_bands", "action": action,
             "token": app.session_state["annotation_token"], "revision": revision,
             "extracted_bands": marks}
    if action == "confirm":
        crop = app.session_state["lane_crop"]
        event.update(marked_composition(crop, marks, gutter=210)[0])
        if app.session_state["ladder_data"]:
            event["base"] = marked_composition(crop, marks)[0]
    event.update(overrides)
    annotated.event = event
    app.run()
    assert not app.exception
    return event


@pytest.mark.parametrize("finish", ["skip", "confirm"])
def test_drawing_button_requires_completed_or_skipped_ladder(annotated, finish):
    crop_gel(annotated)
    app = annotated.app
    assert "mark_extracted_bands" not in keys(app)
    annotation_event(annotated, action="confirm")
    assert "mark_extracted_bands" not in keys(app)
    app.button(key="annotate_ladder").click().run()
    assert "mark_extracted_bands" not in keys(app)
    ladder_event(annotated, action=finish)
    assert app.button(key="mark_extracted_bands").label == "Mark extracted bands"
    token = app.session_state["annotation_token"]
    app.button(key="mark_extracted_bands").click().run()
    assert app.session_state["annotation_stage"] == "extracted"
    assert app.session_state["annotation_token"] != token
    assert annotated.renders[-1][1]["mode"] == "extracted"
    assert annotated.renders[-1][1]["extracted_bands"] == []
    assert "edit_ladder" not in keys(app)
    assert "edit_annotations" not in keys(app)


def test_multiple_rectangles_commit_reopen_remove_and_clear(annotated):
    crop = open_extracted(annotated)
    app = annotated.app
    png = app.session_state["annotation_png"]
    extracted_event(annotated)
    assert app.session_state["extracted_bands_draft"] == MARKS
    assert app.session_state["extracted_bands"] == []
    assert app.session_state["annotation_png"] == png
    assert annotated.renders[-1][1]["extracted_bands"] == MARKS
    # Confirmation supplies the latest complete list even without an edit event.
    latest = [MARKS[1]]
    extracted_event(annotated, marks=latest, action="confirm", revision=2)
    assert app.session_state["annotation_stage"] == "final"
    assert app.session_state["extracted_bands"] == latest
    assert app.session_state["extracted_bands_draft"] is None
    assert app.session_state["annotation_png"] == marked_composition(crop, latest, gutter=210)[1]
    assert app.session_state["annotation_base_png"] == app.session_state["annotation_png"]
    app.button(key="mark_extracted_bands").click().run()
    assert annotated.renders[-1][1]["extracted_bands"] == latest
    extracted_event(annotated, marks=[], action="confirm")
    assert app.session_state["extracted_bands"] == []
    assert app.session_state["annotation_png"] == composition(crop, gutter=210)[1]


def test_cancel_preserves_committed_rectangles_and_ignores_obsolete_editor_events(annotated):
    open_extracted(annotated)
    app = annotated.app
    extracted_event(annotated, action="confirm")
    app.button(key="mark_extracted_bands").click().run()
    png = app.session_state["annotation_png"]
    extracted_event(annotated, marks=[])
    event = extracted_event(annotated, marks=[], action="cancel", revision=2)
    assert app.session_state["extracted_bands"] == MARKS
    assert app.session_state["extracted_bands_draft"] is None
    assert app.session_state["annotation_png"] == png
    assert app.session_state["annotation_stage"] == "final"
    app.button(key="mark_extracted_bands").click().run()
    annotated.event = {**event, "action": "confirm", "revision": 999}
    app.run()
    assert app.session_state["annotation_stage"] == "extracted"
    assert app.session_state["extracted_bands_draft"] == MARKS
    assert app.session_state["annotation_png"] == png


def test_stale_unrelated_and_invalid_drawing_events_preserve_last_valid_draft(annotated):
    open_extracted(annotated)
    app = annotated.app
    for overrides in ({"token": "obsolete"}, {"revision": 0}, {"revision": True},
                      {"kind": "ladder"}, {"kind": "annotations"}, {"action": "delete"}):
        extracted_event(annotated, **overrides)
        assert app.session_state["extracted_bands_draft"] == []
        assert app.session_state["annotation_revision"] == 0
    extracted_event(annotated, revision=2)
    extracted_event(annotated, marks=[], revision=1)
    assert app.session_state["extracted_bands_draft"] == MARKS
    extracted_event(annotated, marks=[dict(MARKS[0], x=-10)], revision=3)
    assert app.error
    assert app.session_state["extracted_bands_draft"] == MARKS
    assert app.session_state["extracted_bands"] == []


def test_invalid_base_output_cannot_partially_commit_rectangles_or_image(annotated):
    crop = open_extracted(annotated, ladder=True)
    app = annotated.app
    png, base_png = app.session_state["annotation_png"], app.session_state["annotation_base_png"]
    extracted_event(annotated, action="confirm", base=None)
    assert app.error
    assert app.session_state["annotation_stage"] == "extracted"
    assert app.session_state["extracted_bands_draft"] == MARKS
    assert app.session_state["extracted_bands"] == []
    assert app.session_state["annotation_png"] == png
    assert app.session_state["annotation_base_png"] == base_png
    extracted_event(annotated, action="confirm", revision=2)
    assert app.session_state["extracted_bands"] == MARKS
    assert app.session_state["annotation_base_png"] == marked_composition(crop, MARKS)[1]
    app.button(key="edit_ladder").click().run()
    assert annotated.renders[-1][1]["extracted_bands"] == MARKS
    ladder_event(annotated, action="remove")
    assert app.session_state["annotation_png"] == marked_composition(crop, MARKS)[1]
    assert app.session_state["extracted_bands"] == MARKS


def test_lane_and_ladder_reediting_keep_committed_rectangles(annotated):
    crop = open_extracted(annotated, ladder=True)
    app = annotated.app
    extracted_event(annotated, action="confirm")
    app.button(key="edit_annotations").click().run()
    assert annotated.renders[-1][1]["extracted_bands"] == MARKS
    data = deepcopy(app.session_state["annotation_data"])
    data["labels"][0]["text"] = "Renamed lane"
    annotation_event(annotated, data=data, action="confirm",
                     base=marked_composition(crop, MARKS)[0],
                     **marked_composition(crop, MARKS, gutter=210)[0])
    assert app.session_state["extracted_bands"] == MARKS
    app.button(key="edit_ladder").click().run()
    assert annotated.renders[-1][1]["extracted_bands"] == MARKS
    ladder_event(annotated, action="confirm", **marked_composition(crop, MARKS, gutter=220)[0])
    assert app.session_state["extracted_bands"] == MARKS
    assert app.session_state["annotation_png"] == marked_composition(crop, MARKS, gutter=220)[1]


@pytest.mark.parametrize("changed", [False, True])
def test_recropping_preserves_marks_only_for_unchanged_geometry(annotated, changed):
    open_extracted(annotated)
    app = annotated.app
    extracted_event(annotated, action="confirm")
    app.button(key="revise_lane_crop").click().run()
    if changed:
        lane_event(annotated.workflow, lanes=((30, 15, 230, 60), (32, 70, 230, 140)), right_edge=230)
    app.button(key="confirm_lane_borders").click().run()
    app.button(key="confirm_lane_crop").click().run()
    assert not app.exception
    assert app.session_state["extracted_bands"] == ([] if changed else MARKS)
    assert app.session_state["extracted_bands_draft"] is None


def test_changed_image_pixels_with_identical_geometry_discard_marks(annotated):
    crop = open_extracted(annotated)
    app = annotated.app
    extracted_event(annotated, action="confirm")
    app.button(key="edit_annotations").click().run()
    image = Image.new("RGB", (crop.width, crop.height), "#123456")
    output = BytesIO()
    image.save(output, format="PNG")
    app.session_state["lane_crop"] = replace(crop, preview_png=output.getvalue())
    app.run()
    assert not app.exception
    assert app.session_state["extracted_bands"] == []
    assert app.session_state["extracted_bands_draft"] is None


def test_new_upload_discards_rectangles_and_drawing_draft(annotated):
    open_extracted(annotated)
    extracted_event(annotated, action="confirm")
    app = annotated.app
    app.button(key="mark_extracted_bands").click().run()
    extracted_event(annotated, marks=[MARKS[0]])
    upload(annotated.workflow, offset=1000)
    assert app.session_state["extracted_bands"] == []
    assert app.session_state["extracted_bands_draft"] is None
