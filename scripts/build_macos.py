"""Build and verify the macOS app and drag-to-Applications installer.

Usage: uv run --frozen --group desktop --group build python scripts/build_macos.py
The build is repeatable from uv.lock, but Apple archive/signature timestamps
mean outputs are not expected to be byte-for-byte reproducible.
"""

from __future__ import annotations

import argparse
import hashlib
from importlib.metadata import version as package_version
import json
import os
from pathlib import Path
import platform
import plistlib
import re
import shutil
import subprocess
import sys
import tempfile
import tomllib
import zipfile


ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / "dist"
WORK = ROOT / "build" / "macos"
APP = DIST / "Gel Analyzer.app"
MIN_MACOS = (14, 0)
MACHO_MAGICS = {
    b"\xfe\xed\xfa\xce", b"\xce\xfa\xed\xfe",
    b"\xfe\xed\xfa\xcf", b"\xcf\xfa\xed\xfe",
    b"\xca\xfe\xba\xbe", b"\xbe\xba\xfe\xca",
    b"\xca\xfe\xba\xbf", b"\xbf\xba\xfe\xca",
}


def run(*args: str | Path, capture: bool = False, env: dict | None = None) -> str:
    command = [str(arg) for arg in args]
    if not capture:
        print("+", " ".join(command), flush=True)
    try:
        result = subprocess.run(
            command, cwd=ROOT, check=True, env=env, text=True,
            stdout=subprocess.PIPE if capture else None,
            stderr=subprocess.STDOUT if capture else None,
        )
    except subprocess.CalledProcessError as exc:
        if capture and exc.stdout:
            print(exc.stdout, file=sys.stderr)
        raise
    return result.stdout or ""


def macos_version(value: str) -> tuple[int, int]:
    parts = [int(part) for part in value.split(".")]
    return tuple((parts + [0])[:2])


def verify_bundle(version: str) -> dict:
    with (APP / "Contents" / "Info.plist").open("rb") as source:
        info = plistlib.load(source)
    expected = {
        "CFBundleShortVersionString": version,
        "CFBundleVersion": version,
        "CFBundleIdentifier": "org.benpollak.gelanalyzer",
        "LSMinimumSystemVersion": "14.0",
    }
    for key, value in expected.items():
        if info.get(key) != value:
            raise RuntimeError(f"Incorrect {key}: expected {value!r}, got {info.get(key)!r}")
    run("/usr/bin/codesign", "--verify", "--deep", "--strict", "--verbose=2", APP)
    signature = run("/usr/bin/codesign", "--display", "--verbose=4", APP, capture=True)
    if "Signature=adhoc" not in signature:
        raise RuntimeError("Expected an ad-hoc signed app")
    resources = APP / "Contents" / "Resources"
    for required in (
        "app.py", "GelAnalyzer.icns", ".streamlit/config.toml", "streamlit/static/index.html",
        "gel_analyzer/ladder_presets.json", "gel_analyzer/viewport.html",
        "gel_analyzer/orientation_component_frontend/index.html",
        "gel_analyzer/well_component_frontend/index.html",
        "gel_analyzer/annotation_component_frontend/index.html",
        "gel_analyzer/annotation_component_frontend/ladder_references/neb-1-kb.webp",
    ):
        if not (resources / required).is_file():
            raise RuntimeError(f"Missing bundled resource: {required}")

    binaries = []
    for path in sorted(APP.rglob("*")):
        if path.is_symlink() or not path.is_file():
            continue
        with path.open("rb") as source:
            if source.read(4) not in MACHO_MAGICS:
                continue
        architectures = run("/usr/bin/lipo", "-archs", path, capture=True).split()
        if architectures != ["arm64"]:
            raise RuntimeError(f"Unexpected architectures in {path}: {architectures}")
        commands = run("/usr/bin/otool", "-l", path, capture=True)
        minimums = re.findall(r"\bminos\s+(\d+(?:\.\d+)*)", commands)
        for block in commands.split("Load command "):
            if "cmd LC_VERSION_MIN_MACOSX" in block:
                minimums += re.findall(r"\bversion\s+(\d+(?:\.\d+)*)", block)
        if not minimums:
            raise RuntimeError(f"Cannot determine macOS minimum for {path}")
        if any(macos_version(value) > MIN_MACOS for value in minimums):
            raise RuntimeError(f"{path} requires newer than macOS 14: {minimums}")
        binaries.append({"path": str(path.relative_to(APP)), "minimum_macos": minimums})
    if not binaries:
        raise RuntimeError("No Mach-O binaries found in app")
    return {
        "version": version,
        "host_macos": platform.mac_ver()[0],
        "target_architecture": "arm64",
        "minimum_macos": "14.0",
        "python": platform.python_version(),
        "pyinstaller": package_version("pyinstaller"),
        "pywebview": package_version("pywebview"),
        "signature": "ad-hoc (not notarized)",
        "binaries": binaries,
    }


def build_archives(version: str) -> None:
    stem = f"Gel-Analyzer-{version}-macOS-arm64"
    zip_path = DIST / f"{stem}.zip"
    dmg_path = DIST / f"{stem}.dmg"
    staging = WORK / "dmg"
    if staging.exists():
        shutil.rmtree(staging)
    staging.mkdir(parents=True)
    run("/usr/bin/ditto", APP, staging / APP.name)
    (staging / "Applications").symlink_to("/Applications", target_is_directory=True)
    (staging / "Install Gel Analyzer.txt").write_text(
        f"Gel Analyzer {version}\n\n"
        "Requires an Apple Silicon Mac running macOS 14 or later.\n\n"
        "Drag Gel Analyzer.app to Applications, then open it from Applications.\n"
        "This release is ad-hoc signed and is not notarized by Apple. If macOS\n"
        "blocks the first launch, try opening it once, then open System Settings\n"
        "> Privacy & Security and choose Open Anyway for Gel Analyzer.\n\n"
        "No Python installation, Terminal, or browser is required.\n"
        "Save your .gel.json project before quitting.\n"
        "Logs: ~/Library/Logs/Gel Analyzer/\n"
    )
    # ditto preserves the framework symlinks and resource forks in .app bundles.
    zip_path.unlink(missing_ok=True)
    run("/usr/bin/ditto", "-c", "-k", "--sequesterRsrc", "--keepParent", APP, zip_path)
    run(
        "/usr/bin/hdiutil", "create", "-volname", f"Gel Analyzer {version}",
        "-srcfolder", staging, "-ov", "-format", "UDZO", "-fs", "HFS+", dmg_path,
    )
    run("/usr/bin/hdiutil", "verify", dmg_path)
    with zipfile.ZipFile(zip_path) as archive:
        bad_member = archive.testzip()
        if bad_member:
            raise RuntimeError(f"ZIP failed its CRC check: {bad_member}")
        if f"{APP.name}/Contents/Info.plist" not in archive.namelist():
            raise RuntimeError("ZIP does not contain the application bundle")
    verify_installer(dmg_path, version)
    checksums = []
    for artifact in (dmg_path, zip_path):
        with artifact.open("rb") as source:
            checksum = hashlib.file_digest(source, "sha256").hexdigest()
        checksums.append(f"{checksum}  {artifact.name}\n")
    (DIST / "SHA256SUMS").write_text("".join(checksums))


def verify_installer(dmg_path: Path, version: str) -> None:
    # Exercise the actual mounted image and a fresh drag-install equivalent,
    # while leaving the user's Applications directory untouched.
    with tempfile.TemporaryDirectory(prefix="gel-analyzer-installer-") as temp:
        scratch = Path(temp)
        mount = scratch / "volume"
        mount.mkdir()
        attached = False
        try:
            run("/usr/bin/hdiutil", "attach", "-readonly", "-nobrowse", "-mountpoint", mount, dmg_path)
            attached = True
            shortcut = mount / "Applications"
            if not shortcut.is_symlink() or shortcut.readlink() != Path("/Applications"):
                raise RuntimeError("Installer is missing its Applications shortcut")
            installed = scratch / "installed" / APP.name
            run("/usr/bin/ditto", mount / APP.name, installed)
            run("/usr/bin/codesign", "--verify", "--deep", "--strict", installed)
            with (installed / "Contents" / "Info.plist").open("rb") as source:
                info = plistlib.load(source)
            if info.get("CFBundleShortVersionString") != version:
                raise RuntimeError("Installed app has the wrong version")
        finally:
            if attached:
                run("/usr/bin/hdiutil", "detach", mount)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--app-only", action="store_true", help="Skip DMG and ZIP creation")
    args = parser.parse_args()
    if sys.platform != "darwin" or platform.machine() != "arm64":
        parser.error("Build on an Apple Silicon Mac using an arm64 Python interpreter")
    if sys.version_info[:2] != (3, 12):
        parser.error("Use the project's locked Python 3.12 environment")
    for tool in ("codesign", "ditto", "hdiutil", "lipo", "otool"):
        if not Path(f"/usr/bin/{tool}").exists():
            parser.error(f"Required macOS tool is unavailable: {tool}")
    version = tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]["version"]
    if not re.fullmatch(r"\d+\.\d+\.\d+", version):
        parser.error(f"Release version must have three numeric components: {version!r}")
    DIST.mkdir(exist_ok=True)
    WORK.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    env["MACOSX_DEPLOYMENT_TARGET"] = "14.0"
    env["PYINSTALLER_CONFIG_DIR"] = str(WORK / "pyinstaller-cache")
    run(
        sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean",
        "--distpath", DIST, "--workpath", WORK / "pyinstaller",
        ROOT / "packaging" / "macos.spec", env=env,
    )
    report = verify_bundle(version)
    report["git_commit"] = run("git", "rev-parse", "HEAD", capture=True).strip()
    (WORK / "validation.json").write_text(json.dumps(report, indent=2) + "\n")
    if not args.app_only:
        build_archives(version)
    print(f"\nBuilt and verified {APP}")
    print(f"Verified {len(report['binaries'])} arm64 binaries support macOS 14 or earlier.")
    print("Ad-hoc signed; separate runtime testing on macOS 14 is still required.")


if __name__ == "__main__":
    main()
