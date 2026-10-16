import assert from "node:assert/strict";
import test from "node:test";
import {drawRectangle, fitPreviewGeometry, isInsideImage, moveRectangle, nearestHandle, normalizeAngle,
  pointerToImage, readSelection, rectangleCorners, resizeRectangle, rotateRectangle,
  rotationHandle, screenRadius} from "../gel_analyzer/orientation_component_frontend/geometry.mjs";
import {createOrientationEditor} from "../gel_analyzer/orientation_component_frontend/editor.mjs";

const initial = {cx: 200, cy: 150, width: 100, height: 60, angle_degrees: 0};
const approximately = (actual, expected) => assert.ok(Math.abs(actual - expected) < 1e-6, `${actual} != ${expected}`);

test("draw works in every direction and discards collapsed rectangles", () => {
  const expected = {cx: 75, cy: 65, width: 50, height: 70, angle_degrees: 0};
  for (const [start, end] of [
    [[50, 30], [100, 100]], [[100, 100], [50, 30]],
    [[100, 30], [50, 100]], [[50, 100], [100, 30]],
  ]) assert.deepEqual(drawRectangle(start, end), expected);
  assert.equal(drawRectangle([4, 5], [4, 100]), null);
  assert.equal(drawRectangle([4, 5], [100, 6]), null);
});

test("source coordinates and screen handle sizes remain consistent at all preview scales", () => {
  for (const scale of [0.1, 0.4, 1, 1.5]) {
    const rect = {left: 50, top: 80, width: 400 * scale, height: 300 * scale};
    pointerToImage(50 + 101 * scale, 80 + 225 * scale, rect, 400, 300)
      .forEach((coordinate, index) => approximately(coordinate, [101, 225][index]));
    assert.deepEqual(pointerToImage(-100, 800, rect, 400, 300), [0, 300]);
    approximately(screenRadius(8, rect, 400) * scale, 8);
  }
  assert.equal(pointerToImage(5, 5, {width: 0, height: 1}, 400, 300), null);
  assert.deepEqual(pointerToImage(-10, 350, {left: 0, top: 0, width: 400, height: 300}, 400, 300, false), [-10, 350]);
});

test("selection validates all corners and finite numeric geometry", () => {
  assert.deepEqual(readSelection(initial, 400, 300), initial);
  for (const invalid of [null, {}, {...initial, width: 1}, {...initial, height: -3},
    {...initial, cx: NaN}, {...initial, angle_degrees: Infinity}, {...initial, width: "100"},
    {...initial, cx: 0}, {...initial, cy: 20, angle_degrees: 45}]) {
    assert.equal(readSelection(invalid, 400, 300), null);
  }
  assert.equal(readSelection({...initial, angle_degrees: 450}, 400, 300).angle_degrees, 90);
});

test("rotation spans a full turn and preserves the marked source-left edge identity", () => {
  for (const angle of [-180, -90, 0, 90, 179, 270, 360, 450, -450]) {
    const selection = rotateRectangle(initial, angle, 400, 300);
    assert.equal(selection.angle_degrees, normalizeAngle(angle));
    assert.equal(selection.width, initial.width);
    assert.equal(selection.height, initial.height);
    const points = rectangleCorners(selection), {edge, point} = rotationHandle(selection, 1);
    approximately(edge[0], (points[0][0] + points[3][0]) / 2);
    approximately(edge[1], (points[0][1] + points[3][1]) / 2);
    approximately(Math.hypot(point[0] - edge[0], point[1] - edge[1]), 28);
  }
  assert.deepEqual(rectangleCorners(initial), [[150, 120], [250, 120], [250, 180], [150, 180]]);
  assert.equal(rotateRectangle({...initial, cx: 55, cy: 35}, 45, 400, 300), null);
});

test("movement clamps all rotated corners to the image without changing angle or size", () => {
  for (const angle of [0, 23, 89, 170, -135]) {
    const selection = {...initial, angle_degrees: angle};
    for (const [dx, dy] of [[-999, -999], [999, 999], [-999, 999], [999, -999]]) {
      const moved = moveRectangle(selection, dx, dy, 400, 300);
      assert.ok(isInsideImage(moved, 400, 300));
      assert.equal(moved.angle_degrees, angle);
      assert.equal(moved.width, 100);
      assert.equal(moved.height, 60);
    }
  }
});

test("rotated resizing anchors the opposite corner, clips expansion, and cannot invert", () => {
  for (const angle of [0, 25, 90, -150]) {
    const selection = {...initial, angle_degrees: angle};
    const original = rectangleCorners(selection);
    for (const corner of [0, 1, 2, 3]) {
      for (const target of [[-800, -800], [1000, 1000], [200, 150]]) {
        const resized = resizeRectangle(selection, corner, target, 400, 300);
        assert.ok(isInsideImage(resized, 400, 300));
        assert.ok(resized.width >= 2 - 1e-7 && resized.height >= 2 - 1e-7);
        assert.equal(resized.angle_degrees, angle);
        const anchor = (corner + 2) % 4;
        rectangleCorners(resized)[anchor].forEach((coordinate, index) => approximately(coordinate, original[anchor][index]));
      }
    }
  }
});

test("preview fits image plus its rotation-handle gutter in width and available viewport height", () => {
  for (const [imageWidth, imageHeight] of [[2000, 600], [400, 2000], [100, 100]]) {
    const fit = fitPreviewGeometry({imageWidth, imageHeight, availableWidth: 640, viewportHeight: 800, chromeHeight: 120});
    assert.ok(fit.wrapperWidth <= 640);
    assert.ok(imageHeight * fit.scale <= fit.heightBudget);
    assert.ok(fit.scale <= 1);
    approximately(fit.wrapperWidth, imageWidth * fit.scale + 2 * fit.gutter);
  }
});

test("overlapping touch targets pick the nearest corner independently of DOM order", () => {
  const selection = {...initial, width: 8, height: 6, angle_degrees: 20};
  for (const unit of [1, 2, 10]) {
    rectangleCorners(selection).forEach((point, corner) => {
      const handle = nearestHandle(selection, point, unit);
      assert.equal(handle.action, "resize");
      assert.equal(handle.corner, corner);
    });
    assert.equal(nearestHandle(selection, rotationHandle(selection, unit).point, unit).action, "rotate");
  }
  assert.equal(nearestHandle(selection, [1000, 1000], 1), null);
});

class FakeNode {
  constructor(id) {
    this.id = id;
    this.dataset = {};
    this.attributes = {};
    this.events = {};
    this.captures = new Set();
    this.style = {setProperty() {}};
    this.clientWidth = 476;
    this.value = "";
    this.textContent = "";
    this.children = {};
  }
  setAttribute(key, value) {
    this.attributes[key] = String(value);
    if (key.startsWith("data-")) this.dataset[key.slice(5)] = String(value);
  }
  querySelector(selector) { return this.children[selector] ??= new FakeNode(selector); }
  closest() { return this.dataset.action ? this : null; }
  focus() { this.focused = true; }
  getBoundingClientRect() { return {left: 0, top: 0, width: 400, height: this.id === "gel" ? 300 : 20}; }
  addEventListener(type, callback) { (this.events[type] ??= []).push(callback); }
  setPointerCapture(id) { this.captures.add(id); }
  hasPointerCapture(id) { return this.captures.has(id); }
  releasePointerCapture(id) { this.captures.delete(id); }
  dispatch(type, args = {}) {
    let prevented = false;
    for (const handler of this.events[type] ?? []) handler({target: this, pointerId: 1,
      button: 0, clientX: 0, clientY: 0, preventDefault() { prevented = true; }, ...args});
    return prevented;
  }
}

function fixture(selection = initial) {
  const nodes = {};
  const doc = {getElementById: id => nodes[id] ??= new FakeNode(id),
    documentElement: new FakeNode("html"), body: new FakeNode("body")};
  doc.getElementById("selection").dataset.action = "move";
  doc.getElementById("rotation").dataset.action = "rotate";
  for (let index = 0; index < 4; index++) {
    const corner = doc.getElementById(`corner-${index}`);
    corner.dataset.action = "resize";
    corner.dataset.corner = String(index);
  }
  const messages = [], frames = [];
  const host = {parent: {innerHeight: 800, postMessage: message => messages.push(message), addEventListener() {}},
    requestAnimationFrame: callback => { frames.push(callback); return frames.length; },
    addEventListener() {}};
  const editor = createOrientationEditor({document: doc, window: host});
  const args = {token: "initial", revision: 0, width: 400, height: 300, selection,
    image_src: "data:image/png;base64,fixture"};
  editor.render(args);
  const values = () => messages.filter(message => message.type === "streamlit:setComponentValue").map(message => message.value);
  const point = (x, y, target = nodes["gel-image"]) => ({clientX: x, clientY: y, target});
  return {editor, nodes, messages, values, args, point};
}

test("initial rendering emits no selection and completed draw emits source geometry exactly once", () => {
  const {editor, nodes, values, point} = fixture(null);
  assert.deepEqual(values(), []);
  nodes.gel.dispatch("pointerdown", point(100, 80));
  nodes.gel.dispatch("pointermove", point(250, 200));
  assert.deepEqual(values(), []);
  nodes.gel.dispatch("pointerup", point(250, 200));
  nodes.gel.dispatch("lostpointercapture");
  assert.equal(values().length, 1);
  assert.deepEqual(values()[0].selection, {cx: 175, cy: 140, width: 150, height: 120, angle_degrees: 0});
  assert.deepEqual(editor.getSelection(), values()[0].selection);
  assert.equal(nodes.gel.captures.size, 0);
});

test("pointer cancellation and tiny replacement restore prior rectangle without stale emission", () => {
  for (const cancelType of ["pointercancel", "lostpointercapture"]) {
    const {editor, nodes, values, point} = fixture();
    nodes.gel.dispatch("pointerdown", point(200, 150, nodes.selection));
    nodes.gel.dispatch("pointermove", point(220, 170, nodes.selection));
    assert.equal(editor.getSelection().cx, 220);
    nodes.gel.dispatch(cancelType);
    nodes.gel.dispatch("pointerup", point(220, 170));
    assert.deepEqual(editor.getSelection(), initial);
    assert.equal(values().length, 0);
  }
  const {editor, nodes, values, point} = fixture();
  nodes.gel.dispatch("pointerdown", point(10, 10));
  nodes.gel.dispatch("pointerup", point(12, 12));
  assert.deepEqual(editor.getSelection(), initial);
  assert.equal(values().length, 0);
});

test("draw-new explicitly clears server selection and a cancelled draw stays empty", () => {
  const {editor, nodes, values, point} = fixture();
  nodes["draw-new"].dispatch("click");
  assert.equal(values().length, 1);
  assert.equal(values()[0].selection, null);
  nodes.gel.dispatch("pointerdown", point(50, 50));
  nodes.gel.dispatch("pointermove", point(150, 150));
  nodes.gel.dispatch("pointercancel");
  assert.equal(editor.getSelection(), null);
  assert.equal(values().length, 1);
  nodes.gel.dispatch("pointerdown", point(150, 150));
  nodes.gel.dispatch("pointerup", point(50, 50));
  assert.equal(values().length, 2);
  assert.deepEqual(values()[1].selection, {cx: 100, cy: 100, width: 100, height: 100, angle_degrees: 0});
});

test("stale server rerenders cannot roll back completed edits or interrupt active drags", () => {
  const {editor, nodes, values, args, point} = fixture();
  nodes.gel.dispatch("pointerdown", point(200, 150, nodes.selection));
  nodes.gel.dispatch("pointermove", point(220, 170, nodes.selection));
  editor.render(args);
  assert.equal(editor.getSelection().cx, 220);
  nodes.gel.dispatch("pointerup", point(220, 170, nodes.selection));
  const edited = editor.getSelection(), revision = editor.getRevision();
  assert.ok(revision > 0);
  editor.render(args);
  assert.deepEqual(editor.getSelection(), edited);
  editor.render({...args, revision, selection: edited});
  assert.deepEqual(editor.getSelection(), edited);
  nodes["rotate-right"].dispatch("click");
  assert.ok(editor.getRevision() > revision);
  editor.render({...args, revision, selection: edited});
  assert.equal(editor.getSelection().angle_degrees, 90);
  assert.equal(values().length, 2);
});

test("replaced session cancels active pointers and rejects events from previously seen tokens", () => {
  const {editor, nodes, values, args, point} = fixture();
  nodes.gel.dispatch("pointerdown", point(200, 150, nodes.selection));
  nodes.gel.dispatch("pointermove", point(230, 180, nodes.selection));
  editor.render({...args, token: "replacement", selection: null});
  nodes.gel.dispatch("pointerup", point(230, 180));
  editor.render(args);
  assert.equal(editor.getSelection(), null);
  assert.equal(nodes.gel.dataset.token, "replacement");
  assert.equal(nodes.gel.captures.size, 0);
  assert.equal(values().length, 0);
});

test("keyboard move, corner resize and full-turn angle controls each commit valid selection", () => {
  const {editor, nodes, values} = fixture();
  nodes.gel.dispatch("keydown", {target: nodes.selection, key: "ArrowRight", shiftKey: true});
  assert.equal(editor.getSelection().cx, 210);
  nodes.gel.dispatch("keydown", {target: nodes["corner-2"], key: "ArrowDown", shiftKey: true});
  assert.equal(editor.getSelection().height, 70);
  nodes.gel.dispatch("keydown", {target: nodes.rotation, key: "ArrowRight"});
  assert.equal(editor.getSelection().angle_degrees, 1);
  nodes.angle.value = "270";
  nodes.angle.dispatch("change");
  assert.equal(editor.getSelection().angle_degrees, -90);
  nodes["rotate-left"].dispatch("click");
  assert.equal(editor.getSelection().angle_degrees, -180);
  assert.equal(values().length, 5);
  assert.ok(values().every(value => isInsideImage(value.selection, 400, 300)));
});

test("pointer rotation works through the angle wrap and rejected angle preserves selection", () => {
  const {editor, nodes, values, point} = fixture();
  nodes.gel.dispatch("pointerdown", point(122, 150, nodes.rotation));
  nodes.gel.dispatch("pointermove", point(200, 72, nodes.rotation));
  nodes.gel.dispatch("pointerup", point(200, 72, nodes.rotation));
  assert.equal(editor.getSelection().angle_degrees, 90);
  assert.equal(values().length, 1);

  const constrained = fixture({...initial, cx: 55, cy: 35});
  constrained.nodes.angle.value = "45";
  constrained.nodes.angle.dispatch("change");
  assert.deepEqual(constrained.editor.getSelection(), {...initial, cx: 55, cy: 35});
  assert.match(constrained.nodes.feedback.textContent, /outside the image/);
  assert.equal(constrained.values().length, 0);
});
