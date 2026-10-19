import test from "node:test";
import assert from "node:assert/strict";
import {selectLabelKeys, selectedFormatting, formatSelectedLabels} from "../gel_analyzer/annotation_component_frontend/label_selection.mjs";
import {labelRuns} from "../gel_analyzer/annotation_component_frontend/rich_text.mjs";

const targetsFor = (labels, keys) => keys.map(key => ({label: labels[Number(key.slice(5))], field: "text"}));

test("modifier selection adds and removes individual lanes, including the last one, without editing saved labels", () => {
  const labels = [{text: "Control", bold: true}, {text: "Treatment", color: "#dc2626"}, {text: "Repeat", italic: true}];
  const before = structuredClone(labels);
  let keys = ["lane:0"];
  keys = selectLabelKeys(keys, "lane:2", true);
  assert.deepEqual(keys, ["lane:0", "lane:2"]);
  assert.equal(selectedFormatting(targetsFor(labels, keys)).bold, false);
  keys = selectLabelKeys(keys, "lane:0", true);
  assert.deepEqual(keys, ["lane:2"]);
  keys = selectLabelKeys(keys, "lane:2", true);
  assert.deepEqual(keys, []);
  assert.deepEqual(selectedFormatting(targetsFor(labels, keys)), {});
  formatSelectedLabels([], null, "italic");
  assert.deepEqual(labels, before, "selecting or deselecting alone must never change text, styles, or runs");
  assert.deepEqual(selectLabelKeys(keys, "lane:1", true), ["lane:1"]);
});

test("a regular click selects only that lane, even when it is already part of the selection", () => {
  assert.deepEqual(selectLabelKeys(["lane:0", "lane:2"], "lane:0"), ["lane:0"]);
  assert.deepEqual(selectLabelKeys(["lane:0", "lane:2"], "lane:1"), ["lane:1"]);
  assert.deepEqual(selectLabelKeys(["lane:0", "lane:2"], "group:g", true), ["group:g"]);
  assert.deepEqual(selectLabelKeys(["group:g"], "lane:1", true), ["lane:1"]);
});

test("bulk style toggles resolve mixed values uniformly and leave every unselected label untouched", () => {
  const labels = [{text: "Control", bold: true, color: "#dc2626"},
    {text: "Untouched", bold: true, italic: true, color: "#9333ea"},
    {text: "Treatment", italic: true, color: "#15803d"}];
  const before = structuredClone(labels);
  const targets = targetsFor(labels, ["lane:0", "lane:2"]);
  assert.equal(selectedFormatting(targets).mixedColor, true);
  for (const style of ["bold", "italic"]) {
    formatSelectedLabels(targets, null, style);
    assert.equal(selectedFormatting(targets)[style], true);
    assert.ok(targets.every(({label}) => labelRuns(label).every(run => run[style])));
    formatSelectedLabels(targets, null, style);
    assert.equal(selectedFormatting(targets)[style], false);
    assert.ok(targets.every(({label}) => labelRuns(label).every(run => !run[style])));
  }
  formatSelectedLabels(targets, null, "color", "#2563eb");
  assert.equal(selectedFormatting(targets).color, "#2563eb");
  assert.equal(selectedFormatting(targets).mixedColor, false);
  assert.deepEqual(labels[1], before[1]);
  assert.deepEqual(labels.map(label => label.text), before.map(label => label.text));
});

test("bulk formatting ignores a stale substring range and preserves unrelated rich text styles", () => {
  const labels = [{text: "Red bold", runs: [{text: "Red ", color: "#dc2626"}, {text: "bold", bold: true}]},
    {text: "Green italic", runs: [{text: "Green ", color: "#15803d"}, {text: "italic", italic: true}]}];
  const before = labels.map(label => labelRuns(label));
  const targets = targetsFor(labels, ["lane:0", "lane:1"]);
  const staleRange = {start: 0, end: 3};
  formatSelectedLabels(targets, staleRange, "italic");
  for (const [index, label] of labels.entries()) {
    assert.deepEqual(labelRuns(label), before[index].map(run => ({...run, italic: true})));
  }
  assert.equal(selectedFormatting(targets, staleRange).italic, true);
});

test("returning to one label preserves substring formatting and empty labels can be styled together", () => {
  const labels = [{text: "Control treated"}, {text: ""}];
  formatSelectedLabels(targetsFor(labels, ["lane:0"]), {start: 8, end: 15}, "bold");
  assert.deepEqual(labelRuns(labels[0]).map(run => [run.text, run.bold]), [["Control ", false], ["treated", true]]);
  formatSelectedLabels(targetsFor(labels, ["lane:0", "lane:1"]), null, "italic");
  assert.equal(labels[1].italic, true);
  assert.equal(labels[1].text, "");
  assert.equal(selectedFormatting(targetsFor(labels, ["lane:0", "lane:1"])).italic, true);
});
