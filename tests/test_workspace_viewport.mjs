import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import vm from 'node:vm';

const html = readFileSync(new URL('../gel_analyzer/viewport.html', import.meta.url), 'utf8');
const script = html.match(/<script>([\s\S]*?)<\/script>/)[1];

function fixture() {
  const messages = [], properties = {}, rootProperties = {};
  const scroller = {scrollTop: 0};
  let top = 250, controlsHeight = 180, imageHeight = 1600, footerHeight = 48;
  const controls = {getBoundingClientRect: () => ({height: controlsHeight})};
  const footer = {getBoundingClientRect: () => ({height: footerHeight})};
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
    documentElement: {style: {setProperty: (key, value) => rootProperties[key] = value}},
    querySelector: selector => selector === '.st-key-gel_footer' ? footer : null,
    querySelectorAll: selector => selector.startsWith('iframe') ? [frame]
      : selector.includes('stImage') ? [image] : [workspace], addEventListener() {}};
  const window = {innerHeight: 800, innerWidth: 1280, addEventListener() {}};
  vm.runInNewContext(script, {window, document, WeakMap,
    MutationObserver: class {observe() {}}, requestAnimationFrame: fn => fn()});
  return {window, scroller, image, frame, messages, properties, rootProperties,
    setTop: value => top = value, setControlsHeight: value => controlsHeight = value,
    setImageHeight: value => imageHeight = value, setFooterHeight: value => footerHeight = value};
}

test('uploaded gel fits beneath the complete app header and broadcasts the same iframe budget', () => {
  const page = fixture();
  assert.equal(page.properties['--gel-workspace-height'], '474px');
  assert.equal(page.image.style.height, '474px');
  assert.equal(page.image.style.width, '355.5px');
  assert.equal(page.messages[0].height, 474);
  page.setTop(300);
  page.window.gelPreviewViewport.refresh();
  assert.equal(page.image.style.height, '424px', 'wrapped header content reduces the image budget');
  assert.equal(page.messages.at(-1).height, 424);
});

test('resizing fits both dimensions and reserves stacked controls on a narrow screen', () => {
  const page = fixture();
  page.window.innerHeight = 600;
  page.window.gelPreviewViewport.refresh();
  assert.equal(page.image.style.height, '274px');
  page.window.innerWidth = 390;
  page.window.gelPreviewViewport.refresh();
  assert.equal(page.image.style.height, '78px');
  assert.equal(page.messages.at(-1).height, 78);
  page.setControlsHeight(100);
  page.window.gelPreviewViewport.refresh();
  assert.equal(page.image.style.height, '158px');
  page.setImageHeight(100);
  page.window.gelPreviewViewport.refresh();
  assert.equal(page.image.style.width, '800px');
  assert.ok(Number.parseFloat(page.image.style.height) <= 158);
});

test('a wrapped footer reserves equal workspace, image, and iframe space without scroll feedback', () => {
  const page = fixture();
  assert.equal(page.rootProperties['--gel-footer-height'], '48px');
  page.setFooterHeight(72);
  page.window.gelPreviewViewport.refresh();
  assert.equal(page.rootProperties['--gel-footer-height'], '72px');
  assert.equal(page.properties['--gel-workspace-height'], '450px');
  assert.equal(page.image.style.height, '450px');
  assert.equal(page.messages.at(-1).height, 450);
  const messageCount = page.messages.length;
  page.scroller.scrollTop = 180;
  page.window.gelPreviewViewport.refresh();
  assert.equal(page.scroller.scrollTop, 180, 'refresh preserves the user scroll position');
  assert.equal(page.properties['--gel-workspace-height'], '450px');
  assert.equal(page.image.style.height, '450px');
  assert.equal(page.messages.length, messageCount, 'scrolling does not resend an unchanged iframe budget');
});
