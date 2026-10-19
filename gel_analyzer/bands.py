"""Migration-axis band proposals and explicit ladder calibration.

Profiles use the middle of each reviewed lane and retain displayed-image XY
coordinates. These are reviewable proposals, not assignments of ladder sizes.
"""

from functools import lru_cache
from io import BytesIO
import math
import re

import numpy as np
from PIL import Image


def band_review_image(png: bytes) -> Image.Image:
    """Decode browser-like display colors without clipping 16-bit gray to 255."""
    with Image.open(BytesIO(png)) as source:
        if source.mode.startswith("I"):
            pixels = np.asarray(source, dtype=np.uint16)
            return Image.fromarray((pixels >> 8).astype(np.uint8)).convert("RGB")
        return source.convert("RGB")


def detect_bands(image: Image.Image, lanes, workflow_orientation="wells_left", *, wells=()) -> list[list[dict]]:
    if workflow_orientation not in ("wells_left", "wells_top"):
        raise ValueError("Choose a supported workflow orientation.")
    pixels = np.asarray(image.convert("F" if image.mode.startswith("I") else "L"), dtype=float)
    top_mode = workflow_orientation == "wells_top"
    span = float(np.ptp(pixels))
    results = []
    for index, (left, top, right, bottom) in enumerate(lanes):
        if not (0 <= left < right <= image.width and 0 <= top < bottom <= image.height):
            raise ValueError("Keep band analysis lanes inside the gel.")
        cross_start, cross_end = (left, right) if top_mode else (top, bottom)
        start, end = (top, bottom) if top_mode else (left, right)
        if index < len(wells):
            start = max(start, wells[index].bounds[3 if top_mode else 2] + 1)
        inset = int((cross_end - cross_start) * .2)
        region = (pixels[start:end, cross_start + inset:cross_end - inset] if top_mode
                  else pixels[cross_start + inset:cross_end - inset, start:end])
        if end - start < 7:
            results.append([])
            continue
        profile = np.median(region, axis=1 if top_mode else 0)
        smooth = np.convolve(np.pad(profile, (1, 1), mode="edge"), [.25, .5, .25], mode="valid")
        radius = max(7, min(80, round(len(profile) * .04)))
        windows = np.lib.stride_tricks.sliding_window_view(np.pad(smooth, radius, mode="edge"), 2 * radius + 1)
        baseline = np.median(windows, axis=1)
        residual = smooth - baseline
        # Both bright fluorescence and dark absorption bands are supported.
        noise = float(np.median(np.abs(np.diff(profile) - np.median(np.diff(profile)))) * 1.4826)
        threshold = max(noise * 4, span * .025, 1e-6)
        strength = np.abs(residual)
        active = strength > threshold
        edges = np.diff(np.r_[False, active, False].astype(int))
        candidates = []
        for begin, stop in zip(np.flatnonzero(edges == 1), np.flatnonzero(edges == -1)):
            if stop - begin < 2:
                continue
            peak = begin + int(np.argmax(strength[begin:stop]))
            position = float(start + peak + .5)
            center = (cross_start + cross_end) / 2
            candidates.append({"x": center if top_mode else position,
                               "y": position if top_mode else center,
                               "position": position, "signal": float(residual[peak])})
        results.append(candidates)
    return results


@lru_cache(maxsize=4)
def crop_band_candidates(png: bytes, lanes: tuple, orientation: str, wells: tuple = ()) -> list[list[dict]]:
    with Image.open(BytesIO(png)) as image:
        return detect_bands(image, lanes, orientation, wells=wells)


def validate_band_rows(rows, lanes, workflow_orientation="wells_left") -> list[list[dict]]:
    """Convert the editable migration table to checked display coordinates."""
    result = [[] for _ in lanes]
    for row in rows:
        lane, position = row.get("Lane"), row.get("Migration (px)")
        if (isinstance(lane, bool) or not isinstance(lane, (int, float)) or not math.isfinite(lane)
                or lane != int(lane) or not 1 <= lane <= len(lanes)):
            raise ValueError("Each band must belong to an existing lane number.")
        if isinstance(position, bool) or not isinstance(position, (int, float)) or not math.isfinite(position):
            raise ValueError("Each band needs a finite migration position in pixels.")
        index = int(lane) - 1
        left, top, right, bottom = lanes[index]
        top_mode = workflow_orientation == "wells_top"
        start, end = (top, bottom) if top_mode else (left, right)
        if not start <= position < end:
            raise ValueError(f"Band positions in lane {lane} must be between {start} and {end} (exclusive).")
        center = (left + right) / 2 if top_mode else (top + bottom) / 2
        if any(band["position"] == position for band in result[index]):
            raise ValueError("Keep distinct positions for bands within a lane.")
        result[index].append({"x": center if top_mode else float(position),
                              "y": float(position) if top_mode else center,
                              "position": float(position), "signal": None})
    return [sorted(bands, key=lambda band: band["position"]) for bands in result]


def fit_ladder(ladder, workflow_orientation="wells_left") -> dict:
    """Fit log10(size) against migration; ignore ambiguous/composite labels.

    At least two distinct, monotonically decreasing sizes are required. Values
    are expressed in bp for DNA or kDa for mass. Extrapolation is never reported.
    """
    if not ladder or not ladder.get("preset"):
        raise ValueError("Place at least two numeric ladder markers to estimate band sizes.")
    points, units = [], set()
    axis = "y" if workflow_orientation == "wells_top" else "x"
    for placement in ladder["placements"]:
        label = ladder["preset"]["labels"][placement["markerIndex"]].replace(",", "")
        match = re.fullmatch(r"\s*(\d+(?:\.\d+)?)\s*(bp|kb|kDa|Da)?\s*", label, re.IGNORECASE)
        if not match:
            continue
        value, unit = float(match[1]), (match[2] or "size").lower()
        if unit == "kb":
            value, unit = value * 1000, "bp"
        elif unit == "da":
            value, unit = value / 1000, "kda"
        if value <= 0:
            continue
        points.append((float(placement[axis]), value))
        units.add(unit)
    points.sort()
    if len(points) < 2:
        raise ValueError("Place at least two unambiguous numeric ladder markers to estimate band sizes.")
    if len(units) != 1:
        raise ValueError("Use the same size units for every calibration marker.")
    if any(a[0] >= b[0] or a[1] <= b[1] for a, b in zip(points, points[1:])):
        raise ValueError("Ladder sizes must decrease along migration with distinct marker positions.")
    positions = np.asarray([p[0] for p in points])
    values = np.log10([p[1] for p in points])
    slope, intercept = np.polyfit(positions, values, 1)
    residual = float(np.sum((values - (slope * positions + intercept)) ** 2))
    total = float(np.sum((values - values.mean()) ** 2))
    return {"slope": float(slope), "intercept": float(intercept), "minimum": float(positions[0]),
            "maximum": float(positions[-1]), "unit": "kDa" if "kda" in units else next(iter(units)),
            "r_squared": 1 - residual / total, "markers": len(points)}


def band_measurements(candidates, calibration=None) -> list[dict]:
    rows = []
    for index, bands in enumerate(candidates, 1):
        for number, band in enumerate(bands, 1):
            position = band["position"]
            inside = calibration and calibration["minimum"] <= position <= calibration["maximum"]
            value = 10 ** (calibration["intercept"] + calibration["slope"] * position) if inside else None
            rows.append({"Lane": index, "Band": number, "Migration (px)": position,
                         "Estimated size": round(value, 3) if value is not None else None,
                         "Unit": calibration["unit"] if calibration else "",
                         "Status": "Interpolated" if inside else "Outside calibration range" if calibration else "Uncalibrated"})
    return rows
