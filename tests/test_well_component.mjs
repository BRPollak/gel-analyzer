import assert from "node:assert/strict";
import test from "node:test";
import {clampRightEdge, clipPoint, laneBorderLimits, moveLaneBorder, nearestHandle, pointerToImage, readPoints, screenRadius, wellsWithLaneBorders} from "../gel_analyzer/well_component_frontend/geometry.mjs";

test("pointer mapping is independent of scale and page offset", () => {
  for (const scale of [1, 0.5, 0.2, 1.25]) {
    const rect = {left: 37, top: 92, width: 1000 * scale, height: 600 * scale};
    assert.deepEqual(pointerToImage(37 + 310 * scale, 92 + 425 * scale, rect, 1000, 600), [310, 425]);
    assert.deepEqual(pointerToImage(rect.left, rect.top, rect, 1000, 600), [0, 0]);
    assert.deepEqual(pointerToImage(rect.left + rect.width, rect.top + rect.height, rect, 1000, 600), [1000, 600]);
    assert.equal(screenRadius(7, rect, 1000) * scale, 7);
  }
});

test("captured pointer clips at all four image edges", () => {
  const rect = {left: 10, top: 20, width: 200, height: 100};
  assert.deepEqual(pointerToImage(-15, -90, rect, 400, 200), [0, 0]);
  assert.deepEqual(pointerToImage(280, 200, rect, 400, 200), [400, 200]);
  assert.deepEqual(clipPoint([125.5, 87.25], 400, 200), [125.5, 87.25]);
  assert.equal(pointerToImage(10, 20, {...rect, width: 0}, 400, 200), null);
});

test("endpoint loading preserves click order and rejects malformed data", () => {
  assert.deepEqual(readPoints([[13, 180], [11, 15]], 400, 200), [[13, 180], [11, 15]]);
  assert.deepEqual(readPoints([[-1, 500]], 400, 200), [[0, 200]]);
  for (const input of [null, [[NaN, 1]], [[1]], [[1, 2, 3]], [[1, 2], [3, 4], [5, 6]]]) {
    assert.deepEqual(readPoints(input, 400, 200), []);
  }
});

test("lane borders round to pixel edges and cannot cross neighbors or collapse", () => {
  const lanes = [[11, 10, 1000, 24], [13, 38, 1000, 55], [9, 80, 1000, 99]];
  assert.deepEqual(laneBorderLimits(lanes, 1, "top", 120), [24, 54]);
  assert.deepEqual(laneBorderLimits(lanes, 1, "bottom", 120), [39, 80]);
  assert.deepEqual(moveLaneBorder(lanes, 1, "top", 11, 120)[1], [13, 24, 1000, 55]);
  assert.deepEqual(moveLaneBorder(lanes, 1, "top", 91, 120)[1], [13, 54, 1000, 55]);
  assert.deepEqual(moveLaneBorder(lanes, 1, "bottom", 90, 120)[1], [13, 38, 1000, 80]);
  assert.deepEqual(moveLaneBorder(lanes, 1, "bottom", 5, 120)[1], [13, 38, 1000, 39]);
  assert.deepEqual(moveLaneBorder(lanes, 0, "top", -500, 120)[0], [11, 0, 1000, 24]);
  assert.deepEqual(moveLaneBorder(lanes, 2, "bottom", 500, 120)[2], [9, 80, 1000, 120]);
  assert.equal(moveLaneBorder(lanes, 1, "top", 29.7, 120)[1][1], 30);
  assert.deepEqual(lanes, [[11, 10, 1000, 24], [13, 38, 1000, 55], [9, 80, 1000, 99]]);
});

test("shared right edge preserves every well and never extends beyond image", () => {
  const wells = [{bounds: [11, 10, 35, 24]}, {bounds: [13, 38, 41, 55]}];
  assert.equal(clampRightEdge(0, wells, 1000), 41);
  assert.equal(clampRightEdge(1001, wells, 1000), 1000);
  assert.equal(clampRightEdge(824.6, wells, 1000), 825);
});

test("well overlays follow lane border adjustments without modifying horizontal evidence", () => {
  const wells = [{bounds: [11, 10, 35, 24], center: [22.5, 17], score: 1},
    {bounds: [13, 38, 41, 55]}];
  const lanes = [[11, 8, 900, 26], [13, 36, 900, 59]];
  assert.deepEqual(wellsWithLaneBorders(wells, lanes), [
    {bounds: [11, 8, 35, 26], center: [22.5, 17], score: 1},
    {bounds: [13, 36, 41, 59], center: [27, 47.5]},
  ]);
  assert.deepEqual(wells[0].bounds, [11, 10, 35, 24]);
});

test("tiny lanes retain independent grips despite overlapping hit areas and DOM order", () => {
  const top = {edge: "top", x: 13, y: 20};
  const bottom = {edge: "bottom", x: 16, y: 21};
  for (const handles of [[top, bottom], [bottom, top]]) {
    assert.equal(nearestHandle(handles, [13, 20], 15), top);
    assert.equal(nearestHandle(handles, [16, 21], 15), bottom);
    assert.equal(nearestHandle(handles, [15.8, 20.8], 15), bottom);
    assert.equal(nearestHandle(handles, [500, 500], 15), null);
  }
  // A thumbnail uses a larger image-coordinate hit radius, with the same pick.
  assert.equal(nearestHandle([bottom, top], [13, 20], 15 / 0.1), top);
});
