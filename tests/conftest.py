"""Shared event-boundary harness for well and lane workflow tests."""

from pathlib import Path
from types import SimpleNamespace

from PIL import Image
import pytest
from streamlit.testing.v1 import AppTest

from gel_analyzer import image_io, well_component, wells


@pytest.fixture
def well_workflow(monkeypatch):
    """Keep real app callbacks; record detection and substitute browser events."""
    monkeypatch.setattr(
        image_io, "find_gel_crop", lambda image: (0, 0, image.width, image.height)
    )

    def orient(image):
        return SimpleNamespace(
            image=image.transpose(Image.Transpose.TRANSPOSE),
            rectangle=SimpleNamespace(
                corners=((0, 0), (image.width, 0), image.size, (0, image.height))
            ),
            counterclockwise_degrees=90.0,
            outline_complete=True,
            supported_edges=(),
        )

    monkeypatch.setattr(image_io, "orient_gel", orient)
    harness = SimpleNamespace(event=None, renders=[], detections=[], expected_counts=[], result=None)

    def component(*args, **kwargs):
        harness.renders.append((args, kwargs))
        return harness.event

    def detect(image, points, *, expected_count=None):
        harness.detections.append((image.copy(), points))
        harness.expected_counts.append(expected_count)
        return harness.result

    monkeypatch.setattr(well_component, "render_well_component", component)
    monkeypatch.setattr(wells, "detect_wells", detect)
    harness.app = AppTest.from_file(Path(__file__).parents[1] / "app.py").run()
    return harness
