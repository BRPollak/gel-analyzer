"""Own the native window and its private, local Streamlit backend.

Keep imports of Streamlit and Cocoa inside their respective entry points: the
same bundled executable is also launched as the backend subprocess.
"""

from __future__ import annotations

import argparse
import atexit
from html import escape
import logging
from logging.handlers import RotatingFileHandler
import os
from pathlib import Path
import socket
import subprocess
import sys
import threading
import time
import tomllib
from urllib.error import URLError
from urllib.request import ProxyHandler, build_opener
from uuid import uuid4


APP_NAME = "Gel Analyzer"
LOGGER = logging.getLogger("gel_analyzer.desktop")
QUIT_MESSAGE = "Quit Gel Analyzer? Save your project before quitting to keep your work."


class BackendError(RuntimeError):
    """The local analysis process could not be started or stopped unexpectedly."""


def resource_root() -> Path:
    """Resolve bundled assets independently of Finder's working directory."""
    return Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent))


def log_directory() -> Path:
    override = os.environ.get("GEL_ANALYZER_LOG_DIR")
    return Path(override).expanduser() if override else Path.home() / "Library" / "Logs" / APP_NAME


def configure_logging(directory: Path) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    handler = RotatingFileHandler(directory / "desktop.log", maxBytes=2_000_000, backupCount=2)
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    LOGGER.setLevel(logging.INFO)
    LOGGER.addHandler(handler)
    LOGGER.propagate = False


def available_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
        listener.bind(("127.0.0.1", 0))
        return listener.getsockname()[1]


def backend_command(port: int, base_path: str, parent_pipe: int) -> list[str]:
    command = [sys.executable]
    if not getattr(sys, "frozen", False):
        command.append(str(resource_root() / "desktop_app.py"))
    return command + ["--gel-backend", "--port", str(port), "--base-path", base_path,
                      "--parent-pipe", str(parent_pipe)]


def backend_options(root: Path, port: int, base_path: str) -> dict[str, object]:
    """Load the shipped theme and force desktop networking/lifecycle settings."""
    with (root / ".streamlit" / "config.toml").open("rb") as config_file:
        config = tomllib.load(config_file)
    options = {f"{section}.{key}": value for section, entries in config.items()
               for key, value in entries.items()}
    options.update({
        # Streamlit otherwise mistakes the frozen module path for a source checkout.
        "global.developmentMode": False,
        "server.address": "127.0.0.1",
        "server.port": port,
        "server.baseUrlPath": base_path,
        "server.headless": True,
        "server.fileWatcherType": "none",
        "server.runOnSave": False,
        "server.enableStaticServing": False,
        "server.enableXsrfProtection": True,
        "server.enableCORS": True,
        "browser.serverAddress": "127.0.0.1",
        "browser.gatherUsageStats": False,
        "client.toolbarMode": "minimal",
    })
    return options


def watch_parent(pipe: int) -> None:
    """EOF also occurs after a crash/SIGKILL, without relying on reusable PIDs."""
    try:
        while os.read(pipe, 1):
            pass
    finally:
        os.close(pipe)
        os._exit(0)


def run_backend(port: int, base_path: str, parent_pipe: int) -> int:
    threading.Thread(target=watch_parent, args=(parent_pipe,), daemon=True,
                     name="parent-watchdog").start()
    root = resource_root()
    os.chdir(root)
    # bootstrap.run expects config to have been loaded by the CLI first.
    from streamlit.web import bootstrap

    options = backend_options(root, port, base_path)
    bootstrap.load_config_options(options)
    bootstrap.run(str(root / "app.py"), False, [], options)
    return 0


class Backend:
    def __init__(self, directory: Path, *, startup_timeout: float = 45.0):
        self.directory = directory
        self.startup_timeout = startup_timeout
        self.stopped = threading.Event()
        self._lock = threading.Lock()
        self.process: subprocess.Popen | None = None
        self._parent_pipe: int | None = None
        self._log = None
        self.url: str | None = None
        # A machine's HTTP_PROXY must never route this local health check online.
        self._http = build_opener(ProxyHandler({}))

    def _spawn(self) -> None:
        with self._lock:
            if self.stopped.is_set():
                raise BackendError("Startup was cancelled.")
            port = available_port()
            base_path = f"gel-{uuid4().hex}"
            self.url = f"http://127.0.0.1:{port}/{base_path}/"
            self.directory.mkdir(parents=True, exist_ok=True)
            self._log = (self.directory / "backend.log").open("wb")
            read_pipe, write_pipe = os.pipe()
            try:
                self.process = subprocess.Popen(
                    backend_command(port, base_path, read_pipe),
                    cwd=resource_root(), stdin=subprocess.DEVNULL,
                    stdout=self._log, stderr=subprocess.STDOUT,
                    pass_fds=(read_pipe,),
                )
                self._parent_pipe = write_pipe
                LOGGER.info("Started local analysis process %s on port %s", self.process.pid, port)
            except BaseException:
                os.close(write_pipe)
                self._log.close()
                self._log = None
                raise
            finally:
                os.close(read_pipe)

    def _healthy(self) -> bool:
        try:
            with self._http.open(f"{self.url}_stcore/health", timeout=0.5) as response:
                return response.status == 200 and response.read(16).strip() == b"ok"
        except (OSError, URLError):
            return False

    def start(self) -> str:
        """Retry early exits (including port races), within one startup deadline."""
        deadline = time.monotonic() + self.startup_timeout
        for attempt in range(3):
            self._spawn()
            while time.monotonic() < deadline and not self.stopped.is_set():
                if self.process.poll() is not None:
                    LOGGER.warning("Analysis process exited during startup (attempt %s, code %s)",
                                   attempt + 1, self.process.returncode)
                    break
                if self._healthy() and self.process.poll() is None:
                    LOGGER.info("Analysis workspace is ready")
                    return self.url
                self.stopped.wait(0.1)
            self._stop_process()
            if self.stopped.is_set():
                raise BackendError("Startup was cancelled.")
            if time.monotonic() >= deadline:
                raise BackendError("The analysis workspace did not become ready in time.")
        raise BackendError("The analysis process could not start. Please close the app and try again.")

    def _stop_process(self) -> None:
        with self._lock:
            process = self.process
            if process is not None and process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=5)
            if self._parent_pipe is not None:
                os.close(self._parent_pipe)
                self._parent_pipe = None
            if self._log is not None:
                self._log.close()
                self._log = None

    def stop(self) -> None:
        self.stopped.set()
        self._stop_process()


def status_page(title: str, message: str, *, log_path: Path | None = None) -> str:
    details = (f"<p class='details'>Diagnostic logs: <code>{escape(str(log_path))}</code></p>"
               if log_path else "<div class='spinner' aria-label='Loading'></div>")
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>{APP_NAME}</title><style>
    body{{margin:0;background:#FAFBFC;color:#172B3A;font:17px -apple-system,BlinkMacSystemFont,sans-serif;
    min-height:100vh;display:grid;place-items:center}} main{{max-width:620px;padding:40px;text-align:center}}
    h1{{font-size:30px;letter-spacing:-.8px}} p{{line-height:1.6;color:#435767}}
    .details{{font-size:13px;overflow-wrap:anywhere}} .spinner{{margin:28px auto;width:28px;height:28px;
    border:3px solid #DCE8E7;border-top-color:#18786F;border-radius:50%;animation:spin 1s linear infinite}}
    @keyframes spin{{to{{transform:rotate(360deg)}}}}</style></head>
    <body><main><h1>{escape(title)}</h1><p>{escape(message)}</p>{details}</main></body></html>"""


def run_desktop() -> int:
    import webview

    directory = log_directory()
    configure_logging(directory)
    backend = Backend(directory)
    atexit.register(backend.stop)
    webview.settings["ALLOW_DOWNLOADS"] = True
    webview.settings["SHOW_DEFAULT_MENUS"] = True
    # Streamlit creates download links in a new window. Keep them in WKWebView,
    # whose download delegate supplies the suggested name and native save panel.
    webview.settings["OPEN_EXTERNAL_LINKS_IN_BROWSER"] = False
    window = webview.create_window(
        APP_NAME,
        html=status_page(APP_NAME, "Starting your analysis workspace…"),
        width=1440, height=960, min_size=(1000, 700),
        background_color="#FAFBFC", text_select=True, confirm_close=True,
        localization={"global.quitConfirmation": QUIT_MESSAGE},
    )
    window.events.closed += backend.stop

    def launch_workspace() -> None:
        try:
            url = backend.start()
            if backend.stopped.is_set():
                return
            window.load_url(url)
            while not backend.stopped.wait(0.5):
                if backend.process.poll() is not None:
                    raise BackendError("The analysis workspace stopped unexpectedly. Close the app and reopen your saved project.")
        except Exception as error:
            LOGGER.exception("Analysis workspace failed")
            backend._stop_process()
            if not backend.stopped.is_set():
                window.load_html(status_page("Unable to open the workspace", str(error), log_path=directory))

    try:
        # Cocoa must run on the main thread; pywebview runs this callback in a worker.
        webview.start(launch_workspace, gui="cocoa", debug=False, private_mode=True)
    finally:
        backend.stop()
        atexit.unregister(backend.stop)
    return 0


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if "--gel-backend" in args:
        parser = argparse.ArgumentParser(description="Gel Analyzer local analysis process")
        parser.add_argument("--gel-backend", action="store_true")
        parser.add_argument("--port", type=int, required=True)
        parser.add_argument("--base-path", required=True)
        parser.add_argument("--parent-pipe", type=int, required=True)
        options = parser.parse_args(args)
        return run_backend(options.port, options.base_path, options.parent_pipe)
    return run_desktop()
