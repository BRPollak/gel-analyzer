/** All coordinates refer to image edges: [0, width] × [0, height]. */
export function clipPoint(point, width, height) {
  return [
    Math.min(width, Math.max(0, point[0])),
    Math.min(height, Math.max(0, point[1])),
  ];
}

/** The SVG has the image's aspect ratio and no internal letterboxing. */
export function pointerToImage(clientX, clientY, rect, width, height) {
  if (!(rect.width > 0 && rect.height > 0)) return null;
  return clipPoint([
    (clientX - rect.left) * width / rect.width,
    (clientY - rect.top) * height / rect.height,
  ], width, height);
}

export function readPoints(points, width, height, workflowOrientation = "wells_left") {
  if (!Array.isArray(points) || points.length > 2) return [];
  if (!points.every(point => Array.isArray(point) && point.length === 2 &&
      point.every(Number.isFinite))) return [];
  const clipped = points.map(point => clipPoint(point, width, height));
  // Orientation makes wells vertical. The first selection anchors the shared
  // x coordinate, including when loading an older, angled guide.
  return clipped.map(point => workflowOrientation === "wells_top" ? [point[0], clipped[0][1]] : [clipped[0][0], point[1]]);
}

/** Move either endpoint while translating the whole vertical guide in x. */
export function moveGuideEndpoint(points, index, point, width, height, workflowOrientation = "wells_left") {
  const clipped = clipPoint(point, width, height);
  return points.map((existing, candidate) => workflowOrientation === "wells_top"
    ? [candidate === index ? clipped[0] : existing[0], clipped[1]]
    : [clipped[0], candidate === index ? clipped[1] : existing[1]]);
}

/** Keep handles equally easy to grab at every responsive image scale. */
export function screenRadius(pixels, rect, width) {
  return rect.width > 0 ? pixels * width / rect.width : pixels;
}

/** Integer border limits retain one pixel of height and ordered, separate lanes. */
export function laneBorderLimits(lanes, index, edge, height) {
  const lane = lanes[index];
  if (edge === "top") return [index === 0 ? 0 : lanes[index - 1][3], lane[3] - 1];
  if (edge === "bottom") return [lane[1] + 1, index === lanes.length - 1 ? height : lanes[index + 1][1]];
  throw new Error("Unknown lane border");
}

export function moveLaneBorder(lanes, index, edge, coordinate, height) {
  const [minimum, maximum] = laneBorderLimits(lanes, index, edge, height);
  const result = lanes.map(lane => [...lane]);
  result[index][edge === "top" ? 1 : 3] = Math.min(maximum, Math.max(minimum, Math.round(coordinate)));
  return result;
}

export function clampRightEdge(coordinate, wells, width) {
  const minimum = Math.max(0, ...wells.map(well => Math.ceil(well.bounds[2])));
  return Math.min(width, Math.max(minimum, Math.round(coordinate)));
}

export function wellsWithLaneBorders(wells, lanes) {
  return wells.map((well, index) => ({...well,
    bounds: [well.bounds[0], lanes[index][1], well.bounds[2], lanes[index][3]],
    center: [well.center?.[0] ?? (well.bounds[0] + well.bounds[2]) / 2,
      (lanes[index][1] + lanes[index][3]) / 2],
  }));
}

/** Pick by distance, not SVG stacking, when generous grip hit areas overlap. */
export function nearestHandle(handles, point, radius) {
  let nearest = null;
  let distance = radius * radius;
  for (const handle of handles) {
    const candidateDistance = (handle.x - point[0]) ** 2 + (handle.y - point[1]) ** 2;
    if (candidateDistance <= distance) {
      nearest = handle;
      distance = candidateDistance;
    }
  }
  return nearest;
}

/** A screen-sized trash column stays reachable even for tightly packed lanes. */
export function laneDeleteLayout(lanes, height, unit) {
  const size = 32 * unit;
  const half = size / 2;
  const layoutHeight = Math.max(height, lanes.length * size);
  const buttons = lanes.map((lane, index) => ({index, x: lane[2] + 20 * unit,
    y: Math.min(layoutHeight - half, Math.max(half, (lane[1] + lane[3]) / 2))}));
  for (let index = 1; index < buttons.length; index++) {
    buttons[index].y = Math.max(buttons[index].y, buttons[index - 1].y + size);
  }
  if (buttons.length) buttons.at(-1).y = Math.min(buttons.at(-1).y, layoutHeight - half);
  for (let index = buttons.length - 2; index >= 0; index--) {
    buttons[index].y = Math.min(buttons[index].y, buttons[index + 1].y - size);
  }
  return {buttons, overflow: layoutHeight - height};
}

/** Analysis-axis views are involutions; the image and stored state stay in XY. */
export const swapPoint = point => [point[1], point[0]];
export const swapBounds = bounds => [bounds[1], bounds[0], bounds[3], bounds[2]];
export const swapWell = well => ({...well, bounds: swapBounds(well.bounds),
  ...(well.center ? {center: swapPoint(well.center)} : {})});

/** A mutable view reuses lane editing math without moving displayed pixels. */
export function laneAxisState(state) {
  if (!state || state.workflowOrientation !== "wells_top") return state;
  return {
    get width() { return state.height; }, get height() { return state.width; },
    get reviewMode() { return state.reviewMode; }, get editable() { return state.editable; },
    get rightEdge() { return state.rightEdge; }, set rightEdge(value) { state.rightEdge = value; },
    get lanes() { return state.lanes.map(swapBounds); }, set lanes(value) { state.lanes = value.map(swapBounds); },
    get wells() { return state.wells.map(swapWell); }, set wells(value) { state.wells = value.map(swapWell); },
  };
}
