const SVG = "http://www.w3.org/2000/svg";
const MAX_BANDS = 500;

/** Convert display coordinates to native gel coordinates, independent of zoom. */
export function extractedBandPoint(event, bounds, layout, clamp = false) {
  if (!layout || !(bounds.width > 0 && bounds.height > 0)) return null;
  let x = (event.clientX - bounds.left) * layout.width / bounds.width - layout.gelX;
  let y = (event.clientY - bounds.top) * layout.height / bounds.height - layout.gelY;
  if (!Number.isFinite(x) || !Number.isFinite(y)) return null;
  if (!clamp && (x < 0 || y < 0 || x > layout.imageWidth || y > layout.imageHeight)) return null;
  x = Math.max(0, Math.min(layout.imageWidth, x));
  y = Math.max(0, Math.min(layout.imageHeight, y));
  return {x, y};
}

export function extractedBandRectangle(start, end) {
  return {x: Math.min(start.x, end.x), y: Math.min(start.y, end.y),
    width: Math.abs(end.x - start.x), height: Math.abs(end.y - start.y)};
}

/** Drawing is isolated from lane text and ladder tools, with crop-relative data. */
export function createExtractedBandEditor({getState, getLayout, canvas, onChange, onAction, status}) {
  const byId = id => document.getElementById(id);
  const overlay = byId("extracted-band-overlay");
  const list = byId("extracted-band-list");
  let disabled = false;
  let drag = null;
  let listSignature = "";
  const active = () => getState()?.mode === "extracted";
  const bands = () => getState()?.extractedBands ?? [];

  function outline(rectangle, draft = false) {
    const layout = getLayout();
    const node = document.createElementNS(SVG, "rect");
    node.setAttribute("x", layout.gelX + rectangle.x);
    node.setAttribute("y", layout.gelY + rectangle.y);
    node.setAttribute("width", rectangle.width);
    node.setAttribute("height", rectangle.height);
    node.setAttribute("fill", "none");
    node.setAttribute("class", "extracted-band-outline");
    node.dataset.draft = String(draft);
    return node;
  }

  function renderOverlay() {
    const layout = getLayout();
    // SVGElement does not reflect an assigned .hidden property to its attribute.
    overlay.toggleAttribute("hidden", !layout || (!active() && !bands().length));
    overlay.dataset.drawing = String(active() && !disabled);
    if (!layout) return;
    overlay.setAttribute("viewBox", `0 0 ${layout.width} ${layout.height}`);
    overlay.replaceChildren(...bands().map(rectangle => outline(rectangle)),
      ...(drag ? [outline(extractedBandRectangle(drag.start, drag.end), true)] : []));
  }

  function render() {
    if (!active() || disabled) cancelDrag();
    byId("extracted-band-panel").hidden = !active();
    byId("extracted-band-actions").hidden = !active();
    byId("extracted-band-count").textContent = `${bands().length} extracted band${bands().length === 1 ? "" : "s"} marked`;
    byId("extracted-band-done").disabled = disabled;
    byId("extracted-band-cancel").disabled = disabled;
    const signature = JSON.stringify([bands(), disabled]);
    if (signature !== listSignature) {
      listSignature = signature;
      list.replaceChildren();
      bands().forEach((rectangle, index) => {
        const row = document.createElement("li");
        const label = document.createElement("span");
        label.textContent = `Band ${index + 1}`;
        const button = document.createElement("button");
        button.type = "button";
        button.textContent = "Remove";
        button.setAttribute("aria-label", `Remove extracted band ${index + 1}`);
        button.disabled = disabled;
        button.addEventListener("click", () => {
          if (!active() || disabled) return;
          getState().extractedBands.splice(index, 1);
          onChange();
          render();
          const remaining = list.querySelectorAll("button");
          (remaining[Math.min(index, remaining.length - 1)] ?? byId("extracted-band-done")).focus();
          status(`Removed extracted band ${index + 1}.`);
        });
        row.append(label, button);
        list.append(row);
      });
    }
    renderOverlay();
  }

  function cancelDrag() {
    if (!drag) return;
    const pointerId = drag.id;
    drag = null;
    if (overlay.hasPointerCapture(pointerId)) overlay.releasePointerCapture(pointerId);
    renderOverlay();
  }

  overlay.addEventListener("pointerdown", event => {
    if (!active() || disabled || drag || event.button !== 0 || event.isPrimary === false) return;
    const layout = getLayout();
    if (!layout) return;
    const start = extractedBandPoint(event, canvas.getBoundingClientRect(), layout);
    if (!start) return;
    if (bands().length >= MAX_BANDS) { status("Remove a rectangle before adding more than 500 bands.", true); return; }
    event.preventDefault();
    drag = {id: event.pointerId, start, end: start};
    overlay.setPointerCapture(event.pointerId);
    renderOverlay();
  });
  overlay.addEventListener("pointermove", event => {
    if (!drag || event.pointerId !== drag.id) return;
    if (!active() || disabled) { cancelDrag(); return; }
    const point = extractedBandPoint(event, canvas.getBoundingClientRect(), getLayout(), true);
    if (!point) { cancelDrag(); return; }
    drag.end = point;
    renderOverlay();
  });
  overlay.addEventListener("pointerup", event => {
    if (!drag || event.pointerId !== drag.id) return;
    if (!active() || disabled) { cancelDrag(); return; }
    const bounds = canvas.getBoundingClientRect(), layout = getLayout();
    const point = extractedBandPoint(event, bounds, layout, true);
    if (!point) { cancelDrag(); return; }
    const rectangle = extractedBandRectangle(drag.start, point);
    cancelDrag();
    // Ignore clicks and accidental tiny drags, measured in displayed pixels.
    if (rectangle.width * bounds.width / layout.width < 3 || rectangle.height * bounds.height / layout.height < 3) return;
    getState().extractedBands.push(rectangle);
    onChange();
    render();
    status(`Marked extracted band ${bands().length}. Drag to add another, or choose Done marking.`);
  });
  for (const type of ["pointercancel", "lostpointercapture"]) {
    overlay.addEventListener(type, event => { if (drag?.id === event.pointerId) cancelDrag(); });
  }
  document.addEventListener("keydown", event => {
    if (active() && drag && event.key === "Escape") {
      event.preventDefault(); cancelDrag(); status("Rectangle cancelled.");
    }
  });
  byId("extracted-band-done").addEventListener("click", () => {
    if (active() && !disabled) { cancelDrag(); onAction("confirm"); }
  });
  byId("extracted-band-cancel").addEventListener("click", () => {
    if (active() && !disabled) { cancelDrag(); onAction("cancel"); }
  });
  return {
    render,
    reset() { cancelDrag(); listSignature = ""; },
    setDisabled(value) { disabled = value; if (value) cancelDrag(); render(); },
  };
}
