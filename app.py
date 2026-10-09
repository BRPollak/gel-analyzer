"""A session-only TIFF gel viewer with cropping and confirmed orientation."""

from io import BytesIO

import streamlit as st

from gel_analyzer.image_io import (
    GelImage, ImageValidationError, load_tiff, orient_gel_image,
)
from gel_analyzer.orientation import OrientationError


def reset_orientation() -> None:
    """Discard any orientation preview when the upload changes."""
    st.session_state.orientation_preview = None
    st.session_state.orientation_requested = False
    st.session_state.orientation_error = None


def request_orientation() -> None:
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

    st.caption("GEL CROP AND ORIENTATION")
    st.title("Agarose Gel Analyzer")
    st.write(
        "Upload a TIFF to automatically trim the surrounding background, "
        "then rotate and orient the gel before confirming the result."
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
        st.text(f"{gel.filename} · {gel.preview_width:,} × {gel.preview_height:,} pixels")
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
        st.image(
            BytesIO(gel.preview_png),
            # Preserve preview pixels; the browser fits them to the container.
            width=gel.preview_width,
            output_format="PNG",
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
