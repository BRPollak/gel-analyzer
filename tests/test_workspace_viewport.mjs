import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import vm from 'node:vm';

const html = readFileSync(new URL('../gel_analyzer/viewport.html', import.meta.url), 'utf8');
const script = html.match(/<script>([\s\S]*?)<\/script>/)[1];

function fixture() {
  const messages = [], properties = {};
  const scroller = {scrollTop: 0};
  let top = 250, controlsHeight = 180, imageHeight = 1600;
  const controls = {getBoundingClientRect: () => ({height: controlsHeight})};
  const workspace = {style: {setProperty: (key, value) => properties[key] = value},
    closest: selector => selector.includes('stMain') ? scroller : null,
    querySelector: () => controls,
    getBoundingClientRect: () => ({top: top - scroller.scrollTop})};
  const container = {clientWidth: 800};
  const image = {complete: true, naturalWidth: 1200, get naturalHeight() {return imageHeight;},
    style: {}, dataset: {}, closest: selector => selector.includes('gel_workspace') ? workspace : container};
  const frame = {contentWindow: {postMessage: value => messages.push(value)},
    closest: selector => selector.includes('gel_workspace') ? workspace : container};
  const document = {body: {}, scrollingElement: scroller,
    querySelectorAll: selector => selector.startsWith('iframe') ? [frame]
      : selector.includes('stImage') ? [image] : [workspace], addEventListener() {}};
  const window = {innerHeight: 800, innerWidth: 1280, addEventListener() {}};
  vm.runInNewContext(script, {window, document, WeakMap,
    MutationObserver: class {observe() {}}, requestAnimationFrame: fn => fn()});
  return {window, scroller, image, frame, messages, properties,
    setTop: value => top = value, setControlsHeight: value => controlsHeight = value,
    setImageHeight: value => imageHeight = value};
}

test('uploaded gel fits beneath the complete app header and broadcasts the same iframe budget', () => {
  const page = fixture();
  assert.equal(page.properties['--gel-workspace-height'], '522px');
  assert.equal(page.image.style.height, '522px');
  assert.equal(page.image.style.width, '391.5px');
  assert.equal(page.messages[0].height, 522);
  page.setTop(300);
  page.window.gelPreviewViewport.refresh();
  assert.equal(page.image.style.height, '472px', 'wrapped header content reduces the image budget');
  assert.equal(page.messages.at(-1).height, 472);
});

test('scrolling and ordinary edits preserve preview size and do not jump the page', () => {
  const page = fixture();
  page.scroller.scrollTop = 180;
  page.window.gelPreviewViewport.refresh();
  assert.equal(page.image.style.height, '522px');
  assert.equal(page.messages.length, 1, 'unchanged budgets do not generate iframe feedback loops');
  assert.doesNotMatch(script, /scrollIntoView/, 'the controller preserves user scroll position');
  assert.match(html, /object-position: center/);
  assert.match(html, /align-items: center; flex-wrap: nowrap/);
});

test('resizing fits both dimensions and reserves stacked controls on a narrow screen', () => {
  const page = fixture();
  page.window.innerHeight = 600;
  page.window.gelPreviewViewport.refresh();
  assert.equal(page.image.style.height, '322px');
  page.window.innerWidth = 390;
  page.window.gelPreviewViewport.refresh();
  assert.equal(page.image.style.height, '126px');
  assert.equal(page.messages.at(-1).height, 126);
  page.setControlsHeight(100);
  page.window.gelPreviewViewport.refresh();
  assert.equal(page.image.style.height, '206px');
  page.setImageHeight(100);
  page.window.gelPreviewViewport.refresh();
  assert.equal(page.image.style.width, '800px');
  assert.ok(Number.parseFloat(page.image.style.height) <= 206);
});
