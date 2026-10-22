import assert from "node:assert/strict";
import test from "node:test";
import {annotationSvg} from "../gel_analyzer/annotation_component_frontend/svg.mjs";
import {drawAnnotations, layoutAnnotations} from "../gel_analyzer/annotation_component_frontend/layout.mjs";

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
  return a.hasInk && b.hasInk && a.inkLeft < b.inkRight && b.inkLeft < a.inkRight &&
    a.inkTop < b.inkBottom && b.inkTop < a.inkBottom;
}

// Rotated text shares two orthogonal axes. Project actual glyph bounds onto
// those axes rather than treating diagonal text's large screen-aligned box as ink.
function rotatedInkIntersects(a, b) {
  const cos = Math.cos(a.rotation), sin = Math.sin(a.rotation);
  const bounds = label => {
    const u = cos * label.baselineX + sin * label.baselineY;
    const v = -sin * label.baselineX + cos * label.baselineY;
    return {left: u - label.advance + label.inkOffsetLeft,
      right: u - label.advance + label.inkOffsetRight,
      top: v - label.ascent, bottom: v + label.descent};
  };
  const x = bounds(a), y = bounds(b);
  return a.hasInk && b.hasInk && x.left < y.right && y.left < x.right && x.top < y.bottom && y.top < x.bottom;
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
      // Groups in the same user-selected column may overlap instead of moving
      // an individual bracket and label farther away from the gel.
      if (layout.labels[index].kind === "group" && other.kind === "group"
        && layout.labels[index].set === other.set) continue;
      assert.equal(rectanglesIntersect(layout.labels[index], other), false,
        `Visible text overlaps: ${layout.labels[index].text}, ${other.text}`);
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
  assert.deepEqual(layoutAnnotations({...input, ladder: null}, measure), layout);
  assert.deepEqual(layout.ladderLabels, []);
  assert.deepEqual(layout.guides, []);
  assert.equal(layout.ladderTiers, 0);
  assert.equal(layout.width, layout.gelX + input.width + 12);
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
  assert.equal(outer.track, nested.track);
  assert.equal(outer.x, nested.x, "overlapping members retain the selected group column");
  assert.ok(set1.x < Math.min(outer.x, nested.x));
  assert.ok(Math.abs(set1.x + set1.depth - (Math.min(...layout.groupLabels
    .filter(label => label.id !== "replicate").map(label => label.inkLeft)) - layout.bracketGap)) < 1e-9,
    "outer brackets stop before the inner groups' visible text");
  for (const group of layout.groupLabels) {
    const bracket = layout.brackets.find(candidate => candidate.id === group.id);
    assert.equal(group.y, (bracket.top + bracket.bottom) / 2);
    assert.ok(group.inkRight <= bracket.x - layout.bracketGap);
    const covered = layout.laneLabels.filter(label =>
      label.inkTop < bracket.bottom + 4 && label.inkBottom > bracket.top - 4);
    assert.ok(bracket.x + bracket.depth <= Math.min(...covered.map(label => label.inkLeft)) - layout.bracketGap);
    assert.equal(bracket.color, "#000000");
  }
  assert.equal(layout.groupLabels[2].font, "italic bold 18px Arial");
  assertLabelsFit(layout);
});

test("editing membership recomputes group spans without breaking the selected column", () => {
  const spec = {...input, height: 250, lanes: [[0, 20, 400, 40], [0, 170, 400, 190]],
    annotations: {labels: [{text: "A"}, {text: "B"}], groups: [
      {id: "a", set: 0, label: "First", lanes: [0]},
      {id: "b", set: 0, label: "Second", lanes: [1]},
    ]}};
  const original = layoutAnnotations(spec, measure);
  assert.equal(original.brackets[0].x, original.brackets[1].x);
  spec.annotations.groups[0].lanes = [0, 1];
  const edited = layoutAnnotations(spec, measure);
  assert.equal(edited.brackets[0].x, edited.brackets[1].x);
  assert.equal(edited.brackets[0].bottom - edited.gelY, 190);
  assert.equal(edited.width, original.width, "overlapping spans do not create another column");
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

test("a shared group column fits visible lane ink, ignoring padding and unrelated longer labels", () => {
  const specification = {width: 400, height: 260,
    lanes: [[0, 0, 400, 30], [0, 100, 400, 130], [0, 210, 400, 240]],
    annotations: {fontSize: 20, labels: [{text: "A"}, {text: "Very long unrelated lane"}, {text: "BC"}],
      groups: [{id: "top", set: 0, label: "Top", lanes: [0]},
        {id: "bottom", set: 0, label: "Bottom", lanes: [2]}]}};
  const layout = layoutAnnotations(specification, measure);
  const boundary = Math.min(...[0, 2].map(index => layout.laneLabels[index].inkLeft));
  for (const [index, laneIndex] of [0, 2].entries()) {
    const bracket = layout.brackets[index];
    const lane = layout.laneLabels[laneIndex];
    assert.equal(bracket.x + bracket.depth, boundary - layout.bracketGap);
    assert.ok(bracket.x > lane.x - lane.width,
      "the bracket can use empty editor-box padding beside a short label");
  }
  assert.equal(layout.brackets[0].x, layout.brackets[1].x,
    "different lane-label lengths cannot stagger groups within a column");
  assert.equal(layout.groupLabels[0].inkRight, layout.groupLabels[1].inkRight);
  assertLabelsFit(layout);
});

test("close groups in each column stay aligned even when brackets and text overlap", () => {
  const specification = {width: 400, height: 160,
    lanes: [[0, 0, 400, 20], [0, 18, 400, 38], [0, 120, 400, 140]],
    annotations: {fontSize: 20, labels: [{text: "A"}, {text: "Long adjacent lane", italic: true}, {text: "C"}],
      groups: [
        {id: "first", set: 0, label: "First", lanes: [0]},
        {id: "second", set: 0, label: "Second", lanes: [1], italic: true},
        {id: "third", set: 0, label: "Third", lanes: [2]},
        {id: "outer-top", set: 1, label: "Outer top", lanes: [0]},
        {id: "outer-bottom", set: 1, label: "Outer bottom", lanes: [2]},
      ]}};
  const original = structuredClone(specification);
  const layout = layoutAnnotations(specification, measure);
  for (const set of [0, 1]) {
    assert.equal(new Set(layout.brackets.filter(bracket => bracket.set === set).map(bracket => bracket.x)).size, 1);
    assert.equal(new Set(layout.groupLabels.filter(label => label.set === set).map(label => label.inkRight)).size, 1);
  }
  const [first, second] = layout.brackets;
  assert.equal(first.bottom - second.top, 2, "small bracket overlap preserves the original lane spans");
  assert.equal(rectanglesIntersect(layout.groupLabels[0], layout.groupLabels[1]), true,
    "a close group label is allowed to overlap instead of moving to another column");
  assertLabelsFit(layout);
  const reversed = layoutAnnotations({...specification,
    annotations: {...specification.annotations, groups: [...specification.annotations.groups].reverse()}}, measure);
  for (const bracket of layout.brackets) {
    assert.deepEqual(reversed.brackets.find(other => other.id === bracket.id), bracket,
      "group creation order does not change the aligned brackets");
  }
  for (const label of layout.groupLabels) {
    const other = reversed.groupLabels.find(other => other.id === label.id);
    assert.equal(other.inkRight, label.inkRight);
    assert.equal(other.y, label.y);
  }
  assert.deepEqual(specification, original, "alignment must not change saved membership or formatting");
});

test("group brackets use visible mixed-font ink and keep both buffers as fonts grow", () => {
  const measureVisible = (text, font) => {
    const metrics = measure(text, font);
    const characterWidth = metrics.width / text.length;
    const leading = text.length - text.trimStart().length;
    const trailing = text.length - text.trimEnd().length;
    return {...metrics, actualBoundingBoxLeft: metrics.actualBoundingBoxLeft - leading * characterWidth,
      actualBoundingBoxRight: metrics.actualBoundingBoxRight - trailing * characterWidth};
  };
  for (const fontSize of [12, 48, 160]) {
    const layout = layoutAnnotations({width: 400, height: 120, lanes: [[0, 20, 400, 100]],
      annotations: {fontSize, labels: [{text: "    A bold tail  ", runs: [
        {text: "    A ", color: "#cc0000"}, {text: "bold", bold: true}, {text: " tail  ", italic: true},
      ]}], groups: [{id: "a", set: 0, label: "Group", lanes: [0], color: "#ff0000"}]}}, measureVisible);
    const label = layout.laneLabels[0];
    const bracket = layout.brackets[0];
    assert.ok(Math.abs(bracket.x + bracket.depth - (label.inkLeft - layout.bracketGap)) < 1e-9);
    assert.ok(Math.abs(label.inkLeft - (label.x - label.advance + 4 * fontSize * 0.6)) < 1e-9);
    assert.equal(label.runs[1].font, `bold ${fontSize}px Arial`);
    assert.equal(label.runs[2].font, `italic ${fontSize}px Arial`);
    assert.equal(bracket.color, "#000000");
    const gapToLane = layout.laneLabels[0].inkLeft - (bracket.x + bracket.depth);
    const gapToGroup = bracket.x - layout.groupLabels[0].inkRight;
    const requiredGap = Math.max(18, fontSize * 0.4) - 1e-9;
    assert.ok(gapToLane >= requiredGap);
    assert.ok(gapToGroup >= requiredGap);
    assertLabelsFit(layout);
  }
});

test("mixed runs render at measured offsets and preserve each segment's font and color", () => {
  const layout = layoutAnnotations({width: 400, height: 100, lanes: [[0, 0, 400, 100]],
    annotations: {fontSize: 20, labels: [{text: "Red bold italic", color: "#123456", runs: [
      {text: "Red ", color: "#ff0000"}, {text: "bold", bold: true}, {text: " italic", italic: true},
    ]}]}}, measure);
  const label = layout.laneLabels[0];
  assert.equal(label.advance, 4 * 20 * 0.6 + 4 * 20 * 0.66 + 7 * 20 * 0.6);
  assert.equal(label.overhangRight, 5);
  const painted = [];
  const context = {fillRect() {}, drawImage() {}, fillText(text, x, y) {
    painted.push({text, x, y, font: this.font, color: this.fillStyle, align: this.textAlign});
  }};
  drawAnnotations({getContext: () => context}, {}, layout);
  assert.deepEqual(painted.map(run => run.text), ["Red ", "bold", " italic"]);
  assert.deepEqual(painted.map(run => run.font), ["20px Arial", "bold 20px Arial", "italic 20px Arial"]);
  assert.deepEqual(painted.map(run => run.color), ["#ff0000", "#123456", "#123456"]);
  for (const [index, run] of painted.entries()) {
    assert.equal(run.align, "left");
    assert.equal(run.y, label.baseline);
    assert.equal(run.x, label.x - label.advance + label.runs[index].offset);
  }
  assertLabelsFit(layout);
});

test("stale runs cannot replace edited plain text and blank labels do not obstruct brackets", () => {
  const layout = layoutAnnotations({width: 400, height: 100, lanes: [[0, 0, 400, 100]],
    annotations: {fontSize: 20, labels: [{text: " ".repeat(80), runs: [{text: "old", color: "#ff0000"}]}],
      groups: [{id: "a", set: 0, label: "Group", lanes: [0]}]}}, measure);
  assert.equal(layout.laneLabels[0].hasInk, false);
  assert.equal(layout.laneLabels[0].runs[0].text, " ".repeat(80));
  assert.equal(layout.laneLabels[0].runs[0].color, "#000000");
  assert.equal(layout.brackets[0].x + layout.brackets[0].depth, layout.gelX - 14 - layout.bracketGap);
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
  assert.throws(() => layoutAnnotations({...input, lanes: [[0, NaN, 400, 10]]}, measure), /could not be drawn/);
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
    ["#000000", "#000000"]);
  assert.equal(calls.filter(call => call.method === "fillRect").length, 1,
    "only the canvas background is filled; editor borders and selections are absent");
});

test("overlarge compositions fail before canvas allocation", () => {
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
    assert.ok(Math.abs(guide.endY - label.inkBottom - 6) < 1e-9,
      "leader clearance is measured from visible ink, not the white backing");
    assert.ok(guide.endY < guide.startY && guide.startY < layout.gelY);
  }
  for (let index = 0; index < layout.ladderLabels.length; index++) {
    const a = layout.ladderLabels[index];
    for (const b of layout.ladderLabels.slice(index + 1)) {
      assert.equal(a.left < b.right && b.left < a.right && a.top < b.bottom && b.top < a.bottom, false);
    }
  }
}

test("ladder labels keep fractional clicked x and start at 80% of the edited lane font", () => {
  const specification = {...input, annotations: {...input.annotations, fontSize: 72},
    ladder: ladderWith([{markerIndex: 2, x: 173.375, y: 45.25}])};
  const before = structuredClone(specification);
  const layout = layoutAnnotations(specification, measure);
  const label = layout.ladderLabels[0];
  assert.equal(label.fontSize, 57.6, "ladder size follows the edited lane size of 72");
  assert.equal(label.font, "57.6px Arial");
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

test("ladder font follows default and explicit sizes at minimum, fractional and maximum limits", () => {
  for (const [height, laneFontSize] of [[1, 1], [39, 31], [6000, 4096]]) {
    for (const fontSize of [undefined, laneFontSize]) {
      const layout = layoutAnnotations({width: 50, height, lanes: [[0, 0, 50, height]],
        annotations: {fontSize, labels: [{text: "A"}]},
        ladder: ladderWith([{markerIndex: 0, x: 25, y: height / 2}], {labels: ["M"]})}, measure);
      assert.equal(layout.fontSize, laneFontSize);
      assert.equal(layout.ladderLabels[0].fontSize, laneFontSize * 0.8);
      assertLadderFits(layout);
    }
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

test("nearby ladder labels shrink together at one level without moving markers or growing the gutter", () => {
  const placements = [{markerIndex: 0, x: 120.125, y: 45.25}, {markerIndex: 1, x: 122.625, y: 46.5},
    {markerIndex: 2, x: 300.875, y: 47.125}];
  const specification = {...input, annotations: {...input.annotations, fontSize: 72,
    groups: [{id: "all", set: 0, label: "Group", lanes: [0, 1, 2]}]},
    ladder: ladderWith(placements)};
  const before = structuredClone(specification);
  const layout = layoutAnnotations(specification, measure);
  const single = layoutAnnotations({...specification, ladder: ladderWith(placements.slice(0, 1))}, measure);
  assert.equal(layout.ladderTiers, 1);
  assert.ok(layout.ladderLabels[0].fontSize > 0 && layout.ladderLabels[0].fontSize < 72 * 0.8);
  assert.equal(new Set(layout.ladderLabels.map(label => label.fontSize)).size, 1);
  assert.equal(new Set(layout.ladderLabels.map(label => label.inkBottom)).size, 1);
  assert.equal(new Set(layout.guides.map(guide => guide.startY - guide.endY)).size, 1);
  assert.equal(layout.gelY, single.gelY, "fitting text does not add another vertical tier");
  assert.deepEqual(layout.ladderLabels.map(label => [label.cropX, label.cropY]),
    placements.map(placement => [placement.x, placement.y]));
  assert.equal(layout.fontSize, 72);
  assert.ok(layout.labels.every(label => label.fontSize === 72), "lane and group fonts stay unchanged");
  assertLadderFits(layout);
  assertLabelsFit(layout);
  const reversed = layoutAnnotations({...specification, ladder: ladderWith([...placements].reverse())}, measure);
  const byMarker = labels => [...labels].sort((a, b) => a.markerIndex - b.markerIndex);
  assert.deepEqual(byMarker(reversed.ladderLabels), byMarker(layout.ladderLabels),
    "the fitted result is independent of placement order");
  const separated = layoutAnnotations({...specification, ladder: ladderWith([
    {...placements[0], x: 10}, {...placements[1], x: 100}, {...placements[2], x: 300},
  ])}, measure);
  assert.equal(separated.ladderTiers, 1);
  assert.ok(separated.ladderLabels.every(label => label.fontSize === 72 * 0.8),
    "moving close markers apart restores the normal ladder font");
  assert.equal(single.ladderLabels[0].fontSize, 72 * 0.8, "removing the collision restores the normal font");
  assert.equal(separated.gelY, layout.gelY);
  assertLadderFits(separated);
  assert.deepEqual(specification, before, "fitting must not modify saved markers, labels, or fonts");
});

test("coincident and unresolvably close markers request correction instead of hiding or raising labels", () => {
  for (const delta of [0, 0.001]) {
    const specification = {...input, ladder: ladderWith([
      {markerIndex: 0, x: 120.125, y: 45}, {markerIndex: 1, x: 120.125 + delta, y: 46},
    ])};
    const before = structuredClone(specification);
    assert.throws(() => layoutAnnotations(specification, measure), /move|remove/i);
    assert.deepEqual(specification, before, "a recoverable preview error preserves both placements");
  }
});

test("ladder fitting remeasures quantized glyph ink instead of assuming proportional metrics", () => {
  const quantizedMeasure = (text, font) => {
    const metrics = measure(text, font);
    return {...metrics, actualBoundingBoxAscent: Math.ceil(metrics.actualBoundingBoxAscent),
      actualBoundingBoxDescent: Math.ceil(metrics.actualBoundingBoxDescent)};
  };
  const specification = {...input, ladder: ladderWith([
    {markerIndex: 0, x: 120.125, y: 45}, {markerIndex: 1, x: 123.25, y: 46},
  ])};
  const layout = layoutAnnotations(specification, quantizedMeasure);
  const proportional = layoutAnnotations(specification, measure);
  assert.ok(layout.ladderLabels.every(label => label.fontSize < proportional.ladderLabels[0].fontSize),
    "pixel-rounded ink requires a smaller font than a proportional estimate");
  for (const label of layout.ladderLabels) {
    const metrics = quantizedMeasure(label.text, label.font);
    assert.equal(label.inkWidth, metrics.actualBoundingBoxAscent + metrics.actualBoundingBoxDescent);
    assert.equal(label.inkWidth, 2, "actual glyph ink can stay wider than the requested font size");
  }
  assertLadderFits(layout);
  const inseparable = {...specification, ladder: ladderWith([
    {markerIndex: 0, x: 120.125, y: 45}, {markerIndex: 1, x: 121.625, y: 46},
  ])};
  assert.throws(() => layoutAnnotations(inseparable, quantizedMeasure), /move|remove/i);
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
    {markerIndex: 0, x: 120, y: 45}, {markerIndex: 1, x: 123, y: 46},
  ])}, measure);
  const calls = [];
  const context = Object.fromEntries(["fillRect", "drawImage", "beginPath", "moveTo", "lineTo", "stroke",
    "fillText", "save", "restore", "translate", "rotate"].map(method => [method, function (...args) {
    calls.push({method, args, font: this.font, color: this.fillStyle, align: this.textAlign,
      lineWidth: this.lineWidth});
  }]));
  const image = {width: input.width, height: input.height};
  drawAnnotations({getContext: () => context}, image, layout);
  assert.deepEqual(calls.find(call => call.method === "drawImage").args, [image, layout.gelX, layout.gelY]);
  const lastStroke = calls.findLastIndex(call => call.method === "stroke");
  assert.ok(calls.filter(call => call.method === "stroke").every(call => call.lineWidth === 1.8));
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
  assert.ok(layout.ladderLabels.every(label => label.fontSize < input.annotations.fontSize * 0.8));
  assert.deepEqual(ladderText.map(call => call.font), layout.ladderLabels.map(label => label.font),
    "export draws the fitted fonts used to calculate collision-free geometry");
  assert.equal(new Set(layout.guides.map(guide => guide.startY - guide.endY)).size, 1);
});

test("invalid ladder coordinates and oversized top gutters fail before canvas allocation", () => {
  for (const placement of [{markerIndex: 0, x: NaN, y: 45}, {markerIndex: 0, x: 10, y: Infinity},
    {markerIndex: 50, x: 10, y: 45}]) {
    assert.throws(() => layoutAnnotations({...input, ladder: ladderWith([placement])}, measure), /could not be drawn/);
  }
  assert.throws(() => layoutAnnotations({...input, ladder: ladderWith([], {labels: ["M".repeat(20000)]})}, measure),
    /too large to render/);
});

for (const angle of [90, 45]) {
  test(`wells at top ${angle}° groups share one row per set regardless of overlap and creation order`, () => {
    const specification = {width: 160, height: 400, workflow_orientation: "wells_top",
      lanes: [[0, 0, 20, 400], [18, 0, 38, 400], [120, 0, 140, 400]],
      annotations: {fontSize: 20, laneLabelAngle: angle,
        labels: [{text: "A"}, {text: "Long adjacent lane", italic: true}, {text: "C"}], groups: [
          {id: "first", set: 0, label: "First group", lanes: [0]},
          {id: "second", set: 0, label: "Second group", lanes: [1], italic: true},
          {id: "third", set: 0, label: "Third", lanes: [2]},
          {id: "outer-top", set: 1, label: "Outer first", lanes: [0]},
          {id: "outer-bottom", set: 1, label: "Outer last", lanes: [2]},
        ]}};
    const original = structuredClone(specification);
    const layout = layoutAnnotations(specification, measure);
    for (const set of [0, 1]) {
      const brackets = layout.brackets.filter(bracket => bracket.set === set);
      const labels = layout.groupLabels.filter(label => label.set === set);
      assert.equal(new Set(brackets.map(bracket => bracket.y)).size, 1);
      assert.equal(new Set(labels.map(label => label.anchorY)).size, 1,
        "group text ends share the same line, including italic glyph overhang");
      for (const label of labels) {
        assert.ok(Math.abs(label.baselineY + label.endOffsetY - label.anchorY) < 1e-9);
        assert.ok(label.inkTop >= 0 && label.editorTop >= 0);
        assert.ok(label.inkBottom <= brackets[0].y - layout.bracketGap + 1e-9);
        assert.ok(label.editorBottom <= brackets[0].y - layout.bracketGap + 1e-9);
      }
    }
    assert.equal(layout.brackets[0].right - layout.brackets[1].left, 2,
      "adjacent groups keep their spans instead of moving to different rows");
    assert.ok(layout.brackets.find(bracket => bracket.set === 1).y
      < Math.min(...layout.groupLabels.filter(label => label.set === 0).map(label => label.inkTop)),
    "the second row stays above the first row's text");
    const reversed = layoutAnnotations({...specification,
      annotations: {...specification.annotations, groups: [...specification.annotations.groups].reverse()}}, measure);
    for (const bracket of layout.brackets) {
      assert.deepEqual(reversed.brackets.find(other => other.id === bracket.id), bracket);
    }
    for (const label of layout.groupLabels) {
      const other = reversed.groupLabels.find(other => other.id === label.id);
      assert.equal(other.anchorY, label.anchorY);
      assert.equal(other.baselineX, label.baselineX);
      assert.equal(other.baselineY, label.baselineY);
    }
    assert.deepEqual(specification, original);
  });

  test(`wells at top ${angle}° labels, sparse groups and left ladder fit without touching the gel`, () => {
    const specification = {width: 220, height: 400, workflow_orientation: "wells_top",
      lanes: [[0, 0, 18, 400], [22, 0, 40, 400], [202, 0, 220, 400]],
      annotations: {fontSize: 24, laneLabelAngle: angle, labels: [
        {text: "Very long treatment label", bold: true, italic: true},
        {text: "Control", italic: true}, {text: "Right edge", bold: true}], groups: [
        {id: "sparse", set: 0, label: "Replicate group", lanes: [0, 2], italic: true},
        {id: "nested", set: 1, label: "All samples", lanes: [0, 1, 2]}]},
      ladder: {preset: {labels: ["10 kb", "2 kb", "100 bp"]}, laneIndex: 0,
        placements: [{markerIndex: 0, x: 9.25, y: .25}, {markerIndex: 1, x: 10.75, y: 30.5},
          {markerIndex: 2, x: 8, y: 399.5}]}};
    const original = structuredClone(specification);
    const layout = layoutAnnotations(specification, measure);
    assert.equal(layout.imageWidth, 220);
    assert.equal(layout.imageHeight, 400);
    for (const label of layout.labels) {
      assert.equal(label.rotationDegrees, angle);
      assert.ok(label.inkLeft >= 0 && label.inkRight <= layout.width);
      assert.ok(label.inkTop >= 0 && label.inkBottom < layout.gelY);
      assert.ok(label.editorTop >= 0 && label.editorRight <= layout.width);
      for (const other of layout.labels.filter(other => other !== label)) {
        assert.equal(rotatedInkIntersects(label, other), false, `${label.text} overlaps ${other.text}`);
      }
    }
    for (const [index, label] of layout.laneLabels.entries()) {
      assert.equal(label.anchor - layout.gelX, (specification.lanes[index][0] + specification.lanes[index][2]) / 2);
    }
    const bracket = layout.brackets.find(item => item.id === "sparse");
    assert.equal(bracket.horizontal, true);
    assert.equal(bracket.left, layout.gelX);
    assert.equal(bracket.right, layout.gelX + 220);
    assert.deepEqual(bracket.ticks, [layout.gelX + 9, layout.gelX + 211]);
    assert.ok(bracket.y + bracket.depth < Math.min(...layout.laneLabels.map(label => label.inkTop)));
    for (const [index, label] of layout.ladderLabels.entries()) {
      assert.equal(label.rotation, 0);
      assert.ok(label.left >= 0 && label.right < layout.gelX);
      assert.ok(label.top >= 0 && label.bottom <= layout.height);
      assert.ok(Math.abs((label.inkTop + label.inkBottom) / 2 - layout.gelY - specification.ladder.placements[index].y) < 1e-9);
    }
    assert.deepEqual(specification, original);
  });
}

test("top lane font follows width and missing angle retains the 90° default", () => {
  const layout = layoutAnnotations({width: 100, height: 400, workflow_orientation: "wells_top",
    lanes: [[0, 0, 20, 400], [60, 0, 100, 400]], annotations: {labels: [{text: "A"}, {text: "B"}]}}, measure);
  assert.equal(layout.fontSize, 24);
  assert.equal(layout.laneLabelAngle, 90);
});


for (const angle of [45, 90]) {
  test(`top ${angle}° default-sized long labels end on one line without false diagonal collisions`, () => {
    const lanes = Array.from({length: 6}, (_, index) => [index * 60, 0, index * 60 + 24, 400]);
    const annotations = {laneLabelAngle: angle, labels: lanes.map((_, index) =>
      ({text: index % 2 ? `Lane ${index + 1}` : `A long treatment label ${index + 1}`, italic: index === 2}))};
    const layout = layoutAnnotations({width: 324, height: 400, lanes, annotations,
      workflow_orientation: "wells_top"}, measure);
    assert.equal(layout.requestedFontSize, 19, "uses the real default,80% of lane width");
    assert.equal(layout.laneFontSize, 19, "ordinary spacing does not shrink text because its length is large");
    assert.equal(layout.reducedFont, false);
    assert.equal(layout.denseFallback, false);
    assert.equal(new Set(layout.laneLabels.map(label => label.anchorY)).size, 1);
    for (const [index, label] of layout.laneLabels.entries()) {
      assert.equal(label.anchor - layout.gelX, index * 60 + 12);
      assert.ok(label.inkBottom <= layout.gelY - 14);
      for (const other of layout.laneLabels.slice(index + 1)) assert.equal(rotatedInkIntersects(label, other), false);
    }
    if (angle === 45) assert.ok(rectanglesIntersect(layout.laneLabels[0], layout.laneLabels[1]),
      "the regression deliberately includes overlapping screen boxes for non-overlapping parallel text");
  });
}

test("actual dense diagonal collisions fit the lane font without changing anchors or requested size", () => {
  const specification = {width: 150, height: 300, workflow_orientation: "wells_top",
    lanes: Array.from({length: 6}, (_, i) => [i * 25, 0, i * 25 + 24, 300]),
    annotations: {laneLabelAngle: 45, fontSize: 19,
      labels: Array.from({length: 6}, (_, i) => ({text: `Long sample ${i + 1}`, bold: i % 2 === 0})),
      groups: [{id: "g", set: 0, lanes: [0, 2, 4], label: "Sparse group"}]}};
  const before = structuredClone(specification);
  const layout = layoutAnnotations(specification, measure);
  assert.equal(layout.requestedFontSize, 19);
  assert.ok(layout.laneFontSize < 19 && layout.laneFontSize >= 1);
  assert.equal(layout.reducedFont, true);
  assert.equal(layout.groupLabels[0].fontSize, 19, "fitting affects lane text only");
  assert.equal(new Set(layout.laneLabels.map(label => label.anchorY)).size, 1);
  for (const [index, label] of layout.laneLabels.entries()) {
    assert.equal(label.anchor - layout.gelX, index * 25 + 12);
    for (const other of layout.laneLabels.slice(index + 1)) assert.equal(rotatedInkIntersects(label, other), false);
  }
  assert.deepEqual(specification, before, "font preference and lane/group associations remain unchanged");
});


test("fitted diagonal lane text uses identical fonts and anchors in canvas and SVG", () => {
  const layout = layoutAnnotations({width: 75, height: 200, workflow_orientation: "wells_top",
    lanes: [[0, 0, 24, 200], [25, 0, 49, 200], [50, 0, 74, 200]],
    annotations: {fontSize: 19, laneLabelAngle: 45,
      labels: [{text: "First long label"}, {text: "Second long label"}, {text: "Third long label"}]}}, measure);
  assert.equal(layout.reducedFont, true);
  const calls = [];
  const context = Object.fromEntries(["fillRect", "drawImage", "save", "restore", "translate", "rotate", "fillText"].map(method =>
    [method, function (...args) { calls.push({method, args, font: this.font}); }]));
  drawAnnotations({getContext: () => context}, {}, layout);
  assert.deepEqual(calls.filter(call => call.method === "translate").map(call => call.args),
    layout.laneLabels.map(label => [label.baselineX, label.baselineY]));
  assert.deepEqual(calls.filter(call => call.method === "fillText").map(call => call.font),
    layout.laneLabels.map(label => label.font));
  const svg = annotationSvg(layout);
  for (const label of layout.laneLabels) {
    assert.ok(svg.includes(`font-size="${label.fontSize}"`));
    assert.ok(svg.includes(`translate(${label.baselineX} ${label.baselineY}) rotate(45)`));
  }
});


for (const [pitch, thickness] of [[12, 10], [4, 3], [1, 1]]) {
  test(`narrow ${pitch}px lane spacing fits diagonal text without a fixed editor-size floor`, () => {
    const lanes = Array.from({length: 6}, (_, i) => [i * pitch, 0, i * pitch + thickness, 100]);
    const layout = layoutAnnotations({width: pitch * 6, height: 100, lanes, workflow_orientation: "wells_top",
      annotations: {laneLabelAngle: 45, labels: lanes.map((_, i) => ({text: `Lane ${i + 1}`}))}}, measure);
    assert.equal(new Set(layout.laneLabels.map(label => label.anchorY)).size, 1);
    assert.ok(layout.laneFontSize > 0);
    for (const [index, label] of layout.laneLabels.entries()) {
      assert.ok(label.boxHeight < pitch * Math.SQRT1_2,
        "the transformed editable target fits between the parallel labels");
      assert.equal(label.anchor - layout.gelX, index * pitch + thickness / 2);
      for (const other of layout.laneLabels.slice(index + 1)) assert.equal(rotatedInkIntersects(label, other), false);
    }
  });
}
