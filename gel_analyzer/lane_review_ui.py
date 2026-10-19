"""Staged Streamlit review of lane heights, right extent, and a lossless crop.

The confirmed orientation remains the source for every revision. Geometry and
the final cropped preview have their own session state; neither replaces the
uploaded TIFF or the confirmed image used for detection.
"""

from io import BytesIO
from uuid import uuid4

from PIL import Image
import streamlit as st

from . import annotation_ui, lane_crop
from .wells import DetectionResult, SelectionError, Well, validate_line
from .workflow_orientation import is_top, lane_bounds


def _orientation(gel=None):
    source = gel if gel is not None else st.session_state.lane_source
    return getattr(source, "workflow_orientation", "wells_left")


def reset_lane_review() -> None:
    annotation_ui.reset_annotations()
    st.session_state.lane_stage = None
    st.session_state.lane_wells = ()
    st.session_state.lane_right = None
    st.session_state.lane_crop = None
    st.session_state.lane_source = None
    st.session_state.lane_token = uuid4().hex
    st.session_state.lane_revision = 0
    st.session_state.lane_error = None
    _clear_boundary_draft()


def _clear_boundary_draft() -> None:
    st.session_state.lane_boundary_stage = None
    st.session_state.lane_boundary_backup = None
    st.session_state.lane_boundary_last = None
    st.session_state.lane_boundary_count = None


def _review_mode() -> str | None:
    boundary = st.session_state.get("lane_boundary_stage")
    return f"boundary_{boundary}" if boundary else st.session_state.lane_stage


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
    annotation_ui.invalidate_confirmation()


def start_lane_review() -> None:
    gel = _confirmed_image()
    result = st.session_state.well_result
    count = st.session_state.get("well_expected_count")
    if (gel is None or result is None or type(count) is not int or count < 1
            or len(result.wells) != count or len(result.lanes) != count):
        return
    orientation = _orientation(gel)
    right = result.lanes[0][3 if is_top(orientation) else 2]
    try:
        validate_line(st.session_state.well_points, (gel.preview_width, gel.preview_height),
                      workflow_orientation=orientation)
        wells = lane_crop.validate_lane_adjustments(
            result.wells, result.lanes, right,
            (gel.preview_width, gel.preview_height),
            workflow_orientation=orientation,
        )
    except (lane_crop.LaneAdjustmentError, SelectionError) as exc:
        st.session_state.lane_error = str(exc)
        return
    st.session_state.lane_source = gel
    annotation_ui.reset_annotations()
    st.session_state.lane_wells = wells
    st.session_state.lane_right = right
    # Freeze the original guide, including uncertain candidates, while the
    # user reviews boundaries. Late guide events cannot replace this review.
    st.session_state.well_editing = False
    _set_stage("borders")


def restore_legacy_review_count() -> None:
    """Adopt existing manual review geometry after upgrading a live session."""
    if (st.session_state.get("well_expected_count") is not None
            or st.session_state.lane_stage not in ("borders", "extent", "cropped")
            or st.session_state.get("lane_boundary_stage")):
        return
    gel = st.session_state.lane_source
    if gel is None:
        return
    result = st.session_state.well_result
    wells = st.session_state.lane_wells
    lanes = _lanes()
    if not wells and result is not None:
        wells, lanes = result.wells, result.lanes
    if not wells:
        return
    try:
        lane_crop.validate_lane_adjustments(
            wells, lanes, st.session_state.lane_right,
            (gel.preview_width, gel.preview_height), workflow_orientation=_orientation(gel),
        )
    except (lane_crop.LaneAdjustmentError, TypeError, ValueError):
        return
    st.session_state.well_expected_count = len(wells)
    st.session_state.well_result = DetectionResult(wells, lanes, result.warnings if result else ())


def _lanes():
    return tuple(
        lane_bounds(well.bounds, st.session_state.lane_right, _orientation())
        for well in st.session_state.lane_wells
    )


def accept_lane_event(event: object) -> None:
    """Accept only legal edits from the active image, stage, and revision."""
    stage = _review_mode()
    gel = _confirmed_image()
    if (
        stage not in ("borders", "extent", "boundary_first", "boundary_last") or gel is None
        or gel is not st.session_state.lane_source or not isinstance(event, dict)
        or event.get("token") != st.session_state.lane_token
        or event.get("kind") != "lane_review" or event.get("mode") != stage
    ):
        return
    revision = event.get("revision")
    if type(revision) is not int or revision <= st.session_state.lane_revision:
        return
    if stage.startswith("boundary_"):
        if event.get("action", "adjust") != "adjust" or event.get("right_edge") != st.session_state.lane_right:
            return
        try:
            wells = lane_crop.validate_boundary_adjustments(
                st.session_state.lane_wells, event.get("lanes"), event.get("right_edge"),
                (gel.preview_width, gel.preview_height), stage=stage,
                workflow_orientation=_orientation(gel),
            )
        except lane_crop.LaneAdjustmentError:
            return
        st.session_state.lane_wells = wells
        st.session_state.lane_revision = revision
        st.session_state.lane_error = None
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
            workflow_orientation=_orientation(gel),
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
        annotation_ui.delete_lane_label(index)
        st.session_state.lane_wells = wells[:index] + wells[index + 1:]
        _sync_reviewed_count()
        # A structural edit invalidates every event from the old collection,
        # including clicks which still use its former lane numbering.
        _set_stage("borders")


def _sync_reviewed_count() -> None:
    """Explicit manual additions/removals establish the revised well count."""
    if st.session_state.lane_wells:
        st.session_state.well_expected_count = len(st.session_state.lane_wells)
        result = st.session_state.well_result
        st.session_state.well_result = DetectionResult(
            st.session_state.lane_wells, _lanes(), result.warnings if result else (),
        )


def _consume_latest_event() -> None:
    accept_lane_event(st.session_state.get(f"lane_overlay_{st.session_state.lane_token}"))


def _boundary_ready(stage=None) -> bool:
    gel = _confirmed_image()
    return (gel is not None and gel is st.session_state.lane_source
            and st.session_state.lane_stage == "borders"
            and (stage is None or st.session_state.get("lane_boundary_stage") == stage))


def _boundary_count_error() -> str | None:
    count = st.session_state.get("lane_boundary_count")
    if type(count) is not int or count < 2:
        return "Enter a whole number of at least 2 lanes, including both boundary wells."
    return None


def change_boundary_count() -> None:
    st.session_state.lane_boundary_count = st.session_state.boundary_lane_count
    st.session_state.lane_error = None


def define_boundary_wells() -> None:
    if not _boundary_ready() or st.session_state.get("lane_boundary_stage"):
        return
    _consume_latest_event()
    gel = _confirmed_image()
    try:
        first = lane_crop.seed_boundary_well(
            st.session_state.lane_wells, st.session_state.well_points,
            st.session_state.lane_right, (gel.preview_width, gel.preview_height),
            workflow_orientation=_orientation(gel),
        )
    except lane_crop.LaneAdjustmentError as exc:
        st.session_state.lane_error = str(exc)
        return
    st.session_state.lane_boundary_backup = {
        "lane_wells": st.session_state.lane_wells, "lane_right": st.session_state.lane_right,
    }
    count = st.session_state.get("well_expected_count")
    st.session_state.lane_boundary_count = max(2, count if type(count) is int and count > 0
                                             else len(st.session_state.lane_wells))
    st.session_state.lane_boundary_last = None
    st.session_state.lane_wells = (first,)
    st.session_state.lane_boundary_stage = "first"
    _set_stage("borders")


def confirm_first_well() -> None:
    if not _boundary_ready("first"):
        return
    _consume_latest_event()
    error = _boundary_count_error()
    if error:
        st.session_state.lane_error = error
        return
    gel = _confirmed_image()
    first = st.session_state.lane_wells[0]
    cross = 0 if is_top(_orientation(gel)) else 1
    maximum = gel.preview_width if cross == 0 else gel.preview_height
    previous = st.session_state.lane_boundary_last
    originals = st.session_state.lane_boundary_backup["lane_wells"]
    if previous is not None:
        center = previous.center[cross]
    elif len(originals) > 1:
        center = originals[-1].center[cross]
    else:
        center = max(point[cross] for point in st.session_state.well_points)
    width = first.bounds[cross + 2] - first.bounds[cross]
    start = min(max(0, center - width / 2), maximum - width)
    bounds = list(first.bounds)
    bounds[cross], bounds[cross + 2] = start, start + width
    last = Well(tuple(bounds), ((bounds[0] + bounds[2]) / 2, (bounds[1] + bounds[3]) / 2))
    st.session_state.lane_wells = (first, last)
    st.session_state.lane_boundary_stage = "last"
    _set_stage("borders")


def back_to_first_well() -> None:
    if not _boundary_ready("last"):
        return
    _consume_latest_event()
    st.session_state.lane_boundary_last = st.session_state.lane_wells[1]
    st.session_state.lane_wells = st.session_state.lane_wells[:1]
    st.session_state.lane_boundary_stage = "first"
    _set_stage("borders")


def cancel_boundary_wells() -> None:
    if not _boundary_ready() or not st.session_state.get("lane_boundary_stage"):
        return
    backup = st.session_state.lane_boundary_backup
    st.session_state.lane_wells = backup["lane_wells"]
    st.session_state.lane_right = backup["lane_right"]
    _clear_boundary_draft()
    _set_stage("borders")


def _generated_boundary_wells():
    error = _boundary_count_error()
    if error:
        raise lane_crop.LaneAdjustmentError(error)
    gel = _confirmed_image()
    first, last = st.session_state.lane_wells
    return lane_crop.generate_boundary_lanes(
        first, last, st.session_state.lane_boundary_count, st.session_state.lane_right,
        (gel.preview_width, gel.preview_height), workflow_orientation=_orientation(gel),
    )


def generate_boundary_lanes() -> None:
    if not _boundary_ready("last"):
        return
    _consume_latest_event()
    try:
        wells = _generated_boundary_wells()
    except lane_crop.LaneAdjustmentError as exc:
        st.session_state.lane_error = str(exc)
        return
    st.session_state.lane_wells = wells
    st.session_state.well_expected_count = st.session_state.lane_boundary_count
    st.session_state.well_result = DetectionResult(wells, _lanes())
    annotation_ui.reset_annotations()
    _clear_boundary_draft()
    _set_stage("borders")


def add_lane() -> None:
    """Append a manual proposal without rerunning detection or changing pixels."""
    if _review_mode() != "borders":
        return
    _consume_latest_event()
    gel = _confirmed_image()
    if gel is None or gel is not st.session_state.lane_source:
        return
    try:
        wells = lane_crop.append_lane(
            st.session_state.lane_wells, st.session_state.well_points,
            st.session_state.lane_right, (gel.preview_width, gel.preview_height),
            workflow_orientation=_orientation(gel),
        )
    except lane_crop.LaneAdjustmentError as exc:
        st.session_state.lane_error = str(exc)
        return
    st.session_state.lane_wells = wells
    _sync_reviewed_count()
    annotation_ui.add_lane_label(len(wells))
    _set_stage("borders")


def confirm_lane_borders() -> None:
    if _review_mode() != "borders":
        return
    _consume_latest_event()
    if _confirmed_image() is st.session_state.lane_source and st.session_state.lane_wells:
        _set_stage("extent")


def back_to_well_review() -> None:
    """Keep manual changes when returning to the three-action well review."""
    if _review_mode() != "borders":
        return
    _consume_latest_event()
    if _confirmed_image() is not st.session_state.lane_source:
        return
    if st.session_state.lane_wells:
        _sync_reviewed_count()
        st.session_state.well_editing = False
    else:
        st.session_state.well_result = None
        st.session_state.well_editing = True
    reset_lane_review()


def back_to_lane_borders() -> None:
    if st.session_state.lane_stage not in ("extent", "cropped"):
        return
    annotation_ui.consume_latest_event()
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
                    workflow_orientation=_orientation(gel),
                )
    except lane_crop.LaneAdjustmentError as exc:
        st.session_state.lane_error = str(exc)
        return
    _set_stage("cropped")
    st.session_state.lane_crop = crop


def show_lane_review(gel, *, image_panel=None, controls_panel=None) -> None:
    # Streamlit can reload a component module independently of this UI module.
    # Resolve the callable on each render so a running app uses its current API.
    from .well_component import render_well_component

    if gel is not st.session_state.lane_source:
        reset_lane_review()
        st.rerun()
    stage = st.session_state.lane_stage
    top_mode = is_top(_orientation(gel))
    if stage == "cropped":
        crop = st.session_state.lane_crop
        annotation_ui.show_annotations(crop, gel.filename)
        return

    with image_panel:
        wells = st.session_state.lane_wells
        event = render_well_component(
            gel.preview_png, gel.preview_width, gel.preview_height,
            points=(), wells=[{"bounds": well.bounds, "center": well.center} for well in wells],
            lanes=_lanes(), editable=True,
            token=st.session_state.lane_token, key=f"lane_overlay_{st.session_state.lane_token}",
            review_mode=_review_mode(), right_edge=st.session_state.lane_right,
            workflow_orientation=_orientation(gel),
        )
        token = st.session_state.lane_token
        accept_lane_event(event)
        if token != st.session_state.lane_token:
            st.rerun()

    with controls_panel:
        boundary = st.session_state.get("lane_boundary_stage")
        if boundary:
            st.subheader("1. First well" if boundary == "first" else "2. Last well")
            st.caption(
                f"Position the {'leftmost' if top_mode else 'topmost'} well and adjust its width."
                if boundary == "first" else
                f"Drag the highlighted lane to the {'rightmost' if top_mode else 'bottommost'} well. Width matches the first."
            )
            st.session_state.boundary_lane_count = st.session_state.lane_boundary_count
            st.number_input(
                "Total lanes (including boundary wells)", min_value=1, value=None, step=1,
                key="boundary_lane_count", on_change=change_boundary_count,
            )
            error = _boundary_count_error()
            if boundary == "first":
                st.button("Confirm first well", key="confirm_first_well", type="primary",
                          on_click=confirm_first_well, disabled=bool(error))
                st.button("Back", key="back_from_first_well", on_click=cancel_boundary_wells)
            else:
                try:
                    _generated_boundary_wells()
                except lane_crop.LaneAdjustmentError as exc:
                    error = str(exc)
                st.button("Generate lanes", key="generate_boundary_lanes", type="primary",
                          on_click=generate_boundary_lanes, disabled=bool(error))
                st.button("Back", key="back_to_first_well", on_click=back_to_first_well)
            st.button("Cancel", key="cancel_boundary_wells", on_click=cancel_boundary_wells)
            if error:
                st.caption(error)
        elif stage == "borders":
            st.subheader("Adjust wells and lanes")
            st.caption(
                ("Drag each lane’s left and right borders. Use its trash button to delete it, "
                 "or Add lane to insert one to the right of the guide. Neighboring lanes cannot overlap.")
                if top_mode else
                ("Drag each lane’s top and bottom borders. Use its trash button to delete it, "
                 "or Add lane to insert one below the guide. Neighboring lanes cannot overlap.")
            )
            count = len(st.session_state.lane_wells)
            st.write(f"{count} lane{'s' if count != 1 else ''} in review")
            if not count:
                st.info("No lanes remain. Choose Add lane, then adjust its borders over the well and bands.")
            st.button(
                "Confirm", key="confirm_lane_borders", type="primary",
                on_click=confirm_lane_borders, disabled=not st.session_state.lane_wells,
            )
            st.button(
                "Add lane", key="add_lane", on_click=add_lane,
                help="Adds a lane in the available space. Nearby borders may move slightly to make room.",
            )
            st.button("Define boundary wells", key="define_boundary_wells", on_click=define_boundary_wells)
            st.caption("Use arrow keys to move a selected handle. Hold Shift to move it farther.")
        else:
            st.subheader("Define bottom of lanes" if top_mode else "Define bottom of lane (right edge)")
            st.caption(
                ("Drag the bottom boundary to choose how much gel to keep. " if top_mode else
                 "Drag the right boundary to choose how much gel to keep. ") +
                "The shaded area will be removed. All wells stay inside the crop."
            )
            st.caption("The crop leaves a small margin around the wells and lanes.")
            st.button(
                "Confirm lanes and crop", key="confirm_lane_crop", type="primary",
                on_click=confirm_lane_crop,
            )
            st.button(
                "Back to lane borders", key="back_to_lane_borders", on_click=back_to_lane_borders,
            )
        if st.session_state.lane_error:
            st.warning(st.session_state.lane_error)
