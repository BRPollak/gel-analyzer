"""Windows preflight checks must fail before loading the native browser."""

from contextlib import contextmanager
import sys
from types import SimpleNamespace

import pytest

from gel_analyzer import desktop, desktop_downloads, windows_runtime


@pytest.fixture
def registry(monkeypatch):
    values = {}
    @contextmanager
    def open_key(root, path, reserved, access):
        key = (root, path, access)
        if key not in values:
            raise FileNotFoundError(path)
        yield key
    fake = SimpleNamespace(HKEY_LOCAL_MACHINE="machine", HKEY_CURRENT_USER="user",
                           KEY_READ=1, KEY_WOW64_32KEY=512, OpenKey=open_key,
                           QueryValueEx=lambda key, name: (values[key][name], 0))
    monkeypatch.setitem(sys.modules, "winreg", fake)
    monkeypatch.setattr(sys, "getwindowsversion",
                        lambda: SimpleNamespace(major=10, minor=0, build=19045), raising=False)
    values[("machine", r"SOFTWARE\Microsoft\NET Framework Setup\NDP\v4\Full", 513)] = {
        "Release": 528040,
    }
    return values


@pytest.mark.parametrize("root,view", [("user", 1), ("machine", 513)])
@pytest.mark.parametrize("build", [19045, 22621])
@pytest.mark.parametrize("version", ["146.0.3856.49", "154.0.4258.31"])
def test_supported_windows_with_user_or_machine_webview(registry, monkeypatch, root, view, build, version):
    monkeypatch.setattr(sys, "getwindowsversion",
                        lambda: SimpleNamespace(major=10, minor=0, build=build))
    registry[(root, rf"SOFTWARE\Microsoft\EdgeUpdate\Clients\{windows_runtime.WEBVIEW2_CLIENT}", view)] = {
        "pv": version,
    }
    assert windows_runtime.prerequisite_error() is None


def test_old_windows_has_actionable_requirement(registry, monkeypatch):
    monkeypatch.setattr(sys, "getwindowsversion",
                        lambda: SimpleNamespace(major=10, minor=0, build=19044))
    assert "Windows 10 version 22H2" in windows_runtime.prerequisite_error()


@pytest.mark.parametrize("release", [None, 461808, "528040"])
def test_missing_or_old_net_framework_is_reported(registry, release):
    registry[("machine", r"SOFTWARE\Microsoft\NET Framework Setup\NDP\v4\Full", 513)] = {
        "Release": release,
    }
    assert ".NET Framework 4.8" in windows_runtime.prerequisite_error()


@pytest.mark.parametrize("version", [None, "0.0.0.0", "85.0.564.0", "invalid", "130"])
def test_missing_or_invalid_webview_has_repair_instructions(registry, version):
    registry[("user", rf"SOFTWARE\Microsoft\EdgeUpdate\Clients\{windows_runtime.WEBVIEW2_CLIENT}", 1)] = {
        "pv": version,
    }
    error = windows_runtime.prerequisite_error()
    assert "WebView2 Runtime" in error
    assert "installer again" in error
    assert "without internet access" in error


@pytest.mark.parametrize("root,view", [("user", 1), ("machine", 513)])
@pytest.mark.parametrize("version", ["86.0.622.0", "97.0.1072.69", "130.0.2849.68", "146.0.3856.48"])
def test_registered_but_old_webview_requires_bundled_upgrade(registry, root, view, version):
    registry[(root, rf"SOFTWARE\Microsoft\EdgeUpdate\Clients\{windows_runtime.WEBVIEW2_CLIENT}", view)] = {
        "pv": version,
    }
    error = windows_runtime.prerequisite_error()
    assert error is not None
    assert "WebView2 Runtime" in error
    assert "installer again" in error


def test_missing_registry_keys_are_treated_as_missing_runtime(registry):
    registry.clear()
    assert ".NET Framework 4.8" in windows_runtime.prerequisite_error()


def test_preflight_failure_does_not_import_browser(monkeypatch, tmp_path):
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setenv("GEL_ANALYZER_LOG_DIR", str(tmp_path))
    monkeypatch.setattr(desktop, "configure_logging", lambda directory: None)
    monkeypatch.setattr(windows_runtime, "prerequisite_error", lambda: "Install WebView2.")
    messages = []
    monkeypatch.setattr(windows_runtime, "show_error", messages.append)
    monkeypatch.setitem(sys.modules, "webview", None)
    assert desktop.run_desktop() == 1
    assert messages == ["Install WebView2."]


def test_windows_desktop_requests_edge_and_native_downloads(monkeypatch, tmp_path):
    backend = desktop.Backend(tmp_path)
    monkeypatch.setattr(desktop, "Backend", lambda directory: backend)
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setenv("GEL_ANALYZER_LOG_DIR", str(tmp_path))
    monkeypatch.setattr(desktop, "configure_logging", lambda directory: None)
    monkeypatch.setattr(windows_runtime, "prerequisite_error", lambda: None)
    class Event:
        def __init__(self):
            self.callbacks = []

        def __iadd__(self, callback):
            self.callbacks.append(callback)
            return self
    window = SimpleNamespace(events=SimpleNamespace(closed=Event(), initialized=Event()))
    settings, calls = {}, []
    fake_webview = SimpleNamespace(
        settings=settings,
        create_window=lambda *args, **kwargs: window,
        start=lambda callback, **kwargs: calls.append(kwargs),
    )
    monkeypatch.setitem(sys.modules, "webview", fake_webview)
    assert desktop.run_desktop() == 0
    assert calls == [{"gui": "edgechromium", "debug": False, "private_mode": True}]
    assert settings["ALLOW_DOWNLOADS"] is False, "Downloads stay disabled until the adapter is installed"
    assert window.events.initialized.callbacks == [desktop_downloads.configure_downloads]
    assert settings["OPEN_EXTERNAL_LINKS_IN_BROWSER"] is False
