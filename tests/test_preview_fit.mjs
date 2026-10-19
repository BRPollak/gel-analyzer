import assert from "node:assert/strict";
import test from "node:test";
import {fitPreviewGeometry, outerViewportHeight, outerViewportReserve} from "../gel_analyzer/well_component_frontend/fit_geometry.mjs";
import {laneDeleteLayout} from "../gel_analyzer/well_component_frontend/geometry.mjs";

test("landscape and portrait previews fit both dimensions without changing source geometry", () => {
  for (const [imageWidth, imageHeight] of [[2400, 800], [800, 2400], [1600, 1600]]) {
    const fit = fitPreviewGeometry({imageWidth, imageHeight, availableWidth: 900,
      viewportHeight: 800, chromeHeight: 60});
    assert.ok(fit.scale <= 1);
    assert.ok(fit.width <= 900);
    assert.ok(fit.height <= 640);
    assert.equal(fit.width / imageWidth, fit.height / imageHeight);
    assert.equal(fit.wrapperWidth, fit.width);
    assert.equal(fit.totalHeight, fit.height);
  }
});

test("small images stay at native size and the lane-review gutter is additional width", () => {
  const fit = fitPreviewGeometry({imageWidth: 280, imageHeight: 180, availableWidth: 1000,
    viewportHeight: 900, chromeHeight: 60, reviewMode: "borders", laneCount: 4});
  assert.equal(fit.scale, 1);
  assert.equal(fit.width, 280);
  assert.equal(fit.height, 180);
  assert.equal(fit.wrapperWidth, 320);
  assert.equal(fit.rightGutter, 40);
  assert.equal(fit.overflowHeight, 0);
});

test("lane crop reserves room for the full enlarged target at either image edge", () => {
  for (const workflowOrientation of ["wells_left", "wells_top"]) {
    const fit = fitPreviewGeometry({imageWidth: 1200, imageHeight: 1200, availableWidth: 400,
      viewportHeight: 500, chromeHeight: 60, reviewMode: "extent", workflowOrientation});
    const top = workflowOrientation === "wells_top";
    assert.equal(fit.rightGutter, top ? 0 : 30);
    assert.equal(fit.bottomGutter, top ? 30 : 0);
    assert.ok(fit.wrapperWidth <= 400);
    assert.ok(fit.totalHeight <= fit.heightBudget + 1e-10);
    assert.equal(fit.width / 1200, fit.height / 1200);
  }
});

test("reserved gutter participates in width fitting and status text participates in height fitting", () => {
  const input = {imageWidth: 2000, imageHeight: 1000, availableWidth: 540,
    viewportHeight: 600, chromeHeight: 80, reviewMode: "borders", laneCount: 6};
  const narrow = fitPreviewGeometry(input);
  assert.equal(narrow.width, 500);
  assert.equal(narrow.wrapperWidth, 540);
  assert.equal(narrow.height, 250);
  const tall = fitPreviewGeometry({...input, imageWidth: 500, imageHeight: 2000});
  assert.equal(tall.height, 420);
  assert.equal(tall.width, 105);
  const moreInstructions = fitPreviewGeometry({...input, imageWidth: 500, imageHeight: 2000, chromeHeight: 140});
  assert.equal(moreInstructions.height, 360);
});

test("lane-delete overflow is counted once and matches its actual native-coordinate layout", () => {
  const lanes = Array.from({length: 10}, (_, index) => [0, index * 2, 2000, index * 2 + 1]);
  const fit = fitPreviewGeometry({imageWidth: 2000, imageHeight: 800, availableWidth: 540,
    viewportHeight: 800, chromeHeight: 60, reviewMode: "borders", laneCount: lanes.length});
  const controls = laneDeleteLayout(lanes, 800, 1 / fit.scale);
  assert.equal(fit.height, 200);
  assert.equal(fit.overflowHeight, controls.overflow * fit.scale);
  assert.equal(fit.totalHeight, 320);
  assert.equal(fit.controlsOverflow, false);
  assert.ok(fit.totalHeight <= fit.heightBudget);

  const many = fitPreviewGeometry({imageWidth: 2000, imageHeight: 800, availableWidth: 540,
    viewportHeight: 600, chromeHeight: 100, reviewMode: "borders", laneCount: 30});
  assert.ok(many.height <= many.heightBudget, "the gel always fits even when many accessible controls need more room");
  assert.equal(many.totalHeight, 30 * 32);
  assert.equal(many.controlsOverflow, true);
});

test("parent viewport is stable when iframe height changes and cross-origin fallback avoids feedback", () => {
  const parent = {innerHeight: 900, visualViewport: {height: 820}};
  const host = {parent, innerHeight: 10, screen: {availHeight: 1000}, outerHeight: 1100};
  assert.equal(outerViewportHeight(host), 820);
  host.innerHeight = 600;
  assert.equal(outerViewportHeight(host), 820);
  delete parent.visualViewport;
  assert.equal(outerViewportHeight(host), 900);
  Object.defineProperty(host, "parent", {get() { throw new Error("cross origin"); }});
  assert.equal(outerViewportHeight(host), 1000);
  host.screen.availHeight = 0;
  assert.equal(outerViewportHeight(host), 1100);
  host.outerHeight = 0;
  assert.equal(outerViewportHeight(host), 800);
  const standalone = {innerHeight: 700, screen: {availHeight: 1000}};
  standalone.parent = standalone;
  assert.equal(outerViewportHeight(standalone), 700);
});

test("actual host chrome and stacked controls take precedence over a fixed reserve", () => {
  const frame = {};
  const host = {parent: {innerHeight: 800, gelPreviewViewport: {
    availableHeight: element => element === frame ? 436 : 1,
  }}, frameElement: frame, innerHeight: 1};
  assert.equal(outerViewportReserve(host), 364);
  const fit = fitPreviewGeometry({imageWidth: 1200, imageHeight: 2000, availableWidth: 600,
    viewportHeight: outerViewportHeight(host), outerReserve: outerViewportReserve(host), chromeHeight: 36});
  assert.equal(fit.height, 400);
  host.innerHeight = 500;
  assert.equal(outerViewportReserve(host), 364, "the component height cannot feed back into its fit");
  Object.defineProperty(host, "parent", {get() { throw new Error("cross origin"); }});
  host.screen = {availHeight: 900};
  host.gelPreviewHeight = 410;
  assert.equal(outerViewportReserve(host), 490);
});
