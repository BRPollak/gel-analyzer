/** Fit presentation pixels without changing the source image or SVG viewBox. */
export function fitPreviewGeometry({imageWidth, imageHeight, availableWidth,
  viewportHeight, chromeHeight = 0, outerReserve = 100, reviewMode = null, laneCount = 0}) {
  if (![imageWidth, imageHeight, availableWidth, viewportHeight].every(value => Number.isFinite(value) && value > 0)) {
    throw new Error("Preview dimensions must be positive finite numbers.");
  }
  const rightGutter = reviewMode === "borders" ? 40 : 0;
  const heightBudget = Math.max(1, viewportHeight - Math.max(0, chromeHeight) - Math.max(0, outerReserve));
  const scale = Math.min(1, Math.max(1, availableWidth - rightGutter) / imageWidth, heightBudget / imageHeight);
  const width = imageWidth * scale;
  const height = imageHeight * scale;
  // laneDeleteLayout keeps 32-screen-pixel targets apart. Count that footprint
  // once, rather than repeatedly subtracting its scale-dependent overflow.
  const controlHeight = reviewMode === "borders" ? Math.max(0, laneCount) * 32 : 0;
  const overflowHeight = Math.max(0, controlHeight - height);
  return {scale, width, height, rightGutter, wrapperWidth: width + rightGutter,
    overflowHeight, totalHeight: height + overflowHeight, heightBudget,
    controlsOverflow: controlHeight > heightBudget};
}

/** The iframe's own height follows our result, so it cannot be an input. */
export function outerViewportHeight(host = globalThis.window) {
  try {
    const parent = host.parent;
    const height = parent?.visualViewport?.height || parent?.innerHeight;
    // A standalone fixture has parent === host; it still represents the outer
    // browser viewport because no embedding page resizes it from our output.
    if (Number.isFinite(height) && height > 0) return height;
  } catch {
    // Cross-origin deployments may hide the parent viewport.
  }
  const fallback = host.screen?.availHeight || host.outerHeight || 800;
  return Number.isFinite(fallback) && fallback > 0 ? fallback : 800;
}
