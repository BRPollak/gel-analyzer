"""Validate annotation snapshots and composed image boundaries."""

from base64 import b64encode
from io import BytesIO
from types import SimpleNamespace

from PIL import Image
import pytest

from gel_analyzer.annotations import (
    AnnotationError, default_annotations, validate_annotations, validate_composition,
)


def styled_annotations():
    data = default_annotations(2)
    data["labels"][0].update(text="α control", bold=True, italic=True, color="#AA11ee")
    data["labels"][1]["text"] = "Treated"
    data["groups"] = [
        {"id": "group-1", "set": 0, "lanes": [1, 0], "label": "Experiment",
         "bold": True, "italic": True, "color": "#1357ab"},
        {"id": "group-2", "set": 1, "lanes": [1], "label": "Replicate A",
         "bold": False, "italic": True, "color": "#204060"},
    ]
    return data


def rich_annotations():
    data = styled_annotations()
    data["labels"][0]["runs"] = [
        {"text": "α", "bold": True, "italic": False, "color": "#AA11ee"},
        {"text": " control", "bold": False, "italic": True, "color": "#202020"},
    ]
    data["labels"][1]["runs"] = [
        {"text": "Treat", "bold": False, "italic": False, "color": "#202020"},
        {"text": "ed", "bold": True, "italic": True, "color": "#1357ab"},
    ]
    data["groups"][0]["runs"] = [
        {"text": "Exper", "bold": True, "italic": True, "color": "#1357ab"},
        {"text": "iment", "bold": False, "italic": False, "color": "#AA11ee"},
    ]
    return data


def composition(crop, *, mode="RGB", image_format="PNG", gutter=180):
    image = Image.new(mode, (crop.width + gutter, crop.height + 24), "white")
    if hasattr(crop, "preview_png"):
        with Image.open(BytesIO(crop.preview_png)) as gel:
            image.paste(gel.convert(mode), (gutter, 12))
    output = BytesIO()
    image.save(output, format=image_format)
    png = output.getvalue()
    return {
        "png": "data:image/png;base64," + b64encode(png).decode("ascii"),
        "width": image.width, "height": image.height, "gel_x": gutter, "gel_y": 12,
    }, png


def test_defaults_have_one_independent_editable_label_per_lane():
    data = default_annotations(3)
    assert [label["text"] for label in data["labels"]] == ["Lane 1", "Lane 2", "Lane 3"]
    assert data["groups"] == []
    assert validate_annotations(data, 3) == data
    data["labels"][0]["bold"] = True
    assert data["labels"][1]["bold"] is False
    assert default_annotations(3)["labels"][0]["bold"] is False


@pytest.mark.parametrize("lanes,expected", [
    (((3, 3, 203, 41), (5, 61, 203, 104)), 32),
    (((20, 100, 1500, 150), (20, 400, 1500, 550)), 80),
    (((20, 0, 1500, 50), (20, 50, 1500, 200)), 80),
    (((40, 200, 3000, 300), (40, 800, 3000, 1100)), 160),
])
def test_initial_font_tracks_native_mean_lane_height_not_gaps_or_image_width(lanes, expected):
    # Mixed lane heights average to 40.5, 100, or 200 native pixels. The
    # initial text scale follows that height even on widely separated lanes.
    data = default_annotations(len(lanes), lanes=lanes)
    assert data["fontSize"] == expected
    assert validate_annotations(data, len(lanes)) == data


@pytest.mark.parametrize("size", [1, 72, 4096])
def test_valid_user_font_sizes_are_preserved_without_old_48_pixel_cap(size):
    data = styled_annotations()
    data["fontSize"] = size
    assert validate_annotations(data, 2)["fontSize"] == size


@pytest.mark.parametrize("size", [0, -1, True, False, 32.0, 32.5, 4097, "32", None])
def test_font_size_requires_positive_whole_pixels_within_canvas_limit(size):
    data = styled_annotations()
    data["fontSize"] = size
    with pytest.raises(AnnotationError):
        validate_annotations(data, 2)


def test_both_styles_and_independent_group_sets_survive_detached_snapshot():
    source = styled_annotations()
    checked = validate_annotations(source, 2)
    assert checked["labels"] == source["labels"]
    assert checked["groups"][0] == {**source["groups"][0], "lanes": [0, 1]}
    assert checked["groups"][1] == source["groups"][1]
    # A late browser mutation cannot edit an accepted snapshot by reference.
    source["labels"][0]["text"] = "Late edit"
    source["groups"][0]["lanes"].clear()
    assert checked["labels"][0]["text"] == "α control"
    assert checked["groups"][0]["lanes"] == [0, 1]


def test_mixed_formatting_survives_detached_snapshot_for_labels_and_groups():
    source = rich_annotations()
    checked = validate_annotations(source, 2)
    assert checked["labels"] == source["labels"]
    assert checked["groups"][0]["runs"] == source["groups"][0]["runs"]
    source["labels"][0]["runs"][0]["color"] = "#000000"
    source["groups"][0]["runs"][1]["text"] = "Late edit"
    assert checked["labels"][0]["runs"][0]["color"] == "#AA11ee"
    assert checked["groups"][0]["runs"][1]["text"] == "iment"


@pytest.mark.parametrize("collection,text_key", [("labels", "text"), ("groups", "label")])
def test_adjacent_matching_runs_merge_without_changing_text_or_source(collection, text_key):
    data = styled_annotations()
    label = data[collection][0]
    style = {key: label[key] for key in ("bold", "italic", "color")}
    label["runs"] = [{"text": char, **style} for char in label[text_key]]
    checked = validate_annotations(data, 2)
    assert checked[collection][0]["runs"] == [{"text": label[text_key], **style}]
    assert len(label["runs"]) == len(label[text_key])


@pytest.mark.parametrize("runs", [
    None, {}, "Lane 1", [],
    [{"text": "Lane 1", "bold": 1, "italic": False, "color": "#202020"}],
    [{"text": "Lane 1", "bold": False, "italic": "false", "color": "#202020"}],
    [{"text": "Lane 1", "bold": False, "italic": False, "color": "red"}],
    [{"text": "Lane 1", "bold": False, "color": "#202020"}],
    [{"text": "Lane\n1", "bold": False, "italic": False, "color": "#202020"}],
    [{"text": "", "bold": False, "italic": False, "color": "#202020"}],
    [{"text": "Lane", "bold": False, "italic": False, "color": "#202020"}],
    [{"text": "Different", "bold": False, "italic": False, "color": "#202020"}],
    [{"text": "x" * 501, "bold": False, "italic": False, "color": "#202020"}],
    [None],
])
def test_invalid_or_incomplete_rich_text_is_rejected(runs):
    data = default_annotations(1)
    data["labels"][0]["runs"] = runs
    with pytest.raises(AnnotationError):
        validate_annotations(data, 1)


def test_rich_text_supports_empty_labels_and_bounded_character_level_formatting():
    data = default_annotations(1)
    data["labels"][0].update(text="", runs=[])
    assert validate_annotations(data, 1) == data
    data["labels"][0].update(text="x" * 500, runs=[
        {"text": "x", "bold": bool(index % 2), "italic": False, "color": "#202020"}
        for index in range(500)
    ])
    assert validate_annotations(data, 1) == data
    data["labels"][0]["runs"].append(data["labels"][0]["runs"][0])
    with pytest.raises(AnnotationError):
        validate_annotations(data, 1)


@pytest.mark.parametrize("changes", [
    {"text": "two\nlines"}, {"text": "x" * 501}, {"text": None},
    {"bold": "true"}, {"italic": 1}, {"color": "red"}, {"color": "#12345g"},
])
def test_invalid_label_content_or_formatting_is_rejected(changes):
    data = default_annotations(2)
    data["labels"][0].update(changes)
    with pytest.raises(AnnotationError):
        validate_annotations(data, 2)


@pytest.mark.parametrize("changes", [
    {"lanes": []}, {"lanes": [2]}, {"lanes": [-1]}, {"lanes": [True]},
    {"lanes": [0, 0]}, {"lanes": "0"}, {"set": 2}, {"set": True},
    {"id": "group-2"}, {"id": ""}, {"label": "bad\nlabel"}, {"bold": 1},
])
def test_groups_require_current_members_and_valid_independent_set(changes):
    data = styled_annotations()
    data["groups"][0].update(changes)
    with pytest.raises(AnnotationError):
        validate_annotations(data, 2)


def test_labels_must_match_current_lane_collection():
    with pytest.raises(AnnotationError):
        validate_annotations(default_annotations(2), 3)


@pytest.mark.parametrize("mode", ["RGB", "RGBA"])
def test_composed_png_can_add_gutters_without_resizing_crop(mode):
    crop = SimpleNamespace(width=203, height=107)
    event, png = composition(crop, mode=mode)
    assert validate_composition(event, crop) == png
    with Image.open(BytesIO(png)) as image:
        assert image.size == (383, 131)


@pytest.mark.parametrize("changes", [
    {"width": 200}, {"height": 100}, {"gel_x": -1}, {"gel_y": -1},
    {"gel_x": 181}, {"gel_y": 25}, {"width": True}, {"height": 1.0},
    {"width": 32768}, {"width": 20000, "height": 20000},
    {"png": "data:image/png;base64,invalid!"}, {"png": "not a data URL"},
    {"png": "data:image/png;base64,é"},
])
def test_composition_rejects_invalid_or_clipped_dimensions_and_encoding(changes):
    crop = SimpleNamespace(width=203, height=107)
    event, _ = composition(crop)
    event.update(changes)
    with pytest.raises(AnnotationError):
        validate_composition(event, crop)


@pytest.mark.parametrize("mode,image_format", [("L", "PNG"), ("RGB", "JPEG")])
def test_composition_requires_actual_color_png(mode, image_format):
    crop = SimpleNamespace(width=203, height=107)
    event, _ = composition(crop, mode=mode, image_format=image_format)
    with pytest.raises(AnnotationError):
        validate_composition(event, crop)


def test_png_dimensions_must_match_claimed_canvas():
    crop = SimpleNamespace(width=203, height=107)
    event, _ = composition(crop)
    event["width"] += 1
    with pytest.raises(AnnotationError):
        validate_composition(event, crop)


def test_top_font_uses_lane_width_and_saved_angles_are_compatible():
    data = default_annotations(2, [(0, 0, 20, 400), (40, 0, 80, 400)], "wells_top")
    assert data["fontSize"] == 24
    assert data["laneLabelAngle"] == 90
    data["laneLabelAngle"] = 45
    assert validate_annotations(data, 2)["laneLabelAngle"] == 45
    del data["laneLabelAngle"]
    assert validate_annotations(data, 2)["laneLabelAngle"] == 90
    for invalid in (0, -90, 89, "45", True):
        data["laneLabelAngle"] = invalid
        with pytest.raises(AnnotationError):
            validate_annotations(data, 2)
