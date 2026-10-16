"""Local SVG rectangle editor for the initial gel crop.

Only geometry crosses this bridge. Preview pixels are never resampled or
modified by the component; the confirmed source image is oriented on the server.
"""

from base64 import b64encode
from pathlib import Path
from typing import Any

import streamlit.components.v1 as components


_component = components.declare_component(
    "orientation_rectangle",
    path=str(Path(__file__).with_name("orientation_component_frontend")),
)


def render_orientation_component(
    preview_png: bytes,
    width: int,
    height: int,
    *,
    selection: dict[str, Any] | None,
    token: str,
    key: str,
    revision: int = 0,
) -> dict[str, Any] | None:
    """Return completed ``{token, revision, selection}`` edits, if any.

    Selection contains ``cx``, ``cy``, ``width``, ``height`` and clockwise
    ``angle_degrees`` in initial-crop pixel-boundary coordinates. Keep ``key``
    stable during editing, pass the last accepted revision, and replace ``token``
    when resetting the editor or changing source images. Initial rendering and
    cancelled/tiny drags emit no event. Callers must reject stale event tokens
    and revisions before accepting geometry.
    """
    return _component(
        image_src="data:image/png;base64," + b64encode(preview_png).decode("ascii"),
        width=width,
        height=height,
        selection=dict(selection) if selection is not None else None,
        token=token,
        revision=revision,
        key=key,
        default=None,
    )
