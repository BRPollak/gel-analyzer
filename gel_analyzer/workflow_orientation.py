"""Workflow axes, independent of image rotation and displayed XY coordinates.

The shared analysis algorithms use migration along x and lane order along y.
Wells-at-top analysis swaps those axes temporarily; source pixels and all
persisted/public coordinates remain in the displayed image's coordinate system.
"""

WELLS_LEFT = "wells_left"
WELLS_TOP = "wells_top"


def is_top(workflow_orientation: str = WELLS_LEFT) -> bool:
    if workflow_orientation not in (WELLS_LEFT, WELLS_TOP):
        raise ValueError("Choose Wells at left or Wells at top for workflow orientation.")
    return workflow_orientation == WELLS_TOP


def swap_point(point):
    return point[1], point[0]


def swap_size(size):
    return size[1], size[0]


def swap_bounds(bounds):
    return bounds[1], bounds[0], bounds[3], bounds[2]


def lane_bounds(bounds, extent, workflow_orientation=WELLS_LEFT):
    """Extend a well downstream, retaining its displayed cross-axis bounds."""
    left, top, right, bottom = bounds
    return (left, top, right, extent) if is_top(workflow_orientation) else (left, top, extent, bottom)


def orientation_text(message: str, workflow_orientation=WELLS_LEFT) -> str:
    """Map legacy axis-specific diagnostics to wells-at-top terminology."""
    if not is_top(workflow_orientation):
        return message
    # A simultaneous substitution prevents one replacement being swapped twice.
    import re

    words = {"top-to-bottom": "left-to-right", "top and bottom": "left and right",
             "above the other": "beside the other", "vertical": "horizontal",
             "horizontal": "vertical", "right edge": "bottom edge", "right boundary": "bottom boundary",
             "left edge": "top edge", "image bottom": "image right edge",
             "one pixel high": "one pixel wide", "image row": "image column",
             "outside top and bottom": "outside left and right"}
    pattern = "|".join(re.escape(word) for word in sorted(words, key=len, reverse=True))
    return re.sub(pattern, lambda match: words[match.group()], message)
