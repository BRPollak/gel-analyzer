"""Gel preparation, orientation-aware analysis, and annotation."""

from dataclasses import replace
from io import BytesIO
import math
from uuid import uuid4

from PIL import Image
import streamlit as st

from gel_analyzer.image_io import (
    GelImage, ImageValidationError, decode_source_image, load_image, orient_gel_image,
)
from gel_analyzer.orientation import GelRectangle, OrientationError, rectangle_from_selection
from gel_analyzer.well_component import render_well_component
from gel_analyzer.wells import SelectionError, detect_wells, validate_line
from gel_analyzer import annotation_ui, lane_review_ui, orientation_ui
from gel_analyzer.viewport import install_preview_viewport


def reset_wells(*, editing: bool = False, preserve_points: bool = False) -> None:
    """Invalidate both geometry and in-flight events, without touching pixels."""
    points = st.session_state.get("well_points", ()) if preserve_points else ()
    st.session_state.well_points = points
    st.session_state.well_result = None
    st.session_state.well_error = None
    st.session_state.well_editing = editing
    st.session_state.well_token = uuid4().hex
    st.session_state.well_revision = 0
    st.session_state.well_detection_request = None
    lane_review_ui.reset_lane_review()


def confirmed_gel() -> GelImage | None:
    gel = st.session_state.gel_image
    if (
        gel is not None and gel.orientation is not None
        and st.session_state.orientation_preview is None
        and not st.session_state.orientation_requested
    ):
        return gel
    return None


def request_well_detection() -> None:
    """Capture only an explicitly confirmed, valid guide for this image."""
    gel = confirmed_gel()
    if gel is None or not st.session_state.well_editing:
        return
    # A fast confirmation can arrive with the pointer-up widget value before
    # the preceding script run has consumed it. Confirm that latest value, not
    # the earlier guide snapshot, so an immediate retry cannot lose its result.
    accept_well_event(
        st.session_state.get(f"well_overlay_{st.session_state.well_token}"), gel,
    )
    try:
        validate_line(st.session_state.well_points, (gel.preview_width, gel.preview_height), **axis_options(gel))
    except SelectionError:
        return
    st.session_state.well_detection_request = (
        st.session_state.well_token, st.session_state.well_points,
        st.session_state.well_expected_count,
    )


def accept_well_event(event: object, gel: GelImage) -> None:
    """Ignore stale/malformed iframe events; retain editable invalid lines."""
    if not st.session_state.well_editing or not isinstance(event, dict):
        return
    revision = event.get("revision")
    if (
        event.get("token") != st.session_state.well_token
        or type(revision) is not int
        or revision <= st.session_state.well_revision
    ):
        return
    points = event.get("points")
    if not isinstance(points, (list, tuple)) or len(points) > 2:
        return
    for point in points:
        if not isinstance(point, (list, tuple)) or len(point) != 2:
            return
        if not all(type(value) in (int, float) and math.isfinite(value) for value in point):
            return
        if not (0 <= point[0] <= gel.preview_width and 0 <= point[1] <= gel.preview_height):
            return
    st.session_state.well_revision = revision
    new_points = tuple(tuple(float(value) for value in point) for point in points)
    if len(new_points) == 2:
        new_points = (new_points[0], (new_points[1][0], new_points[0][1])
                      if gel.workflow_orientation == "wells_top" else (new_points[0][0], new_points[1][1]))
    if new_points != st.session_state.well_points:
        st.session_state.well_points = new_points
        st.session_state.well_result = None
        st.session_state.well_error = None
        st.session_state.well_detection_request = None
        lane_review_ui.reset_lane_review()


def leave_well_selection() -> None:
    """Retain a completed pointer edit even when Back arrives in the same run."""
    gel = confirmed_gel()
    if gel is not None:
        accept_well_event(
            st.session_state.get(f"well_overlay_{st.session_state.well_token}"), gel,
        )
    reset_wells(preserve_points=True)


def start_lane_adjustment() -> None:
    gel = confirmed_gel()
    if gel is not None:
        accept_well_event(
            st.session_state.get(f"well_overlay_{st.session_state.well_token}"), gel,
        )
    lane_review_ui.start_lane_review()


def confirm_detected_lanes() -> None:
    result = st.session_state.well_result
    required = st.session_state.well_expected_count
    if required is not None and (result is None or len(result.wells) != required or len(result.lanes) != required):
        return
    start_lane_adjustment()
    lane_review_ui.confirm_lane_borders()


def change_expected_well_count() -> None:
    """Keep the latest guide while invalidating detection for a new count."""
    count = st.session_state.expected_well_count
    if count == st.session_state.well_expected_count:
        return
    gel = confirmed_gel()
    if gel is not None:
        accept_well_event(
            st.session_state.get(f"well_overlay_{st.session_state.well_token}"), gel,
        )
    st.session_state.well_expected_count = count
    reset_wells(editing=gel is not None, preserve_points=True)


def show_expected_well_count() -> None:
    # Preserve the preference when Streamlit cleans up the hidden widget during
    # result review, lane adjustment, or navigation out of the guide editor.
    st.session_state.expected_well_count = st.session_state.well_expected_count
    st.number_input(
        "Number of wells (optional)", min_value=1, value=None, step=1,
        placeholder="Automatic", key="expected_well_count",
        on_change=change_expected_well_count,
        help="Enter the exact number of wells crossed by the guide. The app will prepare that many wells and lanes and tell you when positions were inferred. Leave blank for automatic counting.",
    )


def show_well_selection(gel: GelImage, image_panel, controls_panel) -> None:
    result = st.session_state.well_result
    with image_panel:
        event = render_well_component(
            gel.preview_png, gel.preview_width, gel.preview_height,
            points=st.session_state.well_points,
            wells=[{"bounds": well.bounds, "center": well.center} for well in result.wells] if result else [],
            lanes=result.lanes if result else [],
            editable=st.session_state.well_editing,
            token=st.session_state.well_token,
            key=f"well_overlay_{st.session_state.well_token}",
            **axis_options(gel),
        )
        accept_well_event(event, gel)
        if result is not None and st.session_state.well_result is None:
            # The event arrived after this component render. Refresh its arguments
            # so an edited candidate cannot leave obsolete outlines on screen.
            st.rerun()
    with controls_panel:
        st.subheader("Define wells")
        result = st.session_state.well_result
        if result is not None:
            count = len(result.wells)
            direction = "vertical" if gel.workflow_orientation == "wells_top" else "horizontal"
            count_guided = st.session_state.well_expected_count is not None
            matches_count = not count_guided or count == len(result.lanes) == st.session_state.well_expected_count
            action = "Prepared" if count_guided else "Detected"
            st.write(f"{action} {count} well{'s' if count != 1 else ''} and {count} {direction} lane{'s' if count != 1 else ''}.")
            if not matches_count:
                st.warning(
                    f"This earlier result does not match the required {st.session_state.well_expected_count} wells. "
                    "Choose Back, then confirm the guide again to fit the exact count."
                )
            if count_guided:
                for message in result.warnings:
                    st.warning(message)
            st.button(
                "Confirm", key="confirm_detected_lanes", type="primary",
                on_click=confirm_detected_lanes, disabled=not count or not matches_count,
            )
            st.button("Adjust", key="adjust_lane_borders", on_click=start_lane_adjustment)
            if st.session_state.lane_error:
                st.warning(st.session_state.lane_error)
            st.button(
                "Back", key="edit_well_line", on_click=reset_wells,
                kwargs={"editing": True, "preserve_points": True},
            )
            return
        st.caption(
            "Click the left and right ends of the well range. Drag either dot to move or extend the horizontal guide."
            if gel.workflow_orientation == "wells_top" else "Click the top and bottom of the well range. "
            "Drag either dot to move or extend the vertical guide."
        )
        if st.session_state.well_error:
            st.warning(st.session_state.well_error)
        if st.session_state.well_editing:
            show_expected_well_count()
            valid = False
            try:
                validate_line(st.session_state.well_points, (gel.preview_width, gel.preview_height), **axis_options(gel))
                valid = True
            except SelectionError as exc:
                st.info(str(exc))
            st.button(
                "Confirm", key="confirm_well_line", type="primary",
                disabled=not valid, on_click=request_well_detection,
            )
            st.button(
                "Back", key="back_from_well_line", on_click=leave_well_selection,
            )


def axis_options(gel: GelImage) -> dict:
    """Keep the existing call path unchanged for the default workflow."""
    return {"workflow_orientation": gel.workflow_orientation} if gel.workflow_orientation == "wells_top" else {}


def change_workflow_orientation() -> None:
    """Stage a workflow change; accepted analysis survives until confirmation."""
    gel = st.session_state.gel_image
    mode = st.session_state.workflow_orientation_choice
    if gel is None or gel.orientation is not None or mode == gel.workflow_orientation:
        return
    orientation_ui.accept_orientation_event(
        st.session_state.get(f"orientation_overlay_{st.session_state.orientation_token}"), gel,
    )
    st.session_state.gel_image = replace(gel, workflow_orientation=mode)
    pending = st.session_state.orientation_preview
    st.session_state.orientation_preview = None
    st.session_state.orientation_error = None
    # Reuse the reviewed outline, without running edge detection again. In the
    # manual editor, keep its live rectangle and let Preview apply the new mode.
    if pending is not None and not st.session_state.orientation_manual:
        if not getattr(pending.orientation, "outline_complete", True):
            tilt = pending.orientation.counterclockwise_degrees - (
                0 if pending.workflow_orientation == "wells_top" else 90
            )
            previous = st.session_state.get("orientation_previous_gel")
            if (previous is not None and previous.workflow_orientation == mode
                    and previous.source_bytes == gel.source_bytes and previous.crop_box == gel.crop_box
                    and not getattr(previous.orientation, "outline_complete", True)
                    and math.isclose(tilt, previous.orientation.counterclockwise_degrees
                                     - (0 if mode == "wells_top" else 90),
                                     rel_tol=0, abs_tol=1e-10)):
                # Undoing the selector change restores the accepted object.
                # Subtracting a quarter turn can lose a few floating-point bits;
                # that must not turn an unchanged preview into an analysis reset.
                st.session_state.orientation_preview = previous
                return
            st.session_state.orientation_preview = orient_gel_image(
                st.session_state.gel_image, fallback_angle_degrees=tilt,
                supported_edges=pending.orientation.supported_edges,
            )
            return
        corners = pending.orientation.corners
        rectangle = GelRectangle(corners, math.dist(corners[0], corners[1]),
                                 math.dist(corners[0], corners[3]),
                                 math.degrees(math.atan2(corners[1][1] - corners[0][1],
                                                        corners[1][0] - corners[0][0])))
        st.session_state.orientation_preview = orient_gel_image(st.session_state.gel_image, rectangle)


def show_workflow_orientation(gel: GelImage) -> None:
    st.session_state.workflow_orientation_choice = gel.workflow_orientation
    st.selectbox(
        "Workflow orientation", ["wells_left", "wells_top"],
        format_func=lambda mode: "Wells at top" if mode == "wells_top" else "Wells at left",
        key="workflow_orientation_choice", on_change=change_workflow_orientation,
        help="Choose lane and migration directions independently of the manual image rotation controls.",
    )
    st.caption("Vertical lanes · bands migrate downward" if gel.workflow_orientation == "wells_top"
               else "Horizontal lanes · bands migrate to the right")
    previous = st.session_state.get("orientation_previous_gel")
    pending = st.session_state.orientation_preview
    if previous is not None and (previous.workflow_orientation != gel.workflow_orientation
                                 or pending is not None and pending != previous):
        st.warning("Confirming this change resets the well selection, lanes, crop, ladder markers, and annotations. "
                   "Return to analysis keeps your existing work.")


def keep_displayed_orientation() -> None:
    gel = st.session_state.gel_image
    if gel is None or gel.orientation is not None or gel.workflow_orientation != "wells_top":
        return
    rectangle = rectangle_from_selection(dict(cx=gel.preview_width / 2, cy=gel.preview_height / 2,
                                             width=gel.preview_width, height=gel.preview_height,
                                             angle_degrees=0), (gel.preview_width, gel.preview_height))
    st.session_state.orientation_preview = orient_gel_image(gel, rectangle)
    st.session_state.orientation_preview_method = "manual"
    st.session_state.orientation_error = None


def reset_orientation_preview() -> None:
    """Close orientation review without discarding a retained analysis."""
    st.session_state.orientation_preview = None
    st.session_state.orientation_requested = False
    st.session_state.orientation_error = None
    st.session_state.orientation_preview_method = None
    st.session_state.orientation_previous_gel = None
    orientation_ui.reset_manual_orientation()


def reset_orientation() -> None:
    """Discard orientation and downstream geometry when the source changes."""
    reset_orientation_preview()
    st.session_state.well_expected_count = None
    reset_wells()


def request_orientation() -> None:
    orientation_ui.reset_manual_orientation()
    if st.session_state.get("orientation_previous_gel") is None:
        st.session_state.well_expected_count = None
        reset_wells()
    st.session_state.orientation_requested = True
    st.session_state.orientation_error = None
    st.session_state.orientation_preview_method = None


def confirm_orientation() -> None:
    """Only an explicit confirmation replaces the current gel image."""
    preview = st.session_state.orientation_preview
    if preview is None:
        return
    previous = st.session_state.get("orientation_previous_gel")
    if previous is not None and preview == previous:
        # Preserve the original object's identity, which binds lane geometry
        # to its source, when the user only inspected an existing orientation.
        st.session_state.gel_image = previous
        reset_orientation_preview()
    else:
        st.session_state.gel_image = preview
        reset_orientation()


def keep_previous_orientation() -> None:
    previous = st.session_state.get("orientation_previous_gel")
    if previous is not None:
        st.session_state.gel_image = previous
        reset_orientation_preview()


def clear_image() -> None:
    """Reset the source and create a fresh uploader on the next rerun."""
    st.session_state.gel_image = None
    st.session_state.upload_error = None
    st.session_state.pending_upload = None
    reset_orientation()
    st.session_state.uploader_generation += 1


def read_upload(uploader_key: str) -> None:
    """Stage the source so main can hide the old preview before processing."""
    st.session_state.gel_image = None
    st.session_state.upload_error = None
    st.session_state.pending_upload = None
    reset_orientation()
    uploaded_file = st.session_state.get(uploader_key)
    if uploaded_file is None:
        return
    st.session_state.pending_upload = (uploaded_file.getvalue(), uploaded_file.name)


def workflow_stage() -> int | None:
    if st.session_state.gel_image is None:
        return None
    if confirmed_gel() is not None:
        if st.session_state.lane_stage == "cropped":
            return 3 if st.session_state.annotation_stage == "final" else 2
        return 1
    return 0


def navigate_workflow(stage: int) -> None:
    """Return to a reached stage, retaining edits before changing event identities."""
    active = workflow_stage()
    if active is None or stage not in range(active + 1):
        return
    gel = confirmed_gel()
    if gel is not None:
        accept_well_event(st.session_state.get(f"well_overlay_{st.session_state.well_token}"), gel)
    lane_review_ui._consume_latest_event()
    annotation_ui.consume_latest_event()
    if stage == 0 and gel is not None:
        # Recreate the first crop directly from the original image. Never
        # resample the accepted orientation or rerun automatic crop detection.
        preview = BytesIO()
        with Image.open(BytesIO(gel.source_bytes)) as source:
            source = decode_source_image(source)
            source.crop(gel.crop_box).save(preview, format="PNG")
        st.session_state.gel_image = replace(gel, preview_png=preview.getvalue(), orientation=None)
        st.session_state.orientation_previous_gel = gel
        st.session_state.orientation_preview = gel
        st.session_state.orientation_preview_method = "confirmed"
        st.session_state.orientation_requested = False
        st.session_state.orientation_error = None
        orientation_ui.reset_manual_orientation()
        # Suspend downstream state until a changed orientation is accepted.
        # Events from the editors being removed must never modify that state.
        for editor in ("well", "lane", "annotation"):
            st.session_state[f"{editor}_token"] = uuid4().hex
            st.session_state[f"{editor}_revision"] = 0
        st.session_state.well_detection_request = None
    elif stage == 1:
        if st.session_state.lane_stage in ("extent", "cropped"):
            lane_review_ui.back_to_lane_borders()
        elif st.session_state.lane_stage is None and st.session_state.well_result is None:
            st.session_state.well_editing = True
    elif stage == 2 and st.session_state.annotation_stage != "lanes":
        annotation_ui.edit_annotations()


def show_workflow_progress() -> None:
    """Native keyboard-accessible controls for revisiting reached stages."""
    active = workflow_stage()
    with st.container(key="gel_progress"):
        columns = st.columns([1, 1.35, 1.15, 1], gap="small")
        for index, (column, label) in enumerate(zip(columns, ("Orient", "Define lanes", "Annotate", "Export"))):
            reached = active is not None and index <= active
            marker = "✓" if active is not None and index < active else str(index + 1)
            with column:
                st.button(
                    f"{marker} · {label}", key=f"workflow_step_{index}",
                    type="primary" if index == active else "secondary",
                    disabled=not reached, on_click=navigate_workflow, args=(index,),
                    width="stretch",
                    help=f"Return to {label.lower()}" if reached else f"Complete the earlier steps to {label.lower()}.",
                )


def main() -> None:
    st.set_page_config(
        page_title="Agarose Gel Analyzer",
        page_icon="🧬",
        layout="wide",
    )
    st.set_option("client.toolbarMode", "minimal")
    install_preview_viewport()
    st.session_state.setdefault("gel_image", None)
    st.session_state.setdefault("upload_error", None)
    st.session_state.setdefault("uploader_generation", 0)
    st.session_state.setdefault("pending_upload", None)
    st.session_state.setdefault("orientation_preview", None)
    st.session_state.setdefault("orientation_requested", False)
    st.session_state.setdefault("orientation_error", None)
    st.session_state.setdefault("orientation_preview_method", None)
    st.session_state.setdefault("orientation_previous_gel", None)
    st.session_state.setdefault("well_expected_count", None)
    if "well_token" not in st.session_state:
        reset_wells()
    if "orientation_token" not in st.session_state:
        orientation_ui.reset_manual_orientation()
    if "lane_stage" not in st.session_state:
        lane_review_ui.reset_lane_review()

    with st.container(key="gel_header"):
        st.title("Agarose Gel Analyzer")
        st.caption("Orient your gel, define lanes, crop, and annotate.")
    progress_slot = st.empty()

    uploader_key = f"gel_upload_{st.session_state.uploader_generation}"
    has_image = st.session_state.gel_image is not None or st.session_state.pending_upload is not None
    upload_panel = st.popover("Change image") if has_image else st.container(key="gel_upload_start")
    with upload_panel:
        if not has_image:
            st.subheader("Start with a gel image")
        st.file_uploader(
            "Open a gel image",
            type=["tif", "tiff", "png", "jpeg", "jpg"],
            accept_multiple_files=False,
            key=uploader_key,
            on_change=read_upload,
            args=(uploader_key,),
            help="Upload one TIFF, PNG, or JPEG (.tif, .tiff, .png, .jpeg, or .jpg). Choose another file to replace it.",
        )
        if has_image:
            st.button("Clear image", key="clear_image", on_click=clear_image)
        st.caption("TIFF, PNG, or JPEG files (.tif, .tiff, .png, .jpeg, or .jpg).")

    # Replace this same slot immediately, so neither the previous upload nor an
    # uncropped new image is shown while the new source is being processed.
    preview_slot = st.empty()
    if st.session_state.pending_upload is not None:
        preview_slot.info("Preparing gel preview…")
        data, filename = st.session_state.pending_upload
        st.session_state.pending_upload = None
        try:
            st.session_state.gel_image = load_image(data, filename)
        except ImageValidationError as exc:
            st.session_state.upload_error = str(exc)

    if st.session_state.orientation_requested:
        st.session_state.orientation_requested = False
        st.session_state.orientation_preview = None
        if st.session_state.gel_image is not None:
            preview_slot.info("Fitting the gel outline and preparing its orientation…")
            try:
                st.session_state.orientation_preview = orient_gel_image(
                    st.session_state.gel_image
                )
                st.session_state.orientation_preview_method = "automatic"
            except OrientationError as exc:
                st.session_state.orientation_error = str(exc)
                orientation_ui.start_manual_orientation()

    request = st.session_state.well_detection_request
    st.session_state.well_detection_request = None
    if request is not None and confirmed_gel() is not None:
        token, points, expected_count = request
        if (
            token == st.session_state.well_token
            and points == st.session_state.well_points
            and expected_count == st.session_state.well_expected_count
        ):
            gel = confirmed_gel()
            st.session_state.well_result = None
            st.session_state.well_error = None
            lane_review_ui.reset_lane_review()
            with st.spinner("Detecting wells and refining lane boundaries…"):
                try:
                    with Image.open(BytesIO(gel.preview_png)) as analysis_source:
                        result = (
                            detect_wells(analysis_source, points, expected_count=expected_count, **axis_options(gel))
                            if expected_count is not None else detect_wells(analysis_source, points, **axis_options(gel))
                        )
                    st.session_state.well_result = result
                    st.session_state.well_editing = False
                except (SelectionError, ValueError) as exc:
                    st.session_state.well_error = str(exc)
                    st.session_state.well_editing = True

    with progress_slot.container():
        show_workflow_progress()

    with preview_slot.container():
        if st.session_state.upload_error:
            st.error(st.session_state.upload_error)
            return

        current_gel: GelImage | None = st.session_state.gel_image
        if current_gel is None:
            return

        pending: GelImage | None = st.session_state.orientation_preview
        gel = pending if pending is not None and not st.session_state.orientation_manual else current_gel
        final_crop = (
            st.session_state.lane_crop
            if confirmed_gel() is not None and st.session_state.lane_stage == "cropped" else None
        )
        visible_width = final_crop.width if final_crop else gel.preview_width
        visible_height = final_crop.height if final_crop else gel.preview_height
        st.text(f"{gel.filename} · {visible_width:,} × {visible_height:,} pixels")
        if final_crop is not None:
            # The annotation editor owns its preview and controls, including
            # its responsive in-component layout.
            with st.expander("Revise analysis"):
                st.button(
                    "Revise lanes and crop", key="revise_lane_crop",
                    on_click=lane_review_ui.back_to_lane_borders,
                )
                st.button(
                    "Edit well line", key="edit_well_line", on_click=reset_wells,
                    kwargs={"editing": True, "preserve_points": True},
                )
            lane_review_ui.show_lane_review(current_gel)
            return

        with st.container(key="gel_workspace"):
            image_panel, controls_column = st.columns([3.2, 1.15], gap="large")
            with controls_column:
                controls_panel = st.container(border=True, key="gel_workflow_controls")
            if current_gel.orientation is None:
                with controls_panel:
                    show_workflow_orientation(current_gel)
            if st.session_state.orientation_manual:
                orientation_ui.show_manual_orientation(
                    current_gel, image_panel, controls_panel, request_orientation,
                )
            elif confirmed_gel() is not None and st.session_state.lane_stage is not None:
                lane_review_ui.show_lane_review(
                    current_gel, image_panel=image_panel, controls_panel=controls_panel,
                )
                with controls_panel:
                    if st.session_state.lane_stage == "borders":
                        st.button(
                            "Edit well line", key="edit_well_line", on_click=reset_wells,
                            kwargs={"editing": True, "preserve_points": True},
                        )
                        st.button("Back", key="back_to_well_review", on_click=lane_review_ui.back_to_well_review)
            elif confirmed_gel() is not None and (
                st.session_state.well_editing or st.session_state.well_result is not None
            ):
                show_well_selection(current_gel, image_panel, controls_panel)
            else:
                with image_panel:
                    st.image(
                        BytesIO(gel.preview_png),
                        # Preserve preview pixels; the browser fits them to the container.
                        width=gel.preview_width,
                        output_format="PNG",
                    )
                with controls_panel:
                    st.subheader("Define wells" if confirmed_gel() is not None else "Rotate and orient")
                    if gel.orientation is not None:
                        if pending is not None:
                            if not getattr(gel.orientation, "outline_complete", True):
                                sides = ", ".join(gel.orientation.supported_edges)
                                st.info(
                                    f"Orientation uses the clearly detected sides{': ' + sides if sides else ''}. "
                                    "The full initial crop is retained because the complete gel outline "
                                    "is not visible. Inspect the preview, then confirm or adjust manually."
                                )
                            else:
                                st.caption(
                                    "The gel has been straightened and cropped with its top edge retained. Inspect the preview, then confirm or adjust the outline."
                                    if gel.workflow_orientation == "wells_top" else "The gel has been straightened, rotated, flipped vertically, "
                                    "and cropped. Inspect the result, then confirm this preview "
                                    "or adjust the outline manually."
                                )
                        else:
                            st.caption("Orientation confirmed. Define the wells to detect your lanes.")
                    elif gel.auto_cropped:
                        st.caption("The gel has been cropped automatically. Orient it to begin defining lanes.")
                    else:
                        st.caption("Orient the image to begin. The full image is preserved until the gel boundary is found.")
                    if confirmed_gel() is not None:
                        st.button(
                            "Define wells", key="define_wells", type="primary", on_click=reset_wells,
                            kwargs={"editing": True, "preserve_points": True},
                        )
                    if st.session_state.orientation_error:
                        st.error(st.session_state.orientation_error)
                    if current_gel.orientation is None:
                        if pending is not None:
                            st.button(
                                "Confirm orientation and reset analysis" if st.session_state.orientation_previous_gel is not None
                                and pending != st.session_state.orientation_previous_gel else "Confirm",
                                key="confirm_orientation", type="primary",
                                on_click=confirm_orientation,
                            )
                        st.button(
                            "Adjust outline manually" if pending is not None else "Draw outline manually",
                            key="adjust_orientation_manually",
                            on_click=orientation_ui.start_manual_orientation,
                        )
                        if pending is None and current_gel.workflow_orientation == "wells_top":
                            st.button("Keep displayed orientation", key="keep_displayed_orientation",
                                      on_click=keep_displayed_orientation,
                                      help="Use the displayed crop as it is, without rotating or flipping its pixels.")
                        if pending is None or st.session_state.orientation_preview_method in ("manual", "confirmed"):
                            st.button(
                                "Automatic orientation" if pending is not None else "Rotate and Orient",
                                key="rotate_and_orient",
                                type="secondary" if pending is not None else "primary",
                                on_click=request_orientation,
                                help="Straighten using the visible gel edges, retaining its top edge. Crop only when the complete outline is clear."
                                if current_gel.workflow_orientation == "wells_top" else
                                "Straighten using the visible gel edges, rotate counterclockwise and flip vertically. Crop only when the complete outline is clear.",
                            )
            if st.session_state.orientation_previous_gel is not None:
                with controls_panel:
                    st.button(
                        "Return to analysis", key="keep_previous_orientation",
                        on_click=keep_previous_orientation,
                        help="Keep the previous orientation and all analysis edits.",
                    )


if __name__ == "__main__":
    main()
