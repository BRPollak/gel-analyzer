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
  assert.equal(annotationPreviewBudget({...input, viewportHeight: 720,
    componentHeight: 950, previewHeight: 220, sidePanel: false, ladderMode: false}), 238);
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
    this.open = false;
    this.value = "";
  }
  setAttribute(key, value) {
    this.attributes[key] = String(value);
    if (key.startsWith("data-")) this.dataset[key.slice(5).replace(/-([a-z])/g, (_, c) => c.toUpperCase())] = String(value);
  }
  removeAttribute(key) { delete this.attributes[key]; }
  get src() { return this.attributes.src ?? ""; }
  set src(value) { this.setAttribute("src", value); }
  showModal() { this.open = true; }
  close() { this.open = false; }
  appendChild(child) { this.children.push(child); child.parent = this; child.parentNode = this; return child; }
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
const referencePresets = [
  {...presets[0], referenceImage: "ladder_references/first.webp", referenceNote: "Supercoiled plasmid sizes."},
  {...presets[1], referenceImage: "ladder_references/second.gif"},
];

function harness(run, overrides = {}) {
  const previousDocument = globalThis.document;
  const html = readFileSync(new URL("../gel_analyzer/annotation_component_frontend/index.html", import.meta.url), "utf8");
  const nodes = Object.fromEntries([...html.matchAll(/<([a-z]+)[^>]*\bid="([^"]+)"/g)]
    .map(match => [match[2], new Node(match[1])]));
  const panelIds = [...Object.keys(nodes)].filter(id => id.startsWith("ladder-")
    && (!id.startsWith("ladder-reference") || id === "ladder-reference-toggle")
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
  const layoutChanges = [];
  // Fixed off-gel hit boxes isolate interaction tests from the shared renderer.
  const getLayout = () => {
    layout.ladderLabels = state.ladder?.mode === "manual" ? state.ladder.placements.map(marker => ({id: marker.id,
      ...(state.workflow_orientation === "wells_top"
        ? {left: 15, right: 65, top: 70 + marker.y - 5, bottom: 70 + marker.y + 5}
        : {left: 80 + marker.x - 5, right: 80 + marker.x + 5, top: 15, bottom: 55})})) : [];
    return layout;
  };
  const controller = createLadderEditor({getState: () => state, getLayout, canvas: nodes.preview,
    onChange() { edits.push(structuredClone(state)); controller.render(); },
    onAction(action) { actions.push(action); }, status(...message) { messages.push(message); },
    onLayout() { layoutChanges.push(true); }});
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
  try { controller.render(); run({state, nodes, layout, actions, edits, messages, layoutChanges, controller, select, clickImage, marker, enterMarkers}); }
  finally {
    if (previousDocument === undefined) delete globalThis.document;
    else globalThis.document = previousDocument;
  }
}

test("preset placement has no default preset; selected markers replace rather than duplicate, and outside clicks do nothing", () => harness(h => {
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

test("lane and preset changes require explicit clearing and update the reference after acceptance", () => harness(h => {
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
  h.nodes["ladder-reference-enlarge"].dispatch("click");
  h.nodes["ladder-change-preset"].dispatch("click");
  h.select("ladder-preset", "other");
  assert.equal(h.state.ladder.preset.id, "example");
  assert.equal(h.nodes["ladder-reference-image"].src, referencePresets[0].referenceImage);
  assert.equal(h.nodes["ladder-reference-dialog"].open, true);
  h.nodes["ladder-accept-change"].dispatch("click");
  assert.deepEqual(h.state.ladder, {preset: referencePresets[1], laneIndex: 1, placements: []});
  assert.equal(h.nodes["ladder-reference-dialog"].open, false);
  assert.equal(h.nodes["ladder-reference-image"].src, referencePresets[1].referenceImage);
  assert.equal(h.nodes["ladder-reference-large"].src, referencePresets[1].referenceImage);
  assert.equal(h.nodes["ladder-reference-note"].hidden, true);
  assert.equal(h.nodes["ladder-reference-selected"].textContent, "");
}, {presets: referencePresets}));

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

test("reference selection and visibility preserve the ladder snapshot and reflect marker status", () => harness(h => {
  assert.equal(h.nodes["ladder-reference"].hidden, true);
  assert.equal(h.nodes["ladder-reference-toggle"].hidden, true);
  assert.equal(h.nodes["ladder-reference-image"].src, "");
  h.enterMarkers();
  assert.deepEqual(h.state.ladder.preset, referencePresets[0]);
  assert.notEqual(h.state.ladder.preset, referencePresets[0]);
  assert.notEqual(h.state.ladder.preset.labels, referencePresets[0].labels);
  assert.deepEqual(h.edits.at(-1).ladder.preset, referencePresets[0]);
  assert.equal(h.nodes["ladder-reference"].hidden, false);
  assert.equal(h.nodes["ladder-reference-name"].textContent, "Example");
  assert.equal(h.nodes["ladder-reference-image"].src, referencePresets[0].referenceImage);
  assert.equal(h.nodes["ladder-reference-large"].src, referencePresets[0].referenceImage);
  assert.match(h.nodes["ladder-reference-image"].alt, /5\.0 kb, 3\.0 kb, 1\.0 kb/);
  assert.equal(h.nodes["ladder-reference-note"].textContent, referencePresets[0].referenceNote);
  assert.equal(h.nodes["ladder-reference-note"].hidden, false);
  assert.equal(h.nodes["ladder-reference-selected"].textContent, "");
  h.marker(1).dispatch("click");
  assert.equal(h.nodes["ladder-reference-selected"].textContent, "Selected: 3.0 kb");
  h.clickImage(50, 20);
  assert.equal(h.nodes["ladder-reference-selected"].textContent, "Selected: 3.0 kb · Placed");
  assert.deepEqual(h.edits.at(-1).ladder.preset, referencePresets[0]);
  const snapshot = structuredClone(h.state.ladder);
  const editCount = h.edits.length;
  const toggle = h.nodes["ladder-reference-toggle"];
  toggle.dispatch("click");
  assert.equal(h.nodes["ladder-reference"].hidden, true);
  assert.equal(toggle.attributes["aria-expanded"], "false");
  assert.equal(h.nodes.component.dataset.referenceOpen, "false");
  toggle.dispatch("click");
  assert.equal(h.nodes["ladder-reference"].hidden, false);
  assert.equal(toggle.attributes["aria-expanded"], "true");
  assert.equal(h.nodes.component.dataset.referenceOpen, "true");
  assert.equal(h.layoutChanges.length, 2);
  h.nodes["ladder-reference-enlarge"].dispatch("click");
  assert.equal(h.nodes["ladder-reference-dialog"].open, true);
  assert.equal(h.nodes["ladder-reference-dialog-title"].textContent, "Example");
  h.nodes["ladder-reference-close"].dispatch("click");
  assert.equal(h.nodes["ladder-reference-dialog"].open, false);
  assert.deepEqual(h.state.ladder, snapshot);
  assert.equal(h.edits.length, editCount);
  assert.deepEqual(h.actions, []);
}, {presets: referencePresets}));

test("a missing reference photo leaves markers and confirmation usable", () => harness(h => {
  h.enterMarkers();
  const editCount = h.edits.length;
  h.nodes["ladder-reference-image"].dispatch("error");
  h.controller.render();
  assert.equal(h.edits.length, editCount);
  assert.equal(h.nodes["ladder-reference-error"].hidden, false);
  assert.equal(h.nodes["ladder-reference-image"].hidden, true);
  assert.equal(h.nodes["ladder-reference-enlarge"].disabled, true);
  h.nodes["ladder-reference-enlarge"].dispatch("click");
  assert.equal(h.nodes["ladder-reference-dialog"].open, false);
  h.marker(2).dispatch("click"); h.clickImage(90, 20);
  assert.equal(h.nodes["ladder-confirm"].disabled, false);
  h.nodes["ladder-confirm"].dispatch("click");
  assert.deepEqual(h.actions, ["confirm"]);
  assert.deepEqual(h.state.ladder.placements, [{markerIndex: 2, x: 90, y: 20}]);
  h.nodes["ladder-change-preset"].dispatch("click"); h.select("ladder-preset", "other");
  h.nodes["ladder-accept-change"].dispatch("click");
  assert.equal(h.nodes["ladder-reference-error"].hidden, true);
  assert.equal(h.nodes["ladder-reference-image"].hidden, false);
  assert.equal(h.nodes["ladder-reference-enlarge"].disabled, false);
}, {presets: referencePresets}));

test("legacy snapshots use a configured photo only for matching identity and labels, and explicit snapshot photos win", () => {
  const cases = [
    {preset: presets[0], expected: referencePresets[0].referenceImage},
    {preset: {...presets[0], id: "custom"}, expected: ""},
    {preset: {...presets[0], labels: ["8 kb", "2 kb"]}, expected: ""},
    {preset: {...presets[0], labels: [...presets[0].labels].reverse()}, expected: ""},
    {preset: {...referencePresets[0], referenceImage: "ladder_references/saved.png"}, expected: "ladder_references/saved.png"},
    {preset: {...referencePresets[0], referenceImage: "https://example.com/photo.png"}, expected: ""},
    {preset: {...referencePresets[0], referenceImage: "ladder_references/../photo.png"}, expected: ""},
  ];
  for (const {preset, expected} of cases) harness(h => {
    assert.equal(h.nodes["ladder-reference-image"].src, expected);
    assert.equal(h.nodes["ladder-reference"].hidden, !expected);
    assert.equal(h.nodes["ladder-reference-toggle"].hidden, !expected);
    assert.deepEqual(h.state.ladder.preset, preset, "reading a legacy reference does not alter the snapshot");
    assert.equal(h.edits.length, 0);
  }, {presets: referencePresets, ladder: {preset, laneIndex: 0, placements: []}, ladderStep: "markers"});
});

test("top ladder keyboard follows downward migration and detected proposals preserve size assignment", () => harness(h => {
  h.select("ladder-preset", "example");
  h.nodes["ladder-continue"].dispatch("click");
  h.select("ladder-lane", "0");
  h.nodes["ladder-use-lane"].dispatch("click");
  h.nodes["ladder-detect-bands"].dispatch("click");
  assert.equal(h.nodes["ladder-detected-bands"].children.length, 2);
  assert.equal(h.nodes["ladder-detected-bands"].children[0].disabled, true, "choose a size before assigning a band");
  h.marker(1).dispatch("click");
  h.nodes["ladder-detected-bands"].children[0].dispatch("click");
  assert.deepEqual(h.state.ladder.placements, [{markerIndex: 1, x: 15, y: 44.25}]);
  const cursor = h.nodes["ladder-cursor"];
  cursor.dispatch("keydown", {key: "ArrowDown", shiftKey: true});
  cursor.dispatch("keydown", {key: "Enter"});
  assert.deepEqual(h.state.ladder.placements, [{markerIndex: 1, x: 15, y: 54.25}]);
  const line = h.nodes["ladder-cursor-line"].attributes;
  assert.equal(line.y1, line.y2);
  assert.equal(Number(line.x2) - Number(line.x1), 20);
  assert.match(cursor.attributes["aria-label"], /Up and Down/);
  h.nodes["ladder-confirm"].dispatch("click");
  assert.deepEqual(h.actions, ["confirm"]);
}, {workflow_orientation: "wells_top", width: 100, height: 200,
  lanes: [[5, 10, 25, 190], [40, 10, 60, 190]],
  bandCandidates: [[{x: 15, y: 44.25}, {x: 15, y: 150}], []]}));

function manualMarker(h, label, x, y) {
  h.clickImage(x, y);
  h.nodes["ladder-manual-label"].value = label;
  h.nodes["ladder-manual-save"].dispatch("click");
  return h.state.ladder.placements.at(-1);
}

test("Manual ladder is independent of presets and lanes and supports add, edit, move and delete", () => harness(h => {
  h.nodes["ladder-manual"].dispatch("click");
  assert.deepEqual(h.state.ladder, {mode: "manual", placements: []});
  assert.equal(h.state.ladderStep, "markers");
  assert.equal(h.nodes["ladder-placement-hint"].textContent, "Click a ladder band to add a marker label.");
  assert.equal(h.nodes["ladder-change-lane"].hidden, true);
  assert.equal(h.nodes["ladder-reference"].hidden, true);
  assert.equal(h.nodes["ladder-detect-bands"].hidden, true);
  const first = manualMarker(h, "500 bp", 20.25, 35.75); // gap outside any lane is valid
  const second = manualMarker(h, "25 kDa", 80.5, 62.25);
  assert.equal(h.state.ladder.placements.length, 2);
  assert.deepEqual([first.label, first.x, first.y], ["500 bp", 20.25, 35.75]);
  h.marker(0).dispatch("click");
  h.nodes["ladder-manual-label"].value = "750 bp";
  h.nodes["ladder-manual-save"].dispatch("click");
  assert.deepEqual(h.state.ladder.placements[0], {...first, label: "750 bp"});
  h.nodes["ladder-manual-move"].dispatch("click");
  h.clickImage(100.375, 70.125);
  assert.deepEqual(h.state.ladder.placements[0], {...first, label: "750 bp", x: 100.375, y: 70.125});
  h.nodes["ladder-manual-delete"].dispatch("click");
  assert.deepEqual(h.state.ladder.placements, [second]);
  h.nodes["ladder-confirm"].dispatch("click");
  assert.deepEqual(h.actions, ["confirm"]);
}, {presets: []}));

test("manual labels validate empty and multiline input and cancel pending labels without touching saved data", () => harness(h => {
  h.nodes["ladder-manual"].dispatch("click");
  h.clickImage(-1, 50);
  assert.equal(h.nodes["ladder-manual-form"].hidden, true);
  h.clickImage(20, 35);
  for (const value of [" ", "500\nbp", "a".repeat(201)]) {
    h.nodes["ladder-manual-label"].value = value;
    h.nodes["ladder-manual-save"].dispatch("click");
    assert.equal(h.state.ladder.placements.length, 0);
    assert.equal(h.nodes["ladder-manual-error"].hidden, false);
  }
  h.nodes["ladder-manual-cancel"].dispatch("click");
  assert.equal(h.nodes["ladder-manual-form"].hidden, true);
  const first = manualMarker(h, "500 bp", 20.25, 35.75);
  h.clickImage(60, 60);
  h.nodes["ladder-manual-label"].value = "25 kDa";
  h.nodes["ladder-confirm"].dispatch("click");
  assert.deepEqual(h.actions, ["confirm"], "confirmation saves a valid pending label first");
  assert.equal(h.state.ladder.placements.length, 2);
  assert.deepEqual(h.state.ladder.placements[0], first);
}));

test("manual labels cannot be dragged over the gel and touch scrolling cannot place markers", () => harness(h => {
  h.nodes["ladder-manual"].dispatch("click");
  const first = manualMarker(h, "500 bp", 20.25, 35.75);
  const overlay = h.nodes["ladder-overlay"];
  const label = h.nodes["ladder-manual-points"].children[0];
  assert.equal(label.children.length, 1);
  assert.equal(label.children[0].tagName, "rect", "only the off-gel text is a selectable hit target");
  assert.ok(Number(label.children[0].attributes.y) + Number(label.children[0].attributes.height) < h.layout.gelY);
  assert.doesNotMatch(label.attributes["aria-label"], /drag/i);
  const down = {target: label, clientX: 70, clientY: 45};
  overlay.dispatch("pointerdown", down);
  overlay.dispatch("pointermove", {clientX: 90, clientY: 90});
  overlay.dispatch("pointerup", {clientX: 90, clientY: 90});
  h.clickImage(60, 60);
  assert.deepEqual(h.state.ladder.placements, [first]);
  assert.equal(h.nodes["ladder-manual-save"].textContent, "Save label", "a drag's trailing click never starts a new label");
  overlay.dispatch("pointerdown", {clientX: 90, clientY: 90});
  overlay.dispatch("pointercancel");
  h.clickImage(80, 40);
  assert.deepEqual(h.state.ladder.placements, [first]);
}));

for (const workflow_orientation of ["wells_left", "wells_top"]) {
  test(`manual keyboard follows the preset migration axis for ${workflow_orientation}`, () => harness(h => {
    h.nodes["ladder-manual"].dispatch("click");
    const first = manualMarker(h, "500 bp", 20.25, 35.75);
    const layer = h.nodes["ladder-manual-points"];
    const top = workflow_orientation === "wells_top";
    layer.dispatch("keydown", {target: layer.children[0], key: top ? "ArrowRight" : "ArrowUp"});
    assert.deepEqual(h.state.ladder.placements[0], first, "the cross-lane axis does not move an annotation");
    layer.dispatch("keydown", {target: layer.children[0], key: top ? "ArrowDown" : "ArrowRight", shiftKey: true});
    assert.deepEqual(h.state.ladder.placements[0], {...first, [top ? "y" : "x"]: first[top ? "y" : "x"] + 10});
    layer.dispatch("keydown", {target: layer.children[0], key: "Delete"});
    assert.deepEqual(h.state.ladder.placements, []);
    assert.equal(h.nodes["ladder-confirm"].disabled, true);
  }, {workflow_orientation}));
}

test("manual and preset switching preserves markers until clearing is accepted", () => harness(h => {
  h.enterMarkers(); h.marker(0).dispatch("click"); h.clickImage(50, 20);
  h.nodes["ladder-change-preset"].dispatch("click");
  h.nodes["ladder-manual"].dispatch("click");
  assert.equal(h.state.ladder.preset.id, "example");
  h.nodes["ladder-keep-current"].dispatch("click");
  h.nodes["ladder-manual"].dispatch("click");
  h.nodes["ladder-accept-change"].dispatch("click");
  const first = manualMarker(h, "500 bp", 20.25, 35.75);
  h.nodes["ladder-back"].dispatch("click");
  assert.equal(h.state.ladderStep, "preset");
  h.nodes["ladder-manual"].dispatch("click");
  assert.deepEqual(h.state.ladder.placements, [first]);
  h.nodes["ladder-change-preset"].dispatch("click");
  h.select("ladder-preset", "example");
  assert.equal(h.state.ladder.mode, "manual");
  h.nodes["ladder-accept-change"].dispatch("click");
  assert.equal(h.state.ladder.preset.id, "example");
  assert.deepEqual(h.state.ladder.placements, []);
}));

test("reopened manual markers survive zoom and resize and labels remain editable", () => harness(h => {
  const original = structuredClone(h.state.ladder);
  h.marker(0).dispatch("click");
  for (const scale of [0.25, 0.75, 1, 2]) {
    h.nodes.preview.getBoundingClientRect = () => ({left: -50, top: 30, width: h.layout.width * scale, height: h.layout.height * scale});
    h.controller.render();
    const dot = h.nodes["ladder-manual-points"].children.find(node => node.dataset.manualCursor).children[1];
    assert.equal(Number(dot.attributes.cx), h.layout.gelX + 20.25);
    assert.equal(Number(dot.attributes.cy), h.layout.gelY + 35.75);
    assert.equal(Number(dot.attributes.r) * scale, 5, "selected band cursor stays visible at every zoom");
    assert.deepEqual(h.state.ladder, original);
  }
  h.marker(0).dispatch("click");
  h.nodes["ladder-manual-label"].value = "25 kDa";
  h.nodes["ladder-manual-save"].dispatch("click");
  assert.equal(h.state.ladder.placements[0].label, "25 kDa");
}, {ladderStep: "markers", ladder: {mode: "manual", placements: [{id: "one", label: "500 bp", x: 20.25, y: 35.75}]}}));

test("manual scroll gestures ignore secondary touches and never reposition annotations", () => harness(h => {
  h.nodes["ladder-manual"].dispatch("click");
  const first = manualMarker(h, "500 bp", 20.25, 35.75);
  const overlay = h.nodes["ladder-overlay"];
  const down = {target: h.nodes["ladder-manual-points"].children[0], clientX: 70, clientY: 83, pointerId: 1};
  overlay.dispatch("pointerdown", down);
  overlay.dispatch("pointerdown", {pointerId: 2, isPrimary: false, clientX: 90, clientY: 93});
  overlay.dispatch("pointermove", {pointerId: 2, clientX: 90, clientY: 93});
  overlay.dispatch("pointerup", {pointerId: 2, clientX: 90, clientY: 93});
  overlay.dispatch("pointercancel", {pointerId: 2});
  assert.deepEqual(h.state.ladder.placements, [first]);
  overlay.dispatch("pointermove", {pointerId: 1, clientX: 80, clientY: 93});
  overlay.dispatch("pointerup", {pointerId: 1, clientX: 80, clientY: 93});
  h.clickImage(50, 60);
  assert.deepEqual(h.state.ladder.placements, [first]);
}));

test("confirm can save the first pending label but cannot bypass a failed preview", () => harness(h => {
  h.nodes["ladder-manual"].dispatch("click");
  h.clickImage(20, 35);
  h.nodes["ladder-manual-label"].value = "500 bp";
  assert.equal(h.nodes["ladder-confirm"].disabled, false);
  h.controller.setDisabled(false, true);
  assert.equal(h.nodes["ladder-confirm"].disabled, true);
  h.controller.setDisabled(false, false);
  h.nodes["ladder-confirm"].dispatch("click");
  assert.deepEqual(h.actions, ["confirm"]);
  assert.equal(h.state.ladder.placements[0].label, "500 bp");
}));
