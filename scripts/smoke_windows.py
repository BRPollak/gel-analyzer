"""Exercise the frozen Windows app without importing application Python code.

Install the locked test-smoke group and Chromium before running:
    uv run --locked --group test-smoke python -m playwright install chromium
    uv run --locked --group test-smoke python scripts/smoke_windows.py \
        --exe "dist/windows/Gel Analyzer/Gel Analyzer.exe" --output dist/windows/validation/smoke

The test interpreter only drives processes and the browser. The app and backend
always run from the frozen executable. --url runs just the browser scenario
against a separately running app, for developing this cross-platform harness.
"""

from __future__ import annotations

import argparse
from contextlib import contextmanager, nullcontext
import ctypes
from ctypes import wintypes
from datetime import datetime, timezone
from io import BytesIO
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import traceback
from urllib.error import URLError
from urllib.request import ProxyHandler, build_opener
from uuid import uuid4
from xml.etree import ElementTree

from PIL import Image


HTTP = build_opener(ProxyHandler({}))


def wait_until(check, description: str, timeout: float = 60):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        value = check()
        if value:
            return value
        time.sleep(0.1)
    raise AssertionError(f"Timed out waiting for {description}")


def healthy(url: str) -> bool:
    try:
        with HTTP.open(url.rstrip("/") + "/_stcore/health", timeout=0.5) as response:
            return response.status == 200 and response.read(16).strip() == b"ok"
    except (OSError, URLError):
        return False


def free_port() -> int:
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        return listener.getsockname()[1]


def frozen_environment(logs: Path) -> dict[str, str]:
    """Do not let the test interpreter make a broken frozen bundle work."""
    environment = {key: value for key, value in os.environ.items()
                   if key not in ("PYTHONHOME", "PYTHONPATH", "VIRTUAL_ENV")}
    windows = Path(environment.get("SystemRoot", r"C:\Windows"))
    environment["PATH"] = os.pathsep.join(str(path) for path in (
        windows / "System32", windows, windows / "System32" / "Wbem"))
    environment["GEL_ANALYZER_LOG_DIR"] = str(logs)
    return environment


@contextmanager
def temporary_webview2_policy(registry, executable_name: str, port: int, profile: Path):
    """Temporarily configure only this app on an elevated disposable CI runner.

    WebView2 150+ ignores environment overrides for elevated processes. Use its
    documented machine policy, preserving every previous value and removing
    only empty keys created by this context. Injecting winreg keeps rollback
    testable on platforms without a Windows registry.
    """
    root = registry.HKEY_LOCAL_MACHINE
    view = registry.KEY_WOW64_64KEY
    access = registry.KEY_READ | registry.KEY_WRITE | view
    prefix = r"SOFTWARE\Policies\Microsoft\Edge\WebView2"
    specifications = (
        (prefix + r"\AdditionalBrowserArguments", f"--remote-debugging-port={port}"),
        (prefix + r"\UserDataFolder", str(profile)),
    )
    missing = object()
    created = []
    previous = []

    def ensure_key(path):
        for end in range(1, len(path.split("\\")) + 1):
            partial = "\\".join(path.split("\\")[:end])
            try:
                key = registry.OpenKey(root, partial, 0, access)
            except FileNotFoundError:
                key = registry.CreateKeyEx(root, partial, 0, access)
                created.append(partial)
            key.Close()

    try:
        for path, value in specifications:
            ensure_key(path)
            with registry.OpenKey(root, path, 0, access) as key:
                try:
                    original = registry.QueryValueEx(key, executable_name)
                except FileNotFoundError:
                    original = missing
                previous.append((path, original))
                registry.SetValueEx(key, executable_name, 0, registry.REG_SZ, value)
        yield
    finally:
        errors = []
        for path, original in reversed(previous):
            try:
                with registry.OpenKey(root, path, 0, access) as key:
                    if original is missing:
                        try:
                            registry.DeleteValue(key, executable_name)
                        except FileNotFoundError:
                            pass
                    else:
                        registry.SetValueEx(key, executable_name, 0, original[1], original[0])
            except OSError as error:
                errors.append(str(error))
        for path in reversed(created):
            try:
                with registry.OpenKey(root, path, 0, access) as key:
                    subkeys, values, _ = registry.QueryInfoKey(key)
                if subkeys == 0 and values == 0:
                    registry.DeleteKeyEx(root, path, view, 0)
            except FileNotFoundError:
                pass
            except OSError as error:
                errors.append(str(error))
        if errors:
            raise RuntimeError("Could not restore temporary WebView2 test policy: " + "; ".join(errors))


def synthetic_images(directory: Path) -> list[Path]:
    """Reproduce the public synthetic well fixture, never use research images."""
    image = Image.new("I;16", (520, 360), 24000)
    # ImageDraw's 16-bit drawing is inconsistent across Pillow releases.
    pixels = image.load()
    for left, top, right, bottom in ((27, 36, 45, 52), (27, 93, 45, 120),
                                    (27, 192, 45, 218), (27, 268, 45, 291)):
        for y in range(top, bottom):
            for x in range(left, right):
                pixels[x, y] = 51000
            for x in range(180, 185):
                pixels[x, y] = 9000
    source = Image.new("I;16", (460, 620), 55000)
    source.paste(image.transpose(Image.Transpose.TRANSPOSE), (50, 50))
    directory.mkdir(parents=True, exist_ok=True)
    paths = []
    for name, format_name in (("synthetic gel.png", "PNG"), ("synthetic gel.jpg", "JPEG"),
                              ("synthetic gel 16-bit.tif", "TIFF")):
        path = directory / name
        converted = source if format_name == "TIFF" else source.point(
            lambda value: value / 256).convert("L")
        converted.save(path, format=format_name)
        paths.append(path)
    return paths


def component_frame(page, name: str):
    from playwright.sync_api import expect

    # Locator waits pump the browser protocol and survive Streamlit rerenders.
    frame = page.frame_locator(f'iframe[src*="{name}"]')
    expect(frame.locator("body")).to_be_visible()
    return frame


def button(page, key: str):
    # Streamlit renders a second, CSS-hidden copy for tooltip-bearing buttons.
    return page.locator(f".st-key-{key} button:visible")


def choose_option(page, label: str, value: str):
    page.get_by_role("combobox", name=label, exact=True).click()
    page.get_by_role("option", name=value, exact=True).click()


def browser_smoke(url: str, output: Path) -> dict:
    from playwright.sync_api import expect, sync_playwright

    expect.set_options(timeout=45_000)
    browser_errors = []
    requests = []
    exports = []
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        context = browser.new_context(viewport={"width": 1500, "height": 1100},
                                      accept_downloads=True)
        context.tracing.start(screenshots=True, snapshots=True, sources=True)
        page = context.new_page()
        page.set_default_timeout(45_000)
        page.on("pageerror", lambda error: browser_errors.append(str(error)))
        page.on("response", lambda response: requests.append(
            {"url": response.url, "status": response.status}) if response.status >= 400 else None)
        try:
            page.goto(url, wait_until="domcontentloaded")
            expect(page.get_by_role("heading", name="Agarose Gel Analyzer")).to_be_visible()
            fixtures = synthetic_images(output / "synthetic-inputs")
            for index, fixture in enumerate(fixtures):
                if index:
                    page.get_by_role("button", name="Replace image", exact=True).click()
                page.locator('input[type="file"]').set_input_files(fixture)
                expect(page.get_by_text(fixture.name, exact=True)).to_be_visible()
                if index:
                    # Close the popover before interacting with the analysis.
                    page.keyboard.press("Escape")
                expect(button(page, "rotate_and_orient")).to_be_enabled()
                expect(page.get_by_test_id("stException")).to_have_count(0)

            # Exercise the shipped orientation component, then use the known
            # synthetic automatic orientation to keep the guide coordinates fixed.
            button(page, "adjust_orientation_manually").click()
            orientation = component_frame(page, "orientation_rectangle")
            expect(orientation.locator("#gel")).to_be_visible()
            expect(orientation.locator("#draw-new")).to_be_enabled()
            orientation.locator("#draw-new").click()
            button(page, "cancel_manual_orientation").click()
            button(page, "rotate_and_orient").click()
            button(page, "confirm_orientation").click()
            button(page, "define_wells").click()
            count = page.get_by_role("spinbutton", name="Number of wells", exact=True)
            count.fill("4")
            count.press("Enter")
            overlay = component_frame(page, "well_line_overlay")
            svg = overlay.locator("#gel")
            expect(svg).to_be_visible()
            # Use the real SVG's viewBox: browser fitting need not be 1:1.
            bounds = svg.bounding_box()
            dimensions = svg.evaluate("(node) => [node.viewBox.baseVal.width, node.viewBox.baseVal.height]")
            assert bounds and dimensions[0] > 0 and dimensions[1] > 0
            for x, y in ((36, 36), (36, 291)):
                svg.click(position={"x": x / dimensions[0] * bounds["width"],
                                    "y": y / dimensions[1] * bounds["height"]})
            button(page, "confirm_well_line").click()
            expect(page.get_by_text("Prepared 4 wells and 4 horizontal lanes.", exact=True)).to_be_visible()
            button(page, "adjust_lane_borders").click()
            review = component_frame(page, "well_line_overlay")
            expect(review.locator("#lane-review")).to_be_visible()
            button(page, "confirm_lane_borders").click()
            button(page, "confirm_lane_crop").click()
            editor = component_frame(page, "lane_annotations")
            labels = editor.locator('.image-label[contenteditable="true"]')
            expect(labels).to_have_count(4)
            labels.first.fill("Windows smoke lane")
            editor.locator("#confirm").click()
            button(page, "skip_ladder").click()

            for image_format in ("PNG", "JPEG", "TIFF", "SVG"):
                if image_format != "PNG":
                    choose_option(page, "Image file type", image_format)
                download_button = page.get_by_role(
                    "button", name=f"Download annotated {image_format}", exact=True)
                expect(download_button).to_be_visible()
                with page.expect_download() as event:
                    download_button.click()
                download = event.value
                destination = output / "exports" / download.suggested_filename
                destination.parent.mkdir(parents=True, exist_ok=True)
                download.save_as(destination)
                data = destination.read_bytes()
                assert len(data) > 100, f"{image_format} export is empty"
                if image_format == "SVG":
                    document = ElementTree.fromstring(data)
                    assert document.tag.endswith("svg")
                    assert "Windows smoke lane" in data.decode("utf-8")
                    details = {"format": "SVG"}
                else:
                    with Image.open(BytesIO(data)) as exported:
                        exported.load()
                        assert exported.format == image_format
                        assert min(exported.size) > 0
                        details = {"format": exported.format, "size": list(exported.size)}
                exports.append({"file": destination.name, "bytes": len(data), **details})

            expect(page.get_by_test_id("stException")).to_have_count(0)
            assert not browser_errors, f"Browser errors: {browser_errors}"
            assert not requests, f"Failed HTTP responses: {requests}"
            page.screenshot(path=str(output / "export-workspace.png"), full_page=True)
            return {"uploads": [path.name for path in fixtures], "exports": exports,
                    "components": ["manual orientation", "well guide", "lane review", "annotations"]}
        except BaseException:
            page.screenshot(path=str(output / "failure.png"), full_page=True)
            (output / "failure.html").write_text(page.content(), encoding="utf-8")
            raise
        finally:
            (output / "browser-errors.json").write_text(
                json.dumps({"javascript": browser_errors, "http": requests}, indent=2), encoding="utf-8")
            context.tracing.stop(path=str(output / "browser-trace.zip"))
            browser.close()


@contextmanager
def frozen_backend(executable: Path, output: Path):
    import msvcrt

    port = free_port()
    base_path = "gel-smoke-" + uuid4().hex
    url = f"http://127.0.0.1:{port}/{base_path}/"
    read_fd, write_fd = os.pipe()
    raw_handle = msvcrt.get_osfhandle(read_fd)
    os.set_handle_inheritable(raw_handle, True)
    startup = subprocess.STARTUPINFO()
    startup.lpAttributeList = {"handle_list": [raw_handle]}
    process = None
    with (output / "frozen-backend-stdio.log").open("ab") as log:
        try:
            process = subprocess.Popen(
                [str(executable), "--gel-backend", "--port", str(port), "--base-path",
                 base_path, "--parent-handle", str(raw_handle)],
                cwd=executable.parent, stdin=subprocess.DEVNULL, stdout=log,
                stderr=subprocess.STDOUT, startupinfo=startup, close_fds=True,
                env=frozen_environment(output / "frozen-backend-logs"),
            )
        except BaseException:
            os.close(write_fd)
            raise
        finally:
            os.set_handle_inheritable(raw_handle, False)
            os.close(read_fd)
        try:
            wait_until(lambda: healthy(url), "frozen backend readiness")
            assert process.poll() is None
            yield url
        finally:
            # Closing only the writer models parent death, not a normal backend
            # terminate: EOF must make the frozen child's watchdog stop itself.
            os.close(write_fd)
            if process is not None:
                try:
                    process.wait(timeout=15)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=10)
                    raise AssertionError("Frozen backend survived parent pipe EOF")
            wait_until(lambda: not healthy(url), "closed backend listener", timeout=10)


class WindowsUI:
    """Small Win32 helper restricted to visible windows belonging to our PID."""

    def __init__(self):
        self.api = ctypes.WinDLL("user32", use_last_error=True)
        self.callback = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
        self.api.EnumWindows.argtypes = [self.callback, wintypes.LPARAM]
        self.api.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
        self.api.IsWindowVisible.argtypes = [wintypes.HWND]
        self.api.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
        self.api.GetClassNameW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
        self.api.PostMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
        self.api.GetDlgItem.argtypes = [wintypes.HWND, ctypes.c_int]
        self.api.GetDlgItem.restype = wintypes.HWND

    def windows(self, pid: int) -> list[tuple[int, str]]:
        found = []

        @self.callback
        def collect(handle, _):
            owner = wintypes.DWORD()
            self.api.GetWindowThreadProcessId(handle, ctypes.byref(owner))
            if owner.value == pid and self.api.IsWindowVisible(handle):
                buffer = ctypes.create_unicode_buffer(1024)
                self.api.GetWindowTextW(handle, buffer, len(buffer))
                found.append((handle, buffer.value))
            return True

        self.api.EnumWindows(collect, 0)
        return found

    def close(self, handle: int):
        self.api.PostMessageW(handle, 0x0010, 0, 0)  # WM_CLOSE

    def accept_quit(self, pid: int):
        for handle, _ in self.windows(pid):
            # pywebview's WinForms quit confirmation is an OK/Cancel MessageBox.
            window_class = ctypes.create_unicode_buffer(256)
            self.api.GetClassNameW(handle, window_class, len(window_class))
            if window_class.value != "#32770":
                continue
            confirm = self.api.GetDlgItem(handle, 1)  # IDOK
            if confirm:
                self.api.PostMessageW(confirm, 0x00F5, 0, 0)  # BM_CLICK


def native_smoke(executable: Path, output: Path, *, force: bool) -> dict:
    import winreg

    logs = output / ("forced-close" if force else "normal-close")
    logs.mkdir(parents=True, exist_ok=True)
    debug_port = free_port()
    profile = Path(tempfile.mkdtemp(prefix="Gel WebView smoke "))
    environment = frozen_environment(logs)
    environment["WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS"] = f"--remote-debugging-port={debug_port}"
    environment["WEBVIEW2_USER_DATA_FOLDER"] = str(profile)
    elevated = bool(ctypes.WinDLL("shell32").IsUserAnAdmin())
    policy = temporary_webview2_policy(winreg, executable.name, debug_port, profile) if elevated else nullcontext()
    try:
        with policy:
            result = _native_smoke(executable, logs, debug_port, environment, force=force)
        result["debugging_configuration"] = "temporary app-specific machine policy" if elevated else "environment"
        return result
    finally:
        shutil.rmtree(profile, ignore_errors=True)


def _native_smoke(executable: Path, logs: Path, debug_port: int,
                  environment: dict[str, str], *, force: bool) -> dict:
    import psutil
    from playwright.sync_api import expect, sync_playwright

    ui = WindowsUI()
    process = subprocess.Popen([str(executable)], cwd=executable.parent, env=environment,
                               stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                               stderr=subprocess.DEVNULL)
    backend = None
    url = None
    try:
        parent = psutil.Process(process.pid)

        def children():
            try:
                return parent.children(recursive=True)
            except psutil.NoSuchProcess:
                raise AssertionError(f"Native app exited with code {process.poll()}")

        def backend_child():
            for child in children():
                try:
                    if "--gel-backend" in child.cmdline():
                        return child
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    continue
            return None

        backend = wait_until(backend_child, "native app backend")
        command = backend.cmdline()
        port = command[command.index("--port") + 1]
        base = command[command.index("--base-path") + 1]
        url = f"http://127.0.0.1:{port}/{base}/"
        wait_until(lambda: healthy(url), "native app backend readiness")
        window = wait_until(lambda: next(((handle, title) for handle, title in ui.windows(process.pid)
                                         if "Gel Analyzer" in title), None), "native app window")
        def renderer_started():
            for child in children():
                try:
                    if child.name().lower() == "msedgewebview2.exe":
                        return True
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    continue
            return False

        wait_until(renderer_started, "WebView2 renderer")

        def debugging_ready():
            try:
                with HTTP.open(f"http://127.0.0.1:{debug_port}/json/version", timeout=0.5) as response:
                    return response.status == 200
            except (OSError, URLError):
                return False

        def save_native_diagnostics():
            descendants = []
            try:
                live_children = parent.children(recursive=True)
            except psutil.NoSuchProcess:
                live_children = []
            for child in live_children:
                try:
                    descendants.append({"pid": child.pid, "name": child.name(),
                                        "command": child.cmdline()})
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    continue
            (logs / "native-processes.json").write_text(json.dumps({
                "debugging_port": debug_port,
                "app_exit_code": process.poll(),
                "windows": [{"handle": handle, "title": title}
                            for handle, title in ui.windows(process.pid)],
                "children": descendants,
            }, indent=2), encoding="utf-8")

        try:
            wait_until(debugging_ready, "WebView2 inspection endpoint")
        finally:
            save_native_diagnostics()
        with sync_playwright() as playwright:
            browser = playwright.chromium.connect_over_cdp(f"http://127.0.0.1:{debug_port}")
            pages = [page for context in browser.contexts for page in context.pages]
            assert pages, "WebView2 has no inspectable page"
            native_page = pages[0]
            native_page.wait_for_url(url + "**", timeout=60_000)
            expect(native_page.get_by_role("heading", name="Agarose Gel Analyzer")).to_be_visible(timeout=45_000)
            native_page.screenshot(path=str(logs / "native-window.png"))
            # Stopping the Playwright driver disconnects inspection; do not send
            # Browser.close to the application being tested.
        if force:
            process.kill()
        else:
            ui.close(window[0])
            deadline = time.monotonic() + 15
            while process.poll() is None and time.monotonic() < deadline:
                ui.accept_quit(process.pid)
                time.sleep(0.1)
        process.wait(timeout=15)
        wait_until(lambda: not backend.is_running(), "native backend exit", timeout=15)
        wait_until(lambda: not healthy(url), "native backend listener shutdown", timeout=10)
        return {"native_window_title": window[1], "renderer": "WebView2",
                "workspace_rendered_in_native_window": True,
                "close": "forced process termination" if force else "native window close",
                "backend_pid": backend.pid, "backend_stopped": True, "listener_closed": True}
    finally:
        if process.poll() is None:
            process.kill()
            process.wait(timeout=10)
        if backend is not None:
            try:
                if backend.is_running():
                    backend.kill()
                    backend.wait(timeout=10)
            except psutil.NoSuchProcess:
                pass


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    target = parser.add_mutually_exclusive_group(required=True)
    target.add_argument("--exe", type=Path, help="Frozen Windows executable")
    target.add_argument("--url", help="Run browser tests only against this existing app URL")
    parser.add_argument("--output", type=Path, default=Path("dist/windows/validation/smoke"))
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    result = {"started_at": datetime.now(timezone.utc).isoformat(), "platform": sys.platform,
              "status": "running", "limitations": [
                  "No clean physical Windows PC installation was performed.",
                  "Native Windows save dialogs are not automated; export bytes are checked in Chromium.",
              ]}
    try:
        if args.url:
            result["browser"] = browser_smoke(args.url, output)
        else:
            if sys.platform != "win32":
                raise RuntimeError("--exe requires a Windows runner; use --url for harness development.")
            executable = args.exe.resolve()
            assert executable.is_file(), executable
            with tempfile.TemporaryDirectory(prefix="Gel Analyzer test ") as temporary:
                # Copying the complete onedir bundle also catches accidental
                # reliance on the source checkout or the original build path.
                bundle = Path(temporary) / "Windows unicode é gel"
                shutil.copytree(executable.parent, bundle)
                copied = bundle / executable.name
                result["bundle_path_contains_spaces_and_unicode"] = True
                result["normal_close"] = native_smoke(copied, output, force=False)
                result["forced_close"] = native_smoke(copied, output, force=True)
                with frozen_backend(copied, output) as url:
                    result["browser"] = browser_smoke(url, output)
                result["inherited_parent_handle_eof_cleanup"] = "passed"
        result["status"] = "passed"
        return 0
    except BaseException as exc:
        result["status"] = "failed"
        result["error"] = str(exc)
        result["traceback"] = traceback.format_exc()
        traceback.print_exc()
        return 1
    finally:
        result["finished_at"] = datetime.now(timezone.utc).isoformat()
        (output / "smoke-results.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
        print(json.dumps(result, indent=2))


if __name__ == "__main__":
    raise SystemExit(main())
