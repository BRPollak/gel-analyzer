"""Download and reopen validated, portable Gel Analyzer projects."""

from pathlib import Path

import streamlit as st

from .projects import ProjectError, load_project, save_project


def _open_project(key):
    uploaded = st.session_state.get(key)
    if uploaded is None:
        return
    try:
        restored = load_project(uploaded.getvalue())
    except ProjectError as exc:
        st.session_state.project_error = str(exc)
        return
    # Validation finishes before any active state is replaced. Fresh tokens
    # ensure late pointer events from the previous project cannot alter it.
    st.session_state.update(restored)
    st.session_state.uploader_generation = st.session_state.get("uploader_generation", 0) + 1
    st.session_state.project_error = None
    st.session_state.project_notice = "Project reopened. Your workflow and annotations have been restored."


def show_project_controls(consume_latest=None):
    """Call after session initialization, before the workflow is rendered.

    ``consume_latest`` may synchronize the current orientation/well/lane and
    annotation component events before generating the download snapshot.
    """
    with st.popover("Project"):
        st.file_uploader("Open project", type=["json"], key="project_upload",
                         max_upload_size=256,
                         on_change=_open_project, args=("project_upload",),
                         help="Open a saved .gel.json project, replacing the current session after validation.")
        if st.session_state.get("gel_image") is not None:
            if consume_latest is not None:
                consume_latest()
            try:
                snapshot = save_project(st.session_state)
            except ProjectError as exc:
                st.warning(str(exc))
            else:
                stem = Path(st.session_state.gel_image.filename).stem
                st.download_button("Save project", snapshot, file_name=f"{stem}.gel.json",
                                   mime="application/json", key="save_project",
                                   help="Save source pixels, workflow orientation, lane and ladder annotations, and confirmed exports.")
        st.caption("Projects include the source image and edits. Save a project to continue in a later session.")
    if st.session_state.get("project_error"):
        st.error(st.session_state.project_error)
    if st.session_state.get("project_notice"):
        st.success(st.session_state.pop("project_notice"))
