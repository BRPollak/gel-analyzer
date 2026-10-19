import test from "node:test";
import assert from "node:assert/strict";
import {labelRuns, textSnapshot, formatRange, formatSelection, editText, selectionStyle, formattingStyle, renderRuns} from "../gel_analyzer/annotation_component_frontend/rich_text.mjs";

const label = () => ({text: "Control treated", bold: false, italic: false, color: "#202020"});

test("text undo leaves revised group membership in place", () => {
  const group = {...label(), label: "Group", id: "g1", set: 0, lanes: [0]};
  delete group.text;
  const before = textSnapshot(group, "label");
  formatRange(group, "label", 0, 5, {bold: true});
  group.lanes = [1, 2];
  Object.assign(group, before);
  assert.deepEqual(group.lanes, [1, 2]);
  assert.equal(group.runs[0].bold, false);
});

test("format only selected text, compose styles and preserve neighboring runs", () => {
  const value = label();
  formatRange(value, "text", 8, 15, {color: "#ff0000"});
  formatRange(value, "text", 0, 7, {bold: true});
  formatRange(value, "text", 8, 15, {italic: true});
  assert.deepEqual(value.runs, [
    {text: "Control", bold: true, italic: false, color: "#202020"},
    {text: " ", bold: false, italic: false, color: "#202020"},
    {text: "treated", bold: false, italic: true, color: "#ff0000"},
  ]);
  assert.equal(selectionStyle(value, "text", 0, 7).bold, true);
  assert.equal(selectionStyle(value, "text", 0, 15).mixedColor, true);
  assert.equal(selectionStyle(value, "text", 0, 15).bold, false);
});

test("absent selections and carets toggle the whole label while preserving mixed styles", () => {
  for (const key of ["text", "label"]) for (const range of [null, ...[0, 1, 2].map(start => ({start, end: start}))]) {
    const value = {...label(), [key]: "AB"};
    formatRange(value, key, 0, 1, {bold: true, italic: true, color: "#0000ff"});
    formatRange(value, key, 1, 2, {color: "#ff0000"});
    assert.deepEqual(formattingStyle(value, key, range), {
      bold: false, italic: false, color: "#0000ff", mixedColor: true,
    }, "caret position must not hide the label's mixed formatting");
    assert.deepEqual(formattingStyle(value, key, {start: 0, end: 1}), {
      bold: true, italic: true, color: "#0000ff", mixedColor: false,
    }, "a nonempty range still describes only the selected text");
    for (const name of ["bold", "italic"]) {
      const formatted = structuredClone(value);
      formatSelection(formatted, key, range, name);
      assert.ok(formatted.runs.every(run => run[name]), "first click applies the style to the whole label");
      assert.equal(formatted[name], true, "whole-label defaults stay consistent for later text edits");
      assert.deepEqual(formatted.runs.map(run => run.color), ["#0000ff", "#ff0000"]);
      formatSelection(formatted, key, range, name);
      assert.ok(formatted.runs.every(run => !run[name]), "second click removes it from the whole label");
      formatSelection(formatted, key, {start: 0, end: 1}, name);
      assert.deepEqual(formatted.runs.map(run => [run.text, run[name]]), [["A", true], ["B", false]],
        "an explicit text range formats only that substring");
    }
    formatSelection(value, key, range, "color", "#008000");
    assert.ok(value.runs.every(run => run.color === "#008000"));
    assert.deepEqual(value.runs.map(run => [run.bold, run.italic]), [[true, true], [false, false]],
      "a whole-label color change preserves each substring's font style");
  }
});

test("typing at a style boundary still inherits the text beside the caret", () => {
  for (const key of ["text", "label"]) {
    const value = {...label(), [key]: "AB"};
    formatRange(value, key, 0, 1, {bold: true, italic: true, color: "#0000ff"});
    assert.equal(formattingStyle(value, key, {start: 1, end: 1}).bold, false);
    editText(value, key, "AXB", {start: 1, end: 1});
    assert.deepEqual(value.runs, [
      {text: "AX", bold: true, italic: true, color: "#0000ff"},
      {text: "B", bold: false, italic: false, color: "#202020"},
    ], "whole-label toolbar state does not change the style inherited by new text");
  }
});

test("rerendering selected text preserves editor selection without stealing toolbar focus", t => {
  const globals = ["window", "document", "NodeFilter"];
  const originals = globals.map(name => Object.getOwnPropertyDescriptor(globalThis, name));
  t.after(() => globals.forEach((name, index) => {
    if (originals[index]) Object.defineProperty(globalThis, name, originals[index]);
    else delete globalThis[name];
  }));
  for (const editorFocused of [true, false]) {
    const originalText = {textContent: "AB", length: 2};
    const node = {dataset: {}, textContent: "AB", children: [],
      contains: child => child === originalText,
      replaceChildren(...children) { this.children = children; }};
    const toolbarButton = {};
    let restored = null;
    // The browser retains the editable selection when a toolbar button has focus.
    const selection = {rangeCount: 1, anchorNode: originalText, focusNode: originalText,
      getRangeAt: () => ({startContainer: originalText, startOffset: 1,
        toString: () => "B", cloneRange: () => ({selectNodeContents() {}, setEnd() {}, toString: () => "A"})}),
      removeAllRanges() {},
      addRange(range) {
        restored = range;
        // Chromium focuses contenteditable when its selection is restored.
        document.activeElement = node;
      }};
    globalThis.window = {getSelection: () => selection};
    globalThis.NodeFilter = {SHOW_TEXT: 4};
    globalThis.document = {activeElement: editorFocused ? node : toolbarButton,
      createElement: () => ({textContent: "", style: {setProperty(name, value) { this[name] = value; }}}),
      createTreeWalker: () => {
        const textNodes = node.children.map(child => ({textContent: child.textContent, length: child.textContent.length}));
        return {nextNode: () => textNodes.shift() ?? null};
      },
      createRange: () => ({setStart(text, offset) { this.start = [text.textContent, offset]; },
        setEnd(text, offset) { this.end = [text.textContent, offset]; }})};
    const value = {...label(), text: "AB"};
    formatRange(value, "text", 1, 2, {bold: true, color: "#0000ff"});
    renderRuns(node, value, "text");
    assert.deepEqual(node.children.map(child => [child.textContent, child.style.fontWeight]), [["A", "normal"], ["B", "bold"]]);
    assert.equal(document.activeElement, editorFocused ? node : toolbarButton);
    if (editorFocused) {
      assert.deepEqual([restored.start, restored.end], [["A", 1], ["B", 1]],
        "mouse formatting keeps the same substring selected across newly rendered spans");
    } else {
      assert.equal(restored, null, "keyboard formatting must leave focus on the toolbar button");
    }
  }
});

test("typing, replacing and deleting preserve unaffected styles", () => {
  const value = label();
  formatRange(value, "text", 8, 15, {color: "#ff0000"});
  editText(value, "text", "Control pretreated", {start: 8, end: 8});
  assert.equal(value.runs.at(-1).text, "treated");
  editText(value, "text", "Control pretest", {start: 11, end: 18});
  assert.equal(value.runs.at(-1).text, "test");
  assert.equal(value.runs.at(-1).color, "#ff0000");
  editText(value, "text", "Control test", {start: 8, end: 11});
  assert.deepEqual(value.runs.map(run => run.text), ["Control ", "test"]);
});

test("exact edit range disambiguates repeated characters at style boundaries", () => {
  const value = {...label(), text: "AAA"};
  formatRange(value, "text", 1, 2, {bold: true});
  editText(value, "text", "AA", {start: 0, end: 1});
  assert.deepEqual(value.runs.map(run => [run.text, run.bold]), [["A", true], ["A", false]]);
});

test("group labels, blank labels, plain-text paste, and legacy labels remain usable", () => {
  const value = {label: "Group", bold: false, italic: false, color: "#000000"};
  formatRange(value, "label", 0, 5, {italic: true});
  editText(value, "label", "");
  assert.deepEqual(value.runs, []);
  formatRange(value, "label", 0, 0, {bold: true});
  editText(value, "label", "new\nname");
  assert.equal(value.label, "newname");
  assert.equal(value.runs[0].bold, true);
  assert.deepEqual(labelRuns(label()), [{...label()}]);
});
