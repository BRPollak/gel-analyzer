import {axes, drawRectangle, fitPreviewGeometry, moveRectangle, nearestHandle, outerViewportHeight, outerViewportReserve,
  pointerToImage, readSelection, rectangleCorners, resizeRectangle, rotateRectangle,
  rotationHandle, sameSelection, screenRadius} from "./geometry.mjs";

/** Dependency-free Streamlit v1 bridge; exported for interaction tests. */
export function createOrientationEditor({document: doc, window: host}) {
  const ids = ["gel", "component", "gel-image", "image-wrap", "status", "feedback", "caption", "toolbar",
    "selection", "top-edge", "top-label", "rotation-line", "rotation", "draw-new", "angle", "rotate-left", "rotate-right"];
  const nodes = Object.fromEntries(ids.map(id => [id, doc.getElementById(id)]));
  const svg = nodes.gel;
  const corners = [0, 1, 2, 3].map(index => doc.getElementById(`corner-${index}`));
  const seenTokens = new Set();
  let state = null, drag = null, revision = 0, drawMode = false;
  let frameHeight = 0, fitFrame = 0;

  function post(type, data = {}) {
    host.parent.postMessage({isStreamlitMessage: true, type, ...data}, "*");
  }
  function emit() {
    if (!state) return;
    revision = Math.max(revision + 1, Date.now() * 1000);
    svg.dataset.revision = String(revision);
    post("streamlit:setComponentValue", {dataType: "json", value: {
      token: state.token, revision, selection: state.selection ? {...state.selection} : null,
    }});
  }
  function resizeFrame() {
    const height = Math.ceil(nodes.component.getBoundingClientRect().height);
    if (height !== frameHeight) {
      frameHeight = height;
      post("streamlit:setFrameHeight", {height});
    }
  }
  function scheduleFit() {
    if (fitFrame) return;
    fitFrame = host.requestAnimationFrame(() => {
      fitFrame = 0;
      repaint();
    });
  }
  function feedback(message = "") {
    if (nodes.feedback.textContent === message) return;
    nodes.feedback.textContent = message;
    scheduleFit();
  }
  function fitPreview() {
    const chromeHeight = ["caption", "toolbar", "status", "feedback"].reduce((sum, id) =>
      sum + nodes[id].getBoundingClientRect().height, 0) + 28;
    const fit = fitPreviewGeometry({imageWidth: state.width, imageHeight: state.height,
      availableWidth: Math.max(1, nodes.component.clientWidth),
      viewportHeight: outerViewportHeight(host), outerReserve: outerViewportReserve(host), chromeHeight});
    nodes["image-wrap"].style.width = `${fit.wrapperWidth}px`;
    nodes["image-wrap"].dataset.previewScale = String(fit.scale);
  }
  function attrs(node, values) {
    for (const [key, value] of Object.entries(values)) node.setAttribute(key, value);
  }
  function line(node, first, second) {
    attrs(node, {x1: first[0], y1: first[1], x2: second[0], y2: second[1]});
  }
  function handle(node, point, radius, unit, label) {
    attrs(node, {transform: `translate(${point[0]} ${point[1]})`, "aria-label": label});
    attrs(node.querySelector(".hit"), {r: 17 * unit});
    attrs(node.querySelector(".dot"), {r: radius * unit});
  }
  function repaint() {
    if (!state) return;
    const selection = state.selection;
    const visible = Boolean(selection);
    const instructions = visible && !drawMode
      ? "Drag inside to move, corners to resize, or the round arrow to rotate. Arrow keys adjust a focused handle; Shift uses larger steps. The marked edge becomes the top of the finished image."
      : "Press and drag on the image to draw a rectangle. The marked edge becomes the top of the finished image.";
    nodes.status.textContent = instructions;
    fitPreview();
    const unit = screenRadius(1, svg.getBoundingClientRect(), state.width);
    for (const node of [nodes.selection, nodes["top-edge"], nodes["top-label"], nodes["rotation-line"], nodes.rotation, ...corners]) {
      node.setAttribute("visibility", visible ? "visible" : "hidden");
    }
    for (const node of [nodes.selection, nodes.rotation, ...corners]) node.setAttribute("tabindex", visible ? "0" : "-1");
    for (const id of ["angle", "rotate-left", "rotate-right"]) nodes[id].disabled = !visible || Boolean(drag);
    nodes["draw-new"].disabled = Boolean(drag);
    nodes["draw-new"].setAttribute("aria-pressed", String(drawMode));
    svg.dataset.dragging = String(Boolean(drag));
    svg.dataset.drawMode = String(drawMode);
    svg.dataset.hasSelection = String(visible);
    if (selection) {
      const points = rectangleCorners(selection);
      attrs(nodes.selection, {points: points.map(point => point.join(",")).join(" "),
        "aria-label": "Move rectangle. Use arrow keys to move; Alt and arrow keys rotate; Shift uses larger steps."});
      const topMode = state.workflow_orientation === "wells_top";
      line(nodes["top-edge"], points[topMode ? 0 : 3], points[topMode ? 1 : 0]);
      const {edge, point} = rotationHandle(selection, unit);
      const [u, v] = axes(selection);
      const labelEdge = topMode ? [(points[0][0] + points[1][0]) / 2, (points[0][1] + points[1][1]) / 2] : edge;
      const inward = topMode ? v : u;
      attrs(nodes["top-label"], {x: labelEdge[0] + inward[0] * 16 * unit,
        y: labelEdge[1] + inward[1] * 16 * unit, "font-size": 10 * unit, "stroke-width": 3 * unit});
      line(nodes["rotation-line"], edge, point);
      corners.forEach((node, index) => handle(node, points[index], 6, unit,
        `Resize corner ${index + 1}. Use arrow keys; hold Shift for larger steps.`));
      handle(nodes.rotation, point, 10, unit, "Rotate rectangle. Use arrow keys to rotate one degree; Shift rotates ten degrees.");
      attrs(nodes.rotation.querySelector(".rotation-symbol"), {"font-size": 17 * unit});
      if (doc.activeElement !== nodes.angle) nodes.angle.value = String(Math.round(selection.angle_degrees * 100) / 100);
    } else nodes.angle.value = "";
    resizeFrame();
  }
  function pointerPosition(event, clip = true) {
    return pointerToImage(event.clientX, event.clientY, svg.getBoundingClientRect(), state.width, state.height, clip);
  }
  function applyRotation(degrees) {
    if (!state?.selection) return false;
    const candidate = rotateRectangle(state.selection, degrees, state.width, state.height);
    if (!candidate) {
      feedback("That angle places a corner outside the image. Move or shrink the rectangle before rotating further.");
      return false;
    }
    state.selection = candidate;
    feedback();
    return true;
  }
  function updateDrag(event) {
    if (!drag || event.pointerId !== drag.pointerId) return;
    const point = pointerPosition(event, drag.action === "draw" || drag.action === "move");
    if (!point) return;
    if (drag.action === "draw") state.selection = drawRectangle(drag.start, point);
    else if (drag.action === "move") state.selection = moveRectangle(drag.original,
      point[0] - drag.start[0], point[1] - drag.start[1], state.width, state.height);
    else if (drag.action === "resize") {
      const cornerPoint = rectangleCorners(drag.original)[drag.corner];
      state.selection = resizeRectangle(drag.original, drag.corner,
        [cornerPoint[0] + point[0] - drag.start[0], cornerPoint[1] + point[1] - drag.start[1]],
        state.width, state.height);
    }
    else {
      const angle = Math.atan2(point[1] - drag.original.cy, point[0] - drag.original.cx);
      applyRotation(drag.original.angle_degrees + (angle - drag.startAngle) * 180 / Math.PI);
    }
    repaint();
  }
  function finishDrag(event, cancelled) {
    if (!drag || event.pointerId !== drag.pointerId) return;
    if (!cancelled) updateDrag(event);
    const active = drag;
    drag = null;
    if (cancelled) state.selection = active.original;
    else if (active.action === "draw") {
      const unit = screenRadius(1, svg.getBoundingClientRect(), state.width);
      if (!state.selection || Math.min(state.selection.width, state.selection.height) < 4 * unit) {
        state.selection = active.original;
        feedback("Drag a larger rectangle to select the gel.");
      } else drawMode = false;
    }
    if (svg.hasPointerCapture(event.pointerId)) svg.releasePointerCapture(event.pointerId);
    repaint();
    if (!cancelled && !sameSelection(state.selection, active.original)) emit();
  }

  svg.addEventListener("pointerdown", event => {
    if (!state || drag || event.button !== 0) return;
    let target = event.target.closest("[data-action]");
    const rawPoint = pointerPosition(event, false);
    if (!rawPoint) return;
    if (!drawMode && state.selection) {
      const nearest = nearestHandle(state.selection, rawPoint, screenRadius(1, svg.getBoundingClientRect(), state.width));
      if (nearest) target = nearest.action === "rotate" ? nodes.rotation : corners[nearest.corner];
    }
    const action = !drawMode && state.selection && target ? target.dataset.action : "draw";
    const point = pointerPosition(event, action === "draw" || action === "move");
    if (!point) return;
    event.preventDefault();
    feedback();
    drag = {action, pointerId: event.pointerId, start: point, original: state.selection ? {...state.selection} : null,
      corner: Number(target?.dataset.corner), startAngle: state.selection
        ? Math.atan2(point[1] - state.selection.cy, point[0] - state.selection.cx) : 0};
    if (action === "draw") state.selection = null;
    else target.focus();
    svg.setPointerCapture(event.pointerId);
    repaint();
  });
  svg.addEventListener("pointermove", updateDrag);
  svg.addEventListener("pointerup", event => finishDrag(event, false));
  svg.addEventListener("pointercancel", event => finishDrag(event, true));
  svg.addEventListener("lostpointercapture", event => finishDrag(event, true));
  svg.addEventListener("keydown", event => {
    if (event.key === "Escape") {
      if (drag) finishDrag({pointerId: drag.pointerId}, true);
      drawMode = false;
      repaint();
      return;
    }
    if (!state?.selection || drag) return;
    const direction = {ArrowLeft: [-1, 0], ArrowRight: [1, 0], ArrowUp: [0, -1], ArrowDown: [0, 1]}[event.key];
    const target = event.target.closest("[data-action]");
    if (!direction || !target) return;
    event.preventDefault();
    const previous = {...state.selection};
    const step = event.shiftKey ? 10 : 1;
    if (target.dataset.action === "rotate" || event.altKey) {
      applyRotation(state.selection.angle_degrees + (direction[0] || direction[1]) * step);
    } else if (target.dataset.action === "resize") {
      const index = Number(target.dataset.corner), point = rectangleCorners(state.selection)[index];
      state.selection = resizeRectangle(state.selection, index,
        [point[0] + direction[0] * step, point[1] + direction[1] * step], state.width, state.height);
      feedback();
    } else {
      state.selection = moveRectangle(state.selection, direction[0] * step, direction[1] * step, state.width, state.height);
      feedback();
    }
    repaint();
    if (!sameSelection(previous, state.selection)) emit();
  });
  nodes["draw-new"].addEventListener("click", () => {
    if (!state || drag) return;
    const changed = state.selection !== null;
    state.selection = null;
    drawMode = true;
    feedback();
    repaint();
    if (changed) emit();
  });
  function rotateFromControl(degrees) {
    if (!state?.selection || drag) return;
    const previous = {...state.selection};
    if (Number.isFinite(degrees)) applyRotation(degrees);
    else feedback("Enter a number for the angle.");
    nodes.angle.value = String(Math.round(state.selection.angle_degrees * 100) / 100);
    repaint();
    if (!sameSelection(previous, state.selection)) emit();
  }
  nodes.angle.addEventListener("change", () => rotateFromControl(nodes.angle.value === "" ? NaN : Number(nodes.angle.value)));
  nodes["rotate-left"].addEventListener("click", () => rotateFromControl(state?.selection?.angle_degrees - 90));
  nodes["rotate-right"].addEventListener("click", () => rotateFromControl(state?.selection?.angle_degrees + 90));

  function render(args, theme = null) {
    if (!args || typeof args.token !== "string" || !Number.isFinite(args.width) || !Number.isFinite(args.height) || args.width <= 0 || args.height <= 0) return;
    const incomingRevision = Number.isSafeInteger(args.revision) && args.revision >= 0 ? args.revision : 0;
    if (!state || args.token !== state.token) {
      if (seenTokens.has(args.token)) return;
      if (drag) finishDrag({pointerId: drag.pointerId}, true);
      seenTokens.add(args.token);
      state = {token: args.token, width: args.width, height: args.height,
        selection: readSelection(args.selection, args.width, args.height)};
      revision = incomingRevision;
      drawMode = !state.selection;
      feedback();
    } else if (!drag && incomingRevision >= revision) {
      state.selection = readSelection(args.selection, state.width, state.height);
      revision = incomingRevision;
    }
    state.workflow_orientation = args.workflow_orientation || "wells_left";
    if (theme?.textColor) doc.documentElement.style.setProperty("--text-color", theme.textColor);
    if (theme?.backgroundColor) doc.body.style.backgroundColor = theme.backgroundColor;
    attrs(svg, {viewBox: `0 0 ${state.width} ${state.height}`});
    attrs(nodes["gel-image"], {width: state.width, height: state.height, href: args.image_src});
    svg.dataset.token = state.token;
    svg.dataset.revision = String(revision);
    repaint();
  }
  host.addEventListener("message", event => {
    if (event.source === host.parent && event.data?.type === "gel:viewport") {
      if (Number.isFinite(event.data.height) && event.data.height > 0) {
        host.gelPreviewHeight = event.data.height;
        scheduleFit();
      }
      return;
    }
    if (event.source === host.parent && event.data?.type === "streamlit:render") render(event.data.args, event.data.theme);
  });
  host.addEventListener("resize", scheduleFit);
  host.visualViewport?.addEventListener("resize", scheduleFit);
  try {
    if (host.parent !== host) {
      host.parent.addEventListener("resize", scheduleFit);
      host.parent.visualViewport?.addEventListener("resize", scheduleFit);
    }
  } catch { /* Cross-origin parent window; own resize still works. */ }
  if (host.ResizeObserver) {
    let previousWidth = -1;
    new host.ResizeObserver(() => {
      const width = nodes.component.clientWidth;
      if (width !== previousWidth) { previousWidth = width; scheduleFit(); }
    }).observe(nodes.component);
  }
  post("streamlit:componentReady", {apiVersion: 1});
  return {render, getSelection: () => state?.selection ? {...state.selection} : null,
    getRevision: () => revision};
}

if (typeof document !== "undefined" && typeof window !== "undefined") {
  createOrientationEditor({document, window});
}
