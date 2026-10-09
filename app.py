"""A session-only TIFF gel viewer with conservative automatic cropping."""

from io import BytesIO

import streamlit as st

from gel_analyzer.image_io import GelImage, ImageValidationError, load_tiff


def clear_image() -> None:
    """Reset the source and create a fresh uploader on the next rerun."""
    st.session_state.gel_image = None
    st.session_state.upload_error = None
    st.session_state.pending_upload = None
    st.session_state.uploader_generation += 1


def read_upload(uploader_key: str) -> None:
    """Stage the source so main can hide the old preview before processing."""
    st.session_state.gel_image = None
    st.session_state.upload_error = None
    st.session_state.pending_upload = None
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

    st.caption("AUTOMATIC GEL CROP")
    st.title("Agarose Gel Analyzer")
    st.write(
        "Upload a TIFF to automatically trim the surrounding background, "
        "keeping a small margin around the gel."
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

    with preview_slot.container():
        if st.session_state.upload_error:
            st.error(st.session_state.upload_error)
            return

        gel: GelImage | None = st.session_state.gel_image
        if gel is None:
            st.info("Your gel preview will appear here.", icon="🖼️")
            return

        st.divider()
        st.subheader("Gel preview")
        st.text(f"{gel.filename} · {gel.preview_width:,} × {gel.preview_height:,} pixels")
        if gel.auto_cropped:
            st.caption("Automatically cropped with a small margin around the gel.")
        else:
            st.caption("Gel boundary uncertain; showing the full image to preserve the gel.")
        st.image(
            BytesIO(gel.preview_png),
            # Preserve preview pixels; the browser fits them to the container.
            width=gel.preview_width,
            output_format="PNG",
        )


if __name__ == "__main__":
    main()
