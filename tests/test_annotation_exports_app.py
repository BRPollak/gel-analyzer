"""Check dependent download controls on a confirmed annotation composition."""

from streamlit.testing.v1 import AppTest


def final_editor():
    return AppTest.from_string('''
from io import BytesIO
from types import SimpleNamespace
from PIL import Image
import streamlit as st
from gel_analyzer.annotation_ui import reset_annotations, show_annotations

if "annotation_stage" not in st.session_state:
    reset_annotations()
    buffer = BytesIO()
    Image.new("RGB", (210, 44), "white").save(buffer, format="PNG")
    st.session_state.annotation_png = buffer.getvalue()
    st.session_state.annotation_dimensions = (210, 44)
    st.session_state.annotation_stage = "final"
    st.session_state.annotation_completed = True
crop = SimpleNamespace(width=30, height=20, crop_box=(0,0,30,20), lanes=((0,0,30,20),))
show_annotations(crop, "my gel.tiff")
''').run()


def test_file_type_updates_resolution_options_and_download_label():
    app = final_editor()
    assert not app.exception
    assert app.selectbox(key="annotation_export_format").value == "PNG"
    assert app.selectbox(key="annotation_export_dpi_PNG").value == 300
    assert app.get("download_button")[0].label == "Download annotated PNG"

    app.selectbox(key="annotation_export_format").select("TIFF").run()
    assert not app.exception
    assert app.selectbox(key="annotation_export_dpi_TIFF").options == ["150", "300", "600", "1200"]
    app.selectbox(key="annotation_export_dpi_TIFF").select(1200).run()
    assert not app.exception
    assert app.get("download_button")[0].label == "Download annotated TIFF"

    app.selectbox(key="annotation_export_format").select("JPEG").run()
    assert app.selectbox(key="annotation_export_dpi_JPEG").options == ["72", "96", "150", "300", "600"]
    assert app.get("download_button")[0].label == "Download annotated JPEG"
    assert any("lossy compression" in caption.value for caption in app.caption)

    app.selectbox(key="annotation_export_format").select("SVG").run()
    assert not app.exception
    resolution = app.selectbox(key="annotation_export_vector_resolution")
    assert resolution.disabled
    assert resolution.value == "Vector · resolution independent"
    assert app.get("download_button")[0].label == "Download annotated SVG"

    app.selectbox(key="annotation_export_format").select("PNG").run()
    assert not app.exception
    assert app.selectbox(key="annotation_export_dpi_PNG").value == 300
