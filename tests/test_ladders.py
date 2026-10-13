"""Validate configurable presets and exact, manual crop-relative placements."""

from copy import deepcopy
import json
from types import SimpleNamespace

import pytest

from gel_analyzer.annotations import AnnotationError
from gel_analyzer.ladders import LadderError, load_presets, validate_ladder


@pytest.fixture
def crop():
    return SimpleNamespace(width=203, height=107, lanes=((3, 3, 203, 41), (5, 41, 203, 104)))


def preset():
    return {"id": "test", "name": "Test ladder", "labels": ["5.0 kb", "3.0 kb", "1.0 kb"]}


def ladder():
    return {"preset": preset(), "laneIndex": 0, "placements": [{"markerIndex": 0, "x": 143.625, "y": 28.25}]}


def test_ladder_errors_follow_existing_annotation_error_handling():
    assert issubclass(LadderError, AnnotationError)


def test_bundled_example_is_explicit_and_loads_independent_snapshots():
    presets = load_presets()
    assert presets[0]["name"] == "Example ladder (edit presets file)"
    assert presets[0]["labels"] == ["5.0 kb", "3.0 kb", "1.0 kb"]
    presets[0]["labels"].clear()
    assert load_presets()[0]["labels"] == ["5.0 kb", "3.0 kb", "1.0 kb"]


def test_configured_order_and_labels_are_preserved_without_size_inference(tmp_path):
    path = tmp_path / "presets.json"
    data = [{**preset(), "labels": ["1.0 kb", "unknown", "5.0 kb"]}, {**preset(), "id": "other"}]
    path.write_text(json.dumps(data))
    assert load_presets(path) == data


@pytest.mark.parametrize("contents", ["", "{", "null", "{}", "[]", '[{"id":"broken"}]'])
def test_bad_or_empty_configuration_can_be_skipped(tmp_path, contents):
    path = tmp_path / "presets.json"
    path.write_text(contents)
    with pytest.raises(LadderError, match="skip ladder annotations"):
        load_presets(path)


def test_missing_preset_file_is_a_recoverable_configuration_error(tmp_path):
    with pytest.raises(LadderError, match="No usable ladder presets"):
        load_presets(tmp_path / "missing.json")


@pytest.mark.parametrize("change", [
    {"id": ""}, {"id": "bad id"}, {"id": "a" * 81}, {"id": 1},
    {"name": ""}, {"name": "   "}, {"name": "two\nlines"}, {"name": "x" * 201},
    {"labels": []}, {"labels": "5 kb"}, {"labels": [None]}, {"labels": [""]},
    {"labels": [" "]}, {"labels": ["5 kb\n3 kb"]}, {"labels": ["5 kb\u20283 kb"]},
    {"labels": ["x" * 201]}, {"labels": ["5 kb", "5 kb"]}, {"labels": ["5 kb", " 5 kb "]},
    {"labels": [str(index) for index in range(201)]},
])
def test_preset_fields_are_bounded_nonempty_single_line_and_unique(tmp_path, change):
    path = tmp_path / "presets.json"
    path.write_text(json.dumps([{**preset(), **change}]))
    with pytest.raises(LadderError):
        load_presets(path)


def test_preset_identifiers_must_be_unique(tmp_path):
    path = tmp_path / "presets.json"
    path.write_text(json.dumps([preset(), preset()]))
    with pytest.raises(LadderError, match="ids must be unique"):
        load_presets(path)


def test_snapshot_is_detached_and_preserves_fractional_native_coordinates(crop):
    source = ladder()
    original = deepcopy(source)
    checked = validate_ladder(source, crop, complete=True)
    assert checked == original
    source["preset"]["labels"][0] = "Changed"
    source["placements"][0]["x"] = 100
    assert checked == original


def test_existing_snapshot_does_not_depend_on_current_preset_file(crop, monkeypatch, tmp_path):
    monkeypatch.setattr("gel_analyzer.ladders.PRESETS_PATH", tmp_path / "missing.json")
    assert validate_ladder(ladder(), crop, complete=True) == ladder()


@pytest.mark.parametrize("draft", [None, {"preset": None, "laneIndex": None, "placements": []},
    {"preset": preset(), "laneIndex": None, "placements": []},
    {"preset": preset(), "laneIndex": 0, "placements": []}])
def test_partial_drafts_are_allowed_but_cannot_be_confirmed(crop, draft):
    assert validate_ladder(draft, crop) == draft
    with pytest.raises(LadderError, match="at least one"):
        validate_ladder(draft, crop, complete=True)


@pytest.mark.parametrize("changes", [
    {"preset": None}, {"preset": "test"}, {"laneIndex": None}, {"laneIndex": True},
    {"laneIndex": -1}, {"laneIndex": 2}, {"laneIndex": 0.0}, {"placements": None},
    {"placements": [None]}, {"placements": [{}]},
])
def test_malformed_snapshot_is_rejected(crop, changes):
    with pytest.raises(LadderError):
        validate_ladder({**ladder(), **changes}, crop)


@pytest.mark.parametrize("changes", [
    {"markerIndex": -1}, {"markerIndex": 3}, {"markerIndex": True}, {"markerIndex": 0.0},
    {"x": True}, {"x": "5"}, {"x": None}, {"x": float("nan")}, {"x": float("inf")},
    {"y": float("-inf")}, {"x": 10 ** 1000}, {"x": 2.999}, {"x": 203},
    {"y": 2.999}, {"y": 41}, {"y": 55}, {"x": -1},
])
def test_invalid_marker_identity_coordinates_or_lane_membership_are_rejected(crop, changes):
    data = ladder()
    data["placements"][0].update(changes)
    with pytest.raises(LadderError):
        validate_ladder(data, crop)


def test_duplicate_marker_is_rejected_but_coincident_different_markers_are_allowed(crop):
    data = ladder()
    data["placements"].append(dict(data["placements"][0]))
    with pytest.raises(LadderError, match="at most once"):
        validate_ladder(data, crop)
    data["placements"][1]["markerIndex"] = 2
    assert validate_ladder(data, crop, complete=True) == data


def test_half_open_shared_boundary_belongs_only_to_lower_lane(crop):
    data = ladder()
    data["placements"][0].update(x=5, y=41)
    with pytest.raises(LadderError, match="highlighted ladder lane"):
        validate_ladder(data, crop)
    data["laneIndex"] = 1
    assert validate_ladder(data, crop, complete=True)["placements"][0] == {"markerIndex": 0, "x": 5.0, "y": 41.0}


def test_input_snapshot_is_not_modified_by_validation(crop):
    data = ladder()
    data["selectedMarker"] = 2
    data["preset"]["extra"] = "ignored"
    original = deepcopy(data)
    checked = validate_ladder(data, crop)
    assert data == original
    assert "selectedMarker" not in checked
    assert "extra" not in checked["preset"]
