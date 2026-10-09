import {clipPoint, pointerToImage, readPoints, screenRadius} from "./geometry.mjs";
import {createLaneReview} from "./lane_review.mjs";

// Streamlit's documented v1 component postMessage protocol. No CDN, external
// runtime, network service, or image processing is used in this iframe.
const svg = document.getElementById("gel");
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
const review = createLaneReview({svg, getState: () => state, pointerPosition,
  repaint, emit: emitEvent});

function post(type, data = {}) {
  window.parent.postMessage({isStreamlitMessage: true, type, ...data}, "*");
}

function resizeFrame() {
  const height = Math.ceil(document.getElementById("component").getBoundingClientRect().height);
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
  drawGuide();
  drawResults();
  review.draw();
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
    handle.setAttribute("aria-label", `Endpoint ${index + 1}, x ${point[0].toFixed(1)}, y ${point[1].toFixed(1)}. Use arrow keys to adjust; Shift moves ten pixels.`);
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
  status.textContent = state.reviewMode === "borders"
    ? "Adjust each lane’s top and bottom border using the arrow handles. Use Up/Down keys on a focused handle. Delete a lane with the trash button on its right, or use Add lane below to insert one at the bottom of the detection line."
    : state.reviewMode === "extent"
    ? "Drag the gold right boundary left or right to choose a shared lane length. The shaded region will be excluded. Use Left/Right keys on the handle."
    : !state.editable
    ? "Detected wells and horizontal lanes. Choose Edit well line to adjust the selection."
    : state.points.length === 0
      ? "Click the top edge of the first well and the bottom edge of the last well, in either order."
      : state.points.length === 1
        ? "Click the other end of the well range. Drag either dot to adjust its position."
        : "Drag the dots so the dotted line passes through the well centers, then confirm below. Arrow keys also adjust a focused dot.";
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
    drag = {index, pointerId: event.pointerId, original: [...state.points[index]],
      wells: state.wells, lanes: state.lanes};
    svg.setPointerCapture(event.pointerId);
    svg.dataset.dragging = "true";
  } else if (state.points.length < 2) {
    const point = pointerPosition(event);
    if (!point) return;
    event.preventDefault();
    state.points.push(point);
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
  state.points[drag.index] = point;
  drawGuide(); // The bridge is deliberately silent until pointerup.
});

function finishDrag(event, cancelled) {
  if (!drag || event.pointerId !== drag.pointerId) return;
  const active = drag;
  drag = null;
  svg.dataset.dragging = "false";
  if (cancelled) {
    state.points[active.index] = active.original;
    state.wells = active.wells;
    state.lanes = active.lanes;
    drawResults();
  } else {
    state.points[active.index] = pointerPosition(event) || state.points[active.index];
    if (state.points[active.index].some((coordinate, index) => coordinate !== active.original[index])) invalidateResults();
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
  state.points[index] = clipPoint([point[0] + direction[0] * step, point[1] + direction[1] * step], state.width, state.height);
  invalidateResults();
  drawGuide();
  emitPoints();
});

window.addEventListener("message", event => {
  if (event.source !== window.parent || event.data?.type !== "streamlit:render") return;
  const args = event.data.args;
  if (!args || typeof args.token !== "string" || !(args.width > 0 && args.height > 0)) return;
  if (event.data.theme?.textColor) document.documentElement.style.setProperty("--text-color", event.data.theme.textColor);
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
    wrap.style.maxWidth = `${args.width}px`;
    image.setAttribute("width", args.width);
    image.setAttribute("height", args.height);
    image.setAttribute("href", args.image_src);
    review.reset();
  }
  // Never overwrite local points for an existing token: a rerun can carry an
  // older snapshot while the pointer is down. Results may update independently.
  state.editable = Boolean(args.editable);
  if (!state.reviewMode) {
    const matchingPoints = JSON.stringify(readPoints(args.points, state.width, state.height)) === JSON.stringify(state.points);
    state.wells = !drag && matchingPoints && Array.isArray(args.wells) ? args.wells : [];
    state.lanes = !drag && matchingPoints && Array.isArray(args.lanes) ? args.lanes : [];
  }
  if (!state.editable && drag) {
    state.points[drag.index] = drag.original;
    drag = null;
    svg.dataset.dragging = "false";
  }
  repaint();
  requestAnimationFrame(resizeFrame);
});

new ResizeObserver(() => {
  repaint();
  resizeFrame();
}).observe(document.getElementById("component"));

post("streamlit:componentReady", {apiVersion: 1});
resizeFrame();
