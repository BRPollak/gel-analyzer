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
