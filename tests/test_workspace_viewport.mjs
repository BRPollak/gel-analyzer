import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import vm from 'node:vm';

const script = readFileSync(new URL('../gel_analyzer/viewport.html', import.meta.url), 'utf8')
  .match(/<script>([\s\S]*?)<\/script>/)[1];

test('reveal the full step when controls grow, without moving on ordinary edits', () => {
  let height = 300, reveals = 0;
  const component = {dataset: {token: 'one', ladderStep: 'preset'},
    getBoundingClientRect: () => ({top: 0, bottom: height, width: 900, height})};
  const groupPanel = {open: false};
  const preview = {dataset: {}, getBoundingClientRect: () => ({top: 0, bottom: 280, width: 600, height: 280})};
  const frame = {style: {}, contentDocument: {getElementById: id =>
    ({component, 'preview-viewport': preview, 'group-panel': groupPanel})[id]},
    getBoundingClientRect: () => ({top: 330, bottom: 330 + height, width: 900, height}),
    closest: () => null, scrollIntoView: () => reveals++};
  const document = {body: {}, querySelectorAll: selector => selector.startsWith('iframe') ? [frame] : [],
    addEventListener() {}};
  const window = {innerHeight: 768, addEventListener() {}};
  vm.runInNewContext(script, {window, document, WeakMap,
    MutationObserver: class {observe() {}}, requestAnimationFrame: fn => fn()});
  assert.equal(reveals, 0, 'the initial short step already fits');
  component.dataset.ladderStep = 'markers'; height = 580;
  window.gelPreviewViewport.refresh();
  assert.equal(reveals, 1, 'tall controls trigger reveal even though the image still fits');
  window.gelPreviewViewport.refresh();
  assert.equal(reveals, 1, 'typing and ordinary rerenders do not reset scroll');
  groupPanel.open = true;
  window.gelPreviewViewport.refresh();
  assert.equal(reveals, 2, 'opening group controls reveals the expanded step');
});
