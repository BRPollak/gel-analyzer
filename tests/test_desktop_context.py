"""Keep annotation repairs confined to the Windows native backend."""

import os
from types import SimpleNamespace

import pytest

from gel_analyzer import desktop, desktop_context


@pytest.mark.parametrize("platform", ["win32", "darwin", "linux"])
@pytest.mark.parametrize("marker", [None, "0", "1", "true"])
def test_windows_desktop_requires_both_platform_and_backend_marker(monkeypatch, platform, marker):
    monkeypatch.setattr(desktop_context, "sys", SimpleNamespace(platform=platform))
    if marker is None:
        monkeypatch.delenv("GEL_ANALYZER_DESKTOP", raising=False)
    else:
        monkeypatch.setenv("GEL_ANALYZER_DESKTOP", marker)
    assert desktop_context.is_windows_desktop() is (platform == "win32" and marker == "1")


@pytest.mark.parametrize("platform", ["win32", "darwin"])
@pytest.mark.parametrize("previous_marker", [None, "unrelated"])
def test_native_backend_marks_windows_before_bootstrap_without_mutating_mac_environment(
        monkeypatch, tmp_path, platform, previous_marker):
    from streamlit.web import bootstrap

    # Record even an initially absent variable so the backend's direct write
    # is restored when this test finishes.
    monkeypatch.setenv("GEL_ANALYZER_DESKTOP", previous_marker or "")
    if previous_marker is None:
        monkeypatch.delenv("GEL_ANALYZER_DESKTOP", raising=False)
    monkeypatch.setattr(desktop, "sys", SimpleNamespace(platform=platform))
    monkeypatch.setattr(desktop, "threading", SimpleNamespace(Thread=lambda **_: SimpleNamespace(start=lambda: None)))
    monkeypatch.setattr(desktop, "resource_root", lambda: tmp_path)
    monkeypatch.chdir(tmp_path)
    options = {"server.port": 12345}
    monkeypatch.setattr(desktop, "backend_options", lambda *args: options)
    calls = []
    expected_marker = "1" if platform == "win32" else previous_marker

    def load(values):
        assert values == options
        assert os.environ.get("GEL_ANALYZER_DESKTOP") == expected_marker
        calls.append("load")

    def run(path, hello, args, values):
        assert path == str(tmp_path / "app.py")
        assert (hello, args, values) == (False, [], options)
        assert os.environ.get("GEL_ANALYZER_DESKTOP") == expected_marker
        calls.append("run")

    monkeypatch.setattr(bootstrap, "load_config_options", load)
    monkeypatch.setattr(bootstrap, "run", run)
    assert desktop.run_backend(12345, "gel-test", 7) == 0
    assert calls == ["load", "run"]
    assert os.environ.get("GEL_ANALYZER_DESKTOP") == expected_marker


@pytest.mark.parametrize("platform, marker, expected", [
    ("win32", "1", True), ("win32", None, False), ("darwin", "1", False),
    ("darwin", None, False), ("linux", None, False),
])
def test_annotation_bridge_explicitly_passes_the_native_windows_flag(monkeypatch, platform, marker, expected):
    from gel_analyzer import annotation_component

    monkeypatch.setattr(desktop_context, "sys", SimpleNamespace(platform=platform))
    if marker is None:
        monkeypatch.delenv("GEL_ANALYZER_DESKTOP", raising=False)
    else:
        monkeypatch.setenv("GEL_ANALYZER_DESKTOP", marker)
    calls = []
    monkeypatch.setattr(annotation_component, "_component", lambda **kwargs: calls.append(kwargs))
    crop = SimpleNamespace(preview_png=b"image", width=10, height=20, lanes=((1, 2, 3, 4),))
    annotation_component.render_annotation_component(crop, annotations={}, token="test", revision=0, error=None, key="test")
    assert len(calls) == 1
    assert calls[0]["windows_desktop"] is expected
