"""Keep annotation drafts independent of widget lifetimes and confirmed PNGs."""

from io import BytesIO
from pathlib import Path
from uuid import uuid4

import streamlit as st

from .annotations import (
    AnnotationError, default_annotations, default_label, validate_annotations, validate_composition,
)


def invalidate_confirmation() -> None:
    st.session_state.annotation_token = uuid4().hex
    st.session_state.annotation_revision = 0
    st.session_state.annotation_png = None
    st.session_state.annotation_dimensions = None
    st.session_state.annotation_error = None


def reset_annotations() -> None:
    st.session_state.annotation_data = None
    invalidate_confirmation()


def add_lane_label(count: int) -> None:
    data = st.session_state.get("annotation_data")
    if data is not None:
        data["labels"].append(default_label(count))


def delete_lane_label(index: int) -> None:
    data = st.session_state.get("annotation_data")
    if data is None:
        return
    data["labels"].pop(index)
    groups = []
    for group in data["groups"]:
        members = [member - (member > index) for member in group["lanes"] if member != index]
        if members:
            groups.append({**group, "lanes": members})
    data["groups"] = groups


def accept_annotation_event(event: object, crop) -> bool:
    """Reject old-stage events and atomically accept confirmation snapshots."""
    if (
        st.session_state.get("lane_stage") != "cropped"
        or crop is not st.session_state.get("lane_crop")
        or st.session_state.annotation_png is not None
        or not isinstance(event, dict) or event.get("kind") != "annotations"
        or event.get("token") != st.session_state.annotation_token
        or event.get("action") not in ("edit", "confirm")
    ):
        return False
    revision = event.get("revision")
    if type(revision) is not int or revision <= st.session_state.annotation_revision:
        return False
    st.session_state.annotation_revision = revision
    try:
        data = validate_annotations(event.get("annotations"), len(crop.lanes))
        # Keep a valid draft even if image encoding needs another attempt.
        st.session_state.annotation_data = data
        if event["action"] == "confirm":
            png = validate_composition(event, crop)
            st.session_state.annotation_png = png
            st.session_state.annotation_dimensions = (event["width"], event["height"])
        st.session_state.annotation_error = None
    except AnnotationError as exc:
        st.session_state.annotation_error = str(exc)
    return True


def consume_latest_event() -> None:
    crop = st.session_state.get("lane_crop")
    if crop is not None and st.session_state.get("annotation_token"):
        accept_annotation_event(
            st.session_state.get(f"annotation_editor_{st.session_state.annotation_token}"), crop,
        )


def edit_annotations() -> None:
    if st.session_state.get("lane_stage") == "cropped":
        invalidate_confirmation()


def show_annotations(crop, filename: str) -> None:
    from .annotation_component import render_annotation_component

    if "annotation_token" not in st.session_state:
        reset_annotations()
    if st.session_state.annotation_data is None:
        st.session_state.annotation_data = default_annotations(len(crop.lanes), crop.lanes)
    st.subheader("3. Annotate lanes")
    if st.session_state.annotation_png is not None:
        width, height = st.session_state.annotation_dimensions
        st.image(BytesIO(st.session_state.annotation_png), width=width, output_format="PNG")
        st.success(f"Annotations confirmed · {width:,} × {height:,} pixels")
        st.button("Edit annotations", key="edit_annotations", on_click=edit_annotations)
        st.download_button(
            "Download annotated PNG", data=st.session_state.annotation_png,
            file_name=f"{Path(filename).stem}-annotated.png", mime="image/png",
            key="download_annotations",
        )
        st.caption("The annotated PNG uses browser display colors. Your original TIFF and lossless crop remain in this session.")
        return
    st.caption("Click a label on the preview to edit it. Use the toolbar to format the selected label.")
    event = render_annotation_component(
        crop, annotations=st.session_state.annotation_data,
        token=st.session_state.annotation_token, revision=st.session_state.annotation_revision,
        error=st.session_state.annotation_error,
        key=f"annotation_editor_{st.session_state.annotation_token}",
    )
    if accept_annotation_event(event, crop):
        st.rerun()
    if st.session_state.annotation_error:
        st.error(st.session_state.annotation_error)
