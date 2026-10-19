import assert from "node:assert/strict";
import test from "node:test";
import {drawAnnotations, layoutAnnotations} from "../gel_analyzer/annotation_component_frontend/layout.mjs";
import {annotationSvg} from "../gel_analyzer/annotation_component_frontend/svg.mjs";
import {ladderImagePoint, manualMarkerAtPoint, moveManualLadderCursor, placeManualLadderMarker,
  pointInImage, removeManualLadderMarker} from "../gel_analyzer/annotation_component_frontend/ladder_geometry.mjs";

function measure(text, font) {
  const size = Number(font.match(/([\d.]+)px/)[1]);
  const width = text.length * size * 0.6;
  return {width, actualBoundingBoxLeft: 1, actualBoundingBoxRight: width + 2,
    actualBoundingBoxAscent: size * 0.8, actualBoundingBoxDescent: size * 0.2};
}

const markers = [{id: "dna", label: "500 bp", x: 71.375, y: 35.25},
  {id: "protein", label: "25 kDa", x: 71.375, y: 82.625}];
const manual = placements => ({mode: "manual", placements});

test("manual add, edit, move and delete preserve identity, fractions, order and the source draft", () => {
  const original = manual([]);
  const added = placeManualLadderMarker(original, "dna", "500 bp", {x: 71.375, y: 35.25}, 200, 100);
  assert.deepEqual(original, manual([]));
  const both = placeManualLadderMarker(added, "protein", "25 kDa", {x: 71.375, y: 82.625}, 200, 100);
  assert.deepEqual(both, manual(markers));
  const edited = placeManualLadderMarker(both, "dna", "  750\nbp  ", {x: 12.5, y: 9.25}, 200, 100);
  assert.deepEqual(edited.placements[0], {id: "dna", label: "750 bp", x: 12.5, y: 9.25});
  assert.deepEqual(edited.placements[1], markers[1]);
  assert.deepEqual(both, manual(markers));
  assert.deepEqual(removeManualLadderMarker(edited, "dna"), manual([markers[1]]));
  assert.deepEqual(removeManualLadderMarker(edited, "missing"), edited);
});

test("manual placement accepts any image pixel without a lane, and rejects margins and invalid text", () => {
  for (const point of [{x: 0, y: 0}, {x: 199.999, y: 99.999}]) {
    assert.equal(pointInImage(point, 200, 100), true);
    assert.ok(placeManualLadderMarker(manual([]), "m", "25 kDa", point, 200, 100));
  }
  for (const point of [null, {x: -0.1, y: 20}, {x: 200, y: 20}, {x: 20, y: 100},
    {x: NaN, y: 20}, {x: 20, y: Infinity}]) {
    assert.equal(pointInImage(point, 200, 100), false);
    assert.equal(placeManualLadderMarker(manual([]), "m", "25 kDa", point, 200, 100), null);
  }
  for (const label of ["", " \t\n", null, 500]) {
    assert.equal(placeManualLadderMarker(manual([]), "m", label, {x: 10, y: 10}, 200, 100), null);
  }
  assert.equal(placeManualLadderMarker(manual([]), "", "500 bp", {x: 10, y: 10}, 200, 100), null);
  assert.equal(placeManualLadderMarker({placements: []}, "m", "500 bp", {x: 10, y: 10}, 200, 100), null);
});

test("manual keyboard motion works on both axes, preserves subpixels and keeps final-edge points stable", () => {
  const point = {x: 71.375, y: 35.25};
  assert.deepEqual(moveManualLadderCursor(point, "ArrowRight", false, 200, 100), {x: 72.375, y: 35.25});
  assert.deepEqual(moveManualLadderCursor(point, "ArrowUp", true, 200, 100), {x: 71.375, y: 25.25});
  assert.deepEqual(moveManualLadderCursor({x: 0, y: 0}, "ArrowLeft", true, 200, 100), {x: 0, y: 0});
  assert.deepEqual(moveManualLadderCursor({x: 199.8, y: 99.8}, "ArrowDown", true, 200, 100), {x: 199.8, y: 99.8});
  assert.deepEqual(moveManualLadderCursor(point, "Enter", false, 200, 100), point);
});

test("manual hit testing chooses the nearest point within the current zoom's native radius", () => {
  const placements = [{id: "first", x: 10, y: 10}, {id: "second", x: 14, y: 10}];
  assert.equal(manualMarkerAtPoint({x: 13, y: 10}, placements, 4).id, "second");
  assert.equal(manualMarkerAtPoint({x: 12, y: 10}, placements, 4).id, "first");
  assert.equal(manualMarkerAtPoint({x: 20, y: 10}, placements, 5), null);
  assert.equal(manualMarkerAtPoint({x: NaN, y: 10}, placements, 5), null);
});

function asPreset(placements) {
  return placements.length ? {preset: {labels: placements.map(marker => marker.label)},
    placements: placements.map((marker, markerIndex) => ({markerIndex, x: marker.x, y: marker.y}))} : null;
}

function withoutEditingMetadata(layout) {
  const result = structuredClone(layout);
  for (const item of [...result.ladderLabels, ...result.guides]) {
    for (const key of ["manual", "id", "pointX", "pointY"]) delete item[key];
  }
  return result;
}

function assertOutsideGel(layout, orientation) {
  for (const label of layout.ladderLabels) {
    assert.ok(label.left >= 0 && label.top >= 0);
    assert.ok(label.right < layout.width && label.bottom < layout.height);
    if (orientation === "wells_top") assert.ok(label.right < layout.gelX, "label stays in left gutter");
    else assert.ok(label.bottom < layout.gelY, "label stays in top gutter");
  }
  for (const guide of layout.guides) {
    if (orientation === "wells_top") {
      assert.ok(guide.startX < layout.gelX && guide.endX < layout.gelX, "dash stays outside gel");
    } else {
      assert.ok(guide.startY < layout.gelY && guide.endY < layout.gelY, "dash stays outside gel");
    }
  }
}

function canvasCalls(layout) {
  const calls = [];
  const context = Object.fromEntries(["fillRect", "drawImage", "beginPath", "moveTo", "lineTo", "stroke",
    "save", "restore", "translate", "rotate", "fillText"].map(method => [method, (...args) => calls.push({
      method, args, font: context.font, fill: context.fillStyle, stroke: context.strokeStyle,
      lineWidth: context.lineWidth, textAlign: context.textAlign, baseline: context.textBaseline,
    })]));
  const canvas = {getContext: () => context};
  drawAnnotations(canvas, {}, layout);
  return {width: canvas.width, height: canvas.height, calls};
}

for (const workflow_orientation of ["wells_left", "wells_top"]) {
  test(`manual labels exactly match preset gutter geometry with ${workflow_orientation} lanes and groups`, () => {
    const input = {width: 200, height: 100, workflow_orientation,
      lanes: workflow_orientation === "wells_top" ? [[30, 0, 50, 100], [100, 0, 120, 100]]
        : [[0, 20, 200, 40], [0, 70, 200, 90]],
      annotations: {fontSize: 18, labels: [{text: "Sample A"}, {text: "Sample B"}],
        groups: [{id: "group", label: "Group", lanes: [0, 1]}]}};
    const placements = [markers[0], {...markers[1], x: 121.375}];
    const snapshot = structuredClone({...input, ladder: manual(placements)});
    const layout = layoutAnnotations(snapshot, measure);
    const preset = layoutAnnotations({...input, ladder: asPreset(placements)}, measure);
    assert.deepEqual(withoutEditingMetadata(layout), preset);
    assert.deepEqual(snapshot, {...input, ladder: manual(placements)}, "saved snapshots stay unchanged");
    assert.equal(layout.ladderLabels.length, 2);
    for (const [index, label] of layout.ladderLabels.entries()) {
      const point = placements[index];
      assert.equal(label.id, point.id);
      assert.equal(label.manual, true);
      assert.equal(label.text, point.label);
      assert.equal(label.pointX, layout.gelX + point.x);
      assert.equal(label.pointY, layout.gelY + point.y);
      assert.equal(label.cropX, point.x);
      assert.equal(label.cropY, point.y);
      assert.equal(layout.guides[index].id, point.id);
      if (workflow_orientation === "wells_top") {
        assert.equal(label.rotation, 0);
        assert.equal(layout.guides[index].y, layout.gelY + point.y);
      } else {
        assert.equal(label.rotation, -Math.PI / 2);
        assert.equal(layout.guides[index].x, layout.gelX + point.x);
      }
    }
    assertOutsideGel(layout, workflow_orientation);
    const longerPlacements = [{...placements[0], label: "Long marker ".repeat(12)}];
    const longer = layoutAnnotations({...input, ladder: manual(longerPlacements)}, measure);
    assert.deepEqual(withoutEditingMetadata(longer),
      layoutAnnotations({...input, ladder: asPreset(longerPlacements)}, measure));
    assertOutsideGel(longer, workflow_orientation);
    for (const current of [layout, longer]) for (const scale of [0.15, 0.4, 1, 2.75]) {
      const rect = {left: -80.25, top: -20.5, width: current.width * scale, height: current.height * scale};
      const point = ladderImagePoint(rect.left + current.ladderLabels[0].pointX * scale,
        rect.top + current.ladderLabels[0].pointY * scale, rect, current);
      assert.ok(Math.abs(point.x - markers[0].x) < 1e-9);
      assert.ok(Math.abs(point.y - markers[0].y) < 1e-9);
    }
  });

  test(`manual edge markers and tiny gels use preset bounds without covering ${workflow_orientation} image pixels`, () => {
    for (const width of [1, 200]) for (const height of [1, 100]) {
      const placements = [{id: "top", label: "500 bp", x: 0, y: 0},
        {id: "bottom", label: "25 kDa", x: width - 0.125, y: height - 0.125}];
      const input = {width, height, workflow_orientation};
      const layout = layoutAnnotations({...input, ladder: manual(placements)}, measure);
      assert.deepEqual(withoutEditingMetadata(layout),
        layoutAnnotations({...input, ladder: asPreset(placements)}, measure));
      assertOutsideGel(layout, workflow_orientation);
      for (const [index, label] of layout.ladderLabels.entries()) {
        assert.equal(label.pointX, layout.gelX + placements[index].x);
        assert.equal(label.pointY, layout.gelY + placements[index].y);
      }
    }
    const input = {width: 200, height: 100, workflow_orientation};
    assert.deepEqual(layoutAnnotations({...input, ladder: manual([])}, measure), layoutAnnotations(input, measure));
  });

  test(`manual nearby and coincident markers follow preset fitting for ${workflow_orientation}`, () => {
    const input = {width: 200, height: 100, workflow_orientation, annotations: {fontSize: 18}};
    const close = [markers[0], {...markers[1], x: markers[0].x + 0.75, y: markers[0].y + 0.75}];
    const layout = layoutAnnotations({...input, ladder: manual(close)}, measure);
    assert.deepEqual(withoutEditingMetadata(layout),
      layoutAnnotations({...input, ladder: asPreset(close)}, measure));
    assert.ok(layout.ladderLabels.every(label => label.fontSize < 18 * 0.8));
    assertOutsideGel(layout, workflow_orientation);
    const [first, second] = layout.ladderLabels;
    if (workflow_orientation === "wells_top") assert.ok(first.bottom < second.top);
    else assert.ok(first.right < second.left);
    const axis = workflow_orientation === "wells_top" ? "y" : "x";
    const coincident = [markers[0], {...markers[1], [axis]: markers[0][axis]}];
    assert.throws(() => layoutAnnotations({...input, ladder: manual(coincident)}, measure), /Two ladder markers are at the same position/);
    assert.throws(() => layoutAnnotations({...input, ladder: asPreset(coincident)}, measure), /Two ladder markers are at the same position/);
  });

  test(`manual ${workflow_orientation} canvas and SVG exactly match presets and escape custom text`, () => {
    const placements = [{id: "marker", label: '<500 bp & "25 kDa">', x: 190.5, y: 0.25}];
    const input = {width: 200, height: 100, workflow_orientation};
    const layout = layoutAnnotations({...input, ladder: manual(placements)}, measure);
    const preset = layoutAnnotations({...input, ladder: asPreset(placements)}, measure);
    assert.deepEqual(canvasCalls(layout), canvasCalls(preset));
    const svg = annotationSvg(layout);
    assert.equal(svg, annotationSvg(preset));
    assert.ok(svg.includes("&lt;500 bp &amp; &quot;25 kDa&quot;&gt;"));
    assert.ok(!svg.includes("NaN") && !svg.includes("undefined"));
    assertOutsideGel(layout, workflow_orientation);
  });
}

test("invalid manual annotations and oversized labels fail before canvas allocation", () => {
  const input = {width: 200, height: 100};
  for (const placement of [{...markers[0], x: 200}, {...markers[0], y: NaN},
    {...markers[0], id: ""}, {...markers[0], label: " "}, null]) {
    assert.throws(() => layoutAnnotations({...input, ladder: manual([placement])}, measure), /manual ladder marker could not be drawn/);
  }
  assert.throws(() => layoutAnnotations({...input, ladder: manual([markers[0], markers[0]])}, measure), /manual ladder marker could not be drawn/);
  for (const workflow_orientation of ["wells_left", "wells_top"]) {
    assert.throws(() => layoutAnnotations({...input, workflow_orientation,
      ladder: manual([{...markers[0], label: "M".repeat(20000)}])}, measure), /too large/);
  }
});
