"""Version 1: a session-only viewer for one unmodified PNG gel image."""

from io import BytesIO

import streamlit as st

from gel_analyzer.image_io import GelImage, ImageValidationError, load_png


def clear_image() -> None:
    """Reset the source and create a fresh uploader on the next rerun."""
    st.session_state.gel_image = None
    st.session_state.upload_error = None
    st.session_state.uploader_generation += 1


def read_upload(uploader_key: str) -> None:
    """Replace the source on every selection, including removal or invalid input."""
    st.session_state.gel_image = None
    st.session_state.upload_error = None
    uploaded_file = st.session_state.get(uploader_key)
    if uploaded_file is None:
        return
    try:
        st.session_state.gel_image = load_png(
            uploaded_file.getvalue(), uploaded_file.name
        )
    except ImageValidationError as exc:
        st.session_state.upload_error = str(exc)


def main() -> None:
    st.set_page_config(
        page_title="Agarose Gel Analyzer",
        page_icon="🧬",
        layout="centered",
    )
    st.session_state.setdefault("gel_image", None)
    st.session_state.setdefault("upload_error", None)
    st.session_state.setdefault("uploader_generation", 0)

    st.caption("VERSION 1 · UPLOAD & DISPLAY")
    st.title("Agarose Gel Analyzer")
    st.write("Upload a gel image to view it at its original proportions.")

    uploader_key = f"gel_upload_{st.session_state.uploader_generation}"
    st.file_uploader(
        "Choose a gel image",
        type=["png"],
        accept_multiple_files=False,
        key=uploader_key,
        on_change=read_upload,
        args=(uploader_key,),
        help="Upload one static PNG. Choose another file to replace it.",
    )
    st.button(
        "Clear image",
        on_click=clear_image,
        disabled=st.session_state.get(uploader_key) is None,
    )
    st.caption("Images stay in this session only. Refreshing the page clears your image.")

    if st.session_state.upload_error:
        st.error(st.session_state.upload_error)

    gel: GelImage | None = st.session_state.gel_image
    if gel is None:
        if not st.session_state.upload_error:
            st.info("Your gel preview will appear here.", icon="🖼️")
        return

    st.divider()
    st.subheader("Gel preview")
    st.text(f"{gel.filename} · {gel.width:,} × {gel.height:,} pixels")
    st.image(
        BytesIO(gel.source_bytes),
        # Explicit source width prevents Streamlit's implicit 1460 px resampling.
        # The browser still caps the displayed width to the available space.
        width=gel.width,
        output_format="PNG",
    )


if __name__ == "__main__":
    main()
