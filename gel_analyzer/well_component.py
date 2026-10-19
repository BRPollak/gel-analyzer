"""Local, dependency-free Streamlit bridge for the well guide overlay.

Geometry is stored separately from the image. The browser receives the exact
PNG bytes and returns only confirmed pointer/keyboard edits in image coordinates.
The caller must rotate ``token`` when resetting or replacing the geometry, and
must reject events whose token no longer matches the current editing session.
"""

from base64 import b64encode
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import streamlit.components.v1 as components


_component = components.declare_component(
    "well_line_overlay", path=str(Path(__file__).with_name("well_component_frontend"))
)


def render_well_component(
    preview_png: bytes,
    width: int,
    height: int,
    *,
    points: Sequence[Sequence[float]],
    wells: Sequence[Mapping[str, Any]],
    lanes: Sequence[Sequence[float]],
    editable: bool,
    token: str,
    key: str,
    review_mode: str | None = None,
    right_edge: int | None = None,
    workflow_orientation: str = "wells_left",
) -> dict[str, Any] | None:
    """Show the overlay and return its last ``{token, revision, points}`` event.

    ``wells`` contain ``bounds`` and optionally ``center``; each bounds/lanes
    tuple is ``(left, top, right, bottom)`` in the confirmed image coordinates.
    A stable key preserves in-progress drags during ordinary Streamlit reruns.
    Initial rendering emits no value, so it cannot erase accepted endpoints.
    Review modes ``borders`` and ``extent`` edit image-coordinate lane geometry and
    return ``kind='lane_review'`` events instead of guide-point events. Rotate
    the token when entering a different review stage; set editable to enable
    its handles. The extent stage uses one shared right edge for every lane.
    ``boundary_first`` reuses the border handles on one movable lane;
    ``boundary_last`` freezes it and allows only translation of its copy.
    """
    return _component(
        image_src="data:image/png;base64," + b64encode(preview_png).decode("ascii"),
        width=width,
        height=height,
        points=[list(point) for point in points],
        wells=[dict(well) for well in wells],
        lanes=[list(lane) for lane in lanes],
        editable=editable,
        token=token,
        review_mode=review_mode,
        right_edge=right_edge,
        workflow_orientation=workflow_orientation,
        key=key,
        default=None,
    )
