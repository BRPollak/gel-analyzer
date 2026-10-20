"""Desktop process lifecycle, packaging paths, and local-only configuration."""

import os
from pathlib import Path
import socket
import subprocess
import sys
import time
from types import SimpleNamespace

import pytest

from gel_analyzer import desktop


def test_frozen_backend_reuses_bundle_executable(monkeypatch):
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "_MEIPASS", "/Applications/Gel Analyzer.app/Contents/Resources", raising=False)
    command = desktop.backend_command(12345, "gel-session", 7)
    parent_option = "--parent-handle" if sys.platform == "win32" else "--parent-pipe"
    assert command == [sys.executable, "--gel-backend", "--port", "12345", "--base-path",
                       "gel-session", parent_option, "7"]
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


@pytest.mark.parametrize("windowed", [False, True])
def test_parent_pipe_eof_exits_backend_even_without_normal_shutdown(tmp_path, monkeypatch, windowed):
    interpreter = Path(sys.executable)
    if windowed:
        if sys.platform != "win32":
            pytest.skip("pythonw.exe is a Windows-only launcher")
        interpreter = interpreter.with_name("pythonw.exe")
        assert interpreter.is_file()
    monkeypatch.setattr(desktop, "backend_command", lambda _, __, parent: [
        str(interpreter), "-c",
        "from gel_analyzer.desktop import watch_parent, parent_pipe_from_handle; "
        "import sys; parent=int(sys.argv[1]); "
        "watch_parent(parent_pipe_from_handle(parent) if sys.platform == 'win32' else parent)",
        str(parent),
    ])
    read_pipe, write_pipe = os.pipe()
    with (tmp_path / "watchdog.log").open("wb") as log:
        try:
            process = desktop.spawn_backend(0, "unused", read_pipe, log, tmp_path)
        finally:
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


def test_backend_exits_after_parent_crashes(tmp_path):
    result = subprocess.run([
        sys.executable, "-c",
        "import os, sys; from pathlib import Path; "
        "from gel_analyzer.desktop import Backend; "
        "backend=Backend(Path(sys.argv[1]), startup_timeout=20); "
        "print(backend.start(), flush=True); os._exit(0)",
        str(tmp_path),
    ], cwd=desktop.resource_root(), capture_output=True, text=True, timeout=30, check=True)
    backend = desktop.Backend(tmp_path)
    backend.url = result.stdout.strip()
    assert backend.url.startswith("http://127.0.0.1:")
    deadline = time.monotonic() + 5
    while backend._healthy() and time.monotonic() < deadline:
        time.sleep(0.1)
    assert not backend._healthy()


@pytest.mark.parametrize("local_app_data", [True, False])
def test_windows_logs_use_writable_user_directory(tmp_path, monkeypatch, local_app_data):
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.delenv("GEL_ANALYZER_LOG_DIR", raising=False)
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    if local_app_data:
        monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "Local data"))
        expected = tmp_path / "Local data"
    else:
        monkeypatch.delenv("LOCALAPPDATA", raising=False)
        expected = tmp_path / "AppData" / "Local"
    assert desktop.log_directory() == expected / "Gel Analyzer" / "Logs"
    monkeypatch.setenv("GEL_ANALYZER_LOG_DIR", str(tmp_path / "custom"))
    assert desktop.log_directory() == tmp_path / "custom"


def test_windowed_backend_preserves_diagnostics_and_existing_streams(tmp_path, monkeypatch):
    log = tmp_path / "logs" / "backend.log"
    original_stdout = sys.stdout
    with monkeypatch.context() as patch:
        patch.setattr(sys, "stdin", None)
        patch.setattr(sys, "stderr", None)
        desktop.ensure_standard_streams(log)
        new_input, new_error = sys.stdin, sys.stderr
        try:
            assert sys.stdout is original_stdout
            assert sys.stdin.read() == ""
            sys.stderr.write("Startup failed: café\n")
            assert log.read_text(encoding="utf-8") == "Startup failed: café\n"
            desktop.ensure_standard_streams(log)
            assert sys.stderr is new_error
        finally:
            new_input.close()
            new_error.close()


def test_windowed_backend_startup_exception_is_recorded(tmp_path, monkeypatch):
    monkeypatch.setenv("GEL_ANALYZER_LOG_DIR", str(tmp_path))
    def fail(*args):
        raise RuntimeError("Test startup error")
    monkeypatch.setattr(desktop, "run_backend", fail)
    with monkeypatch.context() as patch:
        patch.setattr(sys, "stdout", None)
        patch.setattr(sys, "stderr", None)
        try:
            assert desktop.main(["--gel-backend", "--port", "12345", "--base-path",
                                 "test", "--parent-pipe", "7"]) == 1
            assert "RuntimeError: Test startup error" in (tmp_path / "backend.log").read_text()
        finally:
            sys.stderr.close()


@pytest.mark.parametrize("fail_spawn", [False, True])
def test_windows_spawn_inherits_only_read_handle_and_restores_flag(tmp_path, monkeypatch, fail_spawn):
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setitem(sys.modules, "msvcrt", SimpleNamespace(get_osfhandle=lambda fd: 123456))
    monkeypatch.setattr(subprocess, "STARTUPINFO", SimpleNamespace, raising=False)
    monkeypatch.setattr(subprocess, "CREATE_NO_WINDOW", 0x08000000, raising=False)
    changes = []
    monkeypatch.setattr(os, "set_handle_inheritable",
                        lambda handle, inherit: changes.append((handle, inherit)), raising=False)
    def launch(command, **options):
        assert changes == [(123456, True)]
        assert command[-2:] == ["--parent-handle", "123456"]
        assert options["startupinfo"].lpAttributeList == {"handle_list": [123456]}
        assert options["close_fds"] is True
        assert options["creationflags"] == 0x08000000
        assert "pass_fds" not in options
        assert options["stdin"] == subprocess.DEVNULL
        assert options["env"]["GEL_ANALYZER_LOG_DIR"] == str(tmp_path.resolve())
        if fail_spawn:
            raise OSError("Cannot launch")
        return "process"
    monkeypatch.setattr(subprocess, "Popen", launch)
    with (tmp_path / "backend.log").open("wb") as log:
        if fail_spawn:
            with pytest.raises(OSError, match="Cannot launch"):
                desktop.spawn_backend(12345, "test", 7, log, tmp_path)
        else:
            assert desktop.spawn_backend(12345, "test", 7, log, tmp_path) == "process"
    assert changes == [(123456, True), (123456, False)]


def test_spawn_failure_closes_pipe_descriptors_and_log(tmp_path, monkeypatch):
    read_pipe, write_pipe = os.pipe()
    monkeypatch.setattr(desktop, "available_port", lambda: 12345)
    monkeypatch.setattr(os, "pipe", lambda: (read_pipe, write_pipe))
    def fail(*args):
        raise OSError("Cannot launch")
    monkeypatch.setattr(desktop, "spawn_backend", fail)
    backend = desktop.Backend(tmp_path)
    with pytest.raises(OSError, match="Cannot launch"):
        backend._spawn()
    for descriptor in (read_pipe, write_pipe):
        with pytest.raises(OSError):
            os.fstat(descriptor)
    assert backend._parent_pipe is None
    assert backend._log is None


def test_inherited_handle_becomes_noninheritable_descriptor(monkeypatch):
    changes = []
    monkeypatch.setattr(os, "set_handle_inheritable",
                        lambda handle, inherit: changes.append((handle, inherit)), raising=False)
    monkeypatch.setattr(os, "O_BINARY", 32768, raising=False)
    def convert(handle, flags):
        assert handle == 123456
        assert flags == os.O_RDONLY | os.O_BINARY
        assert changes == [(123456, False)]
        return 9
    monkeypatch.setitem(sys.modules, "msvcrt", SimpleNamespace(open_osfhandle=convert))
    assert desktop.parent_pipe_from_handle(123456) == 9


def test_backend_cli_converts_raw_windows_handle(monkeypatch):
    monkeypatch.setattr(desktop, "parent_pipe_from_handle", lambda handle: handle + 1)
    calls = []
    monkeypatch.setattr(desktop, "run_backend", lambda *args: calls.append(args) or 0)
    assert desktop.main(["--gel-backend", "--port", "12345", "--base-path",
                         "test", "--parent-handle", "123456"]) == 0
    assert calls == [(12345, "test", 123457)]
