"""Build and inspect an offline, per-user Windows x64 installer.

Run on Windows with the locked Python 3.12 desktop/build environment:
  python scripts/build_windows.py --webview2-installer path/to/offline-x64.exe

The Microsoft Evergreen Standalone Installer is an external build input.
This script never downloads a prerequisite or needs administrator privileges.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
from importlib.metadata import version as package_version
import json
import os
from pathlib import Path
import platform
import re
import shutil
import struct
import subprocess
import sys
import tomllib


ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / "dist" / "windows"
WORK = ROOT / "build" / "windows"
APP = DIST / "Gel Analyzer"
APP_ID = "org.benpollak.gelanalyzer.windows"
MIN_WINDOWS = "10.0.19045"
ALTERNATE_WEBVIEW2_LOADERS = {
    "_internal/webview/lib/runtimes/win-arm64/native/WebView2Loader.dll": "arm64",
    "_internal/webview/lib/runtimes/win-x86/native/WebView2Loader.dll": "x86",
}
REQUIRED_RESOURCES = (
    "app.py", ".streamlit/config.toml", "GelAnalyzer.ico",
    "streamlit/static/index.html", "gel_analyzer/ladder_presets.json",
    "gel_analyzer/viewport.html",
    "gel_analyzer/orientation_component_frontend/index.html",
    "gel_analyzer/well_component_frontend/index.html",
    "gel_analyzer/annotation_component_frontend/index.html",
    "gel_analyzer/annotation_component_frontend/ladder_references/neb-1-kb.webp",
    "webview/lib/Microsoft.Web.WebView2.Core.dll",
    "webview/lib/Microsoft.Web.WebView2.WinForms.dll",
    "webview/lib/runtimes/win-arm64/native/WebView2Loader.dll",
    "webview/lib/runtimes/win-x64/native/WebView2Loader.dll",
    "webview/lib/runtimes/win-x86/native/WebView2Loader.dll",
    "pythonnet/runtime/Python.Runtime.dll",
    "clr_loader/ffi/dlls/amd64/ClrLoader.dll",
    "licenses/python/LICENSE.txt",
)


def run(*args: str | Path, capture: bool = False, env: dict | None = None) -> str:
    command = [str(arg) for arg in args]
    if not capture:
        print("+", subprocess.list2cmdline(command), flush=True)
    try:
        result = subprocess.run(
            command, cwd=ROOT, check=True, env=env, text=True, encoding="utf-8",
            stdout=subprocess.PIPE if capture else None,
            stderr=subprocess.PIPE if capture else None,
        )
    except subprocess.CalledProcessError as error:
        if capture:
            print(error.stdout or "", file=sys.stderr)
            print(error.stderr or "", file=sys.stderr)
        raise
    return result.stdout or ""


def sha256(path: Path) -> str:
    with path.open("rb") as source:
        return hashlib.file_digest(source, "sha256").hexdigest()


def powershell_json(script: str, *, env: dict | None = None) -> dict:
    # EncodedCommand avoids shell interpolation of installer paths.
    encoded = base64.b64encode(script.encode("utf-16-le")).decode("ascii")
    shell = shutil.which("pwsh.exe") or shutil.which("powershell.exe")
    if shell is None:
        raise RuntimeError("PowerShell is required to inspect Windows Authenticode signatures.")
    child_env = dict(os.environ if env is None else env)
    # A PowerShell 7 parent can pass its module directories to Windows
    # PowerShell 5.1, which then finds incompatible Security/Utility modules.
    # These checks use only built-ins; let the chosen shell build its own paths.
    for key in list(child_env):
        if key.lower() == "psmodulepath":
            del child_env[key]
    output = run(
        shell, "-NoLogo", "-NoProfile", "-NonInteractive",
        "-EncodedCommand", encoded, capture=True, env=child_env,
    )
    return json.loads(output.lstrip("\ufeff").strip())


def verify_webview2_installer(path: Path) -> dict:
    if not path.is_file():
        raise RuntimeError(f"WebView2 offline installer does not exist: {path}")
    # The small online bootstrapper cannot satisfy the offline setup contract.
    if path.stat().st_size < 10_000_000:
        raise RuntimeError("Use the full WebView2 Evergreen Standalone Installer for x64, not the online bootstrapper.")
    env = os.environ.copy()
    env["GEL_BUILD_WEBVIEW2_INSTALLER"] = str(path.resolve())
    metadata = powershell_json(r"""
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
$path = $env:GEL_BUILD_WEBVIEW2_INSTALLER
$signature = Get-AuthenticodeSignature -LiteralPath $path
$info = (Get-Item -LiteralPath $path).VersionInfo
$signer = if ($signature.SignerCertificate) {
    $signature.SignerCertificate.GetNameInfo(
        [System.Security.Cryptography.X509Certificates.X509NameType]::SimpleName, $false)
} else { '' }
[ordered]@{
    signature_status = [string]$signature.Status
    signer = $signer
    signer_subject = [string]$signature.SignerCertificate.Subject
    signer_thumbprint = [string]$signature.SignerCertificate.Thumbprint
    file_version = $info.FileVersion
    product_version = $info.ProductVersion
    product_name = $info.ProductName
    description = $info.FileDescription
} | ConvertTo-Json -Compress
""", env=env)
    if metadata["signature_status"] != "Valid" or metadata["signer"] != "Microsoft Corporation":
        raise RuntimeError(
            "WebView2 prerequisite must have a valid Microsoft Corporation Authenticode signature: "
            f"{metadata['signature_status']}, {metadata['signer']!r}"
        )
    identity = f"{metadata.get('product_name', '')} {metadata.get('description', '')}".lower()
    if "edge" not in identity:
        raise RuntimeError("The signed prerequisite is not identified as a Microsoft Edge installer.")
    return {
        "filename": path.name, "sha256": sha256(path),
        "size_bytes": path.stat().st_size, "intended_architecture": "x64",
        "distribution": "Evergreen Standalone Installer (offline)",
        **metadata,
    }


def inspect_pe(path: Path) -> dict:
    """Read PE architecture and CLR flags without loading the candidate DLL."""
    with path.open("rb") as source:
        header = source.read(64)
        if len(header) != 64 or header[:2] != b"MZ":
            raise RuntimeError(f"Not a Windows PE binary: {path}")
        pe_offset = struct.unpack_from("<I", header, 0x3C)[0]
        source.seek(pe_offset)
        pe = source.read(24)
        if len(pe) != 24 or pe[:4] != b"PE\0\0":
            raise RuntimeError(f"Invalid PE header: {path}")
        machine, sections = struct.unpack_from("<HH", pe, 4)
        optional_size = struct.unpack_from("<H", pe, 20)[0]
        optional = source.read(optional_size)
        if len(optional) < 96:
            raise RuntimeError(f"Incomplete PE optional header: {path}")
        magic = struct.unpack_from("<H", optional)[0]
        if magic not in (0x10B, 0x20B):
            raise RuntimeError(f"Unsupported PE optional header: {path}")
        directories_offset = 112 if magic == 0x20B else 96
        clr_offset = directories_offset + 14 * 8
        clr_rva = struct.unpack_from("<I", optional, clr_offset)[0] if len(optional) >= clr_offset + 8 else 0
        clr_flags = None
        for _ in range(sections):
            section = source.read(40)
            if len(section) != 40:
                raise RuntimeError(f"Incomplete PE section table: {path}")
            virtual_size, virtual_address, raw_size, raw_address = struct.unpack_from("<IIII", section, 8)
            if clr_rva and virtual_address <= clr_rva < virtual_address + max(virtual_size, raw_size):
                next_section = source.tell()
                source.seek(raw_address + clr_rva - virtual_address + 16)
                flags = source.read(4)
                if len(flags) != 4:
                    raise RuntimeError(f"Incomplete CLR header: {path}")
                clr_flags = struct.unpack("<I", flags)[0]
                source.seek(next_section)
        any_cpu = (
            machine == 0x14C and clr_flags is not None
            and bool(clr_flags & 1) and not bool(clr_flags & (2 | 0x20000))
        )
        architecture = {0x8664: "x64", 0x14C: "x86", 0xAA64: "arm64"}.get(machine, hex(machine))
        return {
            "architecture": "anycpu" if any_cpu else architecture,
            "machine": hex(machine), "clr_flags": clr_flags,
            "subsystem": struct.unpack_from("<H", optional, 68)[0],
        }


def verify_binary_architecture(relative_path: str, architecture: str) -> None:
    """Allow other CPU loaders only in the two required upstream SDK paths."""
    if relative_path in ALTERNATE_WEBVIEW2_LOADERS:
        expected = (ALTERNATE_WEBVIEW2_LOADERS[relative_path],)
    else:
        expected = ("x64", "anycpu")
    if architecture not in expected:
        raise RuntimeError(
            f"Unexpected architecture in {relative_path}: {architecture}; expected {' or '.join(expected)}"
        )


def verify_bundle(version: str, app: Path = APP) -> dict:
    executable = app / "Gel Analyzer.exe"
    if not executable.is_file():
        raise RuntimeError(f"Missing application executable: {executable}")
    executable_info = inspect_pe(executable)
    if executable_info["architecture"] != "x64" or executable_info["subsystem"] != 2:
        raise RuntimeError("Gel Analyzer.exe must be a native x64 Windows GUI executable.")
    resources = app / "_internal"
    for required in REQUIRED_RESOURCES:
        if not (resources / required).is_file():
            raise RuntimeError(f"Missing bundled resource: {required}")
    if not list((resources / "webview" / "js").rglob("*.js")):
        raise RuntimeError("Missing pywebview JavaScript bridge resources.")
    binaries = []
    for path in sorted(app.rglob("*")):
        if not path.is_file() or path.suffix.lower() not in (".exe", ".dll", ".pyd"):
            continue
        info = inspect_pe(path)
        relative_path = path.relative_to(app).as_posix()
        verify_binary_architecture(relative_path, info["architecture"])
        binaries.append({"path": relative_path, **info})
    env = os.environ.copy()
    env["GEL_BUILD_APP_EXE"] = str(executable.resolve())
    executable_version = powershell_json(r"""
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
$info = (Get-Item -LiteralPath $env:GEL_BUILD_APP_EXE).VersionInfo
@{ file_version = $info.FileVersion; product_version = $info.ProductVersion } |
    ConvertTo-Json -Compress
""", env=env)
    if executable_version["product_version"] != version:
        raise RuntimeError(f"Incorrect application version: {executable_version}")
    return {
        "version": version, "host_windows": platform.platform(),
        "target_architecture": "x64 (Intel/AMD)", "minimum_windows": MIN_WINDOWS,
        "minimum_dotnet_framework": "4.8",
        "python": platform.python_version(),
        "pyinstaller": package_version("pyinstaller"),
        "pywebview": package_version("pywebview"),
        "signature": "unsigned",
        "application_id": APP_ID, "executable_version": executable_version,
        "binaries": binaries,
        "runtime_testing": "Not performed by this structural build check; run the Windows smoke tests.",
    }


def find_iscc(explicit: Path | None) -> Path:
    candidates = [explicit] if explicit else [
        Path(shutil.which("ISCC.exe")) if shutil.which("ISCC.exe") else None,
        Path(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")) / "Inno Setup 6" / "ISCC.exe",
        Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / "Inno Setup 6" / "ISCC.exe",
    ]
    for candidate in candidates:
        if candidate and candidate.is_file():
            return candidate.resolve()
    raise RuntimeError("Inno Setup 6 compiler not found. Install it or pass --iscc PATH.")


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--app-only", action="store_true", help="Build the application folder without an installer")
    parser.add_argument("--webview2-installer", type=Path, help="Microsoft Evergreen Standalone Installer for x64")
    parser.add_argument("--iscc", type=Path, help="Path to the Inno Setup 6 ISCC.exe compiler")
    args = parser.parse_args(argv)
    if sys.platform != "win32" or platform.machine().lower() not in ("amd64", "x86_64") or struct.calcsize("P") != 8:
        parser.error("Build on Intel/AMD x64 Windows using an x64 Python interpreter.")
    if sys.version_info[:2] != (3, 12):
        parser.error("Use the project's locked Python 3.12 environment.")
    if not args.app_only and not args.webview2_installer:
        parser.error("--webview2-installer is required for the offline installer.")
    version = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]["version"]
    if not re.fullmatch(r"\d+\.\d+\.\d+", version):
        parser.error(f"Release version must have three numeric components: {version!r}")
    iscc = None if args.app_only else find_iscc(args.iscc)
    prerequisite = verify_webview2_installer(args.webview2_installer) if args.webview2_installer else None
    DIST.mkdir(parents=True, exist_ok=True)
    WORK.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    env["PYINSTALLER_CONFIG_DIR"] = str(WORK / "pyinstaller-cache")
    run(
        sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean",
        "--distpath", DIST, "--workpath", WORK / "pyinstaller",
        ROOT / "packaging" / "windows.spec", env=env,
    )
    report = verify_bundle(version)
    report["git_commit"] = run("git", "rev-parse", "HEAD", capture=True).strip()
    if prerequisite:
        report["webview2_installer"] = prerequisite
    if iscc:
        run(
            iscc, f"/DAppVersion={version}", f"/DAppDir={APP}",
            f"/DOutputDir={DIST}", f"/DWebView2Installer={args.webview2_installer.resolve()}",
            ROOT / "packaging" / "windows.iss",
        )
        installer = DIST / f"Gel-Analyzer-{version}-Windows-x64-Setup.exe"
        if not installer.is_file() or installer.stat().st_size < args.webview2_installer.stat().st_size // 2:
            raise RuntimeError("The compiled offline installer is missing or unexpectedly small.")
        inspect_pe(installer)
        checksum = sha256(installer)
        (DIST / "SHA256SUMS-windows.txt").write_text(f"{checksum}  {installer.name}\n", encoding="utf-8")
        report["installer"] = {"filename": installer.name, "sha256": checksum, "size_bytes": installer.stat().st_size}
    (WORK / "validation.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(f"\nBuilt and structurally verified {APP}")
    if iscc:
        print(f"Created {installer}")
    print("Unsigned. Windows runtime and installation tests are required before release.")


if __name__ == "__main__":
    main()
