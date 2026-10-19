import test from "node:test";
import assert from "node:assert/strict";
import {laneColor, laneGripFraction, nearestLaneBorder} from "../gel_analyzer/well_component_frontend/lane_style.mjs";

test("lane colors and staggered grips follow review identity through resize and deletion", () => {
  const wells = Array.from({length: 6}, (_, index) => ({review_id: index,
    bounds: [10, 10 + index * 12, 30, 20 + index * 12]}));
  const presentation = (well, index) => ({color: laneColor(well, index),
    top: laneGripFraction(well, index, "top"), bottom: laneGripFraction(well, index, "bottom")});
  const original = wells.map(presentation);
  assert.deepEqual(original.map(item => item.color),
    ["#38d9f5", "#fbbf24", "#e9a5ff", "#38d9f5", "#fbbf24", "#e9a5ff"]);
  for (let index = 1; index < wells.length; index++) {
    assert.notEqual(original[index].color, original[index - 1].color);
    assert.notEqual(original[index].top, original[index - 1].top);
  }
  for (const item of original) {
    assert.ok(item.top >= .18 && item.top <= .42);
    assert.ok(item.bottom >= .58 && item.bottom <= .82);
    assert.ok(item.top < item.bottom, "opposite borders retain separate grip columns");
  }
  const edited = wells.filter(well => well.review_id !== 1).map(well => ({...well,
    bounds: [well.bounds[0], well.bounds[1] + 1, well.bounds[2], well.bounds[3] - 1]}));
  edited.forEach((well, index) => assert.deepEqual(presentation(well, index), original[well.review_id]));
  assert.deepEqual(presentation({review_id: 6}, 5), original[0], "new identities continue the palette cycle");
});

test("legacy wells use their index and malformed identities do not produce missing colors", () => {
  for (const well of [null, {}, {review_id: -1}, {review_id: 1.5}, {review_id: "1"}]) {
    assert.equal(laneColor(well, 2), "#e9a5ff");
    assert.equal(laneGripFraction(well, 2, "top"), .42);
  }
  assert.equal(laneColor({review_id: 0}, 2), "#38d9f5");
});

test("border targeting chooses the nearest segment and preserves dense lane centers at varied scales", () => {
  for (const scale of [.2, .5, 1, 1.25]) {
    const sparse = [[10, 10, 300, 50], [10, 70, 300, 110]];
    const dense = [[10, 10, 300, 12], [10, 13, 300, 15], [10, 16, 300, 18]];
    const radius = 4 / scale;
    assert.deepEqual(nearestLaneBorder(sparse, [180, 50], radius), {index: 0, edge: "bottom"});
    assert.deepEqual(nearestLaneBorder(sparse, [180, 70], radius), {index: 1, edge: "top"});
    assert.deepEqual(nearestLaneBorder(sparse, [8, 9], radius), {index: 0, edge: "top"},
      "border endpoints retain a round target");
    assert.equal(nearestLaneBorder(sparse, [-20, 10], radius), null,
      "the infinite extension of a border is not a target");
    assert.equal(nearestLaneBorder(sparse, [180, 30], radius), null);
    for (let index = 0; index < dense.length; index++) {
      const lane = dense[index];
      assert.deepEqual(nearestLaneBorder(dense, [180, lane[1] + .2], radius), {index, edge: "top"});
      assert.deepEqual(nearestLaneBorder(dense, [180, lane[3] - .2], radius), {index, edge: "bottom"});
      assert.equal(nearestLaneBorder(dense, [180, (lane[1] + lane[3]) / 2], radius), null,
        "overlapping screen-sized hit targets must not consume the lane body");
    }
  }
});

test("touching and equally close borders prefer the selected lane with deterministic fallback", () => {
  const touching = [[10, 0, 300, 10], [10, 10, 300, 20]];
  assert.deepEqual(nearestLaneBorder(touching, [180, 10], 4), {index: 0, edge: "bottom"});
  assert.deepEqual(nearestLaneBorder(touching, [180, 10], 4, 0), {index: 0, edge: "bottom"});
  assert.deepEqual(nearestLaneBorder(touching, [180, 10], 4, 1), {index: 1, edge: "top"});
  const separated = [[10, 0, 300, 10], [10, 14, 300, 24]];
  assert.deepEqual(nearestLaneBorder(separated, [180, 12], 4), {index: 0, edge: "bottom"});
  assert.deepEqual(nearestLaneBorder(separated, [180, 12], 4, 1), {index: 1, edge: "top"});
  assert.deepEqual(nearestLaneBorder(separated, [180, 12.1], 4, 0), {index: 1, edge: "top"},
    "preference cannot override a genuinely closer border");
  assert.equal(nearestLaneBorder([], [180, 10], 4), null);
  assert.equal(nearestLaneBorder(touching, [NaN, 10], 4), null);
});
