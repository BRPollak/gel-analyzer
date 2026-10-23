import test from "node:test";
import assert from "node:assert/strict";
import {navigateLaneLabel} from "../gel_analyzer/annotation_component_frontend/label_navigation.mjs";

function harness(run) {
  const previous = {document: globalThis.document, window: globalThis.window, NodeFilter: globalThis.NodeFilter};
  const selection = {ranges: [], removeAllRanges() { this.ranges = []; }, addRange(range) { this.ranges.push(range); }};
  globalThis.NodeFilter = {SHOW_TEXT: 4};
  globalThis.window = {getSelection: () => selection};
  globalThis.document = {
    activeElement: null,
    createTreeWalker(node) {
      const texts = [...node.texts];
      return {nextNode: () => texts.shift()};
    },
    createRange() {
      return {setStart(node, offset) { this.start = [node, offset]; },
        setEnd(node, offset) { this.end = [node, offset]; }};
    },
  };
  const label = (...runs) => ({contentEditable: "true", hidden: false,
    texts: runs.filter(Boolean).map(text => ({textContent: text, length: text.length})), textContent: runs.join(""),
    focus() { document.activeElement = this; }});
  const first = label("Control"), second = label("Red ", "bold", " sample"), third = label("Treatment"), group = label("Group");
  // Creation order and interspersed group labels must not determine lane order.
  const nodes = new Map([["group:g", group], ["lane:2", third], ["lane:0", first], ["lane:1", second]]);
  const press = (node, values = {}) => {
    node.focus();
    const event = {key: "Tab", ...values, preventDefault() { this.defaultPrevented = true; }};
    const handled = navigateLaneLabel(event, node, nodes);
    return {event, handled};
  };
  try { run({first, second, third, group, nodes, press, selection, label}); }
  finally {
    for (const [key, value] of Object.entries(previous)) {
      if (value === undefined) delete globalThis[key];
      else globalThis[key] = value;
    }
  }
}

test("Tab selects the entire next logical lane, including every rich text run", () => harness(h => {
  const {event, handled} = h.press(h.first);
  assert.equal(handled, true);
  assert.equal(event.defaultPrevented, true);
  assert.equal(document.activeElement, h.second);
  assert.deepEqual(h.selection.ranges[0].start, [h.second.texts[0], 0]);
  assert.deepEqual(h.selection.ranges[0].end, [h.second.texts.at(-1), h.second.texts.at(-1).length]);
  h.press(h.second);
  assert.equal(document.activeElement, h.third);
}));

test("Shift+Tab selects the entire previous lane in reverse logical order", () => harness(h => {
  const {event, handled} = h.press(h.third, {shiftKey: true});
  assert.equal(handled, true);
  assert.equal(event.defaultPrevented, true);
  assert.equal(document.activeElement, h.second);
  assert.deepEqual(h.selection.ranges[0].start, [h.second.texts[0], 0]);
  assert.deepEqual(h.selection.ranges[0].end, [h.second.texts.at(-1), h.second.texts.at(-1).length]);
  h.press(h.second, {shiftKey: true});
  assert.equal(document.activeElement, h.first);
}));

test("lane boundaries and other labels retain native keyboard navigation", () => harness(h => {
  for (const [node, values] of [[h.third, {}], [h.first, {shiftKey: true}], [h.group, {}], [h.group, {shiftKey: true}]]) {
    const {event, handled} = h.press(node, values);
    assert.equal(handled, false);
    assert.equal(event.defaultPrevented, undefined);
    assert.equal(document.activeElement, node);
    assert.equal(h.selection.ranges.length, 0);
  }
}));

test("modifier shortcuts, composition, handled events and other keys are untouched", () => harness(h => {
  for (const values of [{altKey: true}, {ctrlKey: true}, {metaKey: true}, {isComposing: true},
    {defaultPrevented: true}, {key: "ArrowDown"}, {key: "Enter"}]) {
    assert.equal(h.press(h.first, values).handled, false);
    assert.equal(document.activeElement, h.first);
    assert.equal(h.selection.ranges.length, 0);
  }
}));

test("empty destination labels accept a caret and unavailable labels are skipped", () => harness(h => {
  h.second.textContent = "";
  h.second.texts = [];
  h.press(h.first);
  assert.equal(document.activeElement, h.second);
  assert.deepEqual(h.selection.ranges[0].start, [h.second, 0]);
  assert.deepEqual(h.selection.ranges[0].end, [h.second, 0]);
  for (const property of ["hidden", "contentEditable"]) {
    h.second[property] = property === "hidden" ? true : "false";
    h.press(h.first);
    assert.equal(document.activeElement, h.third);
    h.second[property] = property === "hidden" ? false : "true";
  }
}));
