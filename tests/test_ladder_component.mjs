import test from "node:test";
import assert from "node:assert/strict";
import {readFileSync} from "node:fs";
import {createLadderEditor} from "../gel_analyzer/annotation_component_frontend/ladder.mjs";
import {annotationPreviewBudget, cursorForMarker, ladderImagePoint, laneAtPoint, moveLadderCursor, pointInLane} from "../gel_analyzer/annotation_component_frontend/ladder_geometry.mjs";

test("desktop side panels do not shrink previews and stacked phone controls leave usable image space", () => {
  const input = {viewportHeight: 900, componentHeight: 700, workspaceHeight: 520,
    previewHeight: 330, sidePanel: true, insetY: 18, ladderMode: true};
  assert.equal(annotationPreviewBudget(input), 620);
  assert.equal(annotationPreviewBudget({...input, previewHeight: 390}), 620);
  assert.equal(annotationPreviewBudget({...input, viewportHeight: 720,
    componentHeight: 800, previewHeight: 220, sidePanel: false}), 238);
});

test("pointer coordinates invert composition offsets, zoom and scrolling without rounding or clamping", () => {
  const layout = {width: 800, height: 500, gelX: 103, gelY: 91};
  for (const scale of [0.17, 0.25, 0.5, 0.75, 1]) {
    const rect = {left: -48.2, top: -107.8, width: layout.width * scale, height: layout.height * scale};
    const point = ladderImagePoint(rect.left + (103 + 21.375) * scale,
      rect.top + (91 + 14.125) * scale, rect, layout);
    assert.ok(Math.abs(point.x - 21.375) < 1e-10);
    assert.ok(Math.abs(point.y - 14.125) < 1e-10);
    assert.ok(ladderImagePoint(rect.left, rect.top, rect, layout).x < 0);
  }
  assert.equal(ladderImagePoint(0, 0, {width: 0, height: 20}, layout), null);
});

test("lane selection rejects gaps and right/bottom edges, with deterministic shared borders", () => {
  const lanes = [[3, 10, 90, 20], [3, 20, 90, 30], [3, 35, 90, 45]];
  assert.equal(laneAtPoint({x: 50, y: 20}, lanes), 1);
  assert.equal(laneAtPoint({x: 50, y: 32}, lanes), -1);
  assert.equal(laneAtPoint({x: 90, y: 15}, lanes), -1);
  assert.equal(laneAtPoint({x: 2.99, y: 15}, lanes), -1);
  assert.equal(pointInLane(null, lanes[0]), false);
});

test("keyboard cursor starts from the placement, preserves fractions, and stays in the selected lane", () => {
  const lanes = [[3, 10, 90, 20]];
  const ladder = {laneIndex: 0, placements: [{markerIndex: 0, x: 12.25, y: 18.5}]};
  assert.deepEqual(cursorForMarker(ladder, 0, lanes), {x: 12.25, y: 18.5});
  assert.deepEqual(cursorForMarker(ladder, 1, lanes), {x: 46.5, y: 15});
  assert.equal(moveLadderCursor({x: 12.25, y: 15}, 1, false, lanes[0]).x, 13.25);
  assert.equal(moveLadderCursor({x: 12.25, y: 15}, 1, true, lanes[0]).x, 22.25);
  assert.equal(moveLadderCursor({x: 88.9, y: 15}, 1, true, lanes[0]).x, 89);
  assert.equal(moveLadderCursor({x: 89.8, y: 15}, 1, false, lanes[0]).x, 89.8);
  assert.equal(moveLadderCursor({x: 3, y: 15}, -1, true, lanes[0]).x, 3);
});

class Node {
  constructor(tag = "div") {
    this.tagName = tag;
    this.children = [];
    this.attributes = {};
    this.dataset = {};
    this.style = {};
    this.events = {};
    this.disabled = false;
    this.hidden = false;
    this.value = "";
  }
  setAttribute(key, value) {
    this.attributes[key] = String(value);
    if (key.startsWith("data-")) this.dataset[key.slice(5).replace(/-([a-z])/g, (_, c) => c.toUpperCase())] = String(value);
  }
  removeAttribute(key) { delete this.attributes[key]; }
  appendChild(child) { this.children.push(child); child.parent = this; return child; }
  append(...children) { children.forEach(child => this.appendChild(child)); }
  replaceChildren(...children) { this.children = []; this.append(...children); }
  querySelectorAll(selector) {
    const names = selector.split(",").map(value => value.trim());
    return this.children.flatMap(child => [...(names.includes(child.tagName) ? [child] : []), ...child.querySelectorAll(selector)]);
  }
  focus() { globalThis.document.activeElement = this; }
  addEventListener(name, callback) { (this.events[name] ??= []).push(callback); }
  dispatch(name, values = {}) {
    if (name === "click" && this.disabled) return;
    const event = {target: this, button: 0, pointerId: 1, clientX: 0, clientY: 0, ...values,
      preventDefault() { this.prevented = true; }};
    for (const callback of this.events[name] ?? []) callback(event);
    return event;
  }
  getBoundingClientRect() { return {left: 20, top: 30, width: 150, height: 100}; }
}

const presets = [{id: "example", name: "Example", labels: ["5.0 kb", "3.0 kb", "1.0 kb"]},
  {id: "other", name: "Other", labels: ["10 kb", "1 kb"]}];

function harness(run, overrides = {}) {
  const previousDocument = globalThis.document;
  const html = readFileSync(new URL("../gel_analyzer/annotation_component_frontend/index.html", import.meta.url), "utf8");
  const nodes = Object.fromEntries([...html.matchAll(/<([a-z]+)[^>]*\bid="([^"]+)"/g)]
    .map(match => [match[2], new Node(match[1])]));
  const panelIds = [...Object.keys(nodes)].filter(id => id.startsWith("ladder-")
    && !["ladder-panel", "ladder-actions", "ladder-confirm", "ladder-skip", "ladder-cancel", "ladder-remove"].includes(id));
  panelIds.forEach(id => nodes["ladder-panel"].appendChild(nodes[id]));
  for (const id of ["ladder-confirm", "ladder-skip", "ladder-cancel", "ladder-remove"]) nodes["ladder-actions"].appendChild(nodes[id]);
  globalThis.document = {getElementById: id => nodes[id], createElement: tag => new Node(tag), createElementNS: (_, tag) => new Node(tag)};
  const state = {mode: "ladder", ladderStep: "preset", ladder: null, presets,
    lanes: [[5, 10, 190, 30], [5, 40, 190, 60]], width: 200, height: 100, confirmedLadder: false, ...overrides};
  const layout = {width: 300, height: 200, gelX: 80, gelY: 70};
  const actions = [];
  const edits = [];
  const messages = [];
  const controller = createLadderEditor({getState: () => state, getLayout: () => layout, canvas: nodes.preview,
    onChange() { edits.push(structuredClone(state)); controller.render(); },
    onAction(action) { actions.push(action); }, status(...message) { messages.push(message); }});
  function select(id, value) { nodes[id].value = value; nodes[id].dispatch("change"); }
  function clickImage(x, y) {
    nodes["ladder-overlay"].dispatch("click", {clientX: 20 + (80 + x) / 2, clientY: 30 + (70 + y) / 2});
  }
  function marker(index) { return nodes["ladder-markers"].children[index]; }
  function enterMarkers() {
    select("ladder-preset", "example");
    nodes["ladder-continue"].dispatch("click");
    clickImage(40, 20);
    nodes["ladder-use-lane"].dispatch("click");
  }
  try { controller.render(); run({state, nodes, actions, edits, messages, controller, select, clickImage, marker, enterMarkers}); }
  finally {
    if (previousDocument === undefined) delete globalThis.document;
    else globalThis.document = previousDocument;
  }
}

test("manual workflow has no default preset; selected markers replace rather than duplicate, and outside clicks do nothing", () => harness(h => {
  assert.equal(h.state.ladder, null);
  assert.equal(h.nodes["ladder-continue"].disabled, true);
  h.enterMarkers();
  assert.equal(h.state.ladderStep, "markers");
  assert.equal(h.nodes.component.dataset.ladderStep, "markers");
  assert.equal(h.state.ladder.laneIndex, 0);
  h.clickImage(24.75, 17.5);
  assert.equal(h.state.ladder.placements.length, 0, "a size must be chosen first");
  h.marker(0).dispatch("click");
  h.clickImage(24.75, 17.5);
  assert.deepEqual(h.state.ladder.placements, [{markerIndex: 0, x: 24.75, y: 17.5}]);
  assert.equal(h.marker(0).attributes["aria-pressed"], "true");
  assert.equal(h.marker(0).dataset.placed, "true");
  assert.equal(h.nodes["ladder-skip"].hidden, false, "initial setup remains skippable after placement");
  h.clickImage(28.375, 18.25);
  assert.deepEqual(h.state.ladder.placements, [{markerIndex: 0, x: 28.375, y: 18.25}]);
  for (const [x, y] of [[40, 50], [-1, 15], [40, 35], [190, 15]]) h.clickImage(x, y);
  assert.deepEqual(h.state.ladder.placements, [{markerIndex: 0, x: 28.375, y: 18.25}]);
  assert.equal(h.messages.at(-1)[0], "Click inside the highlighted ladder lane.");
  h.marker(2).dispatch("click");
  h.clickImage(90, 20);
  h.marker(0).dispatch("click");
  h.nodes["ladder-remove-marker"].dispatch("click");
  assert.deepEqual(h.state.ladder.placements, [{markerIndex: 2, x: 90, y: 20}]);
  assert.equal(h.marker(0).attributes["aria-pressed"], "true", "removal leaves size selected for correction");
  h.nodes["ladder-confirm"].dispatch("click");
  assert.deepEqual(h.actions, ["confirm"]);
}));

test("back preserves placements; changing lane or preset requires the explicit clear action", () => harness(h => {
  h.enterMarkers(); h.marker(0).dispatch("click"); h.clickImage(50, 20);
  h.nodes["ladder-back"].dispatch("click");
  assert.equal(h.state.ladder.placements.length, 1);
  h.select("ladder-lane", "1");
  assert.equal(h.state.ladder.laneIndex, 0);
  assert.equal(h.nodes["ladder-guard"].hidden, false);
  h.nodes["ladder-keep-current"].dispatch("click");
  assert.equal(h.state.ladder.placements.length, 1);
  h.select("ladder-lane", "1");
  h.nodes["ladder-accept-change"].dispatch("click");
  assert.equal(h.state.ladder.laneIndex, 1);
  assert.equal(h.state.ladder.placements.length, 0);
  h.nodes["ladder-use-lane"].dispatch("click");
  h.marker(1).dispatch("click"); h.clickImage(60, 50);
  h.nodes["ladder-change-preset"].dispatch("click");
  h.select("ladder-preset", "other");
  assert.equal(h.state.ladder.preset.id, "example");
  h.nodes["ladder-accept-change"].dispatch("click");
  assert.deepEqual(h.state.ladder, {preset: presets[1], laneIndex: 1, placements: []});
}));

test("keyboard positions and places a subset, with one-pixel and ten-pixel movement and focus restoration", () => harness(h => {
  h.enterMarkers(); h.marker(1).dispatch("click");
  h.nodes["ladder-keyboard"].dispatch("click");
  const cursor = h.nodes["ladder-cursor"];
  assert.equal(document.activeElement, cursor);
  cursor.dispatch("keydown", {key: "ArrowRight"});
  cursor.dispatch("keydown", {key: "ArrowLeft", shiftKey: true});
  assert.equal(h.state.ladder.placements.length, 0, "moving a cursor is not a committed placement");
  cursor.dispatch("keydown", {key: "Enter"});
  assert.deepEqual(h.state.ladder.placements, [{markerIndex: 1, x: 88.5, y: 20}]);
  cursor.dispatch("keydown", {key: "Escape"});
  assert.equal(document.activeElement, h.marker(1));
}));

test("touch scrolling and canceled touches never place; a completed tap does", () => harness(h => {
  h.enterMarkers(); h.marker(0).dispatch("click");
  const overlay = h.nodes["ladder-overlay"];
  overlay.dispatch("pointerdown", {clientX: 80, clientY: 80});
  overlay.dispatch("pointermove", {clientX: 90, clientY: 80});
  overlay.dispatch("pointerup", {clientX: 90, clientY: 80});
  h.clickImage(50, 20);
  assert.equal(h.state.ladder.placements.length, 0);
  overlay.dispatch("pointerdown", {clientX: 80, clientY: 80});
  overlay.dispatch("pointercancel");
  h.clickImage(50, 20);
  assert.equal(h.state.ladder.placements.length, 0);
  overlay.dispatch("pointerdown", {clientX: 85, clientY: 75});
  overlay.dispatch("pointerup", {clientX: 85, clientY: 75});
  h.clickImage(50, 20);
  assert.deepEqual(h.state.ladder.placements, [{markerIndex: 0, x: 50, y: 20}]);
}));

test("empty and failed previews remain escapable; confirmation locks interaction without erasing drafts", () => harness(h => {
  h.enterMarkers();
  h.nodes["ladder-confirm"].dispatch("click");
  assert.deepEqual(h.actions, []);
  h.marker(0).dispatch("click"); h.clickImage(50, 20);
  h.controller.setDisabled(false, true);
  assert.equal(h.nodes["ladder-confirm"].disabled, true);
  assert.equal(h.nodes["ladder-cancel"].disabled, false);
  h.nodes["ladder-cancel"].dispatch("click");
  assert.deepEqual(h.actions, ["cancel"]);
  h.controller.setDisabled(true);
  h.clickImage(60, 20);
  assert.equal(h.state.ladder.placements[0].x, 50);
  h.controller.setDisabled(false);
  h.state.confirmedLadder = true;
  h.controller.render();
  h.nodes["ladder-remove"].dispatch("click");
  assert.deepEqual(h.actions, ["cancel"]);
  h.nodes["ladder-accept-change"].dispatch("click");
  assert.deepEqual(h.actions, ["cancel", "remove"]);
}));
