"""Native folder choices persist independently and tolerate unavailable storage."""

import json
from pathlib import Path
import sys

import pytest

from gel_analyzer import desktop_preferences as preferences


@pytest.fixture(autouse=True)
def preference_file(tmp_path, monkeypatch):
    path = tmp_path / "settings" / "preferences.json"
    monkeypatch.setenv("GEL_ANALYZER_PREFERENCES_PATH", str(path))
    return path


def test_folders_persist_separately_and_are_read_fresh(preference_file, tmp_path):
    uploads, downloads, next_upload = [tmp_path / name for name in ("images", "results", "next")]
    for folder in (uploads, downloads, next_upload):
        folder.mkdir()
    preferences.remember_directory("upload", uploads)
    preferences.remember_directory("download", downloads)
    assert preferences.last_directory("upload") == str(uploads)
    assert preferences.last_directory("download") == str(downloads)
    # A new app process can read the file without any session state.
    preference_file.write_text(json.dumps({"upload_directory": str(next_upload),
                                          "download_directory": str(downloads)}))
    assert preferences.last_directory("upload") == str(next_upload)
    assert preferences.last_directory("download") == str(downloads)


@pytest.mark.parametrize("contents", ["broken json", "[]", '{"upload_directory": 12}',
                                      '{"upload_directory": "relative"}'])
def test_corrupt_preferences_use_default_and_can_recover(preference_file, tmp_path, contents):
    preference_file.parent.mkdir()
    preference_file.write_text(contents)
    assert preferences.last_directory("upload", "fallback") == "fallback"
    preferences.remember_directory("upload", tmp_path)
    assert preferences.last_directory("upload") == str(tmp_path)


def test_missing_folder_falls_back_without_overwriting_other_memory(tmp_path):
    unavailable = tmp_path / "external drive"
    unavailable.mkdir()
    preferences.remember_directory("upload", unavailable)
    preferences.remember_directory("download", tmp_path)
    unavailable.rmdir()
    assert preferences.last_directory("upload", "fallback") == "fallback"
    assert preferences.last_directory("download") == str(tmp_path)
    unavailable.mkdir()
    assert preferences.last_directory("upload") == str(unavailable)


def test_preferences_write_failure_does_not_break_file_operation(tmp_path, monkeypatch):
    def fail(*args, **kwargs):
        raise PermissionError("Read-only settings directory")
    monkeypatch.setattr(preferences, "NamedTemporaryFile", fail)
    preferences.remember_directory("upload", tmp_path)
    assert preferences.last_directory("upload", "fallback") == "fallback"


@pytest.mark.parametrize("platform", ["win32", "darwin"])
def test_settings_live_in_user_data_folder(tmp_path, monkeypatch, platform):
    monkeypatch.delenv("GEL_ANALYZER_PREFERENCES_PATH")
    monkeypatch.setattr(sys, "platform", platform)
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "Local"))
    root = tmp_path / "Local" if platform == "win32" else tmp_path / "Library" / "Application Support"
    assert preferences.preferences_path() == root / "Gel Analyzer" / "preferences.json"
