import {layoutAnnotations, drawAnnotations} from "./layout.mjs";
import {annotationSvg} from "./svg.mjs";
import {createLadderEditor} from "./ladder.mjs";
import {createExtractedBandEditor} from "./extracted_bands.mjs";
import {createGroupEditor} from "./groups.mjs";
import {annotationPreviewBudget} from "./ladder_geometry.mjs";
import {selectLabelKeys, selectedFormatting, formatSelectedLabels} from "./label_selection.mjs";
import {navigateLaneLabel} from "./label_navigation.mjs";
import {cleanText, cleanStyle, labelRuns, textSnapshot, editText,
  readSelection, restoreSelection, renderRuns} from "./rich_text.mjs";

// Streamlit's v1 component protocol keeps the editor self-contained and offline.
const byId = id => document.getElementById(id);
const component = byId("component");
const canvas = byId("preview");
const inputLayer = byId("label-inputs");
const seenTokens = new Set();
const inputNodes = new Map();
const COLOR_PRESETS = [
  {name: "Black", color: "#000000"}, {name: "Gray", color: "#666666"},
  {name: "Red", color: "#dc2626"}, {name: "Orange", color: "#ea580c"},
  {name: "Yellow", color: "#eab308"}, {name: "Green", color: "#15803d"},
  {name: "Blue", color: "#2563eb"}, {name: "Purple", color: "#9333ea"},
];
let state = null;
let image = null;
let layout = null;
let revision = 0;
let frameHeight = 0;
let pendingEdit = null;
let confirmationTimer = null;
let confirming = false;
let selected = "lane:0";
let selectedKeys = [selected];
let previewError = "";
let zoomFrame = null;
let outerViewportListeners = [];
let textSelection = null;
const histories = new Map();

const ladderEditor = createLadderEditor({getState: () => state, getLayout: () => layout,
  canvas, onChange: changed, onAction: finishAction, status, onLayout: scheduleZoom});
const extractedBandEditor = createExtractedBandEditor({getState: () => state, getLayout: () => layout,
  canvas, onChange: changed, onAction: finishAction, status});
const groupEditor = createGroupEditor({getState: () => state, isDisabled: () => confirming,
  onChange: changed, onSelect: id => selectLabel(`group:${id}`, false),
  onRename: (id, text) => setLabelText(`group:${id}`, text), status,
  onLayout: () => { scheduleZoom(); resizeFrame(); }});

function syncMode() {
  const laneMode = state?.mode === "lanes";
  component.dataset.mode = state?.mode || "lanes";
  document.querySelectorAll(".lane-only").forEach(node => { node.hidden = !laneMode; });
  byId("actions").hidden = !laneMode;
  byId("confirm").hidden = !laneMode;
  inputLayer.hidden = !laneMode;
  byId("label-angle-field").hidden = !laneMode || state?.workflow_orientation !== "wells_top";
  byId("auto-size").title = "Choose a text size that fits the lanes";
  const top = state?.workflow_orientation === "wells_top";
  byId("group-set-label").textContent = top ? "Row" : "Column";
  byId("group-set").setAttribute("aria-label", top ? "Group row" : "Group column");
  byId("group-set").options[1].textContent = top ? "Set 2 · farther above" : "Set 2 · far left";
}

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

function status(message = "", error = false) {
  byId("status").textContent = message;
  byId("status").dataset.error = String(error);
  resizeFrame();
}

function defaultFontSize(lanes, orientation = state?.workflow_orientation) {
  const axis = orientation === "wells_top" ? 0 : 1;
  const heights = lanes.map(lane => Number(lane[axis + 2]) - Number(lane[axis]))
    .filter(height => Number.isFinite(height) && height > 0);
  return heights.length
    ? Math.max(1, Math.min(4096, Math.round(0.8 * heights.reduce((sum, height) => sum + height, 0) / heights.length)))
    : 18;
}

function readAnnotations(raw, laneBounds, fontSize, orientation) {
  const count = laneBounds.length;
  const labels = Array.from({length: count}, (_, index) => ({text: cleanText(raw?.labels?.[index]?.text),
    ...cleanStyle(raw?.labels?.[index]), runs: labelRuns(raw?.labels?.[index])}));
  const ids = new Set();
  const groups = (Array.isArray(raw?.groups) ? raw.groups : []).slice(0, 100).flatMap((value, index) => {
    const lanes = [...new Set((Array.isArray(value?.lanes) ? value.lanes : [])
      .filter(lane => Number.isInteger(lane) && lane >= 0 && lane < count))].sort((a, b) => a - b);
    if (!lanes.length) return [];
    let id = /^[\w-]{1,80}$/.test(value?.id) ? value.id : `group-${index}`;
    let suffix = 0;
    while (ids.has(id)) id = `group-${index}-${++suffix}`;
    ids.add(id);
    return [{id, set: value?.set === 1 ? 1 : 0, label: cleanText(value?.label), ...cleanStyle(value),
      runs: labelRuns(value, "label"), lanes}];
  });
  const requestedSize = Number(raw?.fontSize ?? fontSize);
  return {labels, groups, laneLabelAngle: raw?.laneLabelAngle === 45 ? 45 : 90, fontSize: Number.isFinite(requestedSize)
    ? Math.max(1, Math.min(4096, Math.round(requestedSize))) : defaultFontSize(laneBounds, orientation)};
}

function selectedLabel() {
  if (!state) return null;
  if (selected.startsWith("lane:")) return state.annotations.labels[Number(selected.slice(5))];
  return state.annotations.groups.find(group => `group:${group.id}` === selected) || null;
}

function selectedTargets() {
  return selectedKeys.map(key => ({key, label: labelForKey(key),
    field: key.startsWith("lane:") ? "text" : "label"})).filter(target => target.label);
}

function setValue(node, value) {
  if (node.value !== String(value)) node.value = value;
}

function syncToolbar() {
  const value = selectedLabel();
  const isGroup = selected.startsWith("group:");
  const multiple = selectedKeys.length > 1;
  const range = !multiple && textSelection?.key === selected ? textSelection : null;
  const style = selectedFormatting(selectedTargets(), range);
  byId("selection-name").textContent = !value ? "Select a label"
    : multiple ? `${selectedKeys.length} lane labels selected`
      : isGroup ? `Group · set ${value.set + 1}` : `Lane ${Number(selected.slice(5)) + 1}`;
  byId("bold").setAttribute("aria-pressed", String(style.bold === true));
  byId("italic").setAttribute("aria-pressed", String(style.italic === true));
  byId("formatting-scope").textContent = !value ? "Click a label to select it"
    : multiple ? "Formatting: all selected labels"
      : range && range.start !== range.end ? "Formatting: selected text" : "Formatting: whole label";
  // Older lane labels use near-black; present those as Black without changing saved colors.
  const color = style.color?.toLowerCase() === "#202020" ? "#000000" : style.color?.toLowerCase();
  const preset = COLOR_PRESETS.find(preset => preset.color === color);
  byId("color-state").textContent = !value ? "" : style.mixedColor ? "· Mixed" : preset ? `· ${preset.name}` : "· Saved color";
  byId("color-presets").querySelectorAll("button").forEach(button => {
    button.setAttribute("aria-pressed", String(!style.mixedColor && color === button.dataset.color));
    button.disabled = confirming || !value;
  });
  setValue(byId("font-size"), state.annotations.fontSize);
  setValue(byId("label-angle"), state.annotations.laneLabelAngle);
  byId("edit-selected-group").hidden = !value || !isGroup;
  for (const name of ["bold", "italic"]) byId(name).disabled = confirming || !value;
  for (const [key, node] of inputNodes) node.dataset.selected = String(selectedKeys.includes(key));
}

function refreshTargets() {
  selectedKeys = selectedKeys.filter(key => labelForKey(key));
  selected = selectedKeys.at(-1) ?? "";
}

function selectLabel(key, updateGroup = true, additive = false) {
  const next = selectLabelKeys(selectedKeys, key, additive);
  if (key !== selected || additive || selectedKeys.length !== next.length) textSelection = null;
  selectedKeys = next;
  selected = selectedKeys.at(-1) ?? "";
  syncToolbar();
  if (updateGroup && key.startsWith("group:")) {
    const group = selectedLabel();
    if (group) {
      groupEditor.selectGroup(group.id);
    }
  }
}

function labelForKey(key) {
  return key.startsWith("lane:") ? state.annotations.labels[Number(key.slice(5))]
    : state.annotations.groups.find(group => `group:${group.id}` === key);
}

function rememberEdit(key) {
  const value = labelForKey(key);
  const history = histories.get(key) ?? {undo: [], redo: []};
  history.undo.push(textSnapshot(value, key.startsWith("lane:") ? "text" : "label"));
  if (history.undo.length > 100) history.undo.shift();
  history.redo = [];
  histories.set(key, history);
}

function captureSelection() {
  if (selectedKeys.length !== 1) { textSelection = null; syncToolbar(); return; }
  const node = inputNodes.get(selected);
  // A rerender can collapse an unfocused DOM selection. Keep the saved range
  // while keyboard users move through the toolbar instead of replacing it.
  const range = node && document.activeElement === node && readSelection(node);
  if (range) textSelection = {key: selected, ...range};
  syncToolbar();
}

function setLabelText(key, text, range) {
  const value = labelForKey(key);
  if (!value) return;
  rememberEdit(key);
  editText(value, key.startsWith("lane:") ? "text" : "label", text, range);
  changed();
}

function updateInputs() {
  if (state.mode !== "lanes") return;
  const boxes = [
    ...layout.laneLabels.map(label => ({...label, key: `lane:${label.index}`, accessible: `Lane ${label.index + 1} label`})),
    ...layout.groupLabels.map(label => ({...label, key: `group:${label.id}`, accessible: `Group set ${label.set + 1} label: ${label.text || label.label || "untitled"}`})),
  ];
  const keep = new Set(boxes.map(box => box.key));
  for (const [key, node] of inputNodes) {
    if (!keep.has(key)) { node.remove(); inputNodes.delete(key); }
  }
  boxes.forEach(box => {
    let node = inputNodes.get(box.key);
    if (!node) {
      node = document.createElement("div");
      node.contentEditable = "true";
      node.setAttribute("role", "textbox");
      node.setAttribute("aria-multiline", "false");
      node.spellcheck = false;
      node.className = "image-label";
      node.dataset.label = box.key;
      node.addEventListener("pointerdown", event => {
        if (confirming || event.button !== 0) return;
        const additive = box.key.startsWith("lane:") && (event.metaKey || event.ctrlKey);
        if (additive) {
          // A modifier click selects the object, without moving a text caret or
          // letting a subsequent focus event replace the multi-selection.
          event.preventDefault();
          if (inputLayer.contains(document.activeElement)) document.activeElement.blur();
          window.getSelection()?.removeAllRanges();
        }
        selectLabel(box.key, true, additive);
      });
      node.addEventListener("focus", () => selectLabel(box.key));
      let beforeEdit = null;
      let composing = false;
      const commitInput = () => {
        setLabelText(box.key, node.textContent, beforeEdit);
        beforeEdit = null;
        captureSelection();
      };
      node.addEventListener("beforeinput", event => {
        if (event.inputType === "insertParagraph" || event.inputType === "insertLineBreak") {
          event.preventDefault(); return;
        }
        beforeEdit = readSelection(node);
        if (beforeEdit && beforeEdit.start === beforeEdit.end) {
          if (event.inputType === "deleteContentBackward") beforeEdit.start = Math.max(0, beforeEdit.start - 1);
          if (event.inputType === "deleteContentForward") beforeEdit.end = Math.min(node.textContent.length, beforeEdit.end + 1);
        }
      });
      node.addEventListener("input", () => { if (!composing) commitInput(); });
      node.addEventListener("compositionstart", () => { composing = true; });
      node.addEventListener("compositionend", () => { composing = false; commitInput(); });
      node.addEventListener("paste", event => {
        event.preventDefault();
        const range = readSelection(node);
        if (!range) return;
        const text = node.textContent;
        const inserted = cleanText(event.clipboardData.getData("text/plain"))
          .slice(0, 500 - (text.length - range.end + range.start));
        setLabelText(box.key, text.slice(0, range.start) + inserted + text.slice(range.end), range);
        restoreSelection(node, {start: range.start + inserted.length, end: range.start + inserted.length});
        captureSelection();
      });
      node.addEventListener("drop", event => event.preventDefault());
      node.addEventListener("keydown", event => {
        if (navigateLaneLabel(event, node, inputNodes)) { captureSelection(); return; }
        if ((event.ctrlKey || event.metaKey) && ["b", "i"].includes(event.key.toLowerCase())) {
          event.preventDefault(); applyFormat(event.key.toLowerCase() === "b" ? "bold" : "italic"); return;
        }
        if ((event.ctrlKey || event.metaKey) && ["z", "y"].includes(event.key.toLowerCase())) {
          event.preventDefault();
          const redo = event.shiftKey || event.key.toLowerCase() === "y";
          const history = histories.get(box.key);
          const from = history?.[redo ? "redo" : "undo"];
          if (from?.length) {
            const value = labelForKey(box.key);
            history[redo ? "undo" : "redo"].push(textSnapshot(value, box.key.startsWith("lane:") ? "text" : "label"));
            delete value.runs;
            Object.assign(value, from.pop());
            if (!value.runs) value.runs = labelRuns(value, box.key.startsWith("lane:") ? "text" : "label");
            textSelection = null; changed();
          }
          return;
        }
        if (event.key === "Enter") { event.preventDefault(); node.blur(); }
        if ((event.key === "ArrowUp" || event.key === "ArrowDown") && !event.altKey && !event.ctrlKey && !event.metaKey) {
          const nodes = [...inputLayer.querySelectorAll(".image-label")];
          const next = nodes[nodes.indexOf(node) + (event.key === "ArrowUp" ? -1 : 1)];
          if (next) { event.preventDefault(); next.focus(); restoreSelection(next, {start: 0, end: next.textContent.length}); }
        }
      });
      inputLayer.appendChild(node);
      inputNodes.set(box.key, node);
    }
    renderRuns(node, labelForKey(box.key), box.key.startsWith("lane:") ? "text" : "label");
    node.setAttribute("aria-label", box.accessible);
    node.dataset.placeholder = box.key.startsWith("lane:") ? `Lane ${box.index + 1}` : "Group";
    node.dataset.selected = String(selectedKeys.includes(box.key));
    node.contentEditable = String(!confirming);
    node.setAttribute("aria-disabled", String(confirming));
    node.style.left = `${(box.rotation ? box.baselineX : box.x) - box.width - 1}px`;
    node.style.top = `${box.rotation ? box.baselineY - box.editorBaseline - 1 : box.y - box.boxHeight / 2 - 1}px`;
    node.style.transformOrigin = box.rotation ? `${box.width + 1}px ${box.editorBaseline + 1}px` : "";
    node.style.transform = box.rotation ? `rotate(${box.rotationDegrees}deg)` : "";
    node.style.width = `${box.width}px`;
    node.style.height = `${box.boxHeight}px`;
    node.style.font = box.font;
    node.style.lineHeight = `${box.boxHeight}px`;
    node.style.setProperty("--label-color", box.color);
  });
}

function outerViewportHeight() {
  // The iframe's own height follows its contents. Using it here would shrink
  // the preview repeatedly as Streamlit acknowledges each frame-height update.
  try {
    const height = window.parent.visualViewport?.height || window.parent.innerHeight;
    if (Number.isFinite(height) && height > 0) return height;
  } catch { /* A cross-origin host can still use the browser/screen fallback. */ }
  const heights = [window.outerHeight, window.screen?.availHeight]
    .filter(height => Number.isFinite(height) && height > 0);
  return heights.length ? Math.min(...heights) : 800;
}

function availableComponentHeight() {
  try {
    const height = window.parent.gelPreviewViewport?.availableHeight(window.frameElement);
    if (Number.isFinite(height) && height > 0) return height;
  } catch { /* Cross-origin hosts provide this measurement via gel:viewport. */ }
  return window.gelPreviewHeight || Math.max(1, outerViewportHeight() - 100);
}

function updateZoom() {
  if (!layout || byId("editor").hidden) return;
  const viewport = byId("preview-viewport");
  const zoom = byId("zoom").value;
  const fit = zoom === "fit";
  viewport.dataset.fit = String(fit);
  component.dataset.previewFit = fit ? "screen" : "manual";
  const style = getComputedStyle(viewport);
  const pixels = property => Number.parseFloat(style[property]) || 0;
  const paddingX = pixels("paddingLeft") + pixels("paddingRight");
  const insetY = pixels("paddingTop") + pixels("paddingBottom")
    + pixels("borderTopWidth") + pixels("borderBottomWidth");
  // The host measures its title, upload control and filename. Only the actual
  // remaining space is shared by this preview and its controls.
  const workspace = byId("ladder-workspace");
  const componentBudget = availableComponentHeight();
  const outsideWorkspace = component.getBoundingClientRect().height - workspace.getBoundingClientRect().height;
  component.style.setProperty("--workspace-budget", `${Math.max(1, componentBudget - outsideWorkspace)}px`);
  const budget = annotationPreviewBudget({viewportHeight: componentBudget,
    componentHeight: component.getBoundingClientRect().height,
    previewHeight: viewport.getBoundingClientRect().height,
    workspaceHeight: workspace.getBoundingClientRect().height,
    sidePanel: window.matchMedia("(min-width: 400px)").matches, insetY,
    ladderMode: state.mode === "ladder", outerReserve: 0, minimumPreview: 1});
  viewport.style.maxHeight = `${budget}px`;
  viewport.style.height = fit ? `${budget}px` : "";
  const availableWidth = Math.max(1, Math.floor(viewport.clientWidth - paddingX) - 1);
  const availableHeight = Math.max(1, Math.floor(budget - insetY) - 1);
  const scale = fit ? Math.min(1, availableWidth / layout.width, availableHeight / layout.height) : Number(zoom);
  component.style.setProperty("--selection-outline-width", `${2 / scale}px`);
  component.style.setProperty("--selection-outline-offset", `${1 / scale}px`);
  component.style.setProperty("--band-outline-width", `${2 / scale}px`);
  byId("preview-stage").style.transform = `scale(${scale})`;
  byId("preview-stage").style.width = `${layout.width}px`;
  byId("preview-stage").style.height = `${layout.height}px`;
  byId("preview-space").style.width = `${Math.ceil(layout.width * scale)}px`;
  byId("preview-space").style.height = `${Math.ceil(layout.height * scale)}px`;
  if (fit) {
    viewport.scrollLeft = 0;
    viewport.scrollTop = 0;
  }
  component.dataset.previewScale = String(scale);
  component.dataset.previewBudget = String(budget);
  const dense = layout.denseFallback ? " Closely spaced labels use extra columns." : "";
  const fitted = state.workflow_orientation === "wells_top" && layout.reducedFont
    ? " Text is sized to keep lane labels aligned." : "";
  byId("size-hint").textContent = `${Math.round(scale * 100)}% view${dense}${fitted}`;
  ladderEditor.render();
  resizeFrame();
}

function scheduleZoom() {
  if (zoomFrame !== null) return;
  zoomFrame = requestAnimationFrame(() => {
    zoomFrame = null;
    updateZoom();
  });
}

function observeOuterViewport() {
  if (outerViewportListeners.length) return;
  try {
    const targets = [window.parent, window.parent.visualViewport].filter(Boolean);
    for (const target of targets) {
      target.addEventListener("resize", scheduleZoom);
      outerViewportListeners.push(target);
    }
  } catch {
    // Parent access may be unavailable in other hosts. A local window resize
    // still signals browser size changes without reading the iframe's height.
    window.addEventListener("resize", scheduleZoom);
    outerViewportListeners.push(window);
  }
}

function stopObservingOuterViewport() {
  for (const target of outerViewportListeners) target.removeEventListener("resize", scheduleZoom);
  outerViewportListeners = [];
  if (zoomFrame !== null) cancelAnimationFrame(zoomFrame);
  zoomFrame = null;
}

function repaint() {
  if (!state || !image?.complete || !image.naturalWidth) return false;
  try {
    const next = layoutAnnotations(state);
    if (next.width > 32767 || next.height > 32767 || next.width * next.height > 64000000)
      throw new Error("The composed image is too large. Shorten labels, reduce the font size, or remove groups before confirming.");
    drawAnnotations(canvas, image, next, state.annotations);
    layout = next;
    previewError = "";
    syncMode();
    updateInputs();
    ladderEditor.setDisabled(confirming, false);
    extractedBandEditor.setDisabled(confirming);
    updateZoom();
    byId("confirm").disabled = confirming;
    return true;
  } catch (error) {
    previewError = error instanceof Error ? error.message : "The annotation preview could not be drawn.";
    byId("confirm").disabled = true;
    ladderEditor.setDisabled(confirming, true);
    extractedBandEditor.setDisabled(true);
    status(previewError, true);
    return false;
  }
}

function canvasSnapshot(target, geometry) {
  const png = target.toDataURL("image/png");
  if (!png.startsWith("data:image/png;base64,"))
    throw new Error("The browser could not compose this image. Reduce annotation size and try again.");
  return {png, svg: annotationSvg(geometry), width: geometry.width, height: geometry.height,
    gel_x: geometry.gelX, gel_y: geometry.gelY};
}

function emit(action) {
  if (!state) return;
  if (action === "confirm" && (!layout || previewError)) return;
  const value = {kind: state.mode === "ladder" ? "ladder" : state.mode === "extracted" ? "extracted_bands" : "annotations",
    action, token: state.token, revision};
  if (state.mode === "ladder") {
    value.ladder = state.ladder;
    value.ladder_step = state.ladderStep;
  } else if (state.mode === "extracted") value.extracted_bands = state.extractedBands;
  else value.annotations = state.annotations;
  if (action === "confirm") {
    Object.assign(value, canvasSnapshot(canvas, layout));
    if ((state.mode === "lanes" || state.mode === "extracted") && state.ladder) {
      const baseCanvas = document.createElement("canvas");
      const baseLayout = layoutAnnotations({...state, ladder: null});
      drawAnnotations(baseCanvas, image, baseLayout, state.annotations);
      value.base = canvasSnapshot(baseCanvas, baseLayout);
    }
  }
  post("streamlit:setComponentValue", {dataType: "json", value});
}

function changed() {
  if (!state || confirming) return;
  revision = Math.max(revision + 1, Date.now() * 1000);
  component.dataset.revision = String(revision);
  status("");
  if (state.mode === "lanes") {
    refreshTargets();
    syncToolbar();
    groupEditor.render();
  }
  repaint();
  // Bound the bridge delay even during continuous typing; each batch carries
  // the latest snapshot and revision, while the preview itself is immediate.
  if (pendingEdit === null) {
    pendingEdit = setTimeout(() => { pendingEdit = null; emit("edit"); }, 120);
  }
}

function flushPendingEdit() {
  if (pendingEdit === null || confirming) return;
  clearTimeout(pendingEdit);
  pendingEdit = null;
  emit("edit");
}

// Parent workflow buttons can remove this iframe. Flush while focus leaves an
// input or the iframe, before the parent handles its navigation click. Clearing
// the pending batch prevents focusout, blur, and pagehide from posting twice.
document.addEventListener("focusout", flushPendingEdit);
window.addEventListener("blur", flushPendingEdit);
window.addEventListener("pagehide", flushPendingEdit);
document.addEventListener("visibilitychange", () => {
  if (document.visibilityState === "hidden") flushPendingEdit();
});

function setConfirming(value) {
  confirming = value;
  byId("editor").querySelectorAll("input, select, button").forEach(node => { node.disabled = value; });
  inputNodes.forEach(node => { node.contentEditable = String(!value); });
  ladderEditor.setDisabled(value, Boolean(previewError));
  extractedBandEditor.setDisabled(value || Boolean(previewError));
  byId("confirm").textContent = value ? "Composing annotations…" : "Confirm annotations";
  if (!value) {
    groupEditor.render();
    syncToolbar();
    byId("confirm").disabled = Boolean(previewError) || !layout;
  }
}

document.addEventListener("selectionchange", () => { if (state) captureSelection(); });

function applyFormat(name, explicitValue) {
  const targets = selectedTargets();
  if (!targets.length || confirming) return;
  // Read the current DOM range as well as the cached range: selectionchange
  // can arrive after a quick toolbar click or keyboard formatting shortcut.
  captureSelection();
  const range = targets.length === 1 && textSelection?.key === selected ? textSelection : null;
  for (const target of targets) rememberEdit(target.key);
  formatSelectedLabels(targets, range, name, explicitValue);
  changed();
  // Keep the range highlighted for pointer users; keyboard users retain the
  // cached range while moving among toolbar controls.
  const node = inputNodes.get(selected);
  if (node && document.activeElement === node) restoreSelection(node, range);
}

function bindFormatButton(button, name, value) {
  button.addEventListener("pointerdown", event => {
    captureSelection();
    // Keep the highlighted substring when using a mouse or touch to format it.
    if (inputLayer.contains(document.activeElement)) event.preventDefault();
  });
  button.addEventListener("click", () => applyFormat(name, value));
}
for (const name of ["bold", "italic"]) bindFormatButton(byId(name), name);
for (const preset of COLOR_PRESETS) {
  const button = document.createElement("button");
  button.type = "button";
  button.className = "color-preset";
  button.dataset.color = preset.color;
  button.setAttribute("aria-label", `${preset.name} text color`);
  button.setAttribute("aria-pressed", "false");
  button.title = preset.name;
  const swatch = document.createElement("span");
  swatch.className = "color-swatch";
  swatch.style.setProperty("--swatch-color", preset.color);
  swatch.setAttribute("aria-hidden", "true");
  button.append(swatch, document.createTextNode(preset.name));
  bindFormatButton(button, "color", preset.color);
  byId("color-presets").appendChild(button);
}
byId("label-angle").addEventListener("change", event => {
  state.annotations.laneLabelAngle = Number(event.target.value) === 45 ? 45 : 90;
  changed();
});
byId("font-size").addEventListener("change", event => {
  state.annotations.fontSize = Math.max(1, Math.min(4096,
    Math.round(Number(event.target.value) || defaultFontSize(state.lanes))));
  changed();
});
byId("font-size").addEventListener("input", event => {
  const value = Number(event.target.value);
  if (Number.isInteger(value) && value >= 1 && value <= 4096) {
    state.annotations.fontSize = value;
    changed();
  }
});
byId("auto-size").addEventListener("click", () => {
  state.annotations.fontSize = defaultFontSize(state.lanes);
  changed();
});
byId("open-groups").addEventListener("click", () => groupEditor.openNew());
byId("edit-selected-group").addEventListener("click", () => {
  if (selected.startsWith("group:")) groupEditor.openGroup(selected.slice(6));
});
byId("zoom").addEventListener("change", updateZoom);
function finishAction(action = "confirm") {
  if (confirming || !state) return;
  if (action === "confirm" && state.mode === "lanes" && !groupEditor.validate()) return;
  clearTimeout(pendingEdit);
  pendingEdit = null;
  if (action === "confirm" && !repaint()) return;
  try {
    revision = Math.max(revision + 1, Date.now() * 1000);
    component.dataset.revision = String(revision);
    setConfirming(true);
    emit(action);
    status(action === "confirm" ? "Composing the final image…" : "Returning to your confirmed image…");
    clearTimeout(confirmationTimer);
    confirmationTimer = setTimeout(() => {
      setConfirming(false);
      status("The action has not completed. Please try again.", true);
    }, 15000);
  } catch (error) {
    setConfirming(false);
    status(error instanceof Error ? error.message : "The image could not be composed. Please try again.", true);
  }
}
byId("confirm").addEventListener("click", () => finishAction("confirm"));


window.addEventListener("message", event => {
  if (event.source === window.parent && event.data?.type === "gel:viewport") {
    if (Number.isFinite(event.data.height) && event.data.height > 0) {
      window.gelPreviewHeight = event.data.height;
      scheduleZoom();
    }
    return;
  }
  if (event.source !== window.parent || event.data?.type !== "streamlit:render") return;
  const args = event.data.args;
  if (!args || typeof args.token !== "string" || !(args.width > 0 && args.height > 0) || !Array.isArray(args.lanes)) return;
  const theme = event.data.theme;
  if (theme?.textColor) document.documentElement.style.setProperty("--text", theme.textColor);
  if (theme?.secondaryBackgroundColor) document.documentElement.style.setProperty("--panel", theme.secondaryBackgroundColor);
  const incomingRevision = Number.isSafeInteger(args.revision) ? args.revision : 0;
  if (!state || state.token !== args.token) {
    if (seenTokens.has(args.token)) return;
    seenTokens.add(args.token);
    clearTimeout(pendingEdit);
    clearTimeout(confirmationTimer);
    pendingEdit = null;
    confirming = false;
    layout = null;
    previewError = "";
    revision = incomingRevision;
    state = {token: args.token, width: args.width, height: args.height,
      lanes: args.lanes.map(lane => [...lane]),
      workflow_orientation: args.workflow_orientation === "wells_top" ? "wells_top" : "wells_left",
      bandCandidates: args.band_candidates ?? [],
      mode: ["ladder", "extracted"].includes(args.mode) ? args.mode : "lanes",
      extractedBands: structuredClone(args.extracted_bands || []),
      ladder: args.ladder ? structuredClone(args.ladder) : null,
      presets: structuredClone(args.presets || []),
      ladderStep: args.ladder_step || "preset", confirmedLadder: Boolean(args.confirmed_ladder),
      annotations: readAnnotations(args.annotations, args.lanes, args.fontSize, args.workflow_orientation)};
    ladderEditor.reset();
    extractedBandEditor.reset();
    syncMode();
    component.dataset.token = args.token;
    component.dataset.revision = String(revision);
    inputLayer.replaceChildren();
    inputNodes.clear();
    histories.clear();
    textSelection = null;
    selected = "lane:0";
    selectedKeys = [selected];
    groupEditor.reset();
    refreshTargets();
    syncToolbar();
    groupEditor.render();
    setConfirming(false);
    byId("loading").hidden = false;
    byId("editor").hidden = true;
    const nextImage = new Image();
    image = nextImage;
    nextImage.onload = () => {
      if (image !== nextImage) return;
      byId("loading").hidden = true;
      byId("editor").hidden = false;
      status("");
      repaint();
      requestAnimationFrame(resizeFrame);
    };
    nextImage.onerror = () => {
      if (image !== nextImage) return;
      byId("loading").hidden = true;
      status("The cropped gel could not be loaded. Return to the crop step and try again.", true);
    };
    nextImage.src = args.image_src;
  } else if (incomingRevision > revision) {
    // Local revisions advance on each keystroke, before the debounced bridge
    // message. A delayed server render therefore cannot erase unsent edits.
    revision = incomingRevision;
    state.annotations = readAnnotations(args.annotations, state.lanes, args.fontSize, state.workflow_orientation);
    state.ladder = args.ladder ? structuredClone(args.ladder) : null;
    state.extractedBands = structuredClone(args.extracted_bands || []);
    state.ladderStep = args.ladder_step || "preset";
    refreshTargets();
    syncToolbar();
    groupEditor.render();
    repaint();
  }
  if (args.error && incomingRevision >= revision) {
    clearTimeout(confirmationTimer);
    setConfirming(false);
    status(String(args.error), true);
  }
  requestAnimationFrame(resizeFrame);
});

new ResizeObserver(() => { updateZoom(); resizeFrame(); }).observe(component);
observeOuterViewport();
window.addEventListener("pagehide", stopObservingOuterViewport);
window.addEventListener("pageshow", () => { observeOuterViewport(); scheduleZoom(); });
post("streamlit:componentReady", {apiVersion: 1});
resizeFrame();
