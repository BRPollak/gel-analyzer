"""Exercise actual Streamlit band-table submission in both workflow axes."""

import pytest
from streamlit.testing.v1 import AppTest


def editor(orientation):
    app = AppTest.from_string('''
from io import BytesIO
from types import SimpleNamespace
from PIL import Image
import streamlit as st
from gel_analyzer.band_ui import show_band_analysis
png = BytesIO()
Image.new("L", (100, 100), 100).save(png, format="PNG")
mode = st.session_state.get("mode", "wells_left")
lanes = ((5, 10, 25, 95),) if mode == "wells_top" else ((10, 5, 95, 25),)
crop = SimpleNamespace(width=100, height=100, lanes=lanes, wells=(),
                       preview_png=png.getvalue(), workflow_orientation=mode)
show_band_analysis(crop, None)
''')
    app.session_state["mode"] = orientation
    return app.run()


@pytest.mark.parametrize("orientation", ["wells_left", "wells_top"])
def test_add_move_remove_manual_band_via_table_submission(orientation):
    app = editor(orientation)
    assert not app.exception
    assert app.session_state["band_data"] == [[]]

    def submit(changes):
        generation = app.session_state["band_editor_generation"]
        app.session_state[f"band_editor_{generation}"] = changes
        app.button(key="apply_band_edits").click().run()
        assert not app.exception
        assert not app.error

    submit({"edited_rows": {}, "added_rows": [{"Lane": 1, "Migration (px)": 50.5}], "deleted_rows": []})
    band = app.session_state["band_data"][0][0]
    assert (band["x"], band["y"]) == ((15, 50.5) if orientation == "wells_top" else (50.5, 15))
    submit({"edited_rows": {"0": {"Migration (px)": 65.5}}, "added_rows": [], "deleted_rows": []})
    assert app.session_state["band_data"][0][0]["position"] == 65.5
    submit({"edited_rows": {}, "added_rows": [], "deleted_rows": [0]})
    assert app.session_state["band_data"] == [[]]


@pytest.mark.parametrize("orientation", ["wells_left", "wells_top"])
def test_invalid_manual_band_table_submission_retains_existing_data(orientation):
    app = editor(orientation)
    app.session_state["band_editor_1"] = {
        "edited_rows": {}, "added_rows": [{"Lane": 1, "Migration (px)": 100}], "deleted_rows": [],
    }
    app.button(key="apply_band_edits").click().run()
    assert not app.exception
    assert app.error and "between" in app.error[0].value
    assert app.session_state["band_data"] == [[]]
