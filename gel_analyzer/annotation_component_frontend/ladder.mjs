import {cursorForMarker, ladderImagePoint, laneAtPoint, moveLadderCursor, movedPastTap, placeLadderMarker} from "./ladder_geometry.mjs";

/** Local interaction state lives outside the clean, exportable canvas. */
export function createLadderEditor({getState, getLayout, canvas, onChange, onAction, status, onLayout = () => {}}) {
  const byId = id => document.getElementById(id);
  const overlay = byId("ladder-overlay");
  const cursorNode = byId("ladder-cursor");
  const markerNodes = new Map();
  let selectedMarker = null;
  let cursor = null;
  let disabled = false;
  let previewError = false;
  let pendingChange = null;
  let pointer = null;
  let suppressClick = false;
  let presetSignature = "";
  let laneSignature = "";
  let markerSignature = "";
  let referenceSignature = "";
  let referenceVisible = true;
  let referenceFailed = false;

  const active = () => getState()?.mode === "ladder";
  const editable = () => active() && !disabled && !pendingChange;
  const placements = () => getState()?.ladder?.placements ?? [];
  const markerLabel = () => getState()?.ladder?.preset.labels[selectedMarker];
  const isPlaced = index => placements().some(item => item.markerIndex === index);

  function changed(message = "") {
    onChange();
    render();
    if (!previewError) status(message);
  }

  function go(step) {
    if (!editable()) return;
    getState().ladderStep = step;
    changed();
    byId("ladder-heading").focus();
  }

  function setPreset(preset) {
    const state = getState();
    state.ladder = {preset: {id: preset.id, name: preset.name, labels: [...preset.labels],
      ...(preset.referenceImage ? {referenceImage: preset.referenceImage} : {}),
      ...(preset.referenceNote ? {referenceNote: preset.referenceNote} : {})},
      laneIndex: state.ladder?.laneIndex ?? null, placements: []};
    selectedMarker = null;
    cursor = null;
    changed(`${preset.name} selected.`);
  }

  function setLane(index) {
    getState().ladder = {...getState().ladder, laneIndex: index, placements: []};
    cursor = selectedMarker === null ? null : cursorForMarker(getState().ladder, selectedMarker, getState().lanes);
    changed(`Lane ${index + 1} selected.`);
  }

  function guard(change) {
    pendingChange = change;
    render();
    byId("ladder-accept-change").focus();
    status(change.message);
  }

  function chooseLane(index) {
    const state = getState();
    if (!editable() || !state.ladder || !Number.isInteger(index) || !state.lanes[index]
      || state.ladder.laneIndex === index) return;
    if (placements().length) {
      guard({kind: "lane", index, message: "Changing the ladder lane clears its placed markers. Your lane labels and groups are kept."});
    } else setLane(index);
  }

  function selectMarker(index) {
    if (!editable()) return;
    selectedMarker = index;
    cursor = cursorForMarker(getState().ladder, index, getState().lanes);
    render();
    const label = markerLabel();
    status(isPlaced(index) ? `${label} selected. Click another band to move it, or choose Remove marker.`
      : `${label} selected. Click its band in the highlighted lane.`);
  }

  function place(point) {
    if (!editable() || selectedMarker === null) {
      if (editable()) status("Choose a size first.", true);
      return;
    }
    const state = getState();
    const next = placeLadderMarker(state.ladder, selectedMarker, point, state.lanes);
    if (!next) {
      status("Click inside the highlighted ladder lane.", true);
      return;
    }
    const moved = isPlaced(selectedMarker);
    state.ladder = next;
    cursor = {...point};
    changed(`${markerLabel()} ${moved ? "moved" : "placed"}. Select another size, or confirm your ladder annotations.`);
  }

  function options(select, values, placeholder) {
    select.replaceChildren();
    for (const value of [{value: "", label: placeholder}, ...values]) {
      const option = document.createElement("option");
      option.value = String(value.value);
      option.textContent = value.label;
      select.appendChild(option);
    }
  }

  function renderMarkers(state) {
    const labels = state.ladder?.preset.labels ?? [];
    const signature = JSON.stringify([state.ladder?.preset.id, labels]);
    if (signature !== markerSignature) {
      markerSignature = signature;
      markerNodes.clear();
      byId("ladder-markers").replaceChildren();
      labels.forEach((label, index) => {
        const button = document.createElement("button");
        button.type = "button";
        button.className = "ladder-marker";
        button.dataset.markerIndex = String(index);
        button.addEventListener("click", () => selectMarker(index));
        const text = document.createElement("span");
        text.textContent = label;
        const detail = document.createElement("span");
        detail.className = "ladder-marker-status";
        button.append(text, detail);
        byId("ladder-markers").appendChild(button);
        markerNodes.set(index, {button, detail});
      });
    }
    for (const [index, {button, detail}] of markerNodes) {
      const placed = isPlaced(index);
      const selected = index === selectedMarker;
      button.setAttribute("aria-pressed", String(selected));
      button.setAttribute("aria-label", `${labels[index]}: ${placed ? "placed" : "available"}${selected ? ", selected" : ""}`);
      button.dataset.placed = String(placed);
      detail.textContent = `${placed ? "✓ Placed" : "Available"}${selected ? " · Selected" : ""}`;
    }
    byId("ladder-placement-hint").textContent = selectedMarker === null
      ? "Choose a size, then click its band in the highlighted lane."
      : isPlaced(selectedMarker) ? `Click another band to move ${markerLabel()}.`
        : `Click the ${markerLabel()} band in the highlighted lane.`;
    byId("ladder-count").textContent = `${placements().length} of ${labels.length} sizes placed`;
    byId("ladder-remove-marker").hidden = selectedMarker === null || !isPlaced(selectedMarker);
  }

  function renderReference(state) {
    const preset = state?.ladder?.preset;
    // Old snapshots can use a configured photo only if the sizes still match.
    const reference = preset?.referenceImage ? preset : (state?.presets ?? []).find(item =>
      item.id === preset?.id && JSON.stringify(item.labels) === JSON.stringify(preset.labels));
    const available = active() && Boolean(reference?.referenceImage
      && /^ladder_references\/[a-zA-Z0-9_-]+\.(?:webp|gif|png|jpe?g)$/.test(reference.referenceImage));
    const signature = available ? JSON.stringify([preset.id, preset.name, preset.labels,
      reference.referenceImage, reference.referenceNote]) : "";
    if (signature !== referenceSignature) {
      referenceSignature = signature;
      referenceVisible = true;
      referenceFailed = false;
      if (byId("ladder-reference-dialog").open) byId("ladder-reference-dialog").close();
      if (available) {
        byId("ladder-reference-name").textContent = preset.name;
        byId("ladder-reference-dialog-title").textContent = preset.name;
        const alt = `${preset.name} band reference. Sizes from top to bottom: ${preset.labels.join(", ")}.`;
        for (const id of ["ladder-reference-image", "ladder-reference-large"]) {
          byId(id).alt = alt;
          byId(id).src = reference.referenceImage;
        }
        byId("ladder-reference-note").textContent = reference.referenceNote ?? "";
        byId("ladder-reference-note").hidden = !reference.referenceNote;
      } else {
        for (const id of ["ladder-reference-image", "ladder-reference-large"]) byId(id).removeAttribute("src");
      }
    }
    const visible = available && referenceVisible;
    byId("component").dataset.referenceOpen = String(visible);
    byId("ladder-reference").hidden = !visible;
    byId("ladder-reference-toggle").hidden = !available;
    byId("ladder-reference-toggle").textContent = visible ? "Hide reference" : "Show reference";
    byId("ladder-reference-toggle").setAttribute("aria-expanded", String(visible));
    byId("ladder-reference-image").hidden = referenceFailed;
    byId("ladder-reference-error").hidden = !referenceFailed;
    byId("ladder-reference-enlarge").disabled = referenceFailed;
    byId("ladder-reference-selected").textContent = selectedMarker === null ? ""
      : `Selected: ${markerLabel()}${isPlaced(selectedMarker) ? " · Placed" : ""}`;
  }

  function drawOverlay(state) {
    const layout = getLayout();
    const shown = active() && state.ladderStep !== "preset" && Boolean(layout);
    // SVG has no HTML hidden property behavior in some browser versions.
    overlay.removeAttribute("hidden");
    overlay.style.display = shown ? "block" : "none";
    if (!shown) return;
    overlay.setAttribute("viewBox", `0 0 ${layout.width} ${layout.height}`);
    overlay.dataset.step = state.ladderStep;
    const layer = byId("ladder-lane-outlines");
    layer.replaceChildren();
    state.lanes.forEach((lane, index) => {
      if (state.ladderStep === "markers" && index !== state.ladder?.laneIndex) return;
      const rect = document.createElementNS("http://www.w3.org/2000/svg", "rect");
      for (const [key, value] of Object.entries({x: layout.gelX + lane[0], y: layout.gelY + lane[1],
        width: lane[2] - lane[0], height: lane[3] - lane[1], class: "ladder-lane-outline",
        "data-selected": String(index === state.ladder?.laneIndex), "data-lane-index": index})) rect.setAttribute(key, value);
      layer.appendChild(rect);
    });
    const lane = state.lanes[state.ladder?.laneIndex];
    const showCursor = state.ladderStep === "markers" && selectedMarker !== null && cursor && lane;
    cursorNode.setAttribute("visibility", showCursor ? "visible" : "hidden");
    cursorNode.setAttribute("tabindex", showCursor && !disabled && !pendingChange ? "0" : "-1");
    cursorNode.setAttribute("aria-disabled", String(disabled || Boolean(pendingChange)));
    if (!showCursor) return;
    cursorNode.setAttribute("aria-label", `${markerLabel()} position. Left and Right move one pixel; Shift moves ten. Enter places the marker. Escape returns to its size button.`);
    cursorNode.setAttribute("aria-valuemin", lane[0]);
    cursorNode.setAttribute("aria-valuemax", lane[2]);
    cursorNode.setAttribute("aria-valuenow", cursor.x);
    cursorNode.setAttribute("aria-valuetext", `${cursor.x.toFixed(2)} pixels from the left of the gel`);
    const x = layout.gelX + cursor.x;
    const y = layout.gelY + cursor.y;
    const line = byId("ladder-cursor-line");
    for (const [key, value] of Object.entries({x1: x, x2: x, y1: layout.gelY + lane[1], y2: layout.gelY + lane[3]})) line.setAttribute(key, value);
    const radius = canvas.getBoundingClientRect().width > 0 ? 5 * layout.width / canvas.getBoundingClientRect().width : 5;
    for (const [key, value] of Object.entries({cx: x, cy: y, r: radius})) byId("ladder-cursor-dot").setAttribute(key, value);
  }

  function render() {
    const state = getState();
    byId("component").dataset.ladderStep = active() ? state.ladderStep ?? "preset" : "";
    byId("ladder-panel").hidden = !active();
    byId("ladder-actions").hidden = !active();
    renderReference(state);
    if (!active()) {
      overlay.removeAttribute("hidden");
      overlay.style.display = "none";
      return;
    }
    const step = state.ladderStep ?? "preset";
    const presets = state.presets ?? [];
    const choices = [...presets];
    if (state.ladder && !choices.some(preset => preset.id === state.ladder.preset.id)) choices.push(state.ladder.preset);
    const signature = JSON.stringify(choices.map(preset => [preset.id, preset.name]));
    if (signature !== presetSignature) {
      presetSignature = signature;
      options(byId("ladder-preset"), choices.map(preset => ({value: preset.id, label: preset.name})), "Choose a preset…");
    }
    byId("ladder-preset").value = state.ladder?.preset.id ?? "";
    if (laneSignature !== String(state.lanes.length)) {
      laneSignature = String(state.lanes.length);
      options(byId("ladder-lane"), state.lanes.map((_, index) => ({value: index, label: `Lane ${index + 1}`})), "Choose a lane…");
    }
    byId("ladder-lane").value = state.ladder?.laneIndex == null ? "" : String(state.ladder.laneIndex);
    byId("ladder-heading").textContent = {preset: "Choose a ladder preset", lane: "Select the ladder lane", markers: "Place ladder size markers"}[step];
    for (const [name, id] of [["preset", "ladder-preset-step"], ["lane", "ladder-lane-step"], ["markers", "ladder-marker-step"]]) byId(id).hidden = step !== name;
    byId("ladder-preset-hint").textContent = choices.length ? "Choose the ladder used in this gel."
      : "No ladder presets are configured yet. Choose Skip ladder to continue.";
    byId("ladder-back").hidden = step === "preset";
    byId("ladder-change-preset").hidden = step !== "markers";
    byId("ladder-change-lane").hidden = step !== "markers";
    byId("ladder-confirm").hidden = step !== "markers";
    byId("ladder-skip").hidden = Boolean(state.confirmedLadder);
    byId("ladder-remove").hidden = !state.confirmedLadder;
    byId("ladder-guard").hidden = !pendingChange;
    byId("ladder-guard-message").textContent = pendingChange?.message ?? "";
    byId("ladder-accept-change").textContent = pendingChange?.kind === "remove" ? "Remove ladder" : "Change and clear markers";
    renderMarkers(state);
    for (const container of [byId("ladder-panel"), byId("ladder-actions")]) {
      container.querySelectorAll("button, select").forEach(node => { node.disabled = disabled || Boolean(pendingChange); });
    }
    for (const name of ["ladder-accept-change", "ladder-keep-current"]) byId(name).disabled = disabled;
    byId("ladder-continue").disabled ||= !state.ladder;
    byId("ladder-use-lane").disabled ||= state.ladder?.laneIndex == null;
    byId("ladder-confirm").disabled ||= !placements().length || previewError;
    byId("ladder-keyboard").disabled ||= selectedMarker === null;
    byId("ladder-confirm").textContent = disabled ? "Composing ladder annotations…" : "Confirm ladder annotations";
    drawOverlay(state);
  }

  byId("ladder-reference-toggle").addEventListener("click", () => {
    referenceVisible = !referenceVisible;
    renderReference(getState());
    onLayout();
  });
  byId("ladder-reference-enlarge").addEventListener("click", () => {
    if (!referenceFailed && !byId("ladder-reference").hidden) byId("ladder-reference-dialog").showModal();
  });
  byId("ladder-reference-close").addEventListener("click", () => byId("ladder-reference-dialog").close());
  byId("ladder-reference-image").addEventListener("error", () => {
    referenceFailed = true;
    renderReference(getState());
    onLayout();
  });
  byId("ladder-reference-image").addEventListener("load", onLayout);

  byId("ladder-preset").addEventListener("change", event => {
    if (!editable()) return;
    const preset = (getState().presets ?? []).find(item => item.id === event.target.value);
    if (!preset || preset.id === getState().ladder?.preset.id) { render(); return; }
    if (placements().length) guard({kind: "preset", preset,
      message: "Changing the preset clears its placed markers. Your lane labels and groups are kept."});
    else setPreset(preset);
  });
  byId("ladder-lane").addEventListener("change", event => {
    if (event.target.value !== "") chooseLane(Number(event.target.value));
    else render();
  });
  byId("ladder-continue").addEventListener("click", () => { if (getState()?.ladder) go("lane"); });
  byId("ladder-use-lane").addEventListener("click", () => { if (getState()?.ladder?.laneIndex != null) go("markers"); });
  byId("ladder-back").addEventListener("click", () => go(getState().ladderStep === "markers" ? "lane" : "preset"));
  byId("ladder-change-preset").addEventListener("click", () => go("preset"));
  byId("ladder-change-lane").addEventListener("click", () => go("lane"));
  byId("ladder-accept-change").addEventListener("click", () => {
    if (disabled || !pendingChange) return;
    const change = pendingChange;
    pendingChange = null;
    if (change.kind === "preset") setPreset(change.preset);
    else if (change.kind === "lane") setLane(change.index);
    else { render(); onAction("remove"); }
    if (change.kind !== "remove") byId("ladder-heading").focus();
  });
  byId("ladder-keep-current").addEventListener("click", () => {
    if (disabled) return;
    pendingChange = null;
    render();
    byId("ladder-heading").focus();
    status("Current ladder annotations kept.");
  });
  byId("ladder-remove-marker").addEventListener("click", () => {
    if (!editable() || selectedMarker === null) return;
    getState().ladder = {...getState().ladder, placements: placements().filter(item => item.markerIndex !== selectedMarker)};
    changed(`${markerLabel()} removed. Click its band to place it again.`);
    markerNodes.get(selectedMarker)?.button.focus();
  });
  byId("ladder-keyboard").addEventListener("click", () => {
    if (!editable() || selectedMarker === null) return;
    cursorNode.focus();
    status("Use Left and Right to position the marker; Shift moves ten pixels. Press Enter to place it, or Escape to return.");
  });
  cursorNode.addEventListener("keydown", event => {
    if (!editable() || !cursor || selectedMarker === null) return;
    const direction = {ArrowLeft: -1, ArrowRight: 1}[event.key];
    if (direction) {
      event.preventDefault();
      cursor = moveLadderCursor(cursor, direction, event.shiftKey, getState().lanes[getState().ladder.laneIndex]);
      drawOverlay(getState());
    } else if (event.key === "Enter") {
      event.preventDefault();
      if (!event.repeat) place(cursor);
    } else if (event.key === "Escape") {
      event.preventDefault();
      markerNodes.get(selectedMarker)?.button.focus();
    }
  });
  for (const action of ["confirm", "cancel", "skip"]) byId(`ladder-${action}`).addEventListener("click", () => {
    if (editable() && (action !== "confirm" || placements().length > 0 && !previewError)) onAction(action);
  });
  byId("ladder-remove").addEventListener("click", () => {
    if (editable()) guard({kind: "remove", message: "Remove all ladder annotations from the final image? Your lane labels and groups are kept."});
  });

  overlay.addEventListener("pointerdown", event => {
    suppressClick = false;
    if (event.isPrimary === false) { suppressClick = true; return; }
    if (!editable() || event.button !== 0) return;
    pointer = {id: event.pointerId, x: event.clientX, y: event.clientY};
  });
  overlay.addEventListener("pointermove", event => {
    if (pointer?.id === event.pointerId && movedPastTap(pointer, event)) suppressClick = true;
  });
  overlay.addEventListener("pointercancel", () => { pointer = null; suppressClick = true; });
  overlay.addEventListener("pointerup", event => {
    if (pointer?.id === event.pointerId && movedPastTap(pointer, event)) suppressClick = true;
    pointer = null;
  });
  overlay.addEventListener("click", event => {
    if (!editable() || suppressClick || event.button !== 0) return;
    const point = ladderImagePoint(event.clientX, event.clientY, canvas.getBoundingClientRect(), getLayout());
    const state = getState();
    if (state.ladderStep === "lane") {
      const index = laneAtPoint(point, state.lanes);
      if (index === -1) status("Click inside a lane, or choose its number above.", true);
      else chooseLane(index);
    } else if (state.ladderStep === "markers") place(point);
  });

  function reset() {
    selectedMarker = null;
    cursor = null;
    pendingChange = null;
    pointer = null;
    suppressClick = false;
    disabled = false;
    previewError = false;
    referenceVisible = true;
    if (byId("ladder-reference-dialog").open) byId("ladder-reference-dialog").close();
  }

  return {render, reset, setDisabled(value, error = false) {
    disabled = Boolean(value);
    previewError = Boolean(error);
    render();
  }};
}
