/** Fit presentation pixels without changing the source image or SVG viewBox. */
export function fitPreviewGeometry({imageWidth, imageHeight, availableWidth,
  viewportHeight, chromeHeight = 0, outerReserve = 100, reviewMode = null, laneCount = 0, workflowOrientation = "wells_left"}) {
  if (![imageWidth, imageHeight, availableWidth, viewportHeight].every(value => Number.isFinite(value) && value > 0)) {
    throw new Error("Preview dimensions must be positive finite numbers.");
  }
  const topMode = workflowOrientation === "wells_top";
  const rightGutter = reviewMode === "borders" && !topMode ? 40 : 0;
  const bottomGutter = reviewMode === "borders" && topMode ? 40 : 0;
  const heightBudget = Math.max(1, viewportHeight - Math.max(0, chromeHeight) - Math.max(0, outerReserve));
  const scale = Math.min(1, Math.max(1, availableWidth - rightGutter) / imageWidth, Math.max(1, heightBudget - bottomGutter) / imageHeight);
  const width = imageWidth * scale;
  const height = imageHeight * scale;
  // laneDeleteLayout keeps 32-screen-pixel targets apart. Count that footprint
  // once, rather than repeatedly subtracting its scale-dependent overflow.
  const controlHeight = reviewMode === "borders" && !topMode ? Math.max(0, laneCount) * 32 : 0;
  const overflowHeight = Math.max(0, controlHeight - height);
  const controlWidth = reviewMode === "borders" && topMode ? Math.max(0, laneCount) * 32 : 0;
  const overflowWidth = Math.max(0, controlWidth - width);
  return {scale, width, height, rightGutter, bottomGutter, wrapperWidth: width + rightGutter + overflowWidth,
    overflowWidth, overflowHeight, totalHeight: height + overflowHeight + bottomGutter, heightBudget,
    controlsOverflow: controlHeight > heightBudget || controlWidth > availableWidth};
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

/** Reserve the real host header and controls, without depending on iframe height. */
export function outerViewportReserve(host = globalThis.window) {
  let height = host.gelPreviewHeight;
  try {
    const measured = host.parent?.gelPreviewViewport?.availableHeight(host.frameElement);
    if (Number.isFinite(measured) && measured > 0) height = measured;
  } catch { /* Cross-origin parents send the same budget with gel:viewport. */ }
  return Number.isFinite(height) && height > 0 ? Math.max(0, outerViewportHeight(host) - height) : 100;
}
