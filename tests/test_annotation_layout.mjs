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

const ladderPreset = {id: "example", name: "Example ladder", labels: ["5.0 kb", "3.0 kb", "1.0 kb"]};

function ladderWith(placements = [], preset = ladderPreset) {
  return {preset, laneIndex: 1, placements};
}

function assertLadderFits(layout) {
  for (const label of layout.ladderLabels) {
    assert.ok(label.left >= 12 && label.top >= 12);
    assert.ok(label.right <= layout.width - 12);
    assert.ok(label.bottom < layout.gelY);
    assert.ok(Math.abs((label.inkLeft + label.inkRight) / 2 - label.x) < 1e-9);
    assert.ok(Math.abs(label.x - layout.gelX - label.cropX) < 1e-9);
  }
  for (const guide of layout.guides) {
    const label = layout.ladderLabels.find(label => label.markerIndex === guide.markerIndex);
    assert.equal(guide.x, label.x);
    assert.equal(guide.startY, layout.gelY - 6);
    assert.equal(guide.endY, label.inkBottom + 4);
    assert.ok(guide.endY < guide.startY && guide.startY < layout.gelY);
  }
  for (let index = 0; index < layout.ladderLabels.length; index++) {
    const a = layout.ladderLabels[index];
    for (const b of layout.ladderLabels.slice(index + 1)) {
      assert.equal(a.left < b.right && b.left < a.right && a.top < b.bottom && b.top < a.bottom, false);
    }
  }
}

test("no ladder retains existing layout and has no extra labels or guides", () => {
  const layout = layoutAnnotations(input, measure);
  assert.deepEqual(layoutAnnotations({...input, ladder: null}, measure), layout);
  assert.deepEqual(layout.ladderLabels, []);
  assert.deepEqual(layout.guides, []);
  assert.equal(layout.ladderTiers, 0);
  assert.equal(layout.width, layout.gelX + input.width + 12);
});

test("ladder labels keep fractional clicked x and half the default font independently of edited lane font", () => {
  const specification = {...input, annotations: {...input.annotations, fontSize: 72},
    ladder: ladderWith([{markerIndex: 2, x: 173.375, y: 45.25}])};
  const before = structuredClone(specification);
  const layout = layoutAnnotations(specification, measure);
  const label = layout.ladderLabels[0];
  assert.equal(label.fontSize, 4.5, "default lane size is 9, even though edited lane size is 72");
  assert.equal(label.font, "4.5px Arial");
  assert.equal(label.text, "1.0 kb");
  assert.equal(label.color, "#202020");
  assert.equal(label.cropX, 173.375);
  assert.equal(label.cropY, 45.25);
  assert.equal(label.rotation, -Math.PI / 2);
  assert.equal(layout.ladderLabels.length, 1, "a preset subset is sufficient");
  assert.equal(layout.fontSize, 72);
  assertLadderFits(layout);
  assertLabelsFit(layout);
  assert.deepEqual(specification, before, "layout must not mutate placement data");
});

test("ladder font halves the bounded default including half-pixel and maximum sizes", () => {
  for (const [height, expected] of [[1, 0.5], [39, 15.5], [6000, 2048]]) {
    const layout = layoutAnnotations({width: 50, height, lanes: [[0, 0, 50, height]],
      annotations: {fontSize: 1, labels: [{text: "A"}]},
      ladder: ladderWith([{markerIndex: 0, x: 25, y: height / 2}], {labels: ["M"]})}, measure);
    assert.equal(layout.ladderLabels[0].fontSize, expected);
    assertLadderFits(layout);
  }
});

test("preset reserves its longest label before placement, without resizing the native crop", () => {
  const preset = {...ladderPreset, labels: ["M", "A longer size label"]};
  const empty = layoutAnnotations({...input, ladder: {preset, laneIndex: null, placements: []}}, measure);
  const short = layoutAnnotations({...input, ladder: ladderWith([{markerIndex: 0, x: 150, y: 45}], preset)}, measure);
  const long = layoutAnnotations({...input, ladder: ladderWith([{markerIndex: 1, x: 150, y: 45}], preset)}, measure);
  assert.ok(empty.gelY > layoutAnnotations(input, measure).gelY);
  assert.equal(empty.gelY, short.gelY);
  assert.equal(empty.gelY, long.gelY);
  assert.equal(empty.ladderTiers, 1);
  assert.equal(long.imageWidth, input.width);
  assert.equal(long.imageHeight, input.height);
  assertLadderFits(long);
});

test("close and coincident ladder labels use vertical tiers without shifting or shrinking", () => {
  const placements = [{markerIndex: 0, x: 120.125, y: 45}, {markerIndex: 1, x: 120.125, y: 46},
    {markerIndex: 2, x: 122.625, y: 47}];
  const layout = layoutAnnotations({...input, ladder: ladderWith(placements)}, measure);
  assert.equal(layout.ladderTiers, 3);
  assert.deepEqual(layout.ladderLabels.map(label => label.tier), [0, 1, 2]);
  assert.ok(layout.ladderLabels.every(label => label.fontSize === 4.5));
  assert.ok(layout.gelY > layoutAnnotations({...input, ladder: ladderWith(placements.slice(0, 1))}, measure).gelY);
  assertLadderFits(layout);
  const reversed = layoutAnnotations({...input, ladder: ladderWith([...placements].reverse())}, measure);
  assert.deepEqual(reversed.ladderLabels.map(label => label.tier), [2, 1, 0], "ties are stable by marker identity");
  const separated = layoutAnnotations({...input, ladder: ladderWith([
    {...placements[0], x: 10}, {...placements[1], x: 100}, {...placements[2], x: 300},
  ])}, measure);
  assert.equal(separated.ladderTiers, 1);
  assertLadderFits(separated);
});

test("rotated ink and backings fit edge markers and do not cover tall lane or group labels", () => {
  const layout = layoutAnnotations({width: 100, height: 100, lanes: [[0, 0, 100, 100]],
    annotations: {fontSize: 160, labels: [{text: "Lane"}],
      groups: [{id: "all", set: 0, label: "Group", lanes: [0]}]},
    ladder: ladderWith([{markerIndex: 0, x: 0, y: 50}, {markerIndex: 1, x: 99.999, y: 50}])}, measure);
  assert.ok(layout.width > layout.gelX + 100 + 12, "rightmost ink expands the right gutter");
  const upperAnnotation = Math.min(...layout.labels.map(label => label.start));
  assert.ok(layout.ladderLabels.every(label => label.bottom + 4 <= upperAnnotation));
  assertLabelsFit(layout);
  assertLadderFits(layout);
});

test("rotated baseline handles glyph overhang and unusual ascent/descent without changing x", () => {
  for (const metrics of [
    {actualBoundingBoxLeft: 3, actualBoundingBoxRight: 20, actualBoundingBoxAscent: 7, actualBoundingBoxDescent: 2},
    {actualBoundingBoxLeft: -2, actualBoundingBoxRight: 20, actualBoundingBoxAscent: -2, actualBoundingBoxDescent: 4},
  ]) {
    const layout = layoutAnnotations({...input, ladder: ladderWith([{markerIndex: 0, x: 76.8125, y: 45}])},
      (text, font) => ({...measure(text, font), ...metrics}));
    const label = layout.ladderLabels[0];
    assert.equal(label.baselineX - metrics.actualBoundingBoxAscent, label.inkLeft);
    assert.equal(label.baselineX + metrics.actualBoundingBoxDescent, label.inkRight);
    assert.equal(label.baselineY - metrics.actualBoundingBoxRight, label.inkTop);
    assert.equal(label.baselineY + metrics.actualBoundingBoxLeft, label.inkBottom);
    assertLadderFits(layout);
  }
});

test("ladder composition draws all leaders behind white label backings and rotated text", () => {
  const layout = layoutAnnotations({...input, ladder: ladderWith([
    {markerIndex: 0, x: 120, y: 45}, {markerIndex: 1, x: 120, y: 46},
  ])}, measure);
  const calls = [];
  const context = Object.fromEntries(["fillRect", "drawImage", "beginPath", "moveTo", "lineTo", "stroke",
    "fillText", "save", "restore", "translate", "rotate"].map(method => [method, function (...args) {
    calls.push({method, args, font: this.font, color: this.fillStyle, align: this.textAlign});
  }]));
  const image = {width: input.width, height: input.height};
  drawAnnotations({getContext: () => context}, image, layout);
  assert.deepEqual(calls.find(call => call.method === "drawImage").args, [image, layout.gelX, layout.gelY]);
  const lastStroke = calls.findLastIndex(call => call.method === "stroke");
  const backings = calls.map((call, index) => ({...call, index})).filter(call => call.method === "fillRect").slice(1);
  assert.equal(backings.length, 2);
  assert.ok(backings.every(call => call.index > lastStroke && call.color === "#ffffff"));
  const firstRotation = calls.findIndex(call => call.method === "rotate");
  assert.ok(backings.every(call => call.index < firstRotation));
  assert.deepEqual(calls.filter(call => call.method === "rotate").map(call => call.args), [[-Math.PI / 2], [-Math.PI / 2]]);
  assert.deepEqual(calls.filter(call => call.method === "translate").map(call => call.args),
    layout.ladderLabels.map(label => [label.baselineX, label.baselineY]));
  assert.equal(calls.filter(call => call.method === "save").length, 2);
  assert.equal(calls.filter(call => call.method === "restore").length, 2);
  const ladderText = calls.filter(call => call.method === "fillText").slice(input.lanes.length);
  assert.ok(ladderText.every(call => call.args[1] === 0 && call.args[2] === 0 && call.align === "left"));
});

test("invalid ladder coordinates and oversized top gutters fail before canvas allocation", () => {
  for (const placement of [{markerIndex: 0, x: NaN, y: 45}, {markerIndex: 0, x: 10, y: Infinity},
    {markerIndex: 50, x: 10, y: 45}]) {
    assert.throws(() => layoutAnnotations({...input, ladder: ladderWith([placement])}, measure), /invalid coordinates/);
  }
  assert.throws(() => layoutAnnotations({...input, ladder: ladderWith([], {labels: ["M".repeat(20000)]})}, measure),
    /too large to render/);
});
