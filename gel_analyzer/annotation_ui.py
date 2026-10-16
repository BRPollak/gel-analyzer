"""Session drafts, optional ladder workflow, and clean confirmed PNGs."""

from copy import deepcopy
from io import BytesIO
from pathlib import Path
from uuid import uuid4

import streamlit as st

from .annotations import (
    AnnotationError, default_annotations, default_label, validate_annotations, validate_composition,
)
from .annotation_exports import EXPORT_FORMATS, export_composition, validate_svg_composition
from .ladders import load_presets, validate_ladder


def _new_event_identity() -> None:
    st.session_state.annotation_token = uuid4().hex
    st.session_state.annotation_revision = 0
    st.session_state.annotation_error = None


def invalidate_confirmation() -> None:
    """Keep semantic annotations while invalidating a crop/editor's output."""
    _new_event_identity()
    st.session_state.annotation_stage = "lanes"
    st.session_state.annotation_png = None
    st.session_state.annotation_svg = None
    st.session_state.annotation_dimensions = None
    st.session_state.annotation_base_png = None
    st.session_state.annotation_base_svg = None
    st.session_state.annotation_base_dimensions = None
    st.session_state.ladder_draft = None


def reset_annotations() -> None:
    st.session_state.annotation_data = None
    st.session_state.ladder_data = None
    st.session_state.ladder_step = "preset"
    st.session_state.annotation_geometry = None
    st.session_state.annotation_completed = False
    st.session_state.ladder_notice = None
    invalidate_confirmation()


def _sync_crop(crop) -> None:
    geometry = (crop.crop_box, crop.width, crop.height, tuple(crop.lanes))
    previous = st.session_state.get("annotation_geometry")
    if previous is not None and previous != geometry:
        if st.session_state.get("ladder_data") or st.session_state.get("ladder_draft"):
            st.session_state.ladder_notice = "The crop or lanes changed. Please place your ladder markers again."
        st.session_state.ladder_data = None
        st.session_state.ladder_draft = None
        st.session_state.ladder_step = "preset"
        st.session_state.annotation_completed = False
    st.session_state.annotation_geometry = geometry


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


def _accept_identity(event, crop, kind, stage, actions) -> bool:
    if (
        st.session_state.get("lane_stage") != "cropped"
        or crop is not st.session_state.get("lane_crop")
        or st.session_state.get("annotation_stage") != stage
        or not isinstance(event, dict) or event.get("kind") != kind
        or event.get("token") != st.session_state.annotation_token
        or event.get("action") not in actions
    ):
        return False
    revision = event.get("revision")
    if type(revision) is not int or revision <= st.session_state.annotation_revision:
        return False
    st.session_state.annotation_revision = revision
    return True


def accept_annotation_event(event: object, crop) -> bool:
    """Accept the latest lane snapshot; confirmation opens the optional offer."""
    if not _accept_identity(event, crop, "annotations", "lanes", ("edit", "confirm")):
        return False
    try:
        data = validate_annotations(event.get("annotations"), len(crop.lanes))
        st.session_state.annotation_data = data
        if event["action"] == "confirm":
            png = validate_composition(event, crop)
            svg = validate_svg_composition(event, crop)
            base = event.get("base") if st.session_state.get("ladder_data") else event
            if not isinstance(base, dict):
                raise AnnotationError("The lane-only image could not be composed. Please try again.")
            base_png = validate_composition(base, crop)
            base_svg = svg if base is event else validate_svg_composition(base, crop)
            # Do not publish either output until both compositions are valid.
            st.session_state.annotation_base_png = base_png
            st.session_state.annotation_base_svg = base_svg
            st.session_state.annotation_base_dimensions = (base["width"], base["height"])
            st.session_state.annotation_png = png
            st.session_state.annotation_svg = svg
            st.session_state.annotation_dimensions = (event["width"], event["height"])
            st.session_state.annotation_stage = (
                "final" if st.session_state.annotation_completed else "ladder_offer"
            )
        st.session_state.annotation_error = None
    except AnnotationError as exc:
        st.session_state.annotation_error = str(exc)
    return True


def _finish_ladder(*, discard=False) -> None:
    if discard:
        st.session_state.ladder_data = None
        st.session_state.annotation_png = st.session_state.annotation_base_png
        st.session_state.annotation_svg = st.session_state.get("annotation_base_svg")
        st.session_state.annotation_dimensions = st.session_state.annotation_base_dimensions
    st.session_state.ladder_draft = None
    st.session_state.annotation_stage = "final"
    st.session_state.annotation_completed = True
    st.session_state.ladder_notice = None
    _new_event_identity()


def skip_ladder() -> None:
    if st.session_state.get("annotation_stage") in ("ladder_offer", "ladder"):
        _finish_ladder(discard=True)


def start_ladder() -> None:
    if st.session_state.get("annotation_stage") not in ("ladder_offer", "final"):
        return
    st.session_state.ladder_draft = deepcopy(st.session_state.ladder_data)
    st.session_state.ladder_step = "markers" if st.session_state.ladder_data else "preset"
    st.session_state.annotation_stage = "ladder"
    _new_event_identity()


def accept_ladder_event(event: object, crop) -> bool:
    if not _accept_identity(event, crop, "ladder", "ladder", ("edit", "confirm", "cancel", "skip", "remove")):
        return False
    if event["action"] in ("cancel", "skip", "remove"):
        _finish_ladder(discard=event["action"] != "cancel")
        return True
    try:
        draft = validate_ladder(event.get("ladder"), crop)
        step = event.get("ladder_step", "preset")
        if step not in ("preset", "lane", "markers"):
            raise AnnotationError("Choose a valid ladder step.")
        st.session_state.ladder_draft = draft
        st.session_state.ladder_step = step
        if event["action"] == "confirm":
            checked = validate_ladder(draft, crop, complete=True)
            png = validate_composition(event, crop)
            svg = validate_svg_composition(event, crop)
            st.session_state.ladder_data = checked
            st.session_state.annotation_png = png
            st.session_state.annotation_svg = svg
            st.session_state.annotation_dimensions = (event["width"], event["height"])
            _finish_ladder()
        st.session_state.annotation_error = None
    except AnnotationError as exc:
        st.session_state.annotation_error = str(exc)
    return True


def consume_latest_event() -> None:
    crop = st.session_state.get("lane_crop")
    if crop is not None and st.session_state.get("annotation_token"):
        event = st.session_state.get(f"annotation_editor_{st.session_state.annotation_token}")
        if st.session_state.get("annotation_stage") == "ladder":
            accept_ladder_event(event, crop)
        else:
            accept_annotation_event(event, crop)


def edit_annotations() -> None:
    if st.session_state.get("lane_stage") == "cropped":
        invalidate_confirmation()


def show_annotations(crop, filename: str) -> None:
    from .annotation_component import render_annotation_component

    if "annotation_stage" not in st.session_state:
        reset_annotations()
    _sync_crop(crop)
    if st.session_state.annotation_data is None:
        st.session_state.annotation_data = default_annotations(len(crop.lanes), crop.lanes)
    stage = st.session_state.annotation_stage
    if stage != "final":
        st.subheader("4. Annotate ladder" if stage == "ladder" else "3. Annotate lanes")
    if st.session_state.ladder_notice:
        st.info(st.session_state.ladder_notice)
    if stage in ("ladder_offer", "final"):
        width, height = st.session_state.annotation_dimensions
        with st.container(key="gel_workspace"):
            image_panel, controls_column = st.columns([3.2, 1.15], gap="large")
            with image_panel:
                st.image(BytesIO(st.session_state.annotation_png), width=width, output_format="PNG")
            with controls_column, st.container(border=True, key="gel_workflow_controls"):
                if stage == "ladder_offer":
                    st.success(f"Annotations confirmed · {width:,} × {height:,} pixels")
                    st.write("Would you like to annotate a ladder?")
                    st.button("Annotate ladder", key="annotate_ladder", type="primary", on_click=start_ladder)
                    st.button("Skip", key="skip_ladder", on_click=skip_ladder)
                    st.button("Edit annotations", key="edit_annotations", on_click=edit_annotations)
                else:
                    with st.container(key="gel_export_options"):
                        image_format = st.selectbox("Image file type", list(EXPORT_FORMATS),
                                                    key="annotation_export_format")
                        specification = EXPORT_FORMATS[image_format]
                        if image_format == "SVG":
                            st.selectbox("Resolution (DPI)", ["Vector · resolution independent"],
                                         disabled=True, key="annotation_export_vector_resolution")
                            dpi = None
                        else:
                            dpi = st.selectbox("Resolution (DPI)", specification["dpi"],
                                               index=specification["dpi"].index(300),
                                               key=f"annotation_export_dpi_{image_format}")
                        st.caption(f"Annotations confirmed · {width:,} × {height:,} pixels")
                        if image_format == "SVG":
                            st.caption("SVG keeps labels and brackets as vectors and embeds the gel at its original pixel resolution."
                                       if st.session_state.get("annotation_svg") else
                                       "This SVG embeds the confirmed image. Edit and reconfirm annotations for vector labels and brackets.")
                        else:
                            st.caption("DPI sets print size; pixel dimensions stay unchanged."
                                       + (" JPEG uses lossy compression." if image_format == "JPEG" else ""))
                        st.button("Edit ladder" if st.session_state.ladder_data else "Annotate ladder",
                                  key="edit_ladder", on_click=start_ladder)
                        st.button("Edit annotations", key="edit_annotations", on_click=edit_annotations)
                        st.caption("Exports use display colors. Your original TIFF and lossless crop remain in this session.")
                    exported = export_composition(
                        st.session_state.annotation_png, image_format, dpi,
                        svg=st.session_state.get("annotation_svg"),
                    )
                    with st.container(key="gel_export_actions"):
                        st.download_button(
                            f"Download annotated {image_format}", data=exported,
                            file_name=f"{Path(filename).stem}-annotated.{specification['extension']}",
                            mime=specification["mime"],
                            key="download_annotations", type="primary",
                        )
        return
    presets = []
    if stage == "ladder":
        try:
            presets = load_presets()
        except AnnotationError as exc:
            st.warning(str(exc))
    else:
        st.caption("Click a label to edit it. Select text within a label to format just that selection.")
    event = render_annotation_component(
        crop, annotations=st.session_state.annotation_data,
        token=st.session_state.annotation_token, revision=st.session_state.annotation_revision,
        error=st.session_state.annotation_error,
        key=f"annotation_editor_{st.session_state.annotation_token}",
        mode="ladder" if stage == "ladder" else "lanes",
        ladder=st.session_state.ladder_draft if stage == "ladder" else st.session_state.ladder_data,
        presets=presets, ladder_step=st.session_state.ladder_step,
        confirmed_ladder=st.session_state.ladder_data is not None,
    )
    accept = accept_ladder_event if stage == "ladder" else accept_annotation_event
    if accept(event, crop):
        st.rerun()
    if st.session_state.annotation_error:
        st.error(st.session_state.annotation_error)
