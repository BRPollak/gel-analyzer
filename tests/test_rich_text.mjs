import test from "node:test";
import assert from "node:assert/strict";
import {labelRuns, textSnapshot, formatRange, formatSelection, editText, selectionStyle} from "../gel_analyzer/annotation_component_frontend/rich_text.mjs";

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

test("whole-label formatting changes only that property across mixed runs", () => {
  const value = label();
  formatRange(value, "text", 8, 15, {color: "#ff0000"});
  formatRange(value, "text", 3, 3, {bold: true});
  assert.deepEqual(value.runs.map(run => [run.color, run.bold]), [["#202020", true], ["#ff0000", true]]);
});

test("formatting without a saved selection follows the toolbar's whole-label toggle state", () => {
  for (const key of ["text", "label"]) for (const name of ["bold", "italic"]) {
    const value = {...label(), [key]: "AB"};
    formatRange(value, key, 0, 1, {[name]: true});
    assert.equal(selectionStyle(value, key, undefined, undefined)[name], false,
      "a reopened mixed label shows an unpressed formatting button");
    formatSelection(value, key, null, name);
    assert.ok(value.runs.every(run => run[name]), "clicking the unpressed button formats the whole label");
    assert.equal(value[name], true, "whole-label defaults stay consistent for later text edits");
    formatSelection(value, key, null, name);
    assert.ok(value.runs.every(run => !run[name]), "the next click removes formatting from the whole label");
    formatSelection(value, key, {start: 0, end: 1}, name);
    assert.deepEqual(value.runs.map(run => [run.text, run[name]]), [["A", true], ["B", false]],
      "an explicit text range still formats only that substring");
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
