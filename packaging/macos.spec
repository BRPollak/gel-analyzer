"""Self-contained Apple Silicon app. Run through scripts/build_macos.py."""

from pathlib import Path
import sys
import tomllib

from PyInstaller.utils.hooks import collect_data_files, collect_submodules, copy_metadata

ROOT = Path(SPECPATH).parent
VERSION = tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]["version"]

# Only explicitly selected application data enters the bundle. In particular,
# never collect the repository root: it may contain users' private gel images.
datas = [
    (str(ROOT / "app.py"), "."),
    (str(ROOT / ".streamlit" / "config.toml"), ".streamlit"),
    (str(Path(sys.base_prefix) / "lib" / "python3.12" / "LICENSE.txt"), "licenses/python"),
]
datas += collect_data_files("gel_analyzer")
datas += collect_data_files("streamlit")
datas += collect_data_files("webview")
datas += copy_metadata("streamlit", recursive=True)
datas += copy_metadata("pywebview", recursive=True)
datas += copy_metadata("numpy")
datas += copy_metadata("pillow")
datas += copy_metadata("pyinstaller")  # Includes the bootloader's license exception.

# Streamlit executes app.py itself, so the application's imports are invisible
# to static analysis of desktop_app.py. Cocoa is chosen dynamically by pywebview.
hiddenimports = collect_submodules("gel_analyzer")
hiddenimports += collect_submodules("streamlit", filter=lambda name: not name.startswith("streamlit.testing"))
hiddenimports += [
    "webview.platforms.cocoa", "AppKit", "Foundation", "WebKit", "Quartz",
    "Security", "UniformTypeIdentifiers", "PyObjCTools.AppHelper",
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
        "PyQt5", "PyQt6", "PySide2", "PySide6", "tkinter", "gi", "pytest", "streamlit.testing",
        "webview.platforms.android", "webview.platforms.cef",
        "webview.platforms.edgechromium", "webview.platforms.gtk",
        "webview.platforms.mshtml", "webview.platforms.qt",
        "webview.platforms.winforms",
    ],
    noarchive=False,
)
pyz = PYZ(a.pure)
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
    argv_emulation=False,
    target_arch="arm64",
    codesign_identity=None,  # PyInstaller applies ad-hoc signatures.
    entitlements_file=None,
)
collection = COLLECT(
    exe, a.binaries, a.datas,
    strip=False,
    upx=False,
    name="Gel Analyzer",
)
app = BUNDLE(
    collection,
    name="Gel Analyzer.app",
    icon=str(ROOT / "packaging" / "GelAnalyzer.icns"),
    bundle_identifier="org.benpollak.gelanalyzer",
    version=VERSION,
    info_plist={
        "CFBundleDisplayName": "Gel Analyzer",
        "CFBundleName": "Gel Analyzer",
        "CFBundleVersion": VERSION,
        "LSMinimumSystemVersion": "14.0",
        "LSApplicationCategoryType": "public.app-category.education",
        "NSHighResolutionCapable": True,
        "NSAppTransportSecurity": {"NSAllowsLocalNetworking": True},
        "NSHumanReadableCopyright": "Gel Analyzer contributors",
    },
)
