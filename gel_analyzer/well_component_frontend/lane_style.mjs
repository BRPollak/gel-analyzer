const LANE_COLORS = ["#38d9f5", "#fbbf24", "#e9a5ff"];

/** Review identity survives resizing/deletion; array position is a legacy fallback. */
function lanePhase(well, index) {
  const identity = Number.isInteger(well?.review_id) && well.review_id >= 0
    ? well.review_id : Number.isInteger(index) && index >= 0 ? index : 0;
  return identity % LANE_COLORS.length;
}

export function laneColor(well, index) {
  return LANE_COLORS[lanePhase(well, index)];
}

/** Stagger neighboring grips while retaining separate leading/trailing columns. */
export function laneGripFraction(well, index, edge) {
  return (edge === "top" ? .18 : .58) + lanePhase(well, index) * .12;
}

/**
 * Resolve overlapping border targets by distance in canonical (wells-left) axes.
 * The lane-width cap leaves its center available for selection on dense gels.
 * An exact tie favors the selected lane, then the earlier lane and top edge.
 */
export function nearestLaneBorder(lanes, point, radius, preferredIndex = null) {
  if (!Array.isArray(point) || !point.every(Number.isFinite) || point.length !== 2 ||
      !Number.isFinite(radius) || radius < 0) return null;
  let nearest = null;
  let distance = Infinity;
  lanes.forEach((lane, index) => {
    const [left, top, right, bottom] = lane;
    const targetRadius = Math.min(radius, Math.max(0, bottom - top) / 4);
    const horizontalDistance = Math.max(left - point[0], 0, point[0] - right);
    for (const [edge, y] of [["top", top], ["bottom", bottom]]) {
      const candidateDistance = horizontalDistance ** 2 + (y - point[1]) ** 2;
      if (candidateDistance > targetRadius ** 2) continue;
      if (candidateDistance < distance || (candidateDistance === distance &&
          index === preferredIndex && nearest?.index !== preferredIndex)) {
        nearest = {index, edge};
        distance = candidateDistance;
      }
    }
  });
  return nearest;
}
