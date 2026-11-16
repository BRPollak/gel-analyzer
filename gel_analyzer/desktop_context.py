"""Identify the Windows native backend without changing browser or Mac behavior."""

import os
import sys


def is_windows_desktop() -> bool:
    """Only the Windows desktop child opts into its platform-specific UI fixes."""
    return sys.platform == "win32" and os.environ.get("GEL_ANALYZER_DESKTOP") == "1"
