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
import threading
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


def prepare_annotations(page, output: Path, *, upload=None):
    """Reach annotation editing through the same UI in Chromium and WebView2."""
    from playwright.sync_api import expect

    expect.set_options(timeout=45_000)
    # Observe rerun completion without replacing component events or
    # application state. Old attribute values retain even transitions
    # too quick for Playwright polling, and this survives iframe remounts.
    page.evaluate("""() => {
        window.gelSmokeRunCompletions = 0;
        new MutationObserver(records => {
            for (const record of records) {
                if (record.target.matches('[data-testid="stApp"]') &&
                    record.oldValue === "running" &&
                    record.target.getAttribute("data-test-script-state") === "notRunning") {
                    window.gelSmokeRunCompletions++;
                }
            }
        }).observe(document.documentElement, {
            subtree: true, attributes: true, attributeOldValue: true,
            attributeFilter: ["data-test-script-state"]
        });
    }""")
    fixtures = synthetic_images(output / "synthetic-inputs")
    for index, fixture in enumerate(fixtures):
        if index:
            page.get_by_role("button", name="Replace image", exact=True).click()
        expect(page.locator('input[type="file"]')).to_have_value("")
        if upload is None:
            page.locator('input[type="file"]').set_input_files(fixture)
        else:
            upload(fixture)
        # The uploader shows its selected filename before the server
        # has processed it. Wait for the analysis preview's st.text, so
        # replacements cannot race callbacks.
        expect(page.get_by_test_id("stText")).to_have_text(fixture.name)
        expect(page.get_by_test_id("stImage").locator("img")).to_be_visible()
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
    expect(page.locator('iframe[src*="orientation_rectangle"]')).to_have_count(0)
    button(page, "rotate_and_orient").click()
    button(page, "confirm_orientation").click()
    button(page, "define_wells").click()
    count = page.get_by_role("spinbutton", name="Number of wells", exact=True)
    overlay = component_frame(page, "well_line_overlay")
    svg = overlay.locator("#gel")
    expect(svg).to_be_visible()
    expect(svg).to_have_attribute("data-editable", "true")
    original_token = svg.get_attribute("data-token")
    assert original_token, "Well component did not receive its initial state"
    if count.input_value() != "4":
        count.fill("4")
        count.press("Enter")
        # Changing the well count creates a new component session. Wait
        # for that server rerender before clicks, or the count callback
        # can discard points drawn on the previous token.
        expect(svg).not_to_have_attribute("data-token", original_token)
    expect(page.get_by_test_id("stApp")).to_have_attribute("data-test-script-state", "notRunning")
    expect(svg).to_have_attribute("data-editable", "true")
    expect(svg).to_have_attribute("data-point-count", "0")
    guide_token = svg.get_attribute("data-token")
    assert guide_token
    for index, (x, y) in enumerate(((36, 36), (36, 291)), start=1):
        ready_svg = overlay.locator(
            f'#gel[data-token="{guide_token}"][data-editable="true"]'
            f'[data-point-count="{index - 1}"]')
        # Remeasure after each acknowledgement: fitting and iframe
        # layout can change as the instruction text is updated.
        bounds = ready_svg.bounding_box()
        dimensions = ready_svg.evaluate(
            "(node) => [node.viewBox.baseVal.width, node.viewBox.baseVal.height]")
        assert bounds and dimensions[0] > 0 and dimensions[1] > 0
        completed_runs = page.evaluate("window.gelSmokeRunCompletions")
        ready_svg.click(position={"x": x / dimensions[0] * bounds["width"],
                                  "y": y / dimensions[1] * bounds["height"]})
        page.wait_for_function(
            "(completed) => window.gelSmokeRunCompletions > completed",
            arg=completed_runs)
        expect(page.get_by_test_id("stApp")).to_have_attribute("data-test-script-state", "notRunning")
        expect(svg).to_have_attribute("data-token", guide_token)
        expect(svg).to_have_attribute("data-point-count", str(index))
    expect(button(page, "confirm_well_line")).to_be_enabled()
    button(page, "confirm_well_line").click()
    expect(page.get_by_text("Prepared 4 wells and 4 horizontal lanes.", exact=True)).to_be_visible()
    button(page, "adjust_lane_borders").click()
    review = component_frame(page, "well_line_overlay")
    expect(review.locator("#gel")).to_have_attribute("data-review-mode", "borders")
    expect(review.locator("#lane-review")).to_be_visible()
    button(page, "confirm_lane_borders").click()
    expect(review.locator("#gel")).to_have_attribute("data-review-mode", "extent")
    button(page, "confirm_lane_crop").click()
    editor = component_frame(page, "lane_annotations")
    labels = editor.locator('.image-label[contenteditable="true"]')
    expect(labels).to_have_count(4)
    expect(page.get_by_test_id("stApp")).to_have_attribute("data-test-script-state", "notRunning")
    return editor, fixtures


def check_annotation_typing(page, editor) -> dict:
    """Use a single click and actual keyboard events across autosave reruns.

    Locator.fill/press can focus their target again, concealing the reported
    interruption. Keyboard events here go only to the current active element.
    """
    from playwright.sync_api import expect

    labels = editor.locator('.image-label[contenteditable="true"]')
    first, second = labels.nth(0), labels.nth(1)
    first.click()
    expect(first).to_be_focused()
    page.keyboard.press("ControlOrMeta+A")
    iframe = page.locator('iframe[src*="lane_annotations"]')
    iframe.evaluate("(node) => { window.gelSmokeAnnotationFrame = node; }")
    first.evaluate("""node => {
        window.gelSmokeTyping = {node, blurCount: 0};
        node.addEventListener("blur", () => window.gelSmokeTyping.blurCount++);
    }""")
    initial_runs = page.evaluate("window.gelSmokeRunCompletions")

    def assert_typing_target(label, text):
        expect(label).to_be_focused()
        expect(label).to_have_text(text)
        assert iframe.evaluate("""node => window.gelSmokeAnnotationFrame === node &&
            document.activeElement === node"""), "Annotation iframe was replaced or lost focus"
        assert label.evaluate("""node => {
            const selection = window.getSelection();
            if (!selection?.rangeCount || !selection.isCollapsed ||
                !node.contains(selection.anchorNode)) return false;
            const prefix = selection.getRangeAt(0).cloneRange();
            prefix.selectNodeContents(node);
            prefix.setEnd(selection.anchorNode, selection.anchorOffset);
            return prefix.toString().length === node.textContent.length;
        }"""), "Text caret moved away from the end of the label"

    expected = ""
    for character in "Windows smoke lane":
        # Each key takes longer than the editor's 120 ms autosave interval.
        # No click, focus(), locator.press(), or fill() repairs lost focus.
        page.keyboard.type(character, delay=180)
        expected += character
        assert_typing_target(first, expected)
        assert first.evaluate("""node => window.gelSmokeTyping?.node === node &&
            window.gelSmokeTyping.blurCount === 0"""), "Typing blurred or replaced the label"
    page.wait_for_function("runs => window.gelSmokeRunCompletions > runs", arg=initial_runs)
    expect(page.get_by_test_id("stApp")).to_have_attribute("data-test-script-state", "notRunning")
    assert_typing_target(first, expected)
    completed_runs = page.evaluate("window.gelSmokeRunCompletions") - initial_runs

    page.keyboard.press("Tab")
    expect(second).to_be_focused()
    for index, character in enumerate("Second label", start=1):
        page.keyboard.type(character, delay=180)
        assert_typing_target(second, "Second label"[:index])
    page.keyboard.press("Shift+Tab")
    expect(first).to_be_focused()
    expect(first).to_have_text(expected)
    return {"slow_typing_characters": len(expected) + len("Second label"),
            "completed_reruns_during_first_label": completed_runs,
            "focus_and_caret_preserved": True, "tab_navigation": True}


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
            editor, fixtures = prepare_annotations(page, output)
            typing = check_annotation_typing(page, editor)
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
            return {"uploads": [path.name for path in fixtures], "exports": exports, "typing": typing,
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


def filename_edit(controls: list[dict]) -> int | None:
    """Find the filename field, excluding the dialog's search/address editors.

    Common file dialogs identify the filename as edt1 (0x480) or a child of
    cmb13 (0x47c). The modern Save dialog observed on Windows 2025 instead
    uses Edit 1001 under ComboBox/FloatNotifySink/DirectUIHWND/DUIViewWndClassName.
    Require that full hierarchy and a unique match, never an arbitrary Edit.
    """
    indexed = {control["handle"]: control for control in controls}
    modern = []
    for control in controls:
        if control["class"] != "Edit" or not control["visible"]:
            continue
        candidate = control
        seen = set()
        ancestry = []
        while candidate and candidate["handle"] not in seen:
            seen.add(candidate["handle"])
            ancestry.append(candidate["class"])
            if candidate["id"] in (0x480, 0x47C):
                return control["handle"]
            candidate = indexed.get(candidate["parent"])
        if control["id"] == 1001 and ancestry[:5] == [
                "Edit", "ComboBox", "FloatNotifySink", "DirectUIHWND", "DUIViewWndClassName"]:
            modern.append(control["handle"])
    return modern[0] if len(modern) == 1 else None


def drive_native_dialog(trigger, respond) -> dict:
    """Start the Win32 responder before a browser click can enter modal UI.

    Playwright remains on its original thread; only independent Win32 calls
    run in the responder, so even a modal browser click can finish safely.
    """
    stopped = threading.Event()
    results, errors = [], []

    def worker():
        try:
            results.append(respond(stopped))
        except BaseException as error:
            errors.append(error)

    thread = threading.Thread(target=worker, daemon=True, name="native-file-dialog")
    thread.start()
    try:
        trigger()
        thread.join(timeout=50)
        if thread.is_alive():
            raise AssertionError("Native file dialog did not finish within 50 seconds")
        if errors:
            raise errors[0]
        assert results, "Native dialog returned no verification result"
        return results[0]
    finally:
        stopped.set()
        thread.join(timeout=1)


def inspect_export(destination: Path, image_format: str) -> dict:
    data = destination.read_bytes()
    assert len(data) > 100, f"{image_format} export is empty"
    if image_format == "SVG":
        document = ElementTree.fromstring(data)
        assert document.tag == "{http://www.w3.org/2000/svg}svg"
        assert "Windows smoke lane" in data.decode("utf-8")
        details = {"format": "SVG"}
    else:
        with Image.open(BytesIO(data)) as exported:
            exported.load()
            assert exported.format == image_format
            assert min(exported.size) > 0
            details = {"format": exported.format, "size": list(exported.size)}
    return {"file": destination.name, "bytes": len(data), **details}


def wait_for_export(destination: Path, image_format: str) -> dict:
    """Wait for WebView2 to finish writing, then validate actual file contents."""
    def ready():
        try:
            return inspect_export(destination, image_format)
        except (OSError, ValueError, AssertionError, ElementTree.ParseError):
            return None

    return wait_until(ready, f"completed native {image_format} export: {destination}", timeout=30)


class KeyboardInput(ctypes.Structure):
    _fields_ = [("vk", ctypes.c_uint16), ("scan", ctypes.c_uint16),
                ("flags", ctypes.c_uint32), ("time", ctypes.c_uint32), ("extra", ctypes.c_size_t)]


class MouseInput(ctypes.Structure):
    _fields_ = [("x", ctypes.c_int32), ("y", ctypes.c_int32), ("data", ctypes.c_uint32),
                ("flags", ctypes.c_uint32), ("time", ctypes.c_uint32), ("extra", ctypes.c_size_t)]


class InputUnion(ctypes.Union):
    _fields_ = [("keyboard", KeyboardInput), ("mouse", MouseInput)]


class NativeInput(ctypes.Structure):
    _fields_ = [("kind", ctypes.c_uint32), ("value", InputUnion)]


class GUIThreadInfo(ctypes.Structure):
    _fields_ = [("size", ctypes.c_uint32), ("flags", ctypes.c_uint32),
                ("active", ctypes.c_void_p), ("focus", ctypes.c_void_p),
                ("capture", ctypes.c_void_p), ("menu", ctypes.c_void_p),
                ("move", ctypes.c_void_p), ("caret", ctypes.c_void_p),
                ("caret_rect", ctypes.c_int32 * 4)]


def native_key(vk=0, *, scan=0, flags=0) -> NativeInput:
    return NativeInput(1, InputUnion(keyboard=KeyboardInput(vk, scan, flags, 0, 0)))


def unicode_keys(text: str) -> list[NativeInput]:
    """SendInput consumes UTF-16 code units, including paired surrogates."""
    raw = text.encode("utf-16-le")
    return [native_key(scan=int.from_bytes(raw[index:index + 2], "little"), flags=flags)
            for index in range(0, len(raw), 2) for flags in (0x4, 0x6)]


class WindowsUI:
    """Small Win32 helper restricted to visible windows belonging to our PID."""

    def __init__(self):
        self.api = ctypes.WinDLL("user32", use_last_error=True)
        self.callback = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
        self.api.EnumWindows.argtypes = [self.callback, wintypes.LPARAM]
        self.api.EnumChildWindows.argtypes = [wintypes.HWND, self.callback, wintypes.LPARAM]
        self.api.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
        self.api.IsWindowVisible.argtypes = [wintypes.HWND]
        self.api.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
        self.api.GetClassNameW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
        self.api.PostMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
        self.api.GetDlgItem.argtypes = [wintypes.HWND, ctypes.c_int]
        self.api.GetDlgItem.restype = wintypes.HWND
        self.api.GetDlgCtrlID.argtypes = [wintypes.HWND]
        self.api.GetParent.argtypes = [wintypes.HWND]
        self.api.GetParent.restype = wintypes.HWND
        self.api.IsWindow.argtypes = [wintypes.HWND]
        self.api.GetForegroundWindow.restype = wintypes.HWND
        self.api.GetGUIThreadInfo.argtypes = [wintypes.DWORD, ctypes.POINTER(GUIThreadInfo)]
        self.api.SendInput.argtypes = [wintypes.UINT, ctypes.POINTER(NativeInput), ctypes.c_int]
        self.api.SendInput.restype = wintypes.UINT
        self.api.SendMessageTimeoutW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM,
                                               wintypes.LPARAM, wintypes.UINT, wintypes.UINT,
                                               ctypes.POINTER(ctypes.c_size_t)]
        self.api.SendMessageTimeoutW.restype = wintypes.LPARAM

    def class_name(self, handle: int) -> str:
        value = ctypes.create_unicode_buffer(256)
        self.api.GetClassNameW(handle, value, len(value))
        return value.value

    def send(self, handle: int, message: int, wparam=0, lparam=0) -> int:
        result = ctypes.c_size_t()
        if not self.api.SendMessageTimeoutW(handle, message, wparam, lparam, 0x3, 3000,
                                           ctypes.byref(result)):
            raise OSError(f"Native control {handle} did not answer message {message:#x}")
        return result.value

    def control_text(self, handle: int) -> str:
        # Unlike GetWindowText, WM_GETTEXT retrieves child edit values in the
        # other process. Windows marshals messages below WM_USER for us.
        value = ctypes.create_unicode_buffer(4096)
        self.send(handle, 0x000D, len(value), ctypes.addressof(value))  # WM_GETTEXT
        return value.value

    def send_keys(self, events: list[NativeInput]) -> None:
        inputs = (NativeInput * len(events))(*events)
        sent = self.api.SendInput(len(inputs), inputs, ctypes.sizeof(NativeInput))
        assert sent == len(inputs), f"Windows accepted only {sent}/{len(inputs)} keyboard events"

    def enter_filename(self, dialog: int, edit: int, text: str) -> None:
        # WM_SETTEXT can change the visible Edit without updating the modern
        # dialog's cached filename. Use its actual keyboard input path instead.
        # The CI dialogs are English (Open/Save As); Alt+N selects File name.
        assert self.api.GetForegroundWindow() == dialog, "Refusing to type outside the app's file dialog"
        self.send_keys([native_key(0x12), native_key(0x4E), native_key(0x4E, flags=0x2),
                        native_key(0x12, flags=0x2)])

        def filename_focused():
            info = GUIThreadInfo(size=ctypes.sizeof(GUIThreadInfo))
            return (self.api.GetGUIThreadInfo(0, ctypes.byref(info)) and info.focus == edit
                    and self.api.GetForegroundWindow() == dialog)

        wait_until(filename_focused, "native filename keyboard focus", timeout=5)
        self.send_keys([native_key(0x11), native_key(0x41), native_key(0x41, flags=0x2),
                        native_key(0x11, flags=0x2)] + unicode_keys(text))
        wait_until(lambda: self.control_text(edit) == text, "typed native filename", timeout=5)

    def controls(self, dialog: int) -> list[dict]:
        found = []

        @self.callback
        def collect(handle, _):
            found.append({"handle": handle, "parent": self.api.GetParent(handle),
                          "id": self.api.GetDlgCtrlID(handle), "class": self.class_name(handle),
                          "visible": bool(self.api.IsWindowVisible(handle))})
            return True

        self.api.EnumChildWindows(dialog, collect, 0)
        return found

    def dialog_snapshot(self, pid: int) -> list[dict]:
        return [{"handle": handle, "title": title, "class": self.class_name(handle),
                 "foreground": handle == self.api.GetForegroundWindow(),
                 "controls": self.controls(handle)} for handle, title in self.windows(pid)]

    def file_dialog(self, pid: int):
        for handle, title in self.windows(pid):
            if self.class_name(handle) != "#32770":
                continue
            controls = self.controls(handle)
            edit = filename_edit(controls)
            if edit:
                return handle, title, edit, controls
        return None

    def respond_file(self, pid: int, selection: Path | None, stopped: threading.Event,
                     *, overwrite=False, cancel=False) -> dict:
        def active(check):
            if stopped.is_set():
                raise AssertionError("Native dialog action was cancelled by the harness")
            return check()

        dialog, title, edit, controls = wait_until(
            lambda: active(lambda: self.file_dialog(pid)), "native file dialog", timeout=35)
        cancelled = cancel or selection is None
        result = {"title": title, "suggested_name": self.control_text(edit),
                  "action": "cancel" if cancelled else "choose", "controls": controls}
        if selection is not None:
            result["requested_path"] = str(selection)
            self.enter_filename(dialog, edit, str(selection))
            result["entered_filename"] = self.control_text(edit)
            assert result["entered_filename"] == str(selection), "Native filename field did not retain the path"
        assert self.api.GetForegroundWindow() == dialog, "Refusing to commit another application's dialog"
        # Enter commits the filename combo's model before Save/Open; Escape
        # cancels. Keep these behind the queued text events in the input stream.
        key = 0x1B if cancelled else 0x0D
        self.send_keys([native_key(key), native_key(key, flags=0x2)])
        if overwrite and not cancelled:
            def overwrite_confirmation():
                for candidate, caption in self.windows(pid):
                    if candidate != dialog and self.class_name(candidate) == "#32770":
                        yes = self.api.GetDlgItem(candidate, 6)  # IDYES
                        if yes:
                            return yes, caption
                return None

            yes, caption = wait_until(lambda: active(overwrite_confirmation),
                                      "native overwrite confirmation", timeout=10)
            result["overwrite_confirmation"] = caption
            assert self.api.PostMessageW(yes, 0x00F5, 0, 0), "Could not confirm overwrite"
        wait_until(lambda: active(lambda: not self.api.IsWindow(dialog)),
                   "native file dialog to close", timeout=10)
        return result

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


def native_annotation_workflow(page, ui: WindowsUI, pid: int, output: Path) -> dict:
    """Exercise real Open/Save dialogs without intercepting WebView2 downloads."""
    from playwright.sync_api import expect

    dialogs = []
    diagnostics = output / "native-dialogs.json"

    def choose(locator, selection=None, *, overwrite=False, cancel=False, download=False):
        try:
            # Every download needs fresh user activation. Deferred DOM click()
            # can open the first Save dialog but suppress later downloads.
            # Uploads use the app's bridge and their file input is hidden.
            trigger = (lambda: locator.click(no_wait_after=True)) if download else (
                lambda: locator.evaluate("node => { setTimeout(() => node.click(), 0); }"))
            result = drive_native_dialog(
                trigger,
                lambda stopped: ui.respond_file(pid, selection, stopped, overwrite=overwrite, cancel=cancel))
            dialogs.append(result)
            diagnostics.write_text(json.dumps(dialogs, indent=2), encoding="utf-8")
            return result
        except BaseException:
            diagnostics.write_text(json.dumps({"completed": dialogs,
                "remaining_windows": ui.dialog_snapshot(pid)}, indent=2), encoding="utf-8")
            raise

    page.wait_for_function("() => Boolean(window.__gelImagePickerInstalled && "
                           "typeof window.pywebview?.api?.choose_image === 'function')")
    file_input = page.locator('input[type="file"]')
    choose(file_input)  # Cancelling the native picker must leave the initial page intact.
    expect(file_input).to_have_value("")
    expect(page.get_by_test_id("stException")).to_have_count(0)

    # Unicode and spaces live in both the native open/save directory paths.
    unicode_output = output / "native α workspace"
    unicode_output.mkdir(parents=True, exist_ok=True)
    editor, fixtures = prepare_annotations(
        page, unicode_output, upload=lambda fixture: choose(page.locator('input[type="file"]'), fixture))
    expect(editor.locator("#component")).to_have_attribute("data-windows-desktop", "true")
    typing = check_annotation_typing(page, editor)
    labels = editor.locator('.image-label[contenteditable="true"]')
    expected_labels = labels.all_text_contents()
    # Cancel a replacement in the real picker after typing; existing work survives.
    page.get_by_role("button", name="Replace image", exact=True).click()
    choose(page.locator('input[type="file"]'))
    page.keyboard.press("Escape")
    expect(labels).to_have_text(expected_labels)
    editor.locator("#confirm").click()
    button(page, "skip_ladder").click()

    export_directory = output / "native α exports"
    export_directory.mkdir(parents=True, exist_ok=True)
    png_button = page.get_by_role("button", name="Download annotated PNG", exact=True)
    expect(png_button).to_be_visible()
    # Populate a known destination before Cancel, so the assertion detects a
    # save despite cancellation rather than checking an unrelated directory.
    choose(png_button, export_directory / "cancelled α export.png", cancel=True, download=True)
    assert not list(export_directory.iterdir()), "Cancelled native export created a file"
    expect(png_button).to_be_visible()
    exports = []
    for image_format, suffix in (("PNG", ""), ("JPEG", ".jpeg"), ("TIFF", ".TIF"), ("SVG", ".svg")):
        if image_format != "PNG":
            choose_option(page, "Image file type", image_format)
        save_button = page.get_by_role("button", name=f"Download annotated {image_format}", exact=True)
        selected = export_directory / f"native α label {image_format}{suffix}"
        destination = selected.with_suffix(".png") if not suffix else selected
        result = choose(save_button, selected, download=True)
        result["requested_path"] = str(selected)
        result["saved_path"] = str(destination)
        try:
            exports.append(wait_for_export(destination, image_format))
        except BaseException:
            # Only inspect this synthetic fixture's names in the disposable
            # runner's Downloads folder, never unrelated user documents.
            downloads = Path(os.environ.get("USERPROFILE", str(Path.home()))) / "Downloads"
            found = []
            for path in downloads.glob("synthetic gel 16-bit-annotated*"):
                if path.is_file():
                    found.append({"path": str(path), "bytes": path.stat().st_size})
                    unexpected = output / "unexpected-native-downloads"
                    unexpected.mkdir(exist_ok=True)
                    shutil.copyfile(path, unexpected / path.name)
            (output / "native-export-failure.json").write_text(json.dumps({
                "requested_path": str(selected), "expected_path": str(destination),
                "dialog": result, "fixture_downloads": found,
                "export_directory_files": [path.name for path in export_directory.iterdir()],
            }, indent=2), encoding="utf-8")
            raise
        expect(save_button).to_be_visible()
        assert page.locator('iframe[src*="lane_annotations"]').count() == 0

    # Force an actual overwrite prompt over our own sentinel fixture.
    choose_option(page, "Image file type", "PNG")
    overwritten = export_directory / "overwrite α image.png"
    overwritten.write_bytes(b"existing smoke fixture")
    choose(page.get_by_role("button", name="Download annotated PNG", exact=True), overwritten,
           overwrite=True, download=True)
    overwrite_export = wait_for_export(overwritten, "PNG")
    expect(page.get_by_test_id("stException")).to_have_count(0)
    diagnostics.write_text(json.dumps(dialogs, indent=2), encoding="utf-8")
    return {"typing": typing, "native_uploads": [path.name for path in fixtures],
            "open_cancel_preserves_annotations": True, "save_cancel": True,
            "exports": exports, "overwrite": overwrite_export,
            "extension_added_when_omitted": True, "unicode_paths": True}


def native_smoke(executable: Path, output: Path, *, force: bool) -> dict:
    import winreg

    logs = output / ("forced-close" if force else "normal-close")
    logs.mkdir(parents=True, exist_ok=True)
    debug_port = free_port()
    profile = Path(tempfile.mkdtemp(prefix="Gel WebView smoke "))
    environment = frozen_environment(logs)
    environment["GEL_ANALYZER_PREFERENCES_PATH"] = str(logs / "preferences.json")
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
    typing = None
    native_dialogs = None
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
            # Preserve the host's download policy and real Save As dialogs.
            # The default CDP attachment otherwise enables allowAndName.
            browser = playwright.chromium.connect_over_cdp(f"http://127.0.0.1:{debug_port}", no_defaults=True)
            pages = [page for context in browser.contexts for page in context.pages]
            assert pages, "WebView2 has no inspectable page"
            native_page = pages[0]
            native_page.set_default_timeout(45_000)
            native_page.wait_for_url(url + "**", timeout=60_000)
            expect(native_page.get_by_role("heading", name="Agarose Gel Analyzer")).to_be_visible(timeout=45_000)
            if not force:
                # Inspect the actual embedded renderer, rather than assuming
                # standalone Chromium covers WebView2 keyboard/focus behavior.
                try:
                    native_dialogs = native_annotation_workflow(native_page, ui, process.pid, logs)
                    typing = native_dialogs["typing"]
                    expect(native_page.get_by_test_id("stException")).to_have_count(0)
                except BaseException:
                    native_page.screenshot(path=str(logs / "annotation-failure.png"), full_page=True)
                    (logs / "annotation-failure.html").write_text(native_page.content(), encoding="utf-8")
                    raise
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
                "annotation_typing": typing,
                "native_dialogs": native_dialogs,
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
                  "Native typing uses WebView2 CDP events, not physical Windows keyboard input.",
              ]}
    try:
        if args.url:
            result["limitations"].append("Browser-only run: native Windows dialogs and lifecycle were not exercised.")
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
