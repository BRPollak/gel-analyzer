import test from "node:test";
import assert from "node:assert/strict";
import {readFileSync} from "node:fs";
import vm from "node:vm";

const source = readFileSync(new URL("../gel_analyzer/desktop_uploads.js", import.meta.url), "utf8");

function harness(chooseImage) {
  const listeners = [], alerts = [], events = [];
  class Input {
    type = "file";
    disabled = false;
    isConnected = true;
    files = [];
    closest(selector) { return selector === '[data-testid="stFileUploader"]'; }
    dispatchEvent(event) { events.push(event); }
  }
  class DataTransfer {
    files = [];
    items = {add: (file) => this.files.push(file)};
  }
  const window = {pywebview: {api: {choose_image: chooseImage}}, alert: (message) => alerts.push(message)};
  const context = vm.createContext({window, document: {addEventListener: (...args) => listeners.push(args)},
    HTMLInputElement: Input, DataTransfer, File, Event, Uint8Array, atob, console: {error() {}}});
  vm.runInContext(source, context);
  const input = new Input();
  let prevented = 0;
  return {input, alerts, events, context, listeners, window,
    get prevented() { return prevented; },
    click: (target = input) => listeners[0][1]({target,
      preventDefault: () => prevented++, stopImmediatePropagation() {}})};
}

test("native selection reaches the existing upload change handler with exact filename and bytes", async () => {
  const image = Buffer.from([0, 127, 128, 255, 13, 10]);
  const h = harness(async () => ({name: "gel with spaces.png", type: "image/png", data: image.toString("base64")}));
  await h.click();
  assert.equal(h.prevented, 1);
  assert.equal(h.listeners[0][2], true, "capture the click before the native browser dialog opens");
  assert.equal(h.input.files[0].name, "gel with spaces.png");
  assert.equal(h.input.files[0].type, "image/png");
  assert.deepEqual(Buffer.from(await h.input.files[0].arrayBuffer()), image);
  assert.equal(h.events.length, 1);
  assert.equal(h.events[0].type, "change");
  assert.equal(h.events[0].bubbles, true);
  assert.equal(h.alerts.length, 0);
});

test("cancellation, errors and replaced inputs do not dispatch spurious uploads", async () => {
  for (const outcome of [null, {error: "Cannot read file"}, new Error("bridge error")]) {
    const h = harness(async () => { if (outcome instanceof Error) throw outcome; return outcome; });
    await h.click();
    assert.equal(h.events.length, 0);
    assert.equal(h.alerts.length, outcome === null ? 0 : 1);
  }
  const h = harness(async () => ({name: "gel.png", type: "image/png", data: "AA=="}));
  h.input.isConnected = false;
  await h.click();
  assert.equal(h.events.length, 0);
});

test("only one native dialog opens at a time and installation is idempotent", async () => {
  let finish, calls = 0;
  const h = harness(() => { calls++; return new Promise((resolve) => {finish = resolve;}); });
  vm.runInContext(source, h.context);
  assert.equal(h.listeners.length, 1);
  const pending = h.click();
  await h.click();
  assert.equal(calls, 1);
  finish(null);
  await pending;
  const next = h.click();
  assert.equal(calls, 2);
  finish(null);
  await next;
});

test("ordinary browser uploads and non-upload clicks retain their normal behavior", async () => {
  const h = harness(async () => assert.fail("must not open a dialog"));
  await h.click({});
  h.input.type = "text";
  await h.click();
  h.input.type = "file";
  delete h.window.pywebview;
  await h.click();
  assert.equal(h.prevented, 0);
  assert.equal(h.events.length, 0);
});
