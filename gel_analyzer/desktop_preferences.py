"""Persist independent native open/save directories outside the application bundle."""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
import sys
from tempfile import NamedTemporaryFile
from threading import Lock
from typing import Literal


LOGGER = logging.getLogger("gel_analyzer.desktop")
DirectoryKind = Literal["upload", "download"]
_lock = Lock()


def preferences_path() -> Path:
    override = os.environ.get("GEL_ANALYZER_PREFERENCES_PATH")
    if override:
        return Path(override).expanduser()
    if sys.platform == "win32":
        root = Path(os.environ.get("LOCALAPPDATA") or Path.home() / "AppData" / "Local")
    else:
        root = Path.home() / "Library" / "Application Support"
    return root / "Gel Analyzer" / "preferences.json"


def _read(path: Path) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except (OSError, ValueError):
        return {}


def last_directory(kind: DirectoryKind, fallback: str = "") -> str:
    """Ignore stale folders, including disconnected drives, without changing memory."""
    with _lock:
        value = _read(preferences_path()).get(f"{kind}_directory")
    if isinstance(value, str):
        try:
            if Path(value).is_absolute() and Path(value).is_dir():
                return value
        except (OSError, ValueError):
            pass
    return fallback


def remember_directory(kind: DirectoryKind, directory: str | Path) -> None:
    """A preference failure must never prevent a successful image open/save."""
    temporary = None
    try:
        directory = Path(directory).resolve()
        if not directory.is_dir():
            return
        with _lock:
            path = preferences_path()
            values = _read(path)
            values[f"{kind}_directory"] = str(directory)
            path.parent.mkdir(parents=True, exist_ok=True)
            with NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent,
                                    prefix=".preferences-", delete=False) as output:
                temporary = Path(output.name)
                json.dump(values, output, ensure_ascii=False)
                output.write("\n")
            temporary.replace(path)
    except (OSError, ValueError):
        LOGGER.warning("Unable to remember the image %s folder", kind, exc_info=True)
    finally:
        if temporary is not None:
            try:
                temporary.unlink(missing_ok=True)
            except OSError:
                LOGGER.warning("Unable to remove temporary preferences", exc_info=True)
