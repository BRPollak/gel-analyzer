"""Project round trips retain both workflow axes, drafts, and clean exports."""

from dataclasses import replace
from hashlib import sha256
from io import BytesIO
import json
from pathlib import Path

import pytest
from PIL import Image

from gel_analyzer.annotations import default_annotations
from gel_analyzer.image_io import GelImage, GelOrientation, load_image
from gel_analyzer.lane_crop import crop_lanes
from gel_analyzer.projects import ProjectError, load_project, save_project
from gel_analyzer.wells import DetectionResult, Well
from gel_analyzer.workflow_orientation import lane_bounds


def image_bytes(image, format, **save_options):
    stream = BytesIO()
    image.save(stream, format=format, **save_options)
    return stream.getvalue()


def project_state(orientation="wells_left", angle=90):
    image = Image.new("L", (120, 90), 64)
    gel = GelImage(image_bytes(image, "TIFF"), "experiment.tiff", 120, 90, "L",
                   image_bytes(image, "PNG"), (0, 0, 120, 90),
                   GelOrientation(((0., 0.), (120., 0.), (120., 90.), (0., 90.)), 0., (120, 90)),
                   workflow_orientation=orientation)
    bounds = ((10, 8, 20, 18), (10, 35, 20, 45)) if orientation == "wells_left" else (
        (8, 10, 18, 20), (35, 10, 45, 20))
    wells = tuple(Well(bound, ((bound[0] + bound[2]) / 2, (bound[1] + bound[3]) / 2)) for bound in bounds)
    extent = 100 if orientation == "wells_left" else 80
    lanes = tuple(lane_bounds(well.bounds, extent, orientation) for well in wells)
    crop = crop_lanes(image, wells, extent, workflow_orientation=orientation)
    annotations = default_annotations(2, crop.lanes, orientation)
    annotations["laneLabelAngle"] = angle
    annotations["labels"][0]["text"] = "Control"
    annotations["groups"] = [{"id": "group1", "set": 0, "lanes": [0, 1], "label": "Experiment",
                              "bold": True, "italic": False, "color": "#123456"}]
    left, top, right, bottom = crop.lanes[0]
    marker_x, marker_y = (left + right) / 2, (top + bottom) / 2
    ladder = {"preset": {"id": "test", "name": "Test ladder", "labels": ["500 bp"]},
              "laneIndex": 0, "placements": [{"markerIndex": 0, "x": marker_x, "y": marker_y}]}
    return {"gel_image": gel, "well_points": ((15., 3.), (15., 60.)) if orientation == "wells_left" else ((3., 15.), (60., 15.)),
            "well_result": DetectionResult(wells, lanes), "well_expected_count": 2,
            "lane_stage": "cropped", "lane_wells": wells, "lane_right": extent, "lane_crop": crop,
            "lane_source": gel, "annotation_data": annotations,
            "annotation_geometry": (crop.crop_box, crop.width, crop.height, tuple(crop.lanes), orientation),
            "ladder_data": ladder, "ladder_draft": ladder, "ladder_step": "markers"}


@pytest.mark.parametrize("orientation", ["wells_left", "wells_top"])
@pytest.mark.parametrize("angle", [90, 45])
def test_round_trip_preserves_axes_annotations_and_source_identity(orientation, angle):
    state = project_state(orientation, angle)
    reopened = load_project(save_project(state))
    for key in ("gel_image", "well_points", "well_result", "lane_crop", "lane_wells",
                "annotation_data", "ladder_data", "ladder_draft"):
        assert reopened[key] == state[key]
    assert reopened["lane_source"] is reopened["gel_image"]
    assert reopened["gel_image"].workflow_orientation == orientation
    assert reopened["annotation_data"]["laneLabelAngle"] == angle
    assert reopened["well_detection_request"] is None
    assert reopened["annotation_geometry"] is None
    again = load_project(save_project(state))
    for editor in ("orientation", "well", "lane", "annotation"):
        assert reopened[f"{editor}_token"] != again[f"{editor}_token"]
        assert reopened[f"{editor}_revision"] == 0


@pytest.mark.parametrize("image_format,extension", [("PNG", "png"), ("JPEG", "jpeg"), ("JPEG", "jpg")])
@pytest.mark.parametrize("orientation", ["wells_left", "wells_top"])
def test_png_and_jpeg_projects_preserve_original_source_and_edits(image_format, extension, orientation):
    state = project_state(orientation, 45)
    source = image_bytes(Image.new("L", (120, 90), 64), image_format)
    imported = load_image(source, f"experiment.{extension}")
    state["gel_image"] = replace(imported, orientation=state["gel_image"].orientation,
                                 workflow_orientation=orientation)
    restored = load_project(save_project(state))
    assert restored["gel_image"] == state["gel_image"]
    assert restored["gel_image"].source_bytes == source
    assert restored["lane_source"] is restored["gel_image"]
    assert restored["lane_crop"] == state["lane_crop"]
    assert restored["annotation_data"] == state["annotation_data"]
    assert restored["ladder_data"] == state["ladder_data"]


@pytest.mark.parametrize("image_format", ["TIFF", "PNG", "JPEG"])
def test_source_orientation_is_applied_once_when_reopening_project(image_format):
    exif = Image.Exif()
    exif[274] = 6
    source = image_bytes(Image.new("L", (90, 120), 64), image_format, exif=exif)
    gel = load_image(source, f"experiment.{image_format.lower()}")
    assert (gel.width, gel.height) == (120, 90)
    restored = load_project(save_project({"gel_image": gel}))
    assert restored["gel_image"] == gel
    assert restored["gel_image"].source_bytes == source


@pytest.mark.parametrize("image_format", ["PNG", "JPEG"])
def test_new_source_formats_still_require_matching_source_dimensions(image_format):
    source = image_bytes(Image.new("L", (120, 90), 64), image_format)
    gel = load_image(source, f"experiment.{image_format.lower()}")
    gel = replace(gel, width=gel.width + 1)
    with pytest.raises(ProjectError, match="dimensions"):
        load_project(save_project({"gel_image": gel}))


@pytest.mark.parametrize("image_format", ["GIF", "BMP"])
def test_project_rejects_unsupported_source_formats(image_format):
    state = project_state()
    source = image_bytes(Image.new("L", (120, 90), 64), image_format)
    state["gel_image"] = replace(state["gel_image"], source_bytes=source)
    with pytest.raises(ProjectError, match="format"):
        load_project(save_project(state))


def test_project_rejects_animated_png_sources():
    state = project_state()
    source = image_bytes(Image.new("L", (120, 90), 64), "PNG", save_all=True,
                         append_images=[Image.new("L", (120, 90), 128)])
    state["gel_image"] = replace(state["gel_image"], source_bytes=source)
    with pytest.raises(ProjectError, match="format"):
        load_project(save_project(state))


def test_project_preview_still_requires_png():
    state = project_state()
    preview = image_bytes(Image.new("L", (120, 90), 64), "JPEG")
    state["gel_image"] = replace(state["gel_image"], preview_png=preview)
    with pytest.raises(ProjectError, match="format"):
        load_project(save_project(state))


def test_missing_orientation_and_label_angle_restore_legacy_defaults():
    document = json.loads(save_project(project_state()))
    def remove_defaults(value):
        if isinstance(value, dict):
            value.pop("workflow_orientation", None)
            value.pop("laneLabelAngle", None)
            for child in value.values():
                remove_defaults(child)
        elif isinstance(value, list):
            for child in value:
                remove_defaults(child)
    remove_defaults(document)
    restored = load_project(json.dumps(document).encode())
    assert restored["gel_image"].workflow_orientation == "wells_left"
    assert restored["lane_crop"].workflow_orientation == "wells_left"
    assert restored["annotation_data"]["laneLabelAngle"] == 90


@pytest.mark.parametrize("complete,edges", [
    (True, ("left", "right", "top", "bottom")),
    (False, ("left", "top")),
    (False, ()),
])
def test_outline_support_metadata_round_trips(complete, edges):
    state = project_state()
    gel = state["gel_image"]
    state["gel_image"] = replace(gel, orientation=replace(
        gel.orientation, outline_complete=complete, supported_edges=edges,
    ))
    restored = load_project(save_project(state))
    assert restored["gel_image"].orientation.outline_complete is complete
    assert restored["gel_image"].orientation.supported_edges == edges


def test_missing_outline_support_metadata_restores_legacy_defaults():
    document = json.loads(save_project(project_state()))
    geometry = document["state"]["gel_image"]["fields"]["orientation"]["fields"]
    geometry.pop("outline_complete")
    geometry.pop("supported_edges")
    restored = load_project(json.dumps(document).encode())
    assert restored["gel_image"].orientation.outline_complete is True
    assert restored["gel_image"].orientation.supported_edges == ()


@pytest.mark.parametrize("complete,edges", [
    (1, ("left",)),
    ("yes", ()),
    (True, ["left", "right"]),
    (True, ("left", "left")),
    (False, ("left", "center")),
    (False, ("left", None)),
    (False, ([],)),
])
def test_invalid_outline_support_metadata_is_rejected(complete, edges):
    state = project_state()
    gel = state["gel_image"]
    state["gel_image"] = replace(gel, orientation=replace(
        gel.orientation, outline_complete=complete, supported_edges=edges,
    ))
    with pytest.raises(ProjectError):
        load_project(save_project(state))


def test_orientation_review_restores_previous_source_identity_and_manual_selection():
    state = project_state("wells_top")
    previous = state["gel_image"]
    state.update(gel_image=replace(previous, orientation=None), orientation_previous_gel=previous,
                 orientation_preview=previous, orientation_preview_method="confirmed",
                 orientation_manual=True, orientation_selection={"cx": 60., "cy": 45.,
                    "width": 100., "height": 70., "angle_degrees": 0.})
    restored = load_project(save_project(state))
    assert restored["lane_source"] is restored["orientation_previous_gel"]
    assert restored["orientation_preview"] is restored["orientation_previous_gel"]
    assert restored["orientation_manual"]
    assert restored["orientation_selection"] == state["orientation_selection"]


def test_pending_orientation_change_preserves_previous_analysis_until_confirmation():
    state = project_state("wells_left")
    previous = state["gel_image"]
    state.update(gel_image=replace(previous, orientation=None, workflow_orientation="wells_top"),
                 orientation_previous_gel=previous,
                 orientation_preview=replace(previous, workflow_orientation="wells_top"),
                 orientation_preview_method="manual")
    restored = load_project(save_project(state))
    assert restored["gel_image"].workflow_orientation == "wells_top"
    assert restored["orientation_previous_gel"].workflow_orientation == "wells_left"
    assert restored["lane_source"] is restored["orientation_previous_gel"]
    assert restored["lane_crop"].workflow_orientation == "wells_left"


@pytest.mark.parametrize("stage", [None, "borders", "extent"])
def test_pre_crop_drafts_restore(stage):
    state = project_state("wells_top")
    state.update(lane_stage=stage, lane_crop=None, annotation_data=None, annotation_geometry=None,
                 ladder_data=None, ladder_draft=None)
    restored = load_project(save_project(state))
    assert restored["lane_stage"] == stage
    assert restored["well_result"] == state["well_result"]


def test_image_before_orientation_can_be_saved_and_reopened():
    state = project_state("wells_top")
    raw = {"gel_image": replace(state["gel_image"], orientation=None)}
    restored = load_project(save_project(raw))
    assert restored["gel_image"] == raw["gel_image"]
    assert restored["lane_stage"] is None


@pytest.mark.parametrize("orientation", ["wells_left", "wells_top"])
def test_final_composition_and_svg_round_trip_match_preview(orientation):
    from gel_analyzer.annotation_exports import validate_svg_composition
    state = project_state(orientation, 45)
    crop = state["lane_crop"]
    size = (crop.width + 20, crop.height + 20)
    png = image_bytes(Image.new("RGB", size, "white"), "PNG")
    markup = (f'<svg xmlns="http://www.w3.org/2000/svg" width="{size[0]}" height="{size[1]}" '
              f'viewBox="0 0 {size[0]} {size[1]}"><image x="10" y="10" width="{crop.width}" height="{crop.height}"/></svg>')
    svg = validate_svg_composition({"width": size[0], "height": size[1], "gel_x": 10, "gel_y": 10, "svg": markup}, crop)
    state.update(annotation_stage="final", annotation_completed=True, annotation_png=png,
                 annotation_svg=svg, annotation_dimensions=size, annotation_base_png=png,
                 annotation_base_svg=svg, annotation_base_dimensions=size, ladder_draft=None)
    restored = load_project(save_project(state))
    assert restored["annotation_png"] == png
    assert restored["annotation_svg"] == svg
    assert restored["annotation_base_png"] == png
    assert restored["annotation_dimensions"] == size
    assert restored["annotation_stage"] == "final"


def test_bands_reopen_on_their_original_lane_and_migration_axis():
    state = project_state("wells_top")
    candidates = []
    for left, top, right, bottom in state["lane_crop"].lanes:
        x, y = (left + right) / 2, (top + bottom) / 2
        candidates.append([{"x": x, "y": y, "position": y, "signal": 24.5}])
    state["band_data"] = candidates
    restored = load_project(save_project(state))
    assert restored["band_data"] == candidates
    assert restored["band_geometry"][-1] == "wells_top"
    assert isinstance(restored["band_editor_generation"], int)
    candidates[0][0]["signal"] = None
    assert load_project(save_project(state))["band_data"][0][0]["signal"] is None
    crop = state["lane_crop"]
    state.update(lane_stage="borders", lane_crop=None,
                 band_geometry=(sha256(crop.preview_png).hexdigest(), tuple(crop.lanes), "wells_top"))
    restored = load_project(save_project(state))
    assert restored["band_data"] == candidates
    assert restored["band_geometry"] == state["band_geometry"]


@pytest.mark.parametrize("change", [
    lambda document: document.update(version=42),
    lambda document: document["state"]["gel_image"]["fields"].update(workflow_orientation="sideways"),
    lambda document: document["state"]["lane_crop"]["fields"].update(workflow_orientation="wells_left"),
    lambda document: document["state"].update(lane_right=-4),
    lambda document: document["state"]["annotation_data"].update(laneLabelAngle=12),
    lambda document: document["state"]["gel_image"]["fields"]["preview_png"].update({"$bytes": "bad"}),
    lambda document: document["state"].update(gel_image={"$record": "Executable", "fields": {}}),
    lambda document: document["state"]["ladder_data"].update(laneIndex=100),
])
def test_invalid_projects_fail_without_mutating_the_existing_session(change):
    state = project_state("wells_top")
    original = state["gel_image"]
    document = json.loads(save_project(state))
    change(document)
    with pytest.raises(ProjectError):
        load_project(json.dumps(document).encode())
    assert state["gel_image"] is original


@pytest.mark.parametrize("payload", [b"", b"not json", b"[]", b'{"format":"gel-analyzer-project","version":1,"state":NaN}'])
def test_malformed_project_is_rejected(payload):
    with pytest.raises(ProjectError):
        load_project(payload)


@pytest.mark.parametrize("orientation", ["wells_left", "wells_top"])
def test_restored_state_keeps_crop_editor_and_angle_without_project_controls(orientation):
    from streamlit.testing.v1 import AppTest
    state = project_state(orientation, 45)
    app = AppTest.from_file(Path(__file__).parents[1] / "app.py").run()
    # Serialization stays compatible with earlier saved state; its former
    # Project popover is no longer part of the application interface.
    for key, value in load_project(save_project(state)).items():
        app.session_state[key] = value
    app.run()
    assert not app.exception
    assert not app.error
    assert app.session_state["gel_image"].workflow_orientation == orientation
    assert app.session_state["lane_crop"] == state["lane_crop"]
    assert app.session_state["annotation_data"]["laneLabelAngle"] == 45
    assert app.session_state["lane_source"] is app.session_state["gel_image"]
    assert all(uploader.key != "project_upload" for uploader in app.file_uploader)
    assert all(button.label != "Save project" for button in app.get("download_button"))
    assert all(popover.proto.popover.label != "Project" for popover in app.get("popover"))
    assert app.subheader[0].value == "Annotate lanes"


def test_project_controls_are_absent_before_upload():
    from streamlit.testing.v1 import AppTest
    app = AppTest.from_file(Path(__file__).parents[1] / "app.py").run()
    assert not app.exception
    assert [uploader.label for uploader in app.file_uploader] == ["Open a gel image"]
    assert all(popover.proto.popover.label != "Project" for popover in app.get("popover"))
    assert all(button.label != "Save project" for button in app.get("download_button"))
