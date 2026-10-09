"""Fit browser previews without resampling source or exported images."""

from pathlib import Path

import streamlit as st


def install_preview_viewport() -> None:
    # This is trusted, bundled UI code only. Never interpolate upload metadata
    # or annotation text into the HTML/JavaScript executed in the host page.
    st.html(
        Path(__file__).with_name("viewport.html").read_text(encoding="utf-8"),
        unsafe_allow_javascript=True,
    )
