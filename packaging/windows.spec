"""Windows x64 app. Build with scripts/build_windows.py on Windows."""

from pathlib import Path
import sys
import tomllib

from PyInstaller.utils.hooks import collect_data_files, collect_submodules, copy_metadata
from PyInstaller.utils.win32.versioninfo import (
    FixedFileInfo, StringFileInfo, StringStruct, StringTable, VarFileInfo, VarStruct,
    VSVersionInfo,
)

ROOT = Path(SPECPATH).parent
VERSION = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]["version"]
VERSION_PARTS = tuple(int(part) for part in VERSION.split(".")) + (0,)
python_license_candidates = (
    Path(sys.base_prefix) / "LICENSE.txt",
    Path(sys.base_prefix) / "Lib" / "LICENSE.txt",
    Path(sys.base_prefix) / "lib" / "python3.12" / "LICENSE.txt",
)
python_license = next((path for path in python_license_candidates if path.is_file()), None)
if python_license is None:
    raise RuntimeError("The build Python installation must include its LICENSE.txt.")

# Keep the allowlist explicit: the checkout may contain private gel photographs.
datas = [
    (str(ROOT / "app.py"), "."),
    (str(ROOT / ".streamlit" / "config.toml"), ".streamlit"),
    (str(ROOT / "packaging" / "GelAnalyzer.ico"), "."),
    (str(python_license), "licenses/python"),
]
datas += collect_data_files("gel_analyzer")
datas += collect_data_files("streamlit")
datas += collect_data_files("webview")
datas += copy_metadata("streamlit", recursive=True)
datas += copy_metadata("pywebview", recursive=True)
datas += copy_metadata("numpy")
datas += copy_metadata("pillow")
datas += copy_metadata("pyinstaller")  # Includes the bootloader license exception.

# Streamlit executes app.py itself; pywebview selects WinForms dynamically.
hiddenimports = collect_submodules("gel_analyzer")
hiddenimports += collect_submodules(
    "streamlit", filter=lambda name: not name.startswith("streamlit.testing"),
)
hiddenimports += [
    "webview.platforms.winforms", "webview.platforms.edgechromium",
    "clr", "pythonnet", "clr_loader",
]

a = Analysis(
    [str(ROOT / "desktop_app.py")],
    pathex=[str(ROOT)],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        "PyQt5", "PyQt6", "PySide2", "PySide6", "tkinter", "gi", "pytest",
        "playwright", "psutil",
        "streamlit.testing", "AppKit", "Foundation", "WebKit", "Quartz",
        "webview.platforms.android", "webview.platforms.cef",
        "webview.platforms.cocoa", "webview.platforms.gtk",
        "webview.platforms.mshtml", "webview.platforms.qt",
    ],
    noarchive=False,
)


def needed_windows_file(entry):
    """The upstream hooks collect loaders for all architectures and for IE."""
    destination = entry[0].replace("\\", "/").lower()
    return not (
        "/win-x86/" in destination
        or "/win-arm64/" in destination
        or destination.startswith("clr_loader/ffi/dlls/x86/")
        or destination.endswith(("webbrowserinterop.x86.dll", "webbrowserinterop.x64.dll"))
    )


a.binaries = [entry for entry in a.binaries if needed_windows_file(entry)]
a.datas = [entry for entry in a.datas if needed_windows_file(entry)]
pyz = PYZ(a.pure)
version_info = VSVersionInfo(
    ffi=FixedFileInfo(
        filevers=VERSION_PARTS, prodvers=VERSION_PARTS,
        mask=0x3F, flags=0x0, OS=0x40004, fileType=0x1, subtype=0x0, date=(0, 0),
    ),
    kids=[
        StringFileInfo([StringTable("040904B0", [
            StringStruct("CompanyName", "Gel Analyzer contributors"),
            StringStruct("FileDescription", "Gel Analyzer"),
            StringStruct("FileVersion", VERSION),
            StringStruct("InternalName", "Gel Analyzer"),
            StringStruct("OriginalFilename", "Gel Analyzer.exe"),
            StringStruct("ProductName", "Gel Analyzer"),
            StringStruct("ProductVersion", VERSION),
            StringStruct("LegalCopyright", "Gel Analyzer contributors"),
        ])]),
        VarFileInfo([VarStruct("Translation", [0x0409, 1200])]),
    ],
)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="Gel Analyzer",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    icon=str(ROOT / "packaging" / "GelAnalyzer.ico"),
    version=version_info,
    uac_admin=False,
)
collection = COLLECT(
    exe, a.binaries, a.datas,
    strip=False, upx=False, name="Gel Analyzer",
)
