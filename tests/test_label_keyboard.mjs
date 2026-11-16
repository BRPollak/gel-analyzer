import test from "node:test";
import assert from "node:assert/strict";
import {handleLabelKeydown} from "../gel_analyzer/annotation_component_frontend/label_keyboard.mjs";

function harness(t, windowsDesktop = true) {
  const originals = ["document", "window", "NodeFilter"].map(key => [key, Object.getOwnPropertyDescriptor(globalThis, key)]);
  t.after(() => originals.forEach(([key, descriptor]) => {
    if (descriptor) Object.defineProperty(globalThis, key, descriptor);
    else delete globalThis[key];
  }));
  const selection = {ranges: [], removeAllRanges() { this.ranges = []; }, addRange(range) { this.ranges.push(range); }};
  globalThis.NodeFilter = {SHOW_TEXT: 4};
  globalThis.window = {getSelection: () => selection};
  globalThis.document = {
    activeElement: null,
    createTreeWalker(node) {
      const texts = [{textContent: node.textContent, length: node.textContent.length}];
      return {nextNode: () => texts.shift()};
    },
    createRange() {
      return {setStart(node, offset) { this.start = [node, offset]; },
        setEnd(node, offset) { this.end = [node, offset]; }};
    },
  };
  const label = text => ({textContent: text, contentEditable: "true", hidden: false,
    focus() { document.activeElement = this; }, blur() { document.activeElement = null; }});
  const first = label("Control"), middle = label("Sample"), last = label("Treatment");
  const inputNodes = new Map([["lane:0", first], ["lane:1", middle], ["lane:2", last]]);
  const formats = [], history = [];
  let captures = 0;
  const press = (values, composing = false) => {
    middle.focus();
    const event = {...values, preventDefault() { this.defaultPrevented = true; }};
    handleLabelKeydown(event, {...(windowsDesktop === null ? {} : {windowsDesktop}), composing, node: middle, inputNodes,
      inputLayer: {querySelectorAll: () => [...inputNodes.values()]},
      captureSelection: () => captures++, applyFormat: value => formats.push(value),
      undoRedo: redo => history.push(redo)});
    return event;
  };
  return {first, middle, last, press, selection, formats, history, captures: () => captures};
}

test("IME candidate keys leave the label, selection, formatting, and history untouched", t => {
  const h = harness(t);
  const keys = ["Enter", "ArrowUp", "ArrowDown", "Tab", "b", "i", "z", "y"];
  for (const mode of ["composition-session", "event-composing", "process-key"]) {
    for (const key of keys) {
      const event = h.press({key, ctrlKey: ["b", "i", "z", "y"].includes(key),
        isComposing: mode === "event-composing", keyCode: mode === "process-key" ? 229 : 0},
      mode === "composition-session");
      assert.equal(event.defaultPrevented, undefined, `${mode}: ${key} must reach the IME`);
      assert.equal(document.activeElement, h.middle, `${mode}: ${key} must retain label focus`);
      assert.equal(h.selection.ranges.length, 0, `${mode}: ${key} must retain the candidate selection`);
    }
  }
  assert.deepEqual(h.formats, []);
  assert.deepEqual(h.history, []);
  assert.equal(h.captures(), 0);
});

test("normal navigation and shortcuts work again after composition ends", t => {
  const h = harness(t);
  assert.equal(h.press({key: "Enter"}).defaultPrevented, true);
  assert.equal(document.activeElement, null);
  for (const [key, target] of [["ArrowUp", h.first], ["ArrowDown", h.last], ["Tab", h.last]]) {
    assert.equal(h.press({key}).defaultPrevented, true);
    assert.equal(document.activeElement, target);
    assert.equal(h.selection.ranges[0].start[1], 0);
    assert.equal(h.selection.ranges[0].end[1], target.textContent.length);
  }
  h.press({key: "Tab", shiftKey: true});
  assert.equal(document.activeElement, h.first);
  assert.equal(h.captures(), 2);
  for (const [key, values] of [["b", {ctrlKey: true}], ["I", {metaKey: true}],
    ["z", {ctrlKey: true}], ["z", {metaKey: true, shiftKey: true}], ["y", {ctrlKey: true}]]) {
    assert.equal(h.press({key, ...values}).defaultPrevented, true);
    assert.equal(document.activeElement, h.middle);
  }
  assert.deepEqual(h.formats, ["bold", "italic"]);
  assert.deepEqual(h.history, [false, true, true]);
  assert.equal(h.press({key: "a"}).defaultPrevented, undefined);
  assert.equal(document.activeElement, h.middle);
});

for (const flag of [false, null]) {
  test(`Mac/browser keyboard behavior is unchanged with Windows flag ${flag}`, t => {
    const h = harness(t, flag);
    const press = h.press;
    for (const key of ["Enter", "ArrowDown", "b", "z"]) {
      const event = press({key, isComposing: true, keyCode: 229,
        ctrlKey: ["b", "z"].includes(key)}, true);
      assert.equal(event.defaultPrevented, true, `${key} retains its original shortcut behavior`);
      assert.equal(document.activeElement, key === "Enter" ? null : key === "ArrowDown" ? h.last : h.middle);
    }
    assert.deepEqual(h.formats, ["bold"]);
    assert.deepEqual(h.history, [false]);
    const event = press({key: "Tab", isComposing: true}, true);
    assert.equal(event.defaultPrevented, undefined, "the existing Tab composition guard is retained");
    assert.equal(document.activeElement, h.middle);
  });
}
