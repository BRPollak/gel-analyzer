import {laneAxisState, swapBounds, swapPoint, clampRightEdge, laneBorderLimits, laneDeleteLayout, lanePositionLimits, moveLaneBorder, moveLanePosition, nearestHandle, screenRadius, wellsWithLaneBorders} from "./geometry.mjs";

/** Axis-constrained review interactions, independent of the guide editor. */
export function createLaneReview({svg, getState: displayState, pointerPosition: displayPointerPosition, repaint, emit}) {
  const isTop = () => displayState()?.workflowOrientation === "wells_top";
  const getState = () => laneAxisState(displayState());
  const pointXY = point => isTop() ? swapPoint(point) : point;
  const pointerPosition = event => {
    const point = displayPointerPosition(event);
    return point && pointXY(point);
  };
  const eventLanes = lanes => lanes.map(lane => isTop() ? swapBounds(lane) : [...lane]);
  const lineXY = points => isTop() ? {x1: points.y1, y1: points.x1, x2: points.y2, y2: points.x2} : points;
  const layer = document.getElementById("lane-review");
  const excluded = document.getElementById("excluded-right");
  const wrap = document.getElementById("image-wrap");
  let handles = [];
  let deleteButtons = [];
  let deletionPending = false;
  let active = null;
  let bodyLayer = null;
  let lineLayer = null;

  const isBoundary = () => ["boundary_first", "boundary_last"].includes(getState()?.reviewMode);

  function element(name, attributes, parent = layer) {
    const node = document.createElementNS("http://www.w3.org/2000/svg", name);
    for (const [key, value] of Object.entries(attributes)) node.setAttribute(key, value);
    parent.appendChild(node);
    return node;
  }

  function makeHandle(index, edge) {
    const position = edge === "position";
    const group = element("g", {class: `review-handle ${edge === "right" ? "extent-handle" : position ? "position-handle" : "border-handle"}${isBoundary() ? " boundary-active" : ""}`,
      "data-review-edge": edge, "data-lane-index": index,
      "data-testid": edge === "right" ? "lane-right-edge" : `lane-${index + 1}-${edge}`,
      role: "slider", tabindex: "0", "aria-orientation": (edge === "right") !== isTop() ? "horizontal" : "vertical"});
    // All line hit regions sit behind every grip, so even a one-pixel-high
    // lane keeps its top and bottom grips independently reachable.
    const line = position ? null : element("line", {class: `review-line ${edge === "right" ? "extent-line" : ""}${isBoundary() ? " boundary-active" : ""}`,
      "pointer-events": "none"}, lineLayer);
    const hit = element(position ? "rect" : "line", {class: position ? "review-body position-handle" : `review-hit ${edge === "right" ? "extent-handle" : "border-handle"}`,
      "data-review-edge": edge, "data-lane-index": index}, position ? bodyLayer : lineLayer);
    const gripHit = element("circle", {fill: "transparent"}, group);
    const grip = element("circle", {class: "review-grip", "pointer-events": "none"}, group);
    const symbol = element("path", {class: "review-symbol"}, group);
    return {group, line, hit, grip, gripHit, symbol, index, edge};
  }

  function makeDeleteButton(index) {
    const connector = element("line", {class: "delete-connector", "pointer-events": "none"});
    const group = element("g", {class: "lane-delete", "data-delete-lane": index,
      "data-testid": `lane-${index + 1}-delete`, role: "button", tabindex: "0",
      "aria-label": `Delete lane ${index + 1}`});
    element("rect", {x: -16, y: -16, width: 32, height: 32, rx: 5, class: "delete-background"}, group);
    element("path", {d: "M-7 -5 H7 M-3 -5 V-8 H3 V-5 M-5 -5 L-4 8 H4 L5 -5 M-2 -2 V5 M2 -2 V5",
      class: "delete-symbol", "pointer-events": "none"}, group);
    const title = element("title", {}, group);
    title.textContent = `Delete lane ${index + 1}`;
    return {group, connector, index};
  }

  function reset() {
    const pointerId = active?.pointerId;
    active = null;
    if (pointerId !== undefined && svg.hasPointerCapture(pointerId)) svg.releasePointerCapture(pointerId);
    layer.replaceChildren();
    bodyLayer = element("g", {"data-testid": "lane-review-bodies"});
    lineLayer = element("g", {"data-testid": "lane-review-lines"});
    handles = [];
    deleteButtons = [];
    deletionPending = false;
    wrap.style.paddingBottom = "0px";
    wrap.style.paddingRight = "0px";
    excluded.setAttribute("visibility", "hidden");
    const state = getState();
    if (state?.reviewMode === "borders") {
      state.lanes.forEach((lane, index) => {
        handles.push(makeHandle(index, "top"), makeHandle(index, "bottom"));
      });
      // Trash controls sit above all draggable hit regions in the SVG stack.
      state.lanes.forEach((lane, index) => deleteButtons.push(makeDeleteButton(index)));
    } else if (state?.reviewMode === "extent") handles.push(makeHandle(-1, "right"));
    else if (state?.reviewMode === "boundary_first" && state.lanes.length) {
      handles.push(makeHandle(0, "position"), makeHandle(0, "top"), makeHandle(0, "bottom"));
    } else if (state?.reviewMode === "boundary_last" && state.lanes.length === 2) {
      handles.push(makeHandle(1, "position"));
    }
  }

  function draw() {
    const state = getState();
    if (!state?.reviewMode) return;
    const unit = screenRadius(1, svg.getBoundingClientRect(), displayState().width);
    const enabled = state.editable && !deletionPending;
    svg.dataset.reviewPending = String(deletionPending);
    if (state.reviewMode === "borders") {
      const layout = laneDeleteLayout(state.lanes, state.height, unit);
      // On a thumbnail, extend the control column below the image instead of
      // shrinking or overlapping the trash targets. Keep that space in-frame.
      wrap.style.paddingBottom = `${isTop() ? 40 : layout.overflow / unit}px`;
      wrap.style.paddingRight = `${isTop() ? layout.overflow / unit : 40}px`;
      deleteButtons.forEach(({group, connector, index}) => {
        const canonical = layout.buttons[index];
        const [x, y] = pointXY([canonical.x, canonical.y]);
        const lane = state.lanes[index];
        group.setAttribute("transform", `translate(${x} ${y}) scale(${unit})`);
        group.setAttribute("tabindex", enabled ? "0" : "-1");
        group.setAttribute("aria-disabled", String(!enabled));
        for (const [attribute, coordinate] of Object.entries(lineXY({x1: lane[2],
          y1: (lane[1] + lane[3]) / 2, x2: canonical.x - 16 * unit, y2: canonical.y}))) {
          connector.setAttribute(attribute, coordinate);
        }
      });
    }
    if (state.reviewMode === "extent") {
      excluded.setAttribute("visibility", "visible");
      excluded.setAttribute("x", isTop() ? 0 : state.rightEdge);
      excluded.setAttribute("y", isTop() ? state.rightEdge : 0);
      excluded.setAttribute("width", isTop() ? state.height : state.width - state.rightEdge);
      excluded.setAttribute("height", isTop() ? state.width - state.rightEdge : state.height);
      excluded.dataset.rightEdge = state.rightEdge;
    }
    handles.forEach(handle => {
      const {group, line, hit, grip, gripHit, symbol, index, edge} = handle;
      let x, y, limits, value;
      let linePoints;
      if (edge === "right") {
        x = state.rightEdge;
        y = state.height / 2;
        limits = [clampRightEdge(0, state.wells, state.width), state.width];
        value = x;
        linePoints = {x1: x, y1: 0, x2: x, y2: state.height};
      } else if (edge === "position") {
        const lane = state.lanes[index];
        x = (lane[0] + lane[2]) / 2;
        y = (lane[1] + lane[3]) / 2;
        limits = lanePositionLimits(lane, state.height);
        value = y;
        const bounds = isTop() ? swapBounds(lane) : lane;
        for (const [attribute, coordinate] of Object.entries({x: bounds[0], y: bounds[1],
          width: bounds[2] - bounds[0], height: bounds[3] - bounds[1]})) hit.setAttribute(attribute, coordinate);
      } else {
        const lane = state.lanes[index];
        x = lane[0] + (lane[2] - lane[0]) * (edge === "top" ? 1 / 3 : 2 / 3);
        y = lane[edge === "top" ? 1 : 3];
        limits = laneBorderLimits(state.lanes, index, edge, state.height);
        value = y;
        linePoints = {x1: lane[0], y1: y, x2: lane[2], y2: y};
      }
      for (const node of line ? [line, hit] : []) {
        for (const [attribute, coordinate] of Object.entries(lineXY(linePoints))) node.setAttribute(attribute, coordinate);
      }
      [x, y] = pointXY([x, y]);
      for (const node of [grip, gripHit]) {
        node.setAttribute("cx", x);
        node.setAttribute("cy", y);
        node.setAttribute("r", (node === grip ? 7 : 15) * unit);
      }
      // Direction arrows distinguish top/bottom grips even when a lane is thin.
      symbol.setAttribute("transform", `translate(${x} ${y}) scale(${unit})${isTop() ? " rotate(90)" : ""}`);
      symbol.setAttribute("d", edge === "right"
        ? "M-5 0 L-1 -3 L-1 3 Z M5 0 L1 -3 L1 3 Z"
        : edge === "position" ? "M0 -5 L-3 -1 L3 -1 Z M0 5 L-3 1 L3 1 Z"
        : edge === "top" ? "M-4 -2 L4 -2 L0 3 Z" : "M-4 2 L4 2 L0 -3 Z");
      group.dataset.x = x;
      group.dataset.y = y;
      group.dataset.value = value;
      group.setAttribute("tabindex", enabled ? "0" : "-1");
      group.setAttribute("aria-disabled", String(!enabled));
      group.setAttribute("aria-valuemin", limits[0]);
      group.setAttribute("aria-valuemax", limits[1]);
      group.setAttribute("aria-valuenow", value);
      group.setAttribute("aria-label", edge === "right"
        ? (isTop() ? "Shared bottom boundary. Use Up and Down arrows; Shift moves ten pixels." : "Shared right boundary. Use Left and Right arrows; Shift moves ten pixels.")
        : edge === "position"
        ? `${index === 0 ? "First" : "Last"} boundary well position. Use ${isTop() ? "Left and Right" : "Up and Down"} arrows; Shift moves ten pixels.`
        : (isTop() ? `Lane ${index + 1} ${edge === "top" ? "left" : "right"} boundary. Use Left and Right arrows; Shift moves ten pixels.`
          : `Lane ${index + 1} ${edge} boundary. Use Up and Down arrows; Shift moves ten pixels.`));
    });
  }

  function update(index, edge, coordinate) {
    const state = getState();
    if (edge === "right") {
      state.rightEdge = clampRightEdge(coordinate, state.wells, state.width);
      state.lanes = state.lanes.map(lane => [lane[0], lane[1], state.rightEdge, lane[3]]);
    } else if (edge === "position") {
      state.lanes = moveLanePosition(state.lanes, index, coordinate, state.height);
      state.wells = wellsWithLaneBorders(state.wells, state.lanes);
    } else {
      state.lanes = moveLaneBorder(state.lanes, index, edge, coordinate, state.height);
      state.wells = wellsWithLaneBorders(state.wells, state.lanes);
    }
    repaint();
  }

  function commit() {
    const state = getState();
    emit({kind: "lane_review", mode: state.reviewMode,
      lanes: eventLanes(state.lanes), right_edge: state.rightEdge});
  }

  function deleteLane(button) {
    const state = getState();
    if (state?.reviewMode !== "borders" || !state.editable || deletionPending || active) return;
    const index = Number(button.dataset.deleteLane);
    if (!Number.isInteger(index) || index < 0 || index >= state.lanes.length) return;
    deletionPending = true;
    draw();
    emit({kind: "lane_review", mode: "borders", action: "delete", lane_index: index,
      lanes: eventLanes(state.lanes), right_edge: state.rightEdge});
  }

  svg.addEventListener("click", event => {
    const button = event.target.closest("[data-delete-lane]");
    if (!button) return;
    event.preventDefault();
    deleteLane(button);
  });

  svg.addEventListener("pointerdown", event => {
    const state = getState();
    if (!state?.reviewMode || !state.editable || deletionPending || event.button !== 0 || active) return;
    const deleteButton = event.target.closest("[data-delete-lane]");
    if (deleteButton) {
      event.preventDefault();
      deleteButton.focus();
      return;
    }
    const point = pointerPosition(event);
    const nearest = point && nearestHandle(handles.map(handle => ({
      handle, x: pointXY([Number(handle.group.dataset.x), Number(handle.group.dataset.y)])[0],
      y: pointXY([Number(handle.group.dataset.x), Number(handle.group.dataset.y)])[1],
    })), point, screenRadius(15, svg.getBoundingClientRect(), displayState().width));
    const handle = nearest ? nearest.handle.group : event.target.closest("[data-review-edge]");
    if (!handle || !point) return;
    event.preventDefault();
    const index = Number(handle.dataset.laneIndex);
    const edge = handle.dataset.reviewEdge;
    if (!handles.some(item => item.index === index && item.edge === edge)) return;
    handles.find(item => item.index === index && item.edge === edge)?.group.focus();
    const value = edge === "right" ? state.rightEdge : edge === "position"
      ? (state.lanes[index][1] + state.lanes[index][3]) / 2 : state.lanes[index][edge === "top" ? 1 : 3];
    active = {index, edge,
      offset: point[edge === "right" ? 0 : 1] - value,
      pointerId: event.pointerId, lanes: state.lanes, wells: state.wells, rightEdge: state.rightEdge};
    svg.setPointerCapture(event.pointerId);
    svg.dataset.dragging = "true";
  });

  svg.addEventListener("pointermove", event => {
    if (!active || event.pointerId !== active.pointerId || !getState()?.editable) return;
    const point = pointerPosition(event);
    if (point) update(active.index, active.edge, point[active.edge === "right" ? 0 : 1] - active.offset);
  });

  function finish(event, cancelled) {
    if (!active || event.pointerId !== active.pointerId) return;
    const prior = active;
    active = null;
    cancelled ||= !getState()?.editable;
    svg.dataset.dragging = "false";
    if (cancelled) {
      Object.assign(getState(), {lanes: prior.lanes, wells: prior.wells, rightEdge: prior.rightEdge});
      repaint();
    } else {
      const point = pointerPosition(event);
      if (point) update(prior.index, prior.edge, point[prior.edge === "right" ? 0 : 1] - prior.offset);
    }
    if (svg.hasPointerCapture(event.pointerId)) svg.releasePointerCapture(event.pointerId);
    if (!cancelled) commit();
  }
  svg.addEventListener("pointerup", event => finish(event, false));
  svg.addEventListener("pointercancel", event => finish(event, true));
  svg.addEventListener("lostpointercapture", event => finish(event, true));

  svg.addEventListener("keydown", event => {
    const state = getState();
    if (!state?.reviewMode || !state.editable || deletionPending || active) return;
    const deleteButton = event.target.closest("[data-delete-lane]");
    if (deleteButton) {
      if (event.key === "Enter" || event.key === " ") {
        event.preventDefault();
        if (!event.repeat) deleteLane(deleteButton);
      }
      return;
    }
    const handle = event.target.closest("[data-review-edge]");
    if (!handle) return;
    const edge = handle.dataset.reviewEdge;
    const index = Number(handle.dataset.laneIndex);
    if (!handles.some(item => item.index === index && item.edge === edge)) return;
    const direction = ((edge === "right") !== isTop() ? {ArrowLeft: -1, ArrowRight: 1} : {ArrowUp: -1, ArrowDown: 1})[event.key];
    if (!direction) return;
    event.preventDefault();
    const value = edge === "right" ? state.rightEdge : edge === "position"
      ? (state.lanes[index][1] + state.lanes[index][3]) / 2 : state.lanes[index][edge === "top" ? 1 : 3];
    update(index, edge, value + direction * (event.shiftKey ? 10 : 1));
    commit();
  });

  return {reset, draw};
}
