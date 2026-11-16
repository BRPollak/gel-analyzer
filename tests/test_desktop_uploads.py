"""Native image selection uses upload memory without disturbing save memory."""

import base64
import sys
from types import SimpleNamespace

import pytest

from gel_analyzer.desktop import DesktopAPI
from gel_analyzer.desktop_preferences import last_directory, remember_directory
from gel_analyzer.desktop_uploads import ImagePicker, install_upload_picker


@pytest.fixture(autouse=True)
def isolated_picker(tmp_path, monkeypatch):
    monkeypatch.setenv("GEL_ANALYZER_PREFERENCES_PATH", str(tmp_path / "preferences.json"))
    monkeypatch.setitem(sys.modules, "webview", SimpleNamespace(FileDialog=SimpleNamespace(OPEN="open")))


def test_native_picker_remembers_selected_folder_on_next_open(tmp_path):
    folder = tmp_path / "Input gels"
    folder.mkdir()
    image = folder / "example.TIFF"
    image.write_bytes(b"gel image")
    remember_directory("download", tmp_path)
    calls = []
    selections = iter([(str(image),), None])

    def choose(kind, **options):
        calls.append((kind, options))
        return next(selections)

    picker = ImagePicker()
    picker.window = SimpleNamespace(create_file_dialog=choose)
    result = picker.choose_image()
    assert result == {"name": image.name, "type": "image/tiff",
                      "data": base64.b64encode(b"gel image").decode("ascii")}
    assert last_directory("upload") == str(folder)
    assert picker.choose_image() is None
    assert calls[1][1]["directory"] == str(folder)
    assert calls[1][0] == "open" and calls[1][1]["allow_multiple"] is False
    assert last_directory("download") == str(tmp_path)


@pytest.mark.parametrize("failure", ["cancel", "missing", "unsupported", "oversized"])
def test_cancelled_or_failed_open_preserves_last_folder(tmp_path, monkeypatch, failure):
    previous = tmp_path / "previous"
    previous.mkdir()
    remember_directory("upload", previous)
    path = tmp_path / ("image.txt" if failure == "unsupported" else "image.png")
    if failure != "missing":
        path.write_bytes(b"image")
    monkeypatch.setattr("gel_analyzer.desktop_uploads.MAX_IMAGE_BYTES", 2 if failure == "oversized" else 200)
    picker = ImagePicker()
    picker.window = SimpleNamespace(create_file_dialog=lambda *_, **__: None if failure == "cancel" else (str(path),))
    result = picker.choose_image()
    assert result is None if failure == "cancel" else result.get("error")
    assert last_directory("upload") == str(previous)


def test_desktop_api_only_selects_files_with_user_dialog(tmp_path):
    api = DesktopAPI()
    assert api.choose_image() is None
    api._image_picker.window = SimpleNamespace(create_file_dialog=lambda *_, **__: None)
    assert api.choose_image() is None
    with pytest.raises(TypeError):
        api.choose_image(str(tmp_path / "not-user-selected.png"))


def test_install_upload_bridge_loads_bundled_script():
    scripts = []
    install_upload_picker(SimpleNamespace(run_js=scripts.append))
    assert len(scripts) == 1 and "api.choose_image()" in scripts[0]
