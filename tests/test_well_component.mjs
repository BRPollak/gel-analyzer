import assert from "node:assert/strict";
import test from "node:test";
import {clampRightEdge, clipPoint, laneBorderLimits, laneDeleteLayout, moveGuideEndpoint, moveLaneBorder, nearestHandle, pointerToImage, readPoints, screenRadius, wellsWithLaneBorders} from "../gel_analyzer/well_component_frontend/geometry.mjs";
import {createLaneReview} from "../gel_analyzer/well_component_frontend/lane_review.mjs";

test("pointer mapping is independent of scale and page offset", () => {
  for (const scale of [1, 0.5, 0.2, 1.25]) {
    const rect = {left: 37, top: 92, width: 1000 * scale, height: 600 * scale};
    assert.deepEqual(pointerToImage(37 + 310 * scale, 92 + 425 * scale, rect, 1000, 600), [310, 425]);
    assert.deepEqual(pointerToImage(rect.left, rect.top, rect, 1000, 600), [0, 0]);
    assert.deepEqual(pointerToImage(rect.left + rect.width, rect.top + rect.height, rect, 1000, 600), [1000, 600]);
    assert.equal(screenRadius(7, rect, 1000) * scale, 7);
  }
});

test("captured pointer clips at all four image edges", () => {
  const rect = {left: 10, top: 20, width: 200, height: 100};
  assert.deepEqual(pointerToImage(-15, -90, rect, 400, 200), [0, 0]);
  assert.deepEqual(pointerToImage(280, 200, rect, 400, 200), [400, 200]);
  assert.deepEqual(clipPoint([125.5, 87.25], 400, 200), [125.5, 87.25]);
  assert.equal(pointerToImage(10, 20, {...rect, width: 0}, 400, 200), null);
});

test("endpoint loading keeps a vertical guide, preserves click order and rejects malformed data", () => {
  assert.deepEqual(readPoints([[13, 180], [11, 15]], 400, 200), [[13, 180], [13, 15]]);
  assert.deepEqual(readPoints([[-1, 500]], 400, 200), [[0, 200]]);
  for (const input of [null, [[NaN, 1]], [[1]], [[1, 2, 3]], [[1, 2], [3, 4], [5, 6]]]) {
    assert.deepEqual(readPoints(input, 400, 200), []);
  }
});

test("either endpoint moves the guide horizontally and adjusts only its own height", () => {
  const points = [[13, 180], [13, 15]];
  assert.deepEqual(moveGuideEndpoint(points, 0, [45, 175], 400, 200), [[45, 175], [45, 15]]);
  assert.deepEqual(moveGuideEndpoint(points, 1, [45, 25], 400, 200), [[45, 180], [45, 25]]);
  assert.deepEqual(moveGuideEndpoint(points, 0, [-10, 220], 400, 200), [[0, 200], [0, 15]]);
  assert.deepEqual(moveGuideEndpoint(points, 1, [450, -10], 400, 200), [[400, 180], [400, 0]]);
  assert.deepEqual(points, [[13, 180], [13, 15]]);
});

test("lane borders round to pixel edges and cannot cross neighbors or collapse", () => {
  const lanes = [[11, 10, 1000, 24], [13, 38, 1000, 55], [9, 80, 1000, 99]];
  assert.deepEqual(laneBorderLimits(lanes, 1, "top", 120), [24, 54]);
  assert.deepEqual(laneBorderLimits(lanes, 1, "bottom", 120), [39, 80]);
  assert.deepEqual(moveLaneBorder(lanes, 1, "top", 11, 120)[1], [13, 24, 1000, 55]);
  assert.deepEqual(moveLaneBorder(lanes, 1, "top", 91, 120)[1], [13, 54, 1000, 55]);
  assert.deepEqual(moveLaneBorder(lanes, 1, "bottom", 90, 120)[1], [13, 38, 1000, 80]);
  assert.deepEqual(moveLaneBorder(lanes, 1, "bottom", 5, 120)[1], [13, 38, 1000, 39]);
  assert.deepEqual(moveLaneBorder(lanes, 0, "top", -500, 120)[0], [11, 0, 1000, 24]);
  assert.deepEqual(moveLaneBorder(lanes, 2, "bottom", 500, 120)[2], [9, 80, 1000, 120]);
  assert.equal(moveLaneBorder(lanes, 1, "top", 29.7, 120)[1][1], 30);
  assert.deepEqual(lanes, [[11, 10, 1000, 24], [13, 38, 1000, 55], [9, 80, 1000, 99]]);
});

test("shared right edge preserves every well and never extends beyond image", () => {
  const wells = [{bounds: [11, 10, 35, 24]}, {bounds: [13, 38, 41, 55]}];
  assert.equal(clampRightEdge(0, wells, 1000), 41);
  assert.equal(clampRightEdge(1001, wells, 1000), 1000);
  assert.equal(clampRightEdge(824.6, wells, 1000), 825);
});

test("well overlays follow lane border adjustments without modifying horizontal evidence", () => {
  const wells = [{bounds: [11, 10, 35, 24], center: [22.5, 17], score: 1},
    {bounds: [13, 38, 41, 55]}];
  const lanes = [[11, 8, 900, 26], [13, 36, 900, 59]];
  assert.deepEqual(wellsWithLaneBorders(wells, lanes), [
    {bounds: [11, 8, 35, 26], center: [22.5, 17], score: 1},
    {bounds: [13, 36, 41, 59], center: [27, 47.5]},
  ]);
  assert.deepEqual(wells[0].bounds, [11, 10, 35, 24]);
});

test("tiny lanes retain independent grips despite overlapping hit areas and DOM order", () => {
  const top = {edge: "top", x: 13, y: 20};
  const bottom = {edge: "bottom", x: 16, y: 21};
  for (const handles of [[top, bottom], [bottom, top]]) {
    assert.equal(nearestHandle(handles, [13, 20], 15), top);
    assert.equal(nearestHandle(handles, [16, 21], 15), bottom);
    assert.equal(nearestHandle(handles, [15.8, 20.8], 15), bottom);
    assert.equal(nearestHandle(handles, [500, 500], 15), null);
  }
  // A thumbnail uses a larger image-coordinate hit radius, with the same pick.
  assert.equal(nearestHandle([bottom, top], [13, 20], 15 / 0.1), top);
});

test("trash controls follow lane ends, remain separate, and fit their reserved gutter at every scale", () => {
  const lanes = [[10, 0, 350, 1], [10, 2, 350, 3], [10, 199, 350, 200]];
  for (const scale of [1, 0.5, 0.2]) {
    const unit = 1 / scale;
    const {buttons, overflow} = laneDeleteLayout(lanes, 200, unit);
    assert.equal(buttons.length, 3);
    buttons.forEach((button, index) => {
      assert.equal((button.x - lanes[index][2]) * scale, 20);
      assert.ok((button.x - lanes[index][2]) * scale + 16 <= 40);
      assert.ok(button.y - 16 * unit >= 0);
      assert.ok(button.y + 16 * unit <= 200 + overflow);
      if (index) assert.ok((button.y - buttons[index - 1].y) * scale >= 32);
    });
  }
  assert.equal(laneDeleteLayout([[10, 10, 150, 70]], 200, 1).buttons[0].x, 170);
  assert.deepEqual(laneDeleteLayout([], 200, 1), {buttons: [], overflow: 0});
});

// The component uses only standard SVG and delegated events. This small DOM
// double exercises its bridge contract without requiring a browser runtime.
class ReviewNode {
  constructor() {
    this.attributes = {};
    this.dataset = {};
    this.style = {};
    this.children = [];
    this.events = {};
    this.captures = new Set();
  }
  setAttribute(key, value) {
    this.attributes[key] = String(value);
    if (key.startsWith("data-")) this.dataset[key.slice(5).replace(/-([a-z])/g, (_, letter) => letter.toUpperCase())] = String(value);
  }
  appendChild(child) { child.parent = this; this.children.push(child); }
  replaceChildren() { this.children = []; }
  querySelector(selector) {
    return this.children.find(child => child.attributes.class === selector.slice(1)) ?? null;
  }
  closest(selector) {
    const attribute = selector.slice(1, -1);
    return attribute in this.attributes ? this : this.parent?.closest(selector) ?? null;
  }
  focus() { this.focused = true; }
  addEventListener(type, callback) { (this.events[type] ??= []).push(callback); }
  getBoundingClientRect() { return {width: 400, height: 200, left: 0, top: 0}; }
  hasPointerCapture(id) { return this.captures.has(id); }
  setPointerCapture(id) { this.captures.add(id); }
  releasePointerCapture(id) { this.captures.delete(id); }
  dispatch(type, event) {
    let prevented = false;
    for (const callback of this.events[type] ?? []) callback({button: 0, pointerId: 1,
      preventDefault() { prevented = true; }, ...event});
    return prevented;
  }
  descendants() { return this.children.flatMap(child => [child, ...child.descendants()]); }
}

test("trash click and keyboard emit one deletion per token without altering local geometry or starting a drag", () => {
  const originalDocument = globalThis.document;
  const svg = new ReviewNode();
  const elements = Object.fromEntries(["lane-review", "excluded-right", "image-wrap"].map(id => [id, new ReviewNode()]));
  globalThis.document = {getElementById: id => elements[id], createElementNS: () => new ReviewNode()};
  try {
    const state = {width: 400, height: 200, reviewMode: "borders", editable: true,
      lanes: [[10, 10, 100, 24], [12, 26, 100, 42]],
      wells: [{bounds: [10, 10, 30, 24]}, {bounds: [12, 26, 33, 42]}], rightEdge: 100};
    const initialLanes = structuredClone(state.lanes);
    const events = [];
    let pointerLookups = 0;
    const review = createLaneReview({svg, getState: () => state,
      pointerPosition: () => { pointerLookups++; return [40, 10]; },
      repaint: () => review.draw(), emit: event => events.push(event)});
    const findButton = index => elements["lane-review"].descendants().find(node => node.dataset.deleteLane === String(index));
    review.reset();
    review.draw();
    let button = findButton(1);
    assert.equal(button.attributes.role, "button");
    assert.equal(button.attributes["aria-label"], "Delete lane 2");
    svg.dispatch("pointerdown", {target: button.children[0]});
    assert.equal(pointerLookups, 0, "trash targets bypass nearest handle picking");
    assert.equal(svg.captures.size, 0);
    assert.equal(button.focused, true);
    svg.dispatch("click", {target: button.children[0]});
    assert.deepEqual(events, [{kind: "lane_review", mode: "borders", action: "delete",
      lane_index: 1, lanes: initialLanes, right_edge: 100}]);
    assert.deepEqual(state.lanes, initialLanes);
    assert.notEqual(events[0].lanes, state.lanes);
    assert.equal(button.attributes["aria-disabled"], "true");
    svg.dispatch("click", {target: findButton(0)});
    svg.dispatch("keydown", {target: button, key: "Enter"});
    assert.equal(events.length, 1, "repeat activation waits for server token reset");

    for (const key of ["Enter", " "]) {
      review.reset();
      review.draw();
      button = findButton(0);
      assert.equal(button.attributes["aria-disabled"], "false");
      assert.equal(svg.dispatch("keydown", {target: button, key}), true);
      assert.equal(events.at(-1).lane_index, 0);
    }
    assert.equal(events.length, 3);
    review.reset();
    state.editable = false;
    review.draw();
    svg.dispatch("click", {target: findButton(0)});
    assert.equal(events.length, 3, "read-only review cannot delete");

    state.editable = true;
    review.reset();
    review.draw();
    const handle = elements["lane-review"].descendants().find(node => node.dataset.reviewEdge === "top" && node.dataset.laneIndex === "0");
    svg.dispatch("pointerdown", {target: handle});
    assert.equal(svg.captures.size, 1, "border handles still start independent drags");
    svg.dispatch("pointerup", {target: handle});
    assert.equal(events.length, 4);
    assert.equal(events.at(-1).kind, "lane_review");
    assert.equal(events.at(-1).action, undefined);
    assert.equal(svg.captures.size, 0);
  } finally {
    if (originalDocument === undefined) delete globalThis.document;
    else globalThis.document = originalDocument;
  }
});

test("guide stays vertical through edits and preserves confirmed results across pending drags", async () => {
  const globals = ["document", "window", "ResizeObserver", "requestAnimationFrame", "cancelAnimationFrame", "getComputedStyle"];
  const originals = new Map(globals.map(name => [name, Object.getOwnPropertyDescriptor(globalThis, name)]));
  const elements = Object.fromEntries(["gel", "component", "gel-image", "image-wrap", "status", "results",
    "endpoint-0", "endpoint-1", "guide", "guide-halo", "lane-review", "excluded-right"]
    .map(id => [id, new ReviewNode()]));
  elements.component.clientWidth = 424;
  for (let index = 0; index < 2; index++) {
    const endpoint = elements[`endpoint-${index}`];
    endpoint.setAttribute("data-endpoint", index);
    for (const className of ["hit", "dot"]) {
      const circle = new ReviewNode();
      circle.setAttribute("class", className);
      endpoint.appendChild(circle);
    }
  }
  const messages = [];
  const host = new ReviewNode();
  host.parent = {innerHeight: 800, postMessage: message => messages.push(message), addEventListener() {}};
  globalThis.document = {getElementById: id => elements[id], createElementNS: () => new ReviewNode()};
  globalThis.window = host;
  globalThis.ResizeObserver = class { observe() {} disconnect() {} };
  globalThis.requestAnimationFrame = () => 1;
  globalThis.cancelAnimationFrame = () => {};
  globalThis.getComputedStyle = () => ({});
  const values = () => messages.filter(message => message.type === "streamlit:setComponentValue").map(message => message.value);
  const svg = elements.gel;
  const pointer = (x, y, target = elements["gel-image"]) => ({clientX: x, clientY: y, target});
  const render = args => host.dispatch("message", {source: host.parent, data: {type: "streamlit:render", args}});
  const shownPoints = () => [0, 1].map(index => {
    const handle = elements[`endpoint-${index}`];
    return [Number(handle.dataset.x), Number(handle.dataset.y)];
  });
  try {
    await import("../gel_analyzer/well_component_frontend/overlay.mjs");
    host.dispatch("message", {source: host.parent, data: {type: "streamlit:render", args: {
      token: "vertical-guide", width: 400, height: 200, editable: true,
      points: [], wells: [], lanes: [], image_src: "data:image/png;base64,fixture",
    }}});
    svg.dispatch("pointerdown", pointer(35, 20));
    svg.dispatch("pointerdown", pointer(80, 180));
    assert.deepEqual(values().at(-1).points, [[35, 20], [35, 180]], "second click cannot angle the guide");

    for (let index = 0; index < 2; index++) {
      const endpoint = elements[`endpoint-${index}`];
      const targetX = 50 + index * 20;
      const targetY = index === 0 ? 30 : 170;
      const before = values().length;
      svg.dispatch("pointerdown", pointer(...shownPoints()[index], endpoint));
      svg.dispatch("pointermove", pointer(targetX, targetY, endpoint));
      assert.equal(elements.guide.attributes.x1, elements.guide.attributes.x2, "live drag remains vertical");
      assert.equal(values().length, before, "drag does not emit intermediate geometry");
      svg.dispatch("pointerup", pointer(targetX, targetY, endpoint));
      assert.equal(values().at(-1).points[0][0], targetX);
      assert.equal(values().at(-1).points[1][0], targetX);
      assert.equal(values().at(-1).points[index][1], targetY);
    }
    assert.deepEqual(shownPoints(), [[70, 30], [70, 170]]);
    svg.dispatch("keydown", {target: elements["endpoint-0"], key: "ArrowLeft", shiftKey: true});
    assert.deepEqual(values().at(-1).points, [[60, 30], [60, 170]]);
    svg.dispatch("keydown", {target: elements["endpoint-1"], key: "ArrowRight"});
    assert.deepEqual(values().at(-1).points, [[61, 30], [61, 170]]);
    svg.dispatch("keydown", {target: elements["endpoint-0"], key: "ArrowDown"});
    assert.deepEqual(values().at(-1).points, [[61, 31], [61, 170]]);
    for (const cancel of ["pointercancel", "lostpointercapture"]) {
      const before = values().length;
      svg.dispatch("pointerdown", pointer(61, 170, elements["endpoint-1"]));
      svg.dispatch("pointermove", pointer(150, 160, elements["endpoint-1"]));
      assert.deepEqual(shownPoints(), [[150, 31], [150, 160]]);
      svg.dispatch(cancel, {target: svg});
      assert.deepEqual(shownPoints(), [[61, 31], [61, 170]], "cancel restores the entire guide");
      assert.equal(values().length, before);
    }
    for (const finishBeforeResult of [false, true]) {
      const args = {token: `detecting-${finishBeforeResult}`, width: 400, height: 200,
        editable: true, points: [[34, 20], [34, 180]], wells: [], lanes: [], image_src: ""};
      render(args);
      svg.dispatch("pointerdown", pointer(34, 180, elements["endpoint-1"]));
      svg.dispatch("pointermove", pointer(70, 185, elements["endpoint-1"]));
      if (finishBeforeResult) svg.dispatch("pointerup", pointer(70, 185, elements["endpoint-1"]));
      render(args);
      assert.deepEqual(shownPoints(), [[70, 20], [70, 185]], "editable reruns cannot roll back local edits");
      const before = values().length;
      render({...args, editable: false,
        wells: [{bounds: [24, 30, 44, 50], center: [34, 40]}], lanes: [[24, 30, 400, 50]]});
      assert.deepEqual(shownPoints(), args.points, "frozen results use the guide that was confirmed");
      const outlines = elements.results.children.filter(node => node.attributes["data-testid"]);
      assert.deepEqual(outlines.map(node => node.attributes["data-testid"]), ["lane-1", "well-1"]);
      assert.equal(svg.captures.size, 0, "freezing results releases an active drag");
      assert.equal(svg.dataset.dragging, "false");
      svg.dispatch("pointerup", pointer(100, 190, elements["endpoint-1"]));
      svg.dispatch("lostpointercapture", {target: svg});
      render(args);
      assert.equal(svg.dataset.editable, "false", "an older editable render cannot reopen a frozen guide");
      assert.deepEqual(shownPoints(), args.points);
      assert.equal(values().length, before, "finishing or cancelling the old drag cannot emit geometry");
      assert.ok(elements.results.children.length > 0, "delayed editable renders cannot hide the result");
    }
  } finally {
    for (const [name, descriptor] of originals) {
      if (descriptor) Object.defineProperty(globalThis, name, descriptor);
      else delete globalThis[name];
    }
  }
});
