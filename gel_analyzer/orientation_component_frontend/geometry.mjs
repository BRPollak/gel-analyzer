/** Source pixel-boundary coordinates, with clockwise angles in image space. */
export const MIN_SIZE = 2;
const EPSILON = 1e-7;
const SIGNS = [[-1, -1], [1, -1], [1, 1], [-1, 1]];

export function normalizeAngle(degrees) {
  return ((degrees + 180) % 360 + 360) % 360 - 180;
}

export function axes(selection) {
  const radians = selection.angle_degrees * Math.PI / 180;
  return [[Math.cos(radians), Math.sin(radians)], [-Math.sin(radians), Math.cos(radians)]];
}

export function rectangleCorners(selection) {
  const [u, v] = axes(selection);
  return SIGNS.map(([x, y]) => [
    selection.cx + x * selection.width / 2 * u[0] + y * selection.height / 2 * v[0],
    selection.cy + x * selection.width / 2 * u[1] + y * selection.height / 2 * v[1],
  ]);
}

export function isInsideImage(selection, width, height) {
  return rectangleCorners(selection).every(([x, y]) =>
    x >= -EPSILON && y >= -EPSILON && x <= width + EPSILON && y <= height + EPSILON);
}

export function readSelection(value, width, height) {
  const keys = ["cx", "cy", "width", "height", "angle_degrees"];
  if (!value || !keys.every(key => Number.isFinite(value[key]))) return null;
  if (value.width < MIN_SIZE || value.height < MIN_SIZE) return null;
  const selection = Object.fromEntries(keys.map(key => [key, value[key]]));
  selection.angle_degrees = normalizeAngle(selection.angle_degrees);
  return isInsideImage(selection, width, height) ? selection : null;
}

export function sameSelection(first, second) {
  if (!first || !second) return first === second;
  return ["cx", "cy", "width", "height", "angle_degrees"].every(key =>
    Math.abs(first[key] - second[key]) < EPSILON);
}

export function pointerToImage(clientX, clientY, rect, width, height, clip = true) {
  if (!(rect.width > 0 && rect.height > 0)) return null;
  const x = (clientX - rect.left) * width / rect.width;
  const y = (clientY - rect.top) * height / rect.height;
  return clip ? [Math.min(width, Math.max(0, x)), Math.min(height, Math.max(0, y))] : [x, y];
}

export function screenRadius(pixels, rect, width) {
  return rect.width > 0 ? pixels * width / rect.width : pixels;
}

export function drawRectangle(start, end) {
  const width = Math.abs(end[0] - start[0]);
  const height = Math.abs(end[1] - start[1]);
  if (width < MIN_SIZE || height < MIN_SIZE) return null;
  return {cx: (start[0] + end[0]) / 2, cy: (start[1] + end[1]) / 2,
    width, height, angle_degrees: 0};
}

export function moveRectangle(selection, dx, dy, width, height) {
  const [u, v] = axes(selection);
  const halfWidth = (Math.abs(u[0]) * selection.width + Math.abs(v[0]) * selection.height) / 2;
  const halfHeight = (Math.abs(u[1]) * selection.width + Math.abs(v[1]) * selection.height) / 2;
  return {...selection,
    cx: Math.max(halfWidth, Math.min(width - halfWidth, selection.cx + dx)),
    cy: Math.max(halfHeight, Math.min(height - halfHeight, selection.cy + dy))};
}

/** Keep the opposite corner fixed and clip expansion at the image boundary. */
export function resizeRectangle(selection, corner, point, width, height) {
  if (!SIGNS[corner]) return selection;
  const [u, v] = axes(selection);
  const [sx, sy] = SIGNS[corner];
  const anchor = rectangleCorners(selection)[(corner + 2) % 4];
  const delta = [point[0] - anchor[0], point[1] - anchor[1]];
  const requestedWidth = Math.max(MIN_SIZE, sx * (delta[0] * u[0] + delta[1] * u[1]));
  const requestedHeight = Math.max(MIN_SIZE, sy * (delta[0] * v[0] + delta[1] * v[1]));
  function at(fraction) {
    const w = selection.width + (requestedWidth - selection.width) * fraction;
    const h = selection.height + (requestedHeight - selection.height) * fraction;
    return {...selection, width: w, height: h,
      cx: anchor[0] + sx * w / 2 * u[0] + sy * h / 2 * v[0],
      cy: anchor[1] + sx * w / 2 * u[1] + sy * h / 2 * v[1]};
  }
  const candidate = at(1);
  if (isInsideImage(candidate, width, height)) return candidate;
  let low = 0, high = 1;
  for (let step = 0; step < 45; step++) {
    const middle = (low + high) / 2;
    if (isInsideImage(at(middle), width, height)) low = middle;
    else high = middle;
  }
  return at(low);
}

/** Rotation preserves the chosen region size; invalid angles are rejected. */
export function rotateRectangle(selection, degrees, width, height) {
  const candidate = {...selection, angle_degrees: normalizeAngle(degrees)};
  return isInsideImage(candidate, width, height) ? candidate : null;
}

export function rotationHandle(selection, unit) {
  const [u] = axes(selection);
  const edge = [selection.cx - u[0] * selection.width / 2, selection.cy - u[1] * selection.width / 2];
  return {edge, point: [edge[0] - u[0] * 28 * unit, edge[1] - u[1] * 28 * unit]};
}

/** Pick by distance so overlapping touch targets never hide a nearby corner. */
export function nearestHandle(selection, point, unit) {
  const handles = rectangleCorners(selection).map((position, corner) => ({position, corner, action: "resize"}));
  handles.push({position: rotationHandle(selection, unit).point, action: "rotate"});
  let nearest = null, distance = 17 * unit;
  for (const handle of handles) {
    const candidate = Math.hypot(point[0] - handle.position[0], point[1] - handle.position[1]);
    if (candidate < distance) { distance = candidate; nearest = handle; }
  }
  return nearest;
}

export function fitPreviewGeometry({imageWidth, imageHeight, availableWidth, viewportHeight, chromeHeight = 0}) {
  const gutter = 38;
  const heightBudget = Math.max(1, viewportHeight - chromeHeight - 100 - gutter * 2);
  const scale = Math.min(1, Math.max(1, availableWidth - gutter * 2) / imageWidth, heightBudget / imageHeight);
  return {scale, wrapperWidth: imageWidth * scale + gutter * 2, gutter, heightBudget};
}

export function outerViewportHeight(host) {
  try {
    const height = host.parent?.visualViewport?.height || host.parent?.innerHeight;
    if (Number.isFinite(height) && height > 0) return height;
  } catch { /* A cross-origin embedding page may hide its viewport. */ }
  return host.screen?.availHeight || host.outerHeight || 800;
}
