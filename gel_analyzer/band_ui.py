"""Review, edit, size, and export bands along the selected migration axis."""

from copy import deepcopy
import csv
from hashlib import sha256
from io import BytesIO, StringIO

import streamlit as st
from PIL import ImageDraw

from .bands import crop_band_candidates, validate_band_rows, fit_ladder, band_measurements, band_review_image


def show_band_analysis(crop, ladder) -> None:
    orientation = getattr(crop, "workflow_orientation", "wells_left")
    geometry = (sha256(crop.preview_png).hexdigest(), tuple(crop.lanes), orientation)
    changed = st.session_state.get("band_geometry") is not None and st.session_state.band_geometry != geometry
    if st.session_state.get("band_geometry") != geometry or st.session_state.get("band_data") is None:
        st.session_state.band_data = deepcopy(crop_band_candidates(crop.preview_png, tuple(crop.lanes), orientation, tuple(crop.wells)))
        st.session_state.band_geometry = geometry
        st.session_state.band_editor_generation = st.session_state.get("band_editor_generation", 0) + 1
    with st.expander("Review bands and estimate sizes"):
        if changed:
            st.info("The crop or lanes changed. Band proposals were recalculated; review their positions again.")
        st.caption("Automatic bands are proposals. Review each lane; add, remove, or move bands by editing their migration position. "
                   + ("Positions are measured downward from the crop's top edge." if orientation == "wells_top"
                      else "Positions are measured rightward from the crop's left edge."))
        if st.button("Detect bands again", key="redetect_bands"):
            st.session_state.band_data = None
            st.rerun()
        rows = [{"Lane": lane + 1, "Migration (px)": band["position"]}
                for lane, bands in enumerate(st.session_state.band_data) for band in bands]
        # Explicit columns keep the add-row editor usable even after all bands
        # are removed or no automatic candidates are found.
        import pandas as pd
        table = pd.DataFrame(rows, columns=["Lane", "Migration (px)"])
        edits = st.data_editor(table, num_rows="dynamic", hide_index=True,
                               key=f"band_editor_{st.session_state.band_editor_generation}",
                               column_config={"Lane": st.column_config.NumberColumn(min_value=1, max_value=len(crop.lanes), step=1),
                                              "Migration (px)": st.column_config.NumberColumn(min_value=0, step=.5)})
        if st.button("Apply band edits", key="apply_band_edits"):
            try:
                st.session_state.band_data = validate_band_rows(edits.to_dict("records"), crop.lanes, orientation)
                st.session_state.band_editor_generation += 1
                st.rerun()
            except ValueError as exc:
                st.error(str(exc))
        review = band_review_image(crop.preview_png)
        drawing = ImageDraw.Draw(review)
        for index, bands in enumerate(st.session_state.band_data):
            left, top, right, bottom = crop.lanes[index]
            for number, band in enumerate(bands, 1):
                x, y = band["x"], band["y"]
                segment = (left, y, right - 1, y) if orientation == "wells_top" else (x, top, x, bottom - 1)
                drawing.line(segment, fill="#ffcf33", width=max(1, min(crop.width, crop.height) // 500))
                drawing.text((x + 2, y + 2), f"{index + 1}.{number}", fill="#ffcf33", stroke_width=1, stroke_fill="#000000")
        st.image(review, caption="Band review overlay · labels are lane.band", width=crop.width)
        review_png = BytesIO()
        review.save(review_png, format="PNG")
        st.download_button("Download band review (PNG)", review_png.getvalue(),
                           file_name="gel-band-review.png", mime="image/png", key="download_band_review")
        calibration = None
        try:
            calibration = fit_ladder(ladder, orientation)
            st.caption(f"Log-linear calibration · {calibration['markers']} markers · R² {calibration['r_squared']:.4f}. "
                       "Sizes are estimates within the marked range; review migration and ladder assignments.")
        except ValueError as exc:
            st.info(str(exc))
        measured = band_measurements(st.session_state.band_data, calibration)
        st.dataframe(measured, hide_index=True)
        if measured:
            output = StringIO()
            writer = csv.DictWriter(output, fieldnames=list(measured[0]))
            writer.writeheader()
            writer.writerows(measured)
            st.download_button("Download band measurements (CSV)", output.getvalue(),
                               file_name="gel-band-measurements.csv", mime="text/csv", key="download_bands")
