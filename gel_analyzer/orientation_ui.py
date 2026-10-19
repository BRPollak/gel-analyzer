"""Manual outline review before accepting an orientation preview."""

import math
from uuid import uuid4

import streamlit as st

from .image_io import GelImage, orient_gel_image
from .orientation import OrientationError, rectangle_from_selection
from .orientation_component import render_orientation_component


def reset_manual_orientation() -> None:
    """Invalidate in-flight events whenever the image or editing stage changes."""
    st.session_state.orientation_manual = False
    st.session_state.orientation_selection = None
    st.session_state.orientation_token = uuid4().hex
    st.session_state.orientation_revision = 0
    st.session_state.orientation_manual_error = None


def start_manual_orientation() -> None:
    """Review the staged outline against the unchanged initial crop."""
    reset_manual_orientation()
    gel = st.session_state.gel_image
    if gel is None or gel.orientation is not None:
        return
    st.session_state.orientation_manual = True
    pending = st.session_state.orientation_preview
    if pending is None:
        return
    # A partial-edge preview retains the entire source. Its expanded envelope
    # is not a detected gel outline and must not seed a fictitious crop box.
    if not getattr(pending.orientation, "outline_complete", True):
        return
    corners = pending.orientation.corners
    cx = sum(point[0] for point in corners) / 4
    cy = sum(point[1] for point in corners) / 4
    width = math.dist(corners[0], corners[1])
    height = math.dist(corners[0], corners[3])
    angle = math.degrees(math.atan2(
        corners[1][1] - corners[0][1], corners[1][0] - corners[0][0],
    ))
    # The automatic fit allows up to two pixels of edge-fitting tolerance.
    # Bring that outline just inside the source for editable manual geometry.
    scale = 1.0
    for x, y in corners:
        for delta, center, limit in (
            (x - cx, cx, gel.preview_width), (y - cy, cy, gel.preview_height),
        ):
            if delta > 0:
                scale = min(scale, (limit - center) / delta)
            elif delta < 0:
                scale = min(scale, -center / delta)
    selection = dict(cx=cx, cy=cy, width=width * scale, height=height * scale,
                     angle_degrees=angle)
    try:
        rectangle_from_selection(selection, (gel.preview_width, gel.preview_height))
    except OrientationError:
        return
    st.session_state.orientation_selection = selection


def accept_orientation_event(event: object, gel: GelImage) -> None:
    """Accept only newer valid geometry from this image's active editor."""
    if not st.session_state.orientation_manual or not isinstance(event, dict):
        return
    revision = event.get("revision")
    if (
        event.get("token") != st.session_state.orientation_token
        or type(revision) is not int
        or revision <= st.session_state.orientation_revision
        or "selection" not in event
    ):
        return
    selection = event["selection"]
    if selection is not None:
        try:
            rectangle = rectangle_from_selection(
                selection, (gel.preview_width, gel.preview_height),
            )
        except OrientationError:
            return
        selection = {name: float(selection[name]) for name in
                     ("cx", "cy", "width", "height", "angle_degrees")}
        selection["angle_degrees"] = rectangle.angle_degrees
    st.session_state.orientation_selection = selection
    st.session_state.orientation_revision = revision
    st.session_state.orientation_manual_error = None


def preview_manual_orientation() -> None:
    """Sample the initial crop once, then stage it for explicit confirmation."""
    gel = st.session_state.gel_image
    if gel is None or gel.orientation is not None or not st.session_state.orientation_manual:
        return
    # Consume a pointer-up event that arrives alongside a fast button click.
    accept_orientation_event(
        st.session_state.get(f"orientation_overlay_{st.session_state.orientation_token}"), gel,
    )
    try:
        rectangle = rectangle_from_selection(
            st.session_state.orientation_selection, (gel.preview_width, gel.preview_height),
        )
        preview = orient_gel_image(gel, rectangle=rectangle)
    except OrientationError as exc:
        st.session_state.orientation_manual_error = str(exc)
        return
    st.session_state.orientation_preview = preview
    st.session_state.orientation_preview_method = "manual"
    st.session_state.orientation_error = None
    reset_manual_orientation()


def show_manual_orientation(gel: GelImage, image_panel, controls_panel, retry) -> None:
    with image_panel:
        event = render_orientation_component(
            gel.preview_png, gel.preview_width, gel.preview_height,
            selection=st.session_state.orientation_selection,
            token=st.session_state.orientation_token,
            revision=st.session_state.orientation_revision,
            workflow_orientation=gel.workflow_orientation,
            key=f"orientation_overlay_{st.session_state.orientation_token}",
        )
        accept_orientation_event(event, gel)
    with controls_panel:
        st.subheader("Adjust gel outline")
        if st.session_state.orientation_error:
            st.warning(
                st.session_state.orientation_error + "\n\n"
                "Draw an outline around the gel to adjust it yourself."
            )
        st.caption(
            "Adjust the outline on the initial crop. The gold edge becomes the top "
            "in the preview. Confirm that preview to continue."
        )
        pending = st.session_state.orientation_preview
        if pending is not None and not getattr(pending.orientation, "outline_complete", True):
            st.caption(
                "The current preview keeps the full image. Draw an outline here "
                "to choose a crop, or cancel to return to that preview."
            )
        if st.session_state.orientation_manual_error:
            st.warning(st.session_state.orientation_manual_error)
        st.button(
            "Preview manual orientation", key="preview_manual_orientation", type="primary",
            disabled=st.session_state.orientation_selection is None,
            on_click=preview_manual_orientation,
        )
        st.button("Automatic orientation", key="rotate_and_orient", on_click=retry)
        st.button(
            "Cancel manual adjustment", key="cancel_manual_orientation",
            on_click=reset_manual_orientation,
        )
