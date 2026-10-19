import {ladderImagePoint, laneAtPoint, movedPastTap, pointInImage, placeManualLadderMarker,
  removeManualLadderMarker, moveManualLadderCursor} from "./ladder_geometry.mjs";

const validLabel = label => Boolean(label.trim()) && label.length <= 200 && !/[\x00-\x1f\x7f\u2028\u2029]/.test(label);

/** Custom text uses the preset ladder gutter; only band locations are editable. */
export function createManualLadderEditor({getState, getLayout, canvas, editable, canConfirm, onChange, status}) {
  const byId = id => document.getElementById(id);
  const overlay = byId("ladder-overlay");
  const layer = byId("ladder-manual-points");
  const input = byId("ladder-manual-label");
  let draft = null;
  let moving = false;
  let pointer = null;
  let suppressClick = false;
  let error = "";
  const active = () => getState()?.mode === "ladder" && getState()?.ladder?.mode === "manual" && getState()?.ladderStep === "markers";
  const placements = () => getState()?.ladder?.placements ?? [];
  const top = () => getState()?.workflow_orientation === "wells_top";
  const directionKeys = () => top() ? ["ArrowUp", "ArrowDown"] : ["ArrowLeft", "ArrowRight"];
  const selected = () => placements().find(item => item.id === draft?.id);
  const dirty = () => draft && (!selected() || input.value !== selected().label);

  function changed(message) {
    onChange();
    render();
    if (canConfirm()) status(message);
  }

  function commit() {
    if (!dirty()) return true;
    if (!validLabel(input.value)) {
      error = "Enter a label on one line (up to 200 characters).";
      render();
      input.focus();
      return false;
    }
    const state = getState();
    const id = draft.id ?? globalThis.crypto?.randomUUID?.() ?? `marker-${Date.now()}-${Math.random().toString(36).slice(2)}`;
    const next = placeManualLadderMarker(state.ladder, id, input.value, draft.point, state.width, state.height);
    if (!next) { status("Click inside the gel image to place a marker.", true); return false; }
    state.ladder = next;
    draft = {id, point: {...draft.point}};
    input.value = next.placements.find(item => item.id === id).label;
    error = "";
    changed("Marker label saved. Click another ladder band to add a marker.");
    return true;
  }

  function select(id, focus = false) {
    if (!commit()) return false;
    const marker = placements().find(item => item.id === id);
    if (!marker) return false;
    draft = {id, point: {x: marker.x, y: marker.y}};
    input.value = marker.label;
    error = "";
    moving = false;
    render();
    if (focus) input.focus();
    return true;
  }

  function remove() {
    if (!editable() || !draft?.id) return;
    getState().ladder = removeManualLadderMarker(getState().ladder, draft.id);
    draft = null;
    moving = false;
    error = "";
    changed("Annotation deleted. Click a ladder band to add a marker label.");
    byId("ladder-heading").focus();
  }

  function markerId(target) {
    while (target && target !== overlay) {
      if (target.dataset?.manualId) return target.dataset.manualId;
      target = target.parentNode;
    }
    return null;
  }

  function element(name, attrs) {
    const node = document.createElementNS("http://www.w3.org/2000/svg", name);
    for (const [key, value] of Object.entries(attrs)) node.setAttribute(key, value);
    return node;
  }

  function draw() {
    layer.replaceChildren();
    const layout = getLayout();
    if (!active() || !layout) return;
    const scale = canvas.getBoundingClientRect().width / layout.width || 1;
    for (const marker of placements()) {
      const label = layout.ladderLabels?.find(item => item.id === marker.id);
      if (!label) continue;
      const group = element("g", {class: "manual-marker", "data-manual-id": marker.id,
        "data-selected": String(marker.id === draft?.id), tabindex: editable() ? 0 : -1,
        role: "button", "aria-label": `${marker.label}. Enter to edit; ${top() ? "Up and Down" : "Left and Right"} to reposition; Delete to remove.`});
      group.appendChild(element("rect", {x: label.left, y: label.top,
        width: label.right - label.left, height: label.bottom - label.top}));
      layer.appendChild(group);
    }
    // As with a preset, only the selected band has a temporary editing cursor.
    // All annotation text and dashes remain in the off-gel gutter.
    if (draft) {
      const state = getState();
      const lane = state.lanes[laneAtPoint(draft.point, state.lanes)] ?? [0, 0, state.width, state.height];
      const x = layout.gelX + draft.point.x, y = layout.gelY + draft.point.y;
      const cursor = element("g", {class: "manual-band-cursor", "data-manual-cursor": "true", "pointer-events": "none", "aria-hidden": "true"});
      cursor.appendChild(element("line", top()
        ? {x1: layout.gelX + lane[0], x2: layout.gelX + lane[2], y1: y, y2: y}
        : {x1: x, x2: x, y1: layout.gelY + lane[1], y2: layout.gelY + lane[3]}));
      cursor.appendChild(element("circle", {cx: x, cy: y, r: 5 / scale}));
      layer.appendChild(cursor);
    }
  }

  function render() {
    byId("ladder-manual-form").hidden = !active() || !draft;
    if (!active()) { layer.replaceChildren(); return; }
    byId("ladder-placement-hint").textContent = moving ? "Click the new position for this marker." : "Click a ladder band to add a marker label.";
    byId("ladder-marker-help").textContent = "Labels appear outside the gel, just like preset ladder markers. Select a label to edit or delete it. Choose Move marker, then click its new band.";
    byId("ladder-count").textContent = `${placements().length} marker${placements().length === 1 ? "" : "s"}`;
    byId("ladder-confirm").disabled = !editable() || !canConfirm() || (!placements().length && !draft);
    byId("ladder-manual-save").textContent = draft?.id ? "Save label" : "Add marker";
    byId("ladder-manual-move").hidden = !draft?.id;
    byId("ladder-manual-delete").hidden = !draft?.id;
    byId("ladder-manual-cancel").textContent = draft?.id ? "Done editing" : "Cancel label";
    byId("ladder-manual-error").textContent = error;
    byId("ladder-manual-error").hidden = !error;
    input.setAttribute("aria-invalid", String(Boolean(error)));
    const list = byId("ladder-markers");
    // Keep keyboard focus stable while the selected marker is being moved.
    const oldFocus = document.activeElement?.dataset?.manualId;
    list.replaceChildren();
    for (const marker of placements()) {
      const button = document.createElement("button");
      button.type = "button";
      button.className = "ladder-marker";
      button.dataset.manualId = marker.id;
      button.textContent = marker.label;
      button.setAttribute("aria-pressed", String(marker.id === draft?.id));
      button.addEventListener("click", () => { if (editable()) select(marker.id, true); });
      list.appendChild(button);
      if (oldFocus === marker.id) button.focus();
    }
    draw();
  }

  input.addEventListener("input", () => { error = ""; byId("ladder-manual-error").hidden = true; input.setAttribute("aria-invalid", "false"); });
  input.addEventListener("keydown", event => {
    if (event.key === "Enter" && !event.isComposing && editable()) { event.preventDefault(); commit(); }
  });
  byId("ladder-manual-save").addEventListener("click", () => { if (editable()) commit(); });
  byId("ladder-manual-delete").addEventListener("click", remove);
  byId("ladder-manual-move").addEventListener("click", () => {
    if (!editable() || !draft?.id || !commit()) return;
    moving = true;
    render();
    status("Click the new position for this marker.");
  });
  byId("ladder-manual-cancel").addEventListener("click", () => {
    if (!editable() || draft?.id && !commit()) return;
    draft = null;
    moving = false;
    error = "";
    render();
    status("Click a ladder band to add a marker label.");
  });
  overlay.addEventListener("click", event => {
    if (!active() || !editable() || event.button !== 0) return;
    if (suppressClick) { suppressClick = false; return; }
    const id = markerId(event.target);
    if (id) { select(id, true); return; }
    const state = getState();
    const point = ladderImagePoint(event.clientX, event.clientY, canvas.getBoundingClientRect(), getLayout());
    if (!pointInImage(point, state.width, state.height)) { status("Click inside the gel image to place a marker.", true); return; }
    if (moving && draft?.id) {
      state.ladder = placeManualLadderMarker(state.ladder, draft.id, selected().label, point, state.width, state.height);
      draft.point = point;
      moving = false;
      changed("Marker moved.");
      return;
    }
    // A second click can refine a pending position without discarding its text.
    if (draft && !draft.id) draft.point = point;
    else {
      if (!commit()) return;
      if (placements().length >= 200) { status("You can add up to 200 manual markers.", true); return; }
      draft = {id: null, point};
      input.value = "";
    }
    render();
    input.focus();
    status("Enter a marker label, then choose Add marker or press Enter.");
  });
  overlay.addEventListener("pointerdown", event => {
    if (!active()) return;
    if (event.isPrimary === false) return;
    suppressClick = false;
    if (!editable() || event.button !== 0) { suppressClick = true; return; }
    pointer = {id: event.pointerId, x: event.clientX, y: event.clientY};
  });
  overlay.addEventListener("pointermove", event => {
    if (active() && pointer?.id === event.pointerId && movedPastTap(pointer, event)) suppressClick = true;
  });
  overlay.addEventListener("pointerup", event => {
    if (!active() || pointer?.id !== event.pointerId) return;
    if (movedPastTap(pointer, event)) suppressClick = true;
    pointer = null;
  });
  overlay.addEventListener("pointercancel", event => {
    if (active() && pointer?.id === event.pointerId) { pointer = null; suppressClick = true; }
  });
  layer.addEventListener("keydown", event => {
    if (!active() || !editable()) return;
    const id = markerId(event.target);
    if (!id) return;
    if (event.key === "Enter") { event.preventDefault(); select(id, true); return; }
    if (!["Delete", "Backspace", ...directionKeys()].includes(event.key)) return;
    event.preventDefault();
    if (!select(id)) return;
    if (["Delete", "Backspace"].includes(event.key)) { remove(); return; }
    const state = getState();
    const point = moveManualLadderCursor(draft.point, event.key, event.shiftKey, state.width, state.height);
    state.ladder = placeManualLadderMarker(state.ladder, id, selected().label, point, state.width, state.height);
    draft.point = point;
    changed("Marker moved.");
    [...layer.children].find(node => node.dataset.manualId === id)?.focus();
  });
  return {render, commit, hasDraft: () => Boolean(draft), reset() {
    draft = null; moving = false; pointer = null; suppressClick = false; error = "";
  }};
}
