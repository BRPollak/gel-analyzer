"""Staged Streamlit review of lane heights, right extent, and a lossless crop.

The confirmed orientation remains the source for every revision. Geometry and
the final cropped preview have their own session state; neither replaces the
uploaded TIFF or the confirmed image used for detection.
"""

from io import BytesIO
from uuid import uuid4

from PIL import Image
import streamlit as st

from . import lane_crop
from .wells import SelectionError, validate_line


def reset_lane_review() -> None:
    st.session_state.lane_stage = None
    st.session_state.lane_wells = ()
    st.session_state.lane_right = None
    st.session_state.lane_crop = None
    st.session_state.lane_source = None
    st.session_state.lane_token = uuid4().hex
    st.session_state.lane_revision = 0
    st.session_state.lane_error = None


def _confirmed_image():
    gel = st.session_state.gel_image
    if (
        gel is not None and gel.orientation is not None
        and st.session_state.orientation_preview is None
        and not st.session_state.orientation_requested
    ):
        return gel
    return None


def _set_stage(stage: str) -> None:
    """Each stage gets a fresh event identity, including return/back actions."""
    st.session_state.lane_stage = stage
    st.session_state.lane_token = uuid4().hex
    st.session_state.lane_revision = 0
    st.session_state.lane_crop = None
    st.session_state.lane_error = None


def start_lane_review() -> None:
    gel = _confirmed_image()
    result = st.session_state.well_result
    if gel is None or result is None:
        return
    try:
        validate_line(st.session_state.well_points, (gel.preview_width, gel.preview_height))
        wells = lane_crop.validate_lane_adjustments(
            result.wells, result.lanes, gel.preview_width,
            (gel.preview_width, gel.preview_height),
        ) if result.wells else ()
    except (lane_crop.LaneAdjustmentError, SelectionError) as exc:
        st.session_state.lane_error = str(exc)
        return
    st.session_state.lane_source = gel
    st.session_state.lane_wells = wells
    st.session_state.lane_right = gel.preview_width
    # Freeze the original guide, including uncertain candidates, while the
    # user reviews boundaries. Late guide events cannot replace this review.
    st.session_state.well_editing = False
    _set_stage("borders")


def _lanes():
    return tuple(
        (well.bounds[0], well.bounds[1], st.session_state.lane_right, well.bounds[3])
        for well in st.session_state.lane_wells
    )


def accept_lane_event(event: object) -> None:
    """Accept only legal edits from the active image, stage, and revision."""
    stage = st.session_state.lane_stage
    gel = _confirmed_image()
    if (
        stage not in ("borders", "extent") or gel is None
        or gel is not st.session_state.lane_source or not isinstance(event, dict)
        or event.get("token") != st.session_state.lane_token
        or event.get("kind") != "lane_review" or event.get("mode") != stage
    ):
        return
    revision = event.get("revision")
    if type(revision) is not int or revision <= st.session_state.lane_revision:
        return
    right = event.get("right_edge")
    action = event.get("action", "adjust")
    if action not in ("adjust", "delete") or (action == "delete" and stage != "borders"):
        return
    index = event.get("lane_index")
    if action == "delete" and (type(index) is not int or not 0 <= index < len(st.session_state.lane_wells)):
        return
    try:
        wells = lane_crop.validate_lane_adjustments(
            st.session_state.lane_wells, event.get("lanes"), right,
            (gel.preview_width, gel.preview_height),
        )
    except lane_crop.LaneAdjustmentError:
        return
    if stage == "borders" and right != st.session_state.lane_right:
        return
    if stage == "extent" and tuple(well.bounds for well in wells) != tuple(
        well.bounds for well in st.session_state.lane_wells
    ):
        return
    st.session_state.lane_wells = wells
    st.session_state.lane_right = int(right)
    st.session_state.lane_revision = revision
    st.session_state.lane_error = None
    st.session_state.lane_crop = None
    if action == "delete":
        st.session_state.lane_wells = wells[:index] + wells[index + 1:]
        # A structural edit invalidates every event from the old collection,
        # including clicks which still use its former lane numbering.
        _set_stage("borders")


def _consume_latest_event() -> None:
    accept_lane_event(st.session_state.get(f"lane_overlay_{st.session_state.lane_token}"))


def add_lane() -> None:
    """Append a manual proposal without rerunning detection or changing pixels."""
    if st.session_state.lane_stage != "borders":
        return
    _consume_latest_event()
    gel = _confirmed_image()
    if gel is None or gel is not st.session_state.lane_source:
        return
    try:
        wells = lane_crop.append_lane(
            st.session_state.lane_wells, st.session_state.well_points,
            st.session_state.lane_right, (gel.preview_width, gel.preview_height),
        )
    except lane_crop.LaneAdjustmentError as exc:
        st.session_state.lane_error = str(exc)
        return
    st.session_state.lane_wells = wells
    _set_stage("borders")


def confirm_lane_borders() -> None:
    if st.session_state.lane_stage != "borders":
        return
    _consume_latest_event()
    if _confirmed_image() is st.session_state.lane_source and st.session_state.lane_wells:
        _set_stage("extent")


def back_to_lane_borders() -> None:
    if st.session_state.lane_stage not in ("extent", "cropped"):
        return
    _consume_latest_event()
    if _confirmed_image() is st.session_state.lane_source and st.session_state.lane_wells:
        _set_stage("borders")


def confirm_lane_crop() -> None:
    if st.session_state.lane_stage != "extent":
        return
    _consume_latest_event()
    gel = _confirmed_image()
    if gel is None or gel is not st.session_state.lane_source:
        return
    try:
        with st.spinner("Cropping to the confirmed lanes…"):
            with Image.open(BytesIO(gel.preview_png)) as source:
                crop = lane_crop.crop_lanes(
                    source, st.session_state.lane_wells, st.session_state.lane_right,
                )
    except lane_crop.LaneAdjustmentError as exc:
        st.session_state.lane_error = str(exc)
        return
    _set_stage("cropped")
    st.session_state.lane_crop = crop


def show_lane_review(gel) -> None:
    # Streamlit can reload a component module independently of this UI module.
    # Resolve the callable on each render so a running app uses its current API.
    from .well_component import render_well_component

    if gel is not st.session_state.lane_source:
        reset_lane_review()
        st.rerun()
    stage = st.session_state.lane_stage
    if stage == "cropped":
        crop = st.session_state.lane_crop
        st.subheader("Cropped gel")
        st.image(BytesIO(crop.preview_png), width=crop.width, output_format="PNG")
        count = len(crop.lanes)
        st.success(f"Crop confirmed · {count} lane{'s' if count != 1 else ''} · {crop.width:,} × {crop.height:,} pixels")
        st.caption("The crop includes the space between lanes, a small margin left of the wells, and a buffer above and below the outer lanes.")
        st.button(
            "Revise lanes and crop", key="revise_lane_crop", on_click=back_to_lane_borders,
        )
        return

    if stage == "borders":
        st.subheader("1. Adjust lane borders")
        st.caption(
            "Drag the top and bottom borders of each numbered lane up or down. "
            "Use the trash button to the right of a lane to delete it, or Add lane to insert "
            "one at the bottom of the guide, below any existing lanes. Neighboring lanes cannot overlap. "
            "Arrow keys adjust a focused handle by one pixel; Shift moves ten pixels."
        )
        for warning in st.session_state.well_result.warnings:
            st.warning(warning)
        count = len(st.session_state.lane_wells)
        st.write(f"{count} lane{'s' if count != 1 else ''} in review")
        if not count:
            st.info("No lanes remain. Choose Add lane, then adjust its borders over the well and bands.")
    else:
        st.subheader("2. Set the right edge")
        st.caption(
            "Drag the right boundary left or right to choose how much of the gel to keep. "
            "The shaded area will be removed. All wells stay inside the crop."
        )
    wells = st.session_state.lane_wells
    event = render_well_component(
        gel.preview_png, gel.preview_width, gel.preview_height,
        points=(), wells=[{"bounds": well.bounds, "center": well.center} for well in wells],
        lanes=_lanes(), editable=True,
        token=st.session_state.lane_token, key=f"lane_overlay_{st.session_state.lane_token}",
        review_mode=stage, right_edge=st.session_state.lane_right,
    )
    token = st.session_state.lane_token
    accept_lane_event(event)
    if token != st.session_state.lane_token:
        st.rerun()
    if st.session_state.lane_error:
        st.warning(st.session_state.lane_error)
    if stage == "borders":
        st.button("Add lane", key="add_lane", on_click=add_lane)
        st.button(
            "Confirm lane borders", key="confirm_lane_borders", type="primary",
            on_click=confirm_lane_borders, disabled=not st.session_state.lane_wells,
        )
    else:
        margin = max(3, round(gel.preview_width * 0.01))
        vertical_margin = max(3, round(gel.preview_height * 0.01))
        st.caption(
            f"Right edge: {st.session_state.lane_right:,} pixels. The crop will run from the "
            f"top lane to the bottom lane, with up to {vertical_margin:,} pixels of buffer "
            f"above and below and {margin:,} pixels left of the wells."
        )
        st.button(
            "Confirm lanes and crop", key="confirm_lane_crop", type="primary",
            on_click=confirm_lane_crop,
        )
        st.button(
            "Back to lane borders", key="back_to_lane_borders", on_click=back_to_lane_borders,
        )
