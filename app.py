"""Session-only gel orientation, lane detection, manual review, and cropping."""

from io import BytesIO
import math
from uuid import uuid4

from PIL import Image
import streamlit as st

from gel_analyzer.image_io import (
    GelImage, ImageValidationError, load_tiff, orient_gel_image,
)
from gel_analyzer.orientation import OrientationError
from gel_analyzer.well_component import render_well_component
from gel_analyzer.wells import SelectionError, detect_wells, validate_line
from gel_analyzer import lane_review_ui


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
        validate_line(st.session_state.well_points, (gel.preview_width, gel.preview_height))
    except SelectionError:
        return
    st.session_state.well_detection_request = (
        st.session_state.well_token, st.session_state.well_points,
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
    if new_points != st.session_state.well_points:
        st.session_state.well_points = new_points
        st.session_state.well_result = None
        st.session_state.well_error = None
        st.session_state.well_detection_request = None
        lane_review_ui.reset_lane_review()


def start_lane_adjustment() -> None:
    gel = confirmed_gel()
    if gel is not None:
        accept_well_event(
            st.session_state.get(f"well_overlay_{st.session_state.well_token}"), gel,
        )
    lane_review_ui.start_lane_review()


def show_well_selection(gel: GelImage) -> None:
    result = st.session_state.well_result
    st.subheader("Wells and lanes")
    st.caption(
        "Click the top of the first selected well and the bottom of the last selected well, "
        "with the line passing through their centers. Either click order works. "
        "Drag the dots to adjust the dotted line."
    )
    event = render_well_component(
        gel.preview_png, gel.preview_width, gel.preview_height,
        points=st.session_state.well_points,
        wells=[{"bounds": well.bounds, "center": well.center} for well in result.wells] if result else [],
        lanes=result.lanes if result else [],
        editable=st.session_state.well_editing,
        token=st.session_state.well_token,
        key=f"well_overlay_{st.session_state.well_token}",
    )
    accept_well_event(event, gel)
    if result is not None and st.session_state.well_result is None:
        # The event arrived after this component render. Refresh its arguments
        # so an edited candidate cannot leave obsolete outlines on screen.
        st.rerun()
    result = st.session_state.well_result
    if result is not None:
        count = len(result.wells)
        if result.warnings:
            st.write(f"{count} well candidate{'s' if count != 1 else ''} detected; review required.")
            for warning in result.warnings:
                st.warning(warning)
        elif count:
            st.success(f"Detected {count} well{'s' if count != 1 else ''} and {count} horizontal lane{'s' if count != 1 else ''}.")
        else:
            st.warning("No wells found. Move the line through the visible well centers and retry.")
        st.caption("Visible wells do not establish whether a sample was loaded. Numbers run from top to bottom.")
        if count:
            st.button(
                "Adjust lane borders", key="adjust_lane_borders", type="primary",
                on_click=start_lane_adjustment,
            )
        if st.session_state.lane_error:
            st.warning(st.session_state.lane_error)
        st.button(
            "Edit well line", key="edit_well_line", on_click=reset_wells,
            kwargs={"editing": True, "preserve_points": True},
        )
    if st.session_state.well_error:
        st.warning(st.session_state.well_error)
    if st.session_state.well_editing:
        valid = False
        try:
            validate_line(st.session_state.well_points, (gel.preview_width, gel.preview_height))
            valid = True
        except SelectionError as exc:
            st.info(str(exc))
        st.button(
            "Confirm line and detect lanes", key="confirm_well_line", type="primary",
            disabled=not valid, on_click=request_well_detection,
        )
        st.button(
            "Reset points", key="reset_well_line", on_click=reset_wells,
            kwargs={"editing": True},
        )


def reset_orientation() -> None:
    """Discard any orientation preview when the upload changes."""
    st.session_state.orientation_preview = None
    st.session_state.orientation_requested = False
    st.session_state.orientation_error = None
    reset_wells()


def request_orientation() -> None:
    reset_wells()
    st.session_state.orientation_requested = True
    st.session_state.orientation_error = None


def confirm_orientation() -> None:
    """Only an explicit confirmation replaces the current gel image."""
    if st.session_state.orientation_preview is not None:
        st.session_state.gel_image = st.session_state.orientation_preview
        reset_orientation()


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


def main() -> None:
    st.set_page_config(
        page_title="Agarose Gel Analyzer",
        page_icon="🧬",
        layout="centered",
    )
    st.session_state.setdefault("gel_image", None)
    st.session_state.setdefault("upload_error", None)
    st.session_state.setdefault("uploader_generation", 0)
    st.session_state.setdefault("pending_upload", None)
    st.session_state.setdefault("orientation_preview", None)
    st.session_state.setdefault("orientation_requested", False)
    st.session_state.setdefault("orientation_error", None)
    if "well_token" not in st.session_state:
        reset_wells()
    if "lane_stage" not in st.session_state:
        lane_review_ui.reset_lane_review()

    st.caption("GEL ORIENTATION AND LANES")
    st.title("Agarose Gel Analyzer")
    st.write(
        "Upload a TIFF to automatically trim the surrounding background, "
        "then confirm its orientation, detect and adjust the lanes, and choose the final crop."
    )

    uploader_key = f"gel_upload_{st.session_state.uploader_generation}"
    st.file_uploader(
        "Choose a gel image",
        type=["tif", "tiff"],
        accept_multiple_files=False,
        key=uploader_key,
        on_change=read_upload,
        args=(uploader_key,),
        help="Upload one single-image TIFF (.tif or .tiff). Choose another file to replace it.",
    )
    st.button(
        "Clear image",
        on_click=clear_image,
        disabled=st.session_state.get(uploader_key) is None,
    )
    st.caption("Images stay in this session only. Refreshing the page clears your image.")

    # Replace this same slot immediately, so neither the previous upload nor an
    # uncropped new image is shown while the new source is being processed.
    preview_slot = st.empty()
    if st.session_state.pending_upload is not None:
        preview_slot.info("Preparing gel preview…")
        data, filename = st.session_state.pending_upload
        st.session_state.pending_upload = None
        try:
            st.session_state.gel_image = load_tiff(data, filename)
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
            except OrientationError as exc:
                st.session_state.orientation_error = str(exc)

    request = st.session_state.well_detection_request
    st.session_state.well_detection_request = None
    if request is not None and confirmed_gel() is not None:
        token, points = request
        if token == st.session_state.well_token and points == st.session_state.well_points:
            gel = confirmed_gel()
            st.session_state.well_result = None
            st.session_state.well_error = None
            lane_review_ui.reset_lane_review()
            with st.spinner("Detecting wells and refining lane boundaries…"):
                try:
                    with Image.open(BytesIO(gel.preview_png)) as analysis_source:
                        result = detect_wells(analysis_source, points)
                    st.session_state.well_result = result
                    st.session_state.well_editing = bool(result.warnings or not result.wells)
                except (SelectionError, ValueError) as exc:
                    st.session_state.well_error = str(exc)
                    st.session_state.well_editing = True

    with preview_slot.container():
        if st.session_state.upload_error:
            st.error(st.session_state.upload_error)
            return

        current_gel: GelImage | None = st.session_state.gel_image
        if current_gel is None:
            st.info("Your gel preview will appear here.", icon="🖼️")
            return

        pending: GelImage | None = st.session_state.orientation_preview
        gel = pending if pending is not None else current_gel
        st.divider()
        st.subheader("Gel preview")
        final_crop = st.session_state.lane_crop if st.session_state.lane_stage == "cropped" else None
        visible_width = final_crop.width if final_crop else gel.preview_width
        visible_height = final_crop.height if final_crop else gel.preview_height
        st.text(f"{gel.filename} · {visible_width:,} × {visible_height:,} pixels")
        if gel.orientation is not None:
            if pending is not None:
                st.caption(
                    "Rotated and straightened, flipped vertically, and cropped to the gel outline. "
                    "The original left side is now at the top. Confirm to accept this image."
                )
            else:
                st.caption("Orientation confirmed. The original left side is at the top.")
        elif gel.auto_cropped:
            st.caption("Automatically cropped with a small margin around the gel.")
        else:
            st.caption("Gel boundary uncertain; showing the full image to preserve the gel.")
        if confirmed_gel() is not None and st.session_state.lane_stage is not None:
            lane_review_ui.show_lane_review(current_gel)
            st.button(
                "Edit well line", key="edit_well_line", on_click=reset_wells,
                kwargs={"editing": True, "preserve_points": True},
            )
        elif confirmed_gel() is not None and (
            st.session_state.well_editing or st.session_state.well_result is not None
        ):
            show_well_selection(current_gel)
        else:
            st.image(
                BytesIO(gel.preview_png),
                # Preserve preview pixels; the browser fits them to the container.
                width=gel.preview_width,
                output_format="PNG",
            )
            if confirmed_gel() is not None:
                st.button(
                    "Define wells", key="define_wells", on_click=reset_wells,
                    kwargs={"editing": True},
                )
        if st.session_state.orientation_error:
            st.error(st.session_state.orientation_error)
        if current_gel.orientation is None:
            st.button(
                "Rotate and Orient",
                key="rotate_and_orient",
                on_click=request_orientation,
                help="Fit the gel outline, straighten and rotate it counterclockwise, flip vertically, then crop.",
            )
            if pending is not None:
                st.button(
                    "Confirm",
                    key="confirm_orientation",
                    type="primary",
                    on_click=confirm_orientation,
                )


if __name__ == "__main__":
    main()
