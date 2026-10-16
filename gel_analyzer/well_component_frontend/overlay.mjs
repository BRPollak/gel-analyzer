import {clipPoint, moveGuideEndpoint, pointerToImage, readPoints, screenRadius} from "./geometry.mjs";
import {createLaneReview} from "./lane_review.mjs";
import {fitPreviewGeometry, outerViewportHeight, outerViewportReserve} from "./fit_geometry.mjs";

// Streamlit's documented v1 component postMessage protocol. No CDN, external
// runtime, network service, or image processing is used in this iframe.
const svg = document.getElementById("gel");
const component = document.getElementById("component");
const image = document.getElementById("gel-image");
const wrap = document.getElementById("image-wrap");
const status = document.getElementById("status");
const resultLayer = document.getElementById("results");
const endpoints = [0, 1].map(index => document.getElementById(`endpoint-${index}`));
const seenTokens = new Set();
let state = null;
let drag = null;
let revision = 0;
let frameHeight = 0;
let fitFrame = 0;
const review = createLaneReview({svg, getState: () => state, pointerPosition,
  repaint, emit: emitEvent});

function post(type, data = {}) {
  window.parent.postMessage({isStreamlitMessage: true, type, ...data}, "*");
}

function resizeFrame() {
  const height = Math.ceil(component.getBoundingClientRect().height);
  if (height !== frameHeight) {
    frameHeight = height;
    post("streamlit:setFrameHeight", {height});
  }
}

function emitEvent(value) {
  if (!state || !state.editable) return;
  revision = Math.max(revision + 1, Date.now() * 1000);
  svg.dataset.revision = String(revision);
  post("streamlit:setComponentValue", {
    dataType: "json",
    value: {token: state.token, revision, ...value},
  });
}

function emitPoints() {
  emitEvent({points: state.points.map(point => [...point])});
}

function repaint() {
  if (!state) return;
  // Instructions may wrap differently after a stage change; measure that real
  // height before allocating the image's viewport budget.
  drawGuide();
  fitPreview();
  drawGuide();
  drawResults();
  review.draw();
}

function fitPreview() {
  const componentStyle = getComputedStyle(component);
  const statusStyle = getComputedStyle(status);
  const wrapStyle = getComputedStyle(wrap);
  const px = value => Number.parseFloat(value) || 0;
  const horizontalPadding = px(componentStyle.paddingLeft) + px(componentStyle.paddingRight);
  const chromeHeight = px(componentStyle.paddingTop) + px(componentStyle.paddingBottom) +
    status.getBoundingClientRect().height + px(statusStyle.marginTop) + px(statusStyle.marginBottom) +
    px(wrapStyle.marginTop) + px(wrapStyle.marginBottom);
  const fit = fitPreviewGeometry({imageWidth: state.width, imageHeight: state.height,
    availableWidth: Math.max(1, component.clientWidth - horizontalPadding),
    viewportHeight: outerViewportHeight(window), outerReserve: outerViewportReserve(window), chromeHeight,
    reviewMode: state.reviewMode, laneCount: state.lanes.length});
  wrap.style.width = `${fit.wrapperWidth}px`;
  wrap.style.maxWidth = `${state.width + fit.rightGutter}px`;
  wrap.dataset.previewScale = String(fit.scale);
  wrap.dataset.heightBudget = String(fit.heightBudget);
  wrap.dataset.controlsOverflow = String(fit.controlsOverflow);
}

function scheduleFit() {
  if (fitFrame) return;
  fitFrame = requestAnimationFrame(() => {
    fitFrame = 0;
    repaint();
    resizeFrame();
  });
}

function pointerPosition(event) {
  return pointerToImage(event.clientX, event.clientY, svg.getBoundingClientRect(), state.width, state.height);
}

function invalidateResults() {
  state.wells = [];
  state.lanes = [];
  drawResults();
}

function drawGuide() {
  if (!state) return;
  const rect = svg.getBoundingClientRect();
  const radius = screenRadius(7, rect, state.width);
  endpoints.forEach((handle, index) => {
    const point = state.points[index];
    handle.setAttribute("visibility", point && !state.reviewMode ? "visible" : "hidden");
    handle.setAttribute("tabindex", point && state.editable && !state.reviewMode ? "0" : "-1");
    handle.setAttribute("aria-disabled", String(!state.editable));
    if (!point) return;
    handle.setAttribute("transform", `translate(${point[0]} ${point[1]})`);
    handle.setAttribute("aria-label", `Endpoint ${index + 1}, x ${point[0].toFixed(1)}, y ${point[1].toFixed(1)}. Up and Down adjust this endpoint; Left and Right move the vertical line. Shift moves ten pixels.`);
    handle.dataset.x = point[0];
    handle.dataset.y = point[1];
    handle.querySelector(".hit").setAttribute("r", screenRadius(18, rect, state.width));
    handle.querySelector(".dot").setAttribute("r", radius);
  });
  for (const id of ["guide", "guide-halo"]) {
    const line = document.getElementById(id);
    line.setAttribute("visibility", state.points.length === 2 && !state.reviewMode ? "visible" : "hidden");
    if (state.points.length === 2) {
      line.setAttribute("x1", state.points[0][0]);
      line.setAttribute("y1", state.points[0][1]);
      line.setAttribute("x2", state.points[1][0]);
      line.setAttribute("y2", state.points[1][1]);
    }
  }
  svg.dataset.editable = String(state.editable);
  svg.dataset.reviewMode = state.reviewMode || "";
  wrap.dataset.reviewMode = state.reviewMode || "";
  svg.dataset.pointCount = String(state.points.length);
  const instructions = state.reviewMode === "borders"
    ? "Adjust each lane’s top and bottom border using the arrow handles. Use Up/Down keys on a focused handle. Delete a lane with the trash button on its right, or use Add lane to insert one at the bottom of the detection line."
    : state.reviewMode === "extent"
    ? "Drag the gold right boundary left or right to choose a shared lane length. The shaded region will be excluded. Use Left/Right keys on the handle."
    : !state.editable
    ? "Detected wells and horizontal lanes."
    : state.points.length === 0
      ? "Click the top edge of the first well and the bottom edge of the last well, in either order."
      : state.points.length === 1
        ? "Click the other end of the well range. The line stays vertical."
        : "Drag either dot to adjust the range or move the vertical line sideways. Arrow keys also adjust a focused dot.";
  if (status.textContent !== instructions) {
    status.textContent = instructions;
    scheduleFit();
  }
}

function element(name, attributes, parent = resultLayer) {
  const node = document.createElementNS("http://www.w3.org/2000/svg", name);
  for (const [key, value] of Object.entries(attributes)) node.setAttribute(key, value);
  parent.appendChild(node);
  return node;
}

function drawResults() {
  resultLayer.replaceChildren();
  if (!state) return;
  const rect = svg.getBoundingClientRect();
  const unit = screenRadius(1, rect, state.width);
  function outline(bounds, className, index) {
    if (!Array.isArray(bounds) || bounds.length !== 4 || !bounds.every(Number.isFinite)) return;
    const [left, top] = clipPoint(bounds.slice(0, 2), state.width, state.height);
    const [right, bottom] = clipPoint(bounds.slice(2, 4), state.width, state.height);
    element("rect", {x: left, y: top, width: Math.max(0, right - left),
      height: Math.max(0, bottom - top), class: `${className} outline`,
      "data-testid": `${className}-${index + 1}`});
  }
  state.lanes.forEach((lane, index) => outline(lane, "lane", index));
  [...state.wells].sort((a, b) => a.bounds[1] - b.bounds[1]).forEach((well, index) => {
    outline(well.bounds, "well", index);
    const [left, top, right, bottom] = well.bounds;
    const center = well.center || [(left + right) / 2, (top + bottom) / 2];
    element("circle", {cx: center[0], cy: center[1], r: 2 * unit, class: "center"});
    const labelX = right + 7 * unit;
    const onRight = labelX + 20 * unit < state.width;
    const label = element("text", {x: onRight ? labelX : Math.max(3 * unit, left - 7 * unit),
      y: center[1], "dominant-baseline": "central", "text-anchor": onRight ? "start" : "end",
      "font-size": 12 * unit, "stroke-width": 3 * unit, class: "number"});
    // Inline style wins over the CSS stroke-width, keeping labels readable.
    label.style.strokeWidth = `${3 * unit}px`;
    label.textContent = String(index + 1);
  });
}

svg.addEventListener("pointerdown", event => {
  if (!state || state.reviewMode || !state.editable || event.button !== 0 || drag) return;
  const handle = event.target.closest("[data-endpoint]");
  if (handle) {
    const index = Number(handle.dataset.endpoint);
    if (!state.points[index]) return;
    event.preventDefault();
    handle.focus();
    drag = {index, pointerId: event.pointerId, original: state.points.map(point => [...point]),
      wells: state.wells, lanes: state.lanes};
    svg.setPointerCapture(event.pointerId);
    svg.dataset.dragging = "true";
  } else if (state.points.length < 2) {
    const point = pointerPosition(event);
    if (!point) return;
    event.preventDefault();
    state.points = readPoints([...state.points, point], state.width, state.height);
    invalidateResults();
    drawGuide();
    emitPoints();
  }
});

svg.addEventListener("pointermove", event => {
  if (!drag || state?.reviewMode || event.pointerId !== drag.pointerId || !state?.editable) return;
  const point = pointerPosition(event);
  if (!point) return;
  if (point.some((coordinate, index) => coordinate !== state.points[drag.index][index])) invalidateResults();
  state.points = moveGuideEndpoint(state.points, drag.index, point, state.width, state.height);
  drawGuide(); // The bridge is deliberately silent until pointerup.
});

function finishDrag(event, cancelled) {
  if (!drag || event.pointerId !== drag.pointerId) return;
  const active = drag;
  drag = null;
  svg.dataset.dragging = "false";
  if (cancelled) {
    state.points = active.original;
    state.wells = active.wells;
    state.lanes = active.lanes;
    drawResults();
  } else {
    state.points = moveGuideEndpoint(state.points, active.index,
      pointerPosition(event) || state.points[active.index], state.width, state.height);
    if (state.points[active.index].some((coordinate, index) => coordinate !== active.original[active.index][index])) invalidateResults();
  }
  if (svg.hasPointerCapture(event.pointerId)) svg.releasePointerCapture(event.pointerId);
  drawGuide();
  if (!cancelled) emitPoints();
}
svg.addEventListener("pointerup", event => finishDrag(event, false));
svg.addEventListener("pointercancel", event => finishDrag(event, true));
svg.addEventListener("lostpointercapture", event => finishDrag(event, true));

svg.addEventListener("keydown", event => {
  if (!state?.editable || state.reviewMode || drag) return;
  const handle = event.target.closest("[data-endpoint]");
  const direction = {ArrowLeft: [-1, 0], ArrowRight: [1, 0], ArrowUp: [0, -1], ArrowDown: [0, 1]}[event.key];
  if (!handle || !direction) return;
  const index = Number(handle.dataset.endpoint);
  const point = state.points[index];
  if (!point) return;
  event.preventDefault();
  const step = event.shiftKey ? 10 : 1;
  state.points = moveGuideEndpoint(state.points, index,
    [point[0] + direction[0] * step, point[1] + direction[1] * step], state.width, state.height);
  invalidateResults();
  drawGuide();
  emitPoints();
});

window.addEventListener("message", event => {
  if (event.source === window.parent && event.data?.type === "gel:viewport") {
    if (Number.isFinite(event.data.height) && event.data.height > 0) {
      window.gelPreviewHeight = event.data.height;
      scheduleFit();
    }
    return;
  }
  if (event.source !== window.parent || event.data?.type !== "streamlit:render") return;
  const args = event.data.args;
  if (!args || typeof args.token !== "string" || !(args.width > 0 && args.height > 0)) return;
  if (event.data.theme?.textColor) document.documentElement.style.setProperty("--text-color", event.data.theme.textColor);
  if (event.data.theme?.backgroundColor) document.body.style.backgroundColor = event.data.theme.backgroundColor;
  if (!state || args.token !== state.token) {
    if (seenTokens.has(args.token)) return; // Delayed renders cannot revive old geometry.
    seenTokens.add(args.token);
    drag = null;
    svg.dataset.dragging = "false";
    state = {token: args.token, width: args.width, height: args.height,
      points: readPoints(args.points, args.width, args.height),
      reviewMode: ["borders", "extent"].includes(args.review_mode) ? args.review_mode : null,
      lanes: Array.isArray(args.lanes) ? args.lanes.map(lane => [...lane]) : [],
      wells: Array.isArray(args.wells) ? args.wells.map(well => ({...well, bounds: [...well.bounds]})) : [],
      rightEdge: Number.isInteger(args.right_edge) ? args.right_edge : (args.lanes?.[0]?.[2] ?? args.width)};
    svg.dataset.token = args.token;
    svg.setAttribute("viewBox", `0 0 ${args.width} ${args.height}`);
    svg.setAttribute("width", args.width);
    svg.setAttribute("height", args.height);
    image.setAttribute("width", args.width);
    image.setAttribute("height", args.height);
    image.setAttribute("href", args.image_src);
    review.reset();
  }
  // A frozen result can only become editable again with a new token. Ignore
  // editable renders that were queued before confirmation completed.
  if (!state.reviewMode && state.editable === false && args.editable) return;
  state.editable = Boolean(args.editable);
  if (!state.reviewMode) {
    if (!state.editable) {
      // Detection may finish after another local edit. Its confirmed guide is
      // authoritative so the corresponding outlines remain visible.
      const pointerId = drag?.pointerId;
      drag = null;
      svg.dataset.dragging = "false";
      if (pointerId !== undefined && svg.hasPointerCapture(pointerId)) svg.releasePointerCapture(pointerId);
      state.points = readPoints(args.points, state.width, state.height);
    }
    // While editing, preserve local points against older snapshots from reruns.
    const matchingPoints = JSON.stringify(readPoints(args.points, state.width, state.height)) === JSON.stringify(state.points);
    state.wells = !drag && matchingPoints && Array.isArray(args.wells) ? args.wells : [];
    state.lanes = !drag && matchingPoints && Array.isArray(args.lanes) ? args.lanes : [];
  }
  repaint();
  requestAnimationFrame(resizeFrame);
});

// Observe only width changes. The iframe height is an output of this layout;
// using its height as another input would cause repeated shrinking and reruns.
let observedWidth = -1;
const observer = new ResizeObserver(entries => {
  const width = entries[0]?.contentRect.width;
  if (width !== observedWidth) {
    observedWidth = width;
    scheduleFit();
  }
});
observer.observe(component);

const resizeTargets = new Set([window]);
try {
  resizeTargets.add(window.parent);
  if (window.parent.visualViewport) resizeTargets.add(window.parent.visualViewport);
} catch { /* Parent viewport access can be unavailable across origins. */ }
for (const target of resizeTargets) {
  try { target.addEventListener("resize", scheduleFit); } catch { /* Cross-origin parent. */ }
}
window.addEventListener("pagehide", () => {
  observer.disconnect();
  if (fitFrame) cancelAnimationFrame(fitFrame);
  for (const target of resizeTargets) {
    try { target.removeEventListener("resize", scheduleFit); } catch { /* Cross-origin parent. */ }
  }
});

post("streamlit:componentReady", {apiVersion: 1});
resizeFrame();
