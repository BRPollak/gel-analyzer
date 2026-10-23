import test from "node:test";
import assert from "node:assert/strict";
import {layoutAnnotations, drawAnnotations} from "../gel_analyzer/annotation_component_frontend/layout.mjs";
import {annotationSvg} from "../gel_analyzer/annotation_component_frontend/svg.mjs";

function measure(text, font) {
  const size = Number(font.match(/([\d.]+)px/)[1]);
  return {width: text.length * size * 0.6, actualBoundingBoxAscent: size * 0.8, actualBoundingBoxDescent: size * 0.2};
}

const bands = [{x: 3.25, y: 7.75, width: 18.5, height: 10.25}, {x: 140, y: 100, width: 60, height: 40}];
function specification(orientation, ladder) {
  return {width: 200, height: 140, workflow_orientation: orientation, ladder,
    lanes: orientation === "wells_top" ? [[10, 0, 30, 140], [70, 0, 90, 140]] : [[0, 10, 200, 30], [0, 70, 200, 90]],
    annotations: {fontSize: 18, labels: [{text: "Control"}, {text: "Sample"}], groups: []}};
}

for (const orientation of ["wells_left", "wells_top"]) {
  for (const [name, ladder] of [["no ladder", null], ["preset ladder", {preset: {labels: ["500 bp"]},
    placements: [{markerIndex: 0, x: 70, y: 55}]}], ["manual ladder", {mode: "manual",
    placements: [{id: "one", label: "500 bp", x: 70, y: 55}]}]]) {
    test(`${orientation} ${name} keeps extracted bands in native gel coordinates without changing layout`, () => {
      const input = {...specification(orientation, ladder), extractedBands: structuredClone(bands)};
      const before = structuredClone(input);
      const layout = layoutAnnotations(input, measure);
      const unmarked = layoutAnnotations(specification(orientation, ladder), measure);
      assert.deepEqual(layout.extractedBands, bands);
      assert.deepEqual({...layout, extractedBands: []}, unmarked,
        "band outlines never change the image, gutters, annotation anchors or canvas size");
      assert.deepEqual(input, before);
      assert.notEqual(layout.extractedBands, input.extractedBands);
      assert.notEqual(layout.extractedBands[0], input.extractedBands[0]);
    });
  }

  test(`${orientation} canvas adds only thin red outline strokes above the original gel`, () => {
    const layout = layoutAnnotations({...specification(orientation, null), extractedBands: bands}, measure);
    const calls = [];
    const context = Object.fromEntries(["fillRect", "drawImage", "beginPath", "moveTo", "lineTo", "stroke",
      "fillText", "save", "restore", "translate", "rotate"].map(method => [method, function (...args) {
      calls.push({method, args, color: this.strokeStyle, lineWidth: this.lineWidth});
    }]));
    const image = {width: 200, height: 140};
    drawAnnotations({getContext: () => context}, image, layout);
    assert.deepEqual(calls.find(call => call.method === "drawImage").args, [image, layout.gelX, layout.gelY]);
    assert.equal(calls.filter(call => call.method === "fillRect").length, 1,
      "only the background is filled; every band interior stays transparent");
    assert.deepEqual(calls.filter(call => ["moveTo", "lineTo"].includes(call.method)).map(call => call.args),
      bands.flatMap(band => {
        const x = layout.gelX + band.x, y = layout.gelY + band.y;
        return [[x, y], [x + band.width, y], [x + band.width, y + band.height], [x, y + band.height], [x, y]];
      }));
    const strokes = calls.filter(call => call.method === "stroke");
    assert.equal(strokes.length, bands.length);
    assert.ok(strokes.every(call => call.color === "#dc2626" && call.lineWidth === 2));
    assert.ok(calls.findIndex(call => call.method === "drawImage") < calls.findIndex(call => call.method === "stroke"));
  });

  test(`${orientation} SVG exports closed unfilled red paths at the same native coordinates`, () => {
    const layout = layoutAnnotations({...specification(orientation, null), extractedBands: bands}, measure);
    const svg = annotationSvg(layout);
    assert.equal([...svg.matchAll(/stroke="#dc2626"/g)].length, bands.length);
    for (const band of bands) {
      const x = layout.gelX + band.x, y = layout.gelY + band.y;
      assert.ok(svg.includes(`<path d="M ${x} ${y} L ${x + band.width} ${y} L ${x + band.width} ${y + band.height} L ${x} ${y + band.height} L ${x} ${y}" fill="none" stroke="#dc2626" stroke-width="2" stroke-linecap="butt"/>`));
    }
    assert.equal([...svg.matchAll(/<rect /g)].length, 1, "bands add no opaque rectangle fill");
    assert.ok(svg.indexOf("<image ") < svg.indexOf('stroke="#dc2626"'));
  });
}
