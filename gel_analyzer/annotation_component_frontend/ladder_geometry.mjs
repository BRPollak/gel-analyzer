/** Convert through the displayed composition, without snapping or clipping. */
export function ladderImagePoint(clientX, clientY, rect, layout) {
  if (!layout || !(rect.width > 0 && rect.height > 0)) return null;
  const x = (clientX - rect.left) * layout.width / rect.width - layout.gelX;
  const y = (clientY - rect.top) * layout.height / rect.height - layout.gelY;
  return Number.isFinite(x) && Number.isFinite(y) ? {x, y} : null;
}

/** Lane bounds are half-open, so touching borders never select two lanes. */
export function pointInLane(point, lane) {
  return Boolean(point && lane && point.x >= lane[0] && point.x < lane[2]
    && point.y >= lane[1] && point.y < lane[3]);
}

export function laneAtPoint(point, lanes) {
  return lanes.findIndex(lane => pointInLane(point, lane));
}

export function cursorForMarker(ladder, markerIndex, lanes) {
  const placed = ladder?.placements.find(item => item.markerIndex === markerIndex);
  if (placed) return {x: placed.x, y: placed.y};
  const lane = lanes[ladder?.laneIndex];
  return lane ? {x: (lane[0] + lane[2]) / 2, y: (lane[1] + lane[3]) / 2} : null;
}

export function moveLadderCursor(cursor, direction, shift, lane) {
  // Keyboard adjustment uses native pixels. Preserve fractional click values,
  // but keep the cursor within the last pixel when reaching a half-open edge.
  // A fractional click in the last pixel must not move left on ArrowRight.
  return {...cursor, x: Math.min(Math.max(cursor.x, lane[0], lane[2] - 1),
    Math.max(lane[0], cursor.x + direction * (shift ? 10 : 1)))};
}

export function placeLadderMarker(ladder, markerIndex, point, lanes) {
  if (!ladder || !Number.isInteger(markerIndex) || markerIndex < 0
    || markerIndex >= ladder.preset.labels.length || !pointInLane(point, lanes[ladder.laneIndex])) return null;
  const placements = ladder.placements.filter(item => item.markerIndex !== markerIndex);
  placements.push({markerIndex, x: point.x, y: point.y});
  placements.sort((a, b) => a.markerIndex - b.markerIndex);
  return {...ladder, placements};
}

/** Pointer movement is measured in screen pixels, independent of gel zoom. */
export function movedPastTap(start, event) {
  return Math.hypot(event.clientX - start.x, event.clientY - start.y) > 6;
}

/** A side panel consumes width, not the vertical preview budget. */
export function annotationPreviewBudget({viewportHeight, componentHeight, previewHeight,
  workspaceHeight, sidePanel, insetY, ladderMode}) {
  const otherHeight = componentHeight - (sidePanel ? workspaceHeight : previewHeight);
  return Math.max(insetY + (ladderMode ? 220 : 1), Math.floor(viewportHeight - otherHeight - 100));
}
