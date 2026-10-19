"""Desktop process lifecycle, packaging paths, and local-only configuration."""

import os
from pathlib import Path
import socket
import subprocess
import sys

import pytest

from gel_analyzer import desktop


def test_frozen_backend_reuses_bundle_executable(monkeypatch):
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "_MEIPASS", "/Applications/Gel Analyzer.app/Contents/Resources", raising=False)
    command = desktop.backend_command(12345, "gel-session", 7)
    assert command == [sys.executable, "--gel-backend", "--port", "12345", "--base-path",
                       "gel-session", "--parent-pipe", "7"]
    assert desktop.resource_root() / "app.py" == Path("/Applications/Gel Analyzer.app/Contents/Resources/app.py")


def test_development_backend_uses_absolute_entrypoint(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    command = desktop.backend_command(12345, "gel-session", 7)
    assert Path(command[1]).is_absolute()
    assert Path(command[1]).is_file()
    assert Path(command[1]).name == "desktop_app.py"


def test_bundled_config_overrides_server_and_telemetry_settings(tmp_path, monkeypatch):
    (tmp_path / ".streamlit").mkdir()
    (tmp_path / ".streamlit" / "config.toml").write_text(
        '[server]\naddress="0.0.0.0"\nport=8501\nheadless=false\n'
        '[browser]\ngatherUsageStats=true\n[theme]\nprimaryColor="#123456"\n'
    )
    monkeypatch.chdir("/")
    options = desktop.backend_options(tmp_path, 49152, "gel-private")
    assert options["global.developmentMode"] is False
    assert options["server.address"] == "127.0.0.1"
    assert options["server.port"] == 49152
    assert options["server.baseUrlPath"] == "gel-private"
    assert options["server.headless"] is True
    assert options["browser.gatherUsageStats"] is False
    assert options["server.fileWatcherType"] == "none"
    assert options["server.enableXsrfProtection"] is True
    assert options["theme.primaryColor"] == "#123456"


def test_local_health_checks_ignore_proxy_environment(tmp_path, monkeypatch):
    monkeypatch.setenv("HTTP_PROXY", "http://proxy.invalid:8080")
    backend = desktop.Backend(tmp_path)
    assert not any(getattr(handler, "proxies", None) for handler in backend._http.handlers)


def test_backend_starts_outside_checkout_and_shuts_down(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    backend = desktop.Backend(tmp_path / "logs", startup_timeout=20)
    try:
        url = backend.start()
        assert url.startswith("http://127.0.0.1:") and "/gel-" in url
        assert backend._healthy()
        assert backend.process.poll() is None
        with backend._http.open(url, timeout=2) as response:
            assert response.status == 200
            assert b"Streamlit" in response.read()
    finally:
        backend.stop()
    assert backend.process.poll() is not None
    backend.stop()  # A closed-window callback and finally block may both run.


def test_occupied_port_is_retried_without_attaching_to_existing_server(tmp_path, monkeypatch):
    original = desktop.available_port
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as occupied:
        occupied.bind(("127.0.0.1", 0))
        occupied.listen()
        occupied_port = occupied.getsockname()[1]
        ports = iter([occupied_port, original()])
        monkeypatch.setattr(desktop, "available_port", lambda: next(ports))
        backend = desktop.Backend(tmp_path, startup_timeout=20)
        try:
            assert f":{occupied_port}/" not in backend.start()
            assert backend._healthy()
        finally:
            backend.stop()


def test_unresponsive_startup_is_timed_out_and_reaped(tmp_path, monkeypatch):
    monkeypatch.setattr(desktop, "backend_command", lambda *_: [
        sys.executable, "-c", "import time; time.sleep(60)",
    ])
    backend = desktop.Backend(tmp_path, startup_timeout=0.2)
    with pytest.raises(desktop.BackendError, match="did not become ready"):
        backend.start()
    assert backend.process.poll() is not None
    assert backend._parent_pipe is None


def test_repeated_early_exit_reports_failure_and_reaps_process(tmp_path, monkeypatch):
    monkeypatch.setattr(desktop, "backend_command", lambda *_: [sys.executable, "-c", "raise SystemExit(2)"])
    backend = desktop.Backend(tmp_path, startup_timeout=5)
    with pytest.raises(desktop.BackendError, match="could not start"):
        backend.start()
    assert backend.process.returncode == 2
    assert backend._parent_pipe is None


def test_closed_window_prevents_backend_start(tmp_path):
    backend = desktop.Backend(tmp_path)
    backend.stop()
    with pytest.raises(desktop.BackendError, match="cancelled"):
        backend.start()
    assert backend.process is None


def test_parent_pipe_eof_exits_backend_even_without_normal_shutdown():
    read_pipe, write_pipe = os.pipe()
    process = subprocess.Popen([
        sys.executable, "-c",
        "from gel_analyzer.desktop import watch_parent; import sys; watch_parent(int(sys.argv[1]))",
        str(read_pipe),
    ], pass_fds=(read_pipe,), cwd=desktop.resource_root())
    os.close(read_pipe)
    try:
        assert process.poll() is None
        os.close(write_pipe)
        write_pipe = None
        assert process.wait(timeout=5) == 0
    finally:
        if write_pipe is not None:
            os.close(write_pipe)
        if process.poll() is None:
            process.kill()
            process.wait()


def test_error_page_escapes_diagnostics_and_log_override(tmp_path, monkeypatch):
    monkeypatch.setenv("GEL_ANALYZER_LOG_DIR", str(tmp_path))
    assert desktop.log_directory() == tmp_path
    html = desktop.status_page("Cannot start", '<script>alert("failure")</script>', log_path=tmp_path)
    assert "<script>" not in html
    assert "&lt;script&gt;" in html
    assert str(tmp_path) in html
