import assert from "node:assert/strict";
import test from "node:test";
import {annotationFont, drawAnnotations, layoutAnnotations} from "../gel_analyzer/annotation_component_frontend/layout.mjs";

// Deliberately model italic ink extending past both ends of its advance width.
function measure(text, font) {
  const size = Number(font.match(/([\d.]+)px/)[1]);
  const width = text.length * size * (font.includes("bold") ? 0.66 : 0.6);
  return {width, actualBoundingBoxLeft: font.includes("italic") ? 3 : 0,
    actualBoundingBoxRight: width + (font.includes("italic") ? 5 : 0),
    actualBoundingBoxAscent: size * 0.8, actualBoundingBoxDescent: size * 0.2};
}

const lanes = [[0, 0, 400, 8], [0, 40, 400, 52], [0, 88, 400, 100]];
const input = {width: 400, height: 100, lanes,
  annotations: {fontSize: 18, labels: [
    {text: "Top", bold: true, italic: true, color: "#1234ab"},
    {text: "Middle"}, {text: "Bottom", italic: true},
  ], groups: []}};

function rectanglesIntersect(a, b) {
  return a.x - a.width < b.x && b.x - b.width < a.x &&
    a.y - a.boxHeight / 2 < b.y + b.boxHeight / 2 &&
    b.y - b.boxHeight / 2 < a.y + a.boxHeight / 2;
}

function assertLabelsFit(layout) {
  for (const label of layout.labels) {
    assert.ok(label.x - label.width >= 0);
    assert.ok(label.y - label.boxHeight / 2 >= 0);
    assert.ok(label.y + label.boxHeight / 2 <= layout.height);
    assert.ok(label.x + label.overhangRight < layout.gelX);
    assert.ok(label.x - label.advance - label.overhangLeft >= 0);
    const inkTop = label.baseline - label.ascent;
    const inkBottom = label.baseline + label.descent;
    assert.ok(Math.abs((inkTop + inkBottom) / 2 - label.y) < 0.00001);
  }
  for (let index = 0; index < layout.labels.length; index++) {
    for (const other of layout.labels.slice(index + 1)) {
      assert.equal(rectanglesIntersect(layout.labels[index], other), false,
        `Text boxes overlap: ${layout.labels[index].text}, ${other.text}`);
    }
  }
}

test("lane text centers follow native cropped coordinates, with padding for edge labels", () => {
  const original = structuredClone(input);
  const layout = layoutAnnotations(input, measure);
  assert.equal(layout.fontSize, 18);
  assert.equal(layout.imageWidth, 400);
  assert.equal(layout.imageHeight, 100);
  assert.ok(layout.gelY > 12, "top lane ink extends above the gel and gets its own margin");
  for (const [index, label] of layout.laneLabels.entries()) {
    assert.equal(label.y - layout.gelY, (lanes[index][1] + lanes[index][3]) / 2);
    assert.equal(label.font.includes("Arial"), true);
  }
  assert.equal(layout.laneLabels[0].font, "italic bold 18px Arial");
  assert.equal(layout.laneLabels[0].color, "#1234ab");
  assertLabelsFit(layout);
  assert.deepEqual(input, original, "layout must not mutate saved annotations or lane coordinates");
});

test("both group sets coexist, use independent columns, and retain sparse membership ticks", () => {
  const annotations = {...input.annotations, groups: [
    {id: "outer", set: 0, label: "Outer", lanes: [0, 2], bold: true, color: "#aa0000"},
    {id: "nested", set: 0, label: "Nested", lanes: [1], italic: true},
    {id: "replicate", set: 1, label: "Independent set", lanes: [0, 1, 2], bold: true, italic: true},
  ]};
  const layout = layoutAnnotations({...input, annotations}, measure);
  const outer = layout.brackets.find(bracket => bracket.id === "outer");
  const nested = layout.brackets.find(bracket => bracket.id === "nested");
  const set1 = layout.brackets.find(bracket => bracket.id === "replicate");
  assert.equal(outer.top, layout.gelY);
  assert.equal(outer.bottom, layout.gelY + 100);
  assert.deepEqual(outer.ticks, [layout.gelY + 4, layout.gelY + 94]);
  assert.notEqual(outer.track, nested.track);
  assert.ok(set1.x < Math.min(outer.x, nested.x));
  for (const group of layout.groupLabels) {
    const bracket = layout.brackets.find(candidate => candidate.id === group.id);
    assert.equal(group.y, (bracket.top + bracket.bottom) / 2);
    assert.ok(group.x + group.overhangRight < bracket.x);
    assert.ok(bracket.x + bracket.depth < Math.min(...layout.laneLabels.map(label => label.x - label.width)));
  }
  assert.equal(layout.groupLabels[2].font, "italic bold 18px Arial");
  assertLabelsFit(layout);
});

test("disjoint groups share a column while editing membership recomputes the span and tracks", () => {
  const spec = {...input, height: 250, lanes: [[0, 20, 400, 40], [0, 170, 400, 190]],
    annotations: {labels: [{text: "A"}, {text: "B"}], groups: [
      {id: "a", set: 0, label: "First", lanes: [0]},
      {id: "b", set: 0, label: "Second", lanes: [1]},
    ]}};
  const original = layoutAnnotations(spec, measure);
  assert.equal(original.brackets[0].x, original.brackets[1].x);
  spec.annotations.groups[0].lanes = [0, 1];
  const edited = layoutAnnotations(spec, measure);
  assert.notEqual(edited.brackets[0].x, edited.brackets[1].x);
  assert.equal(edited.brackets[0].bottom - edited.gelY, 190);
  assert.ok(edited.width > original.width);
  spec.annotations.groups = [];
  const deleted = layoutAnnotations(spec, measure);
  assert.equal(deleted.brackets.length, 0);
  assert.ok(deleted.width < original.width);
  assert.deepEqual(deleted.laneLabels.map(label => label.text), ["A", "B"]);
});

test("long, bold italic labels expand the margin using ink bounds without resizing the gel", () => {
  const short = layoutAnnotations(input, measure);
  const annotations = structuredClone(input.annotations);
  annotations.labels[1] = {text: "Very long label ".repeat(15), bold: true, italic: true};
  annotations.groups = [{id: "long", set: 1, label: "Long group ".repeat(8), lanes: [0, 2], italic: true}];
  const layout = layoutAnnotations({...input, annotations}, measure);
  assert.ok(layout.gelX > short.gelX + 1000);
  assert.equal(layout.width - layout.gelX, short.width - short.gelX);
  assert.equal(layout.imageWidth, 400);
  assertLabelsFit(layout);
});

test("dense and coincident lane centers preserve the chosen font and never overlap", () => {
  const denseLanes = [[0, 0, 400, 1], [0, 1, 400, 2], [0, 1, 400, 2], [0, 2, 400, 3]];
  const layout = layoutAnnotations({width: 400, height: 4, lanes: denseLanes,
    annotations: {fontSize: 18, labels: denseLanes.map((_, index) => ({text: `Lane ${index}`}))}}, measure);
  assert.equal(layout.fontSize, 18);
  assert.equal(layout.reducedFont, false);
  assert.equal(layout.denseFallback, true);
  for (const label of layout.laneLabels) {
    assert.equal(label.y - layout.gelY, (denseLanes[label.index][1] + denseLanes[label.index][3]) / 2);
  }
  assertLabelsFit(layout);
});

test("default font is 80 percent of average lane height, including mixed heights", () => {
  const equal = layoutAnnotations({width: 400, height: 300,
    lanes: [[0, 0, 400, 100], [0, 100, 400, 200], [0, 200, 400, 300]],
    annotations: {labels: [{text: "A"}, {text: "B"}, {text: "C"}]}}, measure);
  assert.equal(equal.fontSize, 80);
  assert.equal(equal.denseFallback, false, "80px labels fit adjacent 100px lanes in one column");
  assert.ok(equal.laneLabels.every(label => label.track === 0));
  assertLabelsFit(equal);

  const mixed = layoutAnnotations({width: 400, height: 300,
    lanes: [[0, 0, 400, 20], [0, 20, 400, 80], [0, 80, 400, 300]],
    annotations: {labels: [{text: "A"}, {text: "B"}, {text: "C"}],
      groups: [{id: "all", set: 1, label: "Group", lanes: [0, 1, 2]}]}}, measure);
  assert.equal(mixed.fontSize, 80, "a narrow lane must not reduce the average-based default");
  assert.equal(mixed.groupLabels[0].fontSize, 80);
  assert.equal(mixed.denseFallback, true);
  assertLabelsFit(mixed);
});

test("font sizes across 1–4096 are honored for labels and both group sets", () => {
  for (const fontSize of [1, 80, 160, 4096]) {
    const layout = layoutAnnotations({width: 400, height: 100, lanes: [[0, 0, 400, 100]],
      annotations: {fontSize, labels: [{text: "A"}], groups: [
        {id: "a", set: 0, label: "B", lanes: [0]},
        {id: "b", set: 1, label: "C", lanes: [0]},
      ]}}, measure);
    assert.equal(layout.fontSize, fontSize);
    assert.equal(layout.requestedFontSize, fontSize);
    assert.ok(layout.labels.every(label => label.fontSize === fontSize));
    assertLabelsFit(layout);
  }
});

test("missing labels and invalid group members cannot produce invalid geometry", () => {
  const layout = layoutAnnotations({...input, annotations: {groups: [
    {id: "empty", set: 0, label: "Omit", lanes: [-1, 50, NaN]},
    {id: "valid", set: 1, label: "One", lanes: [2, 2, -1, 50]},
  ]}}, measure);
  assert.deepEqual(layout.laneLabels.map(label => label.text), ["", "", ""]);
  assert.equal(layout.groupLabels.length, 1);
  assert.deepEqual(layout.groupLabels[0].lanes, [2]);
  assert.equal(layout.brackets[0].ticks.length, 1);
  assertLabelsFit(layout);
  assert.throws(() => layoutAnnotations({...input, lanes: [[0, NaN, 400, 10]]}, measure), /invalid coordinates/);
});

test("punctuation entirely above or below the baseline remains visually centered", () => {
  for (const metrics of [{actualBoundingBoxAscent: -2, actualBoundingBoxDescent: 4},
    {actualBoundingBoxAscent: 12, actualBoundingBoxDescent: -8}]) {
    const layout = layoutAnnotations({...input, annotations: {labels: [{text: "_"}]}},
      (text, font) => ({...measure(text, font), ...metrics}));
    const label = layout.laneLabels[0];
    assert.equal((label.baseline - metrics.actualBoundingBoxAscent +
      label.baseline + metrics.actualBoundingBoxDescent) / 2, label.y);
    assertLabelsFit(layout);
  }
});

test("composed canvas contains only native image pixels, text, and group strokes", () => {
  const annotations = {...input.annotations, groups: [
    {id: "a", set: 0, label: "Group A", lanes: [0, 1], bold: true, italic: true, color: "#336699"},
    {id: "b", set: 1, label: "Group B", lanes: [1, 2], color: "#008800"},
  ]};
  const layout = layoutAnnotations({...input, annotations}, measure);
  const calls = [];
  const context = Object.fromEntries(["fillRect", "drawImage", "beginPath", "moveTo", "lineTo", "stroke", "fillText"]
    .map(method => [method, function (...args) {
      calls.push({method, args, font: this.font, color: this.fillStyle,
        strokeColor: this.strokeStyle, align: this.textAlign, baseline: this.textBaseline});
    }]));
  const canvas = {getContext: () => context};
  const image = {width: 400, height: 100};
  assert.equal(drawAnnotations(canvas, image, layout, annotations), layout);
  assert.equal(canvas.width, layout.width);
  assert.equal(canvas.height, layout.height);
  assert.deepEqual(calls.find(call => call.method === "drawImage").args,
    [image, layout.gelX, layout.gelY], "drawImage must not scale the original crop");
  const text = calls.filter(call => call.method === "fillText");
  assert.equal(text.length, 5);
  assert.equal(text[0].font, "italic bold 18px Arial");
  assert.equal(text[0].color, "#1234ab");
  assert.equal(text[3].color, "#336699");
  for (const call of text) {
    assert.equal(call.align, "right");
    assert.equal(call.baseline, "alphabetic");
  }
  assert.deepEqual(calls.filter(call => call.method === "stroke").map(call => call.strokeColor),
    ["#336699", "#008800"]);
  assert.equal(calls.filter(call => call.method === "fillRect").length, 1,
    "only the canvas background is filled; editor borders and selections are absent");
});

test("both formatting toggles combine and overlarge compositions fail before canvas allocation", () => {
  assert.equal(annotationFont({bold: true, italic: true}, 20), "italic bold 20px Arial");
  assert.throws(() => layoutAnnotations({...input, width: 32767}, measure), /too large to render/);
  assert.throws(() => layoutAnnotations({...input, width: 8100, height: 8100}, measure), /too large to render/);
  assert.throws(() => layoutAnnotations({...input, annotations: {fontSize: 18, labels: [{text: "x".repeat(5000)}]}}, measure),
    /Shorten labels/);
});
