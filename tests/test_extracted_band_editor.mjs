import test from "node:test";
import assert from "node:assert/strict";
import {readFileSync} from "node:fs";
import {createExtractedBandEditor, extractedBandPoint} from "../gel_analyzer/annotation_component_frontend/extracted_bands.mjs";

class Node {
  constructor(tagName = "div") {
    Object.assign(this, {tagName, children: [], attributes: {}, dataset: {}, events: {}, captures: new Set(), disabled: false});
  }
  setAttribute(key, value) { this.attributes[key] = String(value); }
  toggleAttribute(key, present) {
    if (present) this.attributes[key] = "";
    else delete this.attributes[key];
  }
  hasAttribute(key) { return Object.hasOwn(this.attributes, key); }
  append(...children) { this.children.push(...children); }
  replaceChildren(...children) { this.children = children; }
  querySelectorAll(tagName) {
    return this.children.flatMap(child => [...(child.tagName === tagName ? [child] : []), ...child.querySelectorAll(tagName)]);
  }
  addEventListener(type, callback) { (this.events[type] ??= []).push(callback); }
  dispatch(type, values = {}) {
    if (type === "click" && this.disabled) return;
    const event = {target: this, button: 0, pointerId: 1, isPrimary: true, ...values,
      preventDefault() { this.defaultPrevented = true; }};
    for (const callback of this.events[type] ?? []) callback(event);
    return event;
  }
  setPointerCapture(id) { this.captures.add(id); }
  hasPointerCapture(id) { return this.captures.has(id); }
  releasePointerCapture(id) { this.captures.delete(id); this.dispatch("lostpointercapture", {pointerId: id}); }
  focus() { document.activeElement = this; }
}

function harness(run, overrides = {}) {
  const previous = globalThis.document;
  const html = readFileSync(new URL("../gel_analyzer/annotation_component_frontend/index.html", import.meta.url), "utf8");
  const nodes = Object.fromEntries([...html.matchAll(/<([a-z]+)[^>]*\bid="([^"]+)"/g)]
    .map(match => [match[2], new Node(match[1])]));
  globalThis.document = Object.assign(new Node(), {getElementById: id => nodes[id],
    createElement: tag => new Node(tag), createElementNS: (_, tag) => new Node(tag)});
  const state = {mode: "extracted", extractedBands: [], ...overrides};
  const geometry = {layout: {width: 400, height: 300, imageWidth: 200, imageHeight: 160, gelX: 80, gelY: 60},
    bounds: {left: -40, top: 30, width: 200, height: 150}};
  nodes.preview.getBoundingClientRect = () => geometry.bounds;
  const edits = [], actions = [], messages = [];
  const controller = createExtractedBandEditor({getState: () => state, getLayout: () => geometry.layout,
    canvas: nodes.preview, onChange() { edits.push(structuredClone(state.extractedBands)); },
    onAction(action) { actions.push(action); }, status(...message) { messages.push(message); }});
  const overlay = nodes["extracted-band-overlay"];
  overlay.setAttribute("hidden", "");
  const point = (x, y) => ({clientX: geometry.bounds.left + (geometry.layout.gelX + x) * geometry.bounds.width / geometry.layout.width,
    clientY: geometry.bounds.top + (geometry.layout.gelY + y) * geometry.bounds.height / geometry.layout.height});
  const pointer = (type, x, y, values = {}) => overlay.dispatch(type, {...point(x, y), ...values});
  const draw = (x0, y0, x1, y1) => {
    pointer("pointerdown", x0, y0); pointer("pointermove", x1, y1); pointer("pointerup", x1, y1);
  };
  const buttons = () => nodes["extracted-band-list"].querySelectorAll("button");
  try { controller.render(); run({state, nodes, geometry, controller, edits, actions, messages, overlay, point, pointer, draw, buttons}); }
  finally { if (previous === undefined) delete globalThis.document; else globalThis.document = previous; }
}

for (const [x0, y0, x1, y1] of [[20, 30, 80, 70], [80, 30, 20, 70], [20, 70, 80, 30], [80, 70, 20, 30]]) {
  test(`drag from (${x0}, ${y0}) to (${x1}, ${y1}) produces the same transparent native rectangle`, () => harness(h => {
    h.pointer("pointerdown", x0, y0);
    assert.equal(h.overlay.hasPointerCapture(1), true);
    h.pointer("pointermove", x1, y1);
    assert.equal(h.overlay.children[0].dataset.draft, "true");
    assert.equal(h.edits.length, 0, "moving a preview does not commit a rectangle");
    h.pointer("pointerup", x1, y1);
    assert.deepEqual(h.state.extractedBands, [{x: 20, y: 30, width: 60, height: 40}]);
    assert.equal(h.overlay.hasPointerCapture(1), false);
    assert.equal(h.overlay.children[0].attributes.fill, "none");
    assert.equal(h.overlay.children[0].dataset.draft, "false");
    assert.equal(h.nodes["extracted-band-count"].textContent, "1 extracted band marked");
  }));
}

test("zoom, resizing, scrolling and gutter changes preserve native geometry and align the overlay", () => harness(h => {
  h.draw(20.25, 30.5, 80.75, 70.25);
  const original = structuredClone(h.state.extractedBands);
  for (const scale of [0.17, 0.75, 1, 2]) {
    h.geometry.bounds = {left: -105, top: -240, width: 400 * scale, height: 300 * scale};
    h.controller.render();
    const rectangle = h.overlay.children[0].attributes;
    assert.equal(rectangle.x, "100.25");
    assert.equal(rectangle.y, "90.5");
    assert.equal(h.overlay.attributes.viewBox, "0 0 400 300");
    const point = extractedBandPoint(h.point(50, 90), h.geometry.bounds, h.geometry.layout);
    assert.ok(Math.abs(point.x - 50) < 1e-10 && Math.abs(point.y - 90) < 1e-10);
    assert.deepEqual(h.state.extractedBands, original);
  }
  h.geometry.layout.gelX = 110;
  h.geometry.layout.gelY = 85;
  h.controller.render();
  assert.equal(h.overlay.children[0].attributes.x, "130.25");
  assert.equal(h.overlay.children[0].attributes.y, "115.5");
  h.draw(100, 110, 130, 140);
  assert.deepEqual(h.state.extractedBands[1], {x: 100, y: 110, width: 30, height: 30});
}));

test("drawing starts only in the gel while its final corner is clamped to the gel", () => harness(h => {
  for (const [x, y] of [[-1, 30], [20, -1], [201, 40], [40, 161]]) h.draw(x, y, 50, 50);
  assert.deepEqual(h.state.extractedBands, []);
  h.draw(20, 30, 260, 190);
  h.draw(20, 30, -60, -40);
  assert.deepEqual(h.state.extractedBands, [{x: 20, y: 30, width: 180, height: 130}, {x: 0, y: 0, width: 20, height: 30}]);
}));

test("lane and ladder modes display existing outlines without intercepting or changing annotations", () => harness(h => {
  h.draw(20, 30, 80, 70);
  const original = structuredClone(h.state.extractedBands);
  for (const mode of ["lanes", "ladder"]) {
    h.state.mode = mode;
    h.controller.render();
    assert.equal(h.overlay.dataset.drawing, "false");
    assert.equal(h.nodes["extracted-band-panel"].hidden, true);
    assert.equal(h.nodes["extracted-band-actions"].hidden, true);
    assert.equal(h.overlay.hasAttribute("hidden"), false, "committed outlines remain visible");
    h.draw(100, 110, 130, 140);
    h.buttons()[0].dispatch("click");
    h.nodes["extracted-band-done"].dispatch("click");
    h.nodes["extracted-band-cancel"].dispatch("click");
    assert.deepEqual(h.state.extractedBands, original);
    assert.deepEqual(h.actions, []);
  }
}));

test("tiny drags are rejected by displayed size and cancel gestures never save", () => harness(h => {
  for (const [width, height] of [[0, 0], [4, 20], [20, 4]]) h.draw(20, 30, 20 + width, 30 + height);
  assert.deepEqual(h.state.extractedBands, []);
  for (const type of ["pointercancel", "lostpointercapture", "Escape"]) {
    h.pointer("pointerdown", 20, 30);
    h.pointer("pointermove", 80, 70);
    if (type === "Escape") {
      const event = document.dispatch("keydown", {key: "Escape"});
      assert.equal(event.defaultPrevented, true);
    } else h.overlay.dispatch(type);
    h.pointer("pointerup", 80, 70);
    assert.equal(h.overlay.children.length, 0);
    assert.equal(h.overlay.hasPointerCapture(1), false);
    assert.equal(h.edits.length, 0);
  }
  h.draw(20, 30, 26, 36);
  assert.deepEqual(h.state.extractedBands, [{x: 20, y: 30, width: 6, height: 6}], "three displayed pixels per side is accepted");
}));

test("multiple rectangles can be removed individually with focus preserved", () => harness(h => {
  h.draw(20, 30, 80, 70); h.draw(100, 110, 130, 140); h.draw(90, 20, 120, 40);
  const [first, , third] = structuredClone(h.state.extractedBands);
  assert.equal(h.buttons().length, 3);
  assert.equal(h.buttons()[1].attributes["aria-label"], "Remove extracted band 2");
  h.buttons()[1].dispatch("click");
  assert.deepEqual(h.state.extractedBands, [first, third]);
  assert.equal(document.activeElement, h.buttons()[1]);
  assert.equal(h.overlay.children.length, 2);
  h.buttons()[1].dispatch("click"); h.buttons()[0].dispatch("click");
  assert.deepEqual(h.state.extractedBands, []);
  assert.equal(document.activeElement, h.nodes["extracted-band-done"]);
  assert.equal(h.edits.length, 6);
}));

test("secondary pointers cannot start or finish a rectangle", () => harness(h => {
  h.pointer("pointerdown", 20, 30, {isPrimary: false, pointerId: 2});
  h.pointer("pointerup", 80, 70, {pointerId: 2});
  h.pointer("pointerdown", 20, 30, {button: 2});
  assert.equal(h.overlay.children.length, 0);
  h.pointer("pointerdown", 20, 30);
  h.pointer("pointermove", 180, 140, {pointerId: 2});
  h.pointer("pointerup", 180, 140, {pointerId: 2});
  h.overlay.dispatch("pointercancel", {pointerId: 2});
  assert.equal(h.overlay.hasPointerCapture(1), true);
  h.pointer("pointerup", 80, 70);
  assert.deepEqual(h.state.extractedBands, [{x: 20, y: 30, width: 60, height: 40}]);
}));

test("Done marking and Cancel route their actions and discard any in-progress drag", () => harness(h => {
  h.draw(20, 30, 80, 70);
  for (const [id, action] of [["extracted-band-done", "confirm"], ["extracted-band-cancel", "cancel"]]) {
    h.pointer("pointerdown", 100, 100);
    h.nodes[id].dispatch("click");
    h.pointer("pointerup", 130, 140);
    assert.equal(h.actions.at(-1), action);
    assert.equal(h.state.extractedBands.length, 1);
    assert.equal(h.overlay.hasPointerCapture(1), false);
  }
  assert.deepEqual(h.actions, ["confirm", "cancel"]);
}));

test("disabling or leaving drawing mode cancels an unfinished rectangle", () => harness(h => {
  h.pointer("pointerdown", 20, 30);
  h.controller.setDisabled(true);
  h.pointer("pointerup", 80, 70);
  assert.equal(h.nodes["extracted-band-done"].disabled, true);
  assert.equal(h.overlay.dataset.drawing, "false");
  h.nodes["extracted-band-done"].dispatch("click");
  h.nodes["extracted-band-cancel"].dispatch("click");
  h.controller.setDisabled(false);
  h.pointer("pointerdown", 20, 30);
  h.state.mode = "ladder";
  h.pointer("pointerup", 80, 70);
  assert.deepEqual(h.state.extractedBands, []);
  assert.deepEqual(h.actions, []);
  assert.equal(h.overlay.hasPointerCapture(1), false);
}));

test("a missing or hidden preview cancels a drag without creating invalid coordinates", () => harness(h => {
  h.pointer("pointerdown", 20, 30);
  h.geometry.layout = null;
  h.overlay.dispatch("pointermove", {clientX: 40, clientY: 50});
  assert.equal(h.overlay.hasAttribute("hidden"), true);
  assert.equal(h.overlay.hasPointerCapture(1), false);
  assert.deepEqual(h.state.extractedBands, []);
  h.geometry.layout = {width: 400, height: 300, imageWidth: 200, imageHeight: 160, gelX: 80, gelY: 60};
  h.pointer("pointerdown", 20, 30);
  h.geometry.bounds.width = 0;
  h.overlay.dispatch("pointerup", {clientX: 40, clientY: 50});
  assert.deepEqual(h.state.extractedBands, []);
  assert.equal(extractedBandPoint({clientX: NaN, clientY: 0}, {left: 0, top: 0, width: 100, height: 100}, h.geometry.layout), null);
}));

test("SVG hidden attributes reflect whether drawing or committed outlines should be visible", () => harness(h => {
  assert.equal(h.overlay.hasAttribute("hidden"), false, "drawing removes the initial SVG hidden attribute");
  h.state.mode = "lanes";
  h.controller.render();
  assert.equal(h.overlay.hasAttribute("hidden"), true, "an empty inactive overlay is hidden");
  h.state.mode = "extracted";
  h.controller.render();
  assert.equal(h.overlay.hasAttribute("hidden"), false);
  h.draw(20, 30, 80, 70);
  h.state.mode = "ladder";
  h.controller.render();
  assert.equal(h.overlay.hasAttribute("hidden"), false, "committed rectangles remain visible outside drawing mode");
  h.geometry.layout = null;
  h.controller.render();
  assert.equal(h.overlay.hasAttribute("hidden"), true, "missing layouts cannot leave a stale SVG visible");
}));

test("the 500 rectangle limit prevents a new drag while existing rectangles remain removable", () => harness(h => {
  h.draw(20, 30, 80, 70);
  assert.equal(h.state.extractedBands.length, 500);
  assert.equal(h.overlay.hasPointerCapture(1), false);
  assert.match(h.messages.at(-1)[0], /500 bands/);
  h.buttons()[0].dispatch("click");
  h.draw(20, 30, 80, 70);
  assert.equal(h.state.extractedBands.length, 500);
  assert.deepEqual(h.state.extractedBands.at(-1), {x: 20, y: 30, width: 60, height: 40});
}, {extractedBands: Array.from({length: 500}, () => ({x: 0, y: 0, width: 10, height: 10}))}));
