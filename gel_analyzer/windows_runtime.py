"""Check Windows prerequisites without importing the browser or .NET runtime."""

from __future__ import annotations

import sys


WEBVIEW2_CLIENT = "{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}"
NET_FRAMEWORK_48_RELEASE = 528040
MINIMUM_WINDOWS_BUILD = 19045


def _registry_value(root, path: str, name: str, *, view: int = 0):
    import winreg

    try:
        with winreg.OpenKey(root, path, 0, winreg.KEY_READ | view) as key:
            return winreg.QueryValueEx(key, name)[0]
    except OSError:
        return None


def prerequisite_error() -> str | None:
    """Require the supported OS, .NET 4.8, and stable Evergreen WebView2."""
    import winreg

    version = sys.getwindowsversion()
    if (version.major, version.minor, version.build) < (10, 0, MINIMUM_WINDOWS_BUILD):
        return "Gel Analyzer requires Windows 10 version 22H2 or Windows 11. Update Windows before installing."

    net_key = r"SOFTWARE\Microsoft\NET Framework Setup\NDP\v4\Full"
    release = _registry_value(winreg.HKEY_LOCAL_MACHINE, net_key, "Release",
                              view=winreg.KEY_WOW64_32KEY)
    if not isinstance(release, int) or release < NET_FRAMEWORK_48_RELEASE:
        return ("Gel Analyzer requires Microsoft .NET Framework 4.8 or later. "
                "Install it through Windows Update, then reopen Gel Analyzer.")

    webview_key = rf"SOFTWARE\Microsoft\EdgeUpdate\Clients\{WEBVIEW2_CLIENT}"
    for root, view in ((winreg.HKEY_CURRENT_USER, 0),
                       (winreg.HKEY_LOCAL_MACHINE, winreg.KEY_WOW64_32KEY)):
        installed = _registry_value(root, webview_key, "pv", view=view)
        try:
            parts = tuple(int(part) for part in str(installed).split("."))
        except ValueError:
            continue
        if len(parts) == 4 and parts >= (86, 0, 622, 0):
            return None
    return ("Gel Analyzer requires Microsoft Edge WebView2 Runtime. "
            "Run the Gel Analyzer installer again to install it, then reopen the app.\n\n"
            "On a computer without internet access, install the WebView2 Evergreen "
            "Standalone Installer for x64 first.")


def show_error(message: str) -> None:
    """Report startup failures even when no console or browser is available."""
    import ctypes
    from ctypes import wintypes

    message_box = ctypes.windll.user32.MessageBoxW
    message_box.argtypes = [wintypes.HWND, wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.UINT]
    message_box.restype = ctypes.c_int
    message_box(None, message, "Gel Analyzer", 0x10)
