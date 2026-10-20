"""Reject incomplete, wrongly targeted or unauthenticated Windows packages."""

import hashlib
from pathlib import Path
import struct

import pytest

from scripts import build_windows


def write_pe(path: Path, machine: int, clr_flags: int | None = None) -> Path:
    """Minimal PE fixture with one section; no executable code is present."""
    data = bytearray(1024)
    data[:2] = b"MZ"
    struct.pack_into("<I", data, 0x3C, 128)
    data[128:132] = b"PE\0\0"
    struct.pack_into("<HH", data, 132, machine, 1)
    struct.pack_into("<H", data, 148, 224)
    struct.pack_into("<H", data, 152, 0x10B)
    struct.pack_into("<H", data, 152 + 68, 2)
    struct.pack_into("<IIII", data, 152 + 224 + 8, 512, 0x2000, 512, 512)
    if clr_flags is not None:
        struct.pack_into("<II", data, 152 + 96 + 14 * 8, 0x2000, 72)
        struct.pack_into("<I", data, 512 + 16, clr_flags)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return path


@pytest.mark.parametrize(
    ("machine", "flags", "expected"),
    [
        (0x8664, None, "x64"),
        (0xAA64, None, "arm64"),
        (0x14C, None, "x86"),
        (0x14C, 9, "anycpu"),  # IL-only and strong-name signed
        (0x14C, 3, "x86"),  # IL-only with 32BITREQUIRED
        (0x14C, 0x20001, "x86"),  # 32BITPREFERRED is not AnyCPU here
    ],
)
def test_pe_architecture_distinguishes_managed_and_native(tmp_path, machine, flags, expected):
    candidate = write_pe(tmp_path / "candidate.dll", machine, flags)
    assert build_windows.inspect_pe(candidate)["architecture"] == expected


def test_pe_inspection_rejects_a_nonbinary(tmp_path):
    candidate = tmp_path / "fake.dll"
    candidate.write_text("Not an executable", encoding="utf-8")
    with pytest.raises(RuntimeError, match="Not a Windows PE"):
        build_windows.inspect_pe(candidate)


@pytest.mark.parametrize(
    ("relative_path", "architecture", "allowed"),
    [
        ("_internal/webview/lib/runtimes/win-arm64/native/WebView2Loader.dll", "arm64", True),
        ("_internal/webview/lib/runtimes/win-x86/native/WebView2Loader.dll", "x86", True),
        ("_internal/webview/lib/runtimes/win-arm64/native/WebView2Loader.dll", "x86", False),
        ("_internal/webview/lib/runtimes/win-x64/native/WebView2Loader.dll", "arm64", False),
        ("_internal/webview/lib/runtimes/win-arm64/native/AnotherLibrary.dll", "arm64", False),
        ("_internal/other/WebView2Loader.dll", "x86", False),
        ("Gel Analyzer.exe", "arm64", False),
    ],
)
def test_alternate_sdk_loaders_are_allowed_only_at_exact_vendor_paths(relative_path, architecture, allowed):
    if allowed:
        build_windows.verify_binary_architecture(relative_path, architecture)
    else:
        with pytest.raises(RuntimeError, match="Unexpected architecture"):
            build_windows.verify_binary_architecture(relative_path, architecture)


def test_bundle_cannot_omit_webview_runtime_loader(tmp_path):
    app = tmp_path / "app"
    write_pe(app / "Gel Analyzer.exe", 0x8664)
    missing = "webview/lib/runtimes/win-x64/native/WebView2Loader.dll"
    for resource in build_windows.REQUIRED_RESOURCES:
        if resource != missing:
            path = app / "_internal" / resource
            path.parent.mkdir(parents=True, exist_ok=True)
            path.touch()
    with pytest.raises(RuntimeError, match="win-x64/native/WebView2Loader.dll"):
        build_windows.verify_bundle("1.0.3", app)


def test_bundle_rejects_native_arm64_dependency(tmp_path):
    app = tmp_path / "app"
    write_pe(app / "Gel Analyzer.exe", 0x8664)
    for resource in build_windows.REQUIRED_RESOURCES:
        path = app / "_internal" / resource
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.suffix == ".dll":
            architecture = build_windows.ALTERNATE_WEBVIEW2_LOADERS.get(f"_internal/{resource}", "x64")
            write_pe(path, {"x64": 0x8664, "arm64": 0xAA64, "x86": 0x14C}[architecture])
        else:
            path.touch()
    bridge = app / "_internal/webview/js/api.js"
    bridge.parent.mkdir(parents=True, exist_ok=True)
    bridge.touch()
    write_pe(app / "_internal/unsupported.dll", 0xAA64)
    with pytest.raises(RuntimeError, match="Unexpected architecture.*arm64"):
        build_windows.verify_bundle("1.0.3", app)


def large_prerequisite(tmp_path: Path) -> Path:
    candidate = tmp_path / "WebView2-X64.exe"
    with candidate.open("wb") as output:
        output.truncate(10_000_000)
    return candidate


def test_offline_prerequisite_rejects_small_online_bootstrapper(tmp_path):
    candidate = tmp_path / "bootstrapper.exe"
    candidate.write_bytes(b"MZ")
    with pytest.raises(RuntimeError, match="not the online bootstrapper"):
        build_windows.verify_webview2_installer(candidate)


@pytest.mark.parametrize(
    ("status", "signer"),
    [("NotSigned", ""), ("HashMismatch", "Microsoft Corporation"), ("Valid", "Another Publisher")],
)
def test_offline_prerequisite_requires_valid_microsoft_signature(tmp_path, monkeypatch, status, signer):
    monkeypatch.setattr(build_windows, "powershell_json", lambda *args, **kwargs: {
        "signature_status": status, "signer": signer,
    })
    with pytest.raises(RuntimeError, match="valid Microsoft Corporation Authenticode"):
        build_windows.verify_webview2_installer(large_prerequisite(tmp_path))


def test_valid_prerequisite_records_content_hash_and_version(tmp_path, monkeypatch):
    candidate = large_prerequisite(tmp_path)
    metadata = {
        "signature_status": "Valid", "signer": "Microsoft Corporation",
        "product_name": "Microsoft Edge Update", "description": "Microsoft Edge Update Setup",
        "file_version": "1.2.3.4", "product_version": "1.2.3.4",
    }
    monkeypatch.setattr(build_windows, "powershell_json", lambda *args, **kwargs: metadata)
    report = build_windows.verify_webview2_installer(candidate)
    assert report["sha256"] == hashlib.sha256(candidate.read_bytes()).hexdigest()
    assert report["product_version"] == "1.2.3.4"
    assert report["signature_status"] == "Valid"


@pytest.mark.parametrize("modern_available", [True, False])
@pytest.mark.parametrize("module_path_key", ["PSModulePath", "PSMODULEPATH"])
def test_signature_shell_does_not_inherit_incompatible_module_paths(monkeypatch, modern_available, module_path_key):
    available = {
        "powershell.exe": r"C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe",
    }
    if modern_available:
        available["pwsh.exe"] = r"C:\Program Files\PowerShell\7\pwsh.exe"
    monkeypatch.setattr(build_windows.shutil, "which", available.get)
    calls = []
    monkeypatch.setattr(
        build_windows, "run",
        lambda *args, **kwargs: calls.append((args, kwargs)) or '{"signature_status":"Valid"}',
    )
    parent_env = {module_path_key: r"C:\Program Files\PowerShell\7\Modules", "GEL_BUILD_APP_EXE": "app.exe"}
    assert build_windows.powershell_json("Get-AuthenticodeSignature app.exe", env=parent_env) == {
        "signature_status": "Valid",
    }
    command, options = calls[0]
    assert command[0] == available["pwsh.exe" if modern_available else "powershell.exe"]
    assert options["env"] == {"GEL_BUILD_APP_EXE": "app.exe"}
    assert module_path_key in parent_env  # The parent shell's environment is unchanged.
