"""Local Streamlit bridge for the live annotation editor and canvas renderer."""

from base64 import b64encode
from pathlib import Path

import streamlit.components.v1 as components


_component = components.declare_component(
    "lane_annotations", path=str(Path(__file__).with_name("annotation_component_frontend"))
)


def render_annotation_component(crop, *, annotations, token, revision, error, key,
                                mode="lanes", ladder=None, presets=(),
                                ladder_step="preset", confirmed_ladder=False):
    return _component(
        image_src="data:image/png;base64," + b64encode(crop.preview_png).decode("ascii"),
        width=crop.width, height=crop.height, lanes=[list(lane) for lane in crop.lanes],
        annotations=annotations, token=token, revision=revision, error=error,
        mode=mode, ladder=ladder, presets=list(presets), ladder_step=ladder_step,
        confirmed_ladder=confirmed_ladder,
        key=key, default=None,
    )
