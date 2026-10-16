/** Plain text plus explicit runs; no pasted HTML is stored or exported. */
export const cleanText = value => String(value ?? "").replace(/[\u0000-\u001f\u007f]/g, "").slice(0, 500);
export const cleanStyle = value => ({bold: value?.bold === true, italic: value?.italic === true,
  color: /^#[\da-f]{6}$/i.test(value?.color) ? value.color : "#000000"});
const sameStyle = (a, b) => a.bold === b.bold && a.italic === b.italic && a.color === b.color;

export function mergeRuns(runs) {
  const result = [];
  for (const value of runs) {
    if (!value.text) continue;
    const run = {text: value.text, ...cleanStyle(value)};
    const previous = result.at(-1);
    if (previous && sameStyle(previous, run)) previous.text += run.text;
    else result.push(run);
  }
  return result;
}

export function labelRuns(value, key = "text") {
  const text = cleanText(value?.[key]);
  const runs = Array.isArray(value?.runs) ? value.runs.map(run =>
    ({text: cleanText(run.text), ...cleanStyle({...value, ...run})})) : [];
  return runs.map(run => run.text).join("") === text ? mergeRuns(runs)
    : text ? [{text, ...cleanStyle(value)}] : [];
}

/** Text undo must not roll back group membership or identity. */
export function textSnapshot(value, key = "text") {
  return {[key]: value[key], ...cleanStyle(value), runs: labelRuns(value, key)};
}

function sliceRuns(runs, start, end) {
  let offset = 0;
  return runs.flatMap(run => {
    const text = run.text.slice(Math.max(0, start - offset), Math.max(0, end - offset));
    offset += run.text.length;
    return text ? [{...run, text}] : [];
  });
}

export function selectionStyle(value, key, start = 0, end = value[key].length) {
  const runs = labelRuns(value, key);
  const selected = start === end ? sliceRuns(runs, Math.max(0, start - 1), Math.max(1, start))
    : sliceRuns(runs, start, end);
  const first = selected[0] ?? cleanStyle(value);
  return {bold: selected.length ? selected.every(run => run.bold) : first.bold,
    italic: selected.length ? selected.every(run => run.italic) : first.italic, color: first.color,
    mixedColor: selected.some(run => run.color !== first.color)};
}

/** Toolbar actions with only a caret apply to the complete label. */
export function formattingStyle(value, key, range) {
  return range && range.start !== range.end
    ? selectionStyle(value, key, range.start, range.end) : selectionStyle(value, key);
}

export function formatRange(value, key, start, end, patch) {
  const text = value[key];
  // A caret (or a toolbar selection without a range) retains whole-label formatting.
  if (start === end) { start = 0; end = text.length; Object.assign(value, patch); }
  const runs = labelRuns(value, key);
  value.runs = mergeRuns([...sliceRuns(runs, 0, start),
    ...sliceRuns(runs, start, end).map(run => ({...run, ...patch})), ...sliceRuns(runs, end, text.length)]);
}

/** Use the same selection or whole-label state as the toolbar. */
export function formatSelection(value, key, range, name, explicitValue) {
  const style = formattingStyle(value, key, range);
  formatRange(value, key, range?.start ?? 0, range?.end ?? 0,
    {[name]: explicitValue ?? !style[name]});
}

/** Preserve unaffected runs on insertion, replacement, deletion, and paste. */
export function editText(value, key, nextText, editRange = null) {
  const text = value[key];
  const next = cleanText(nextText);
  let start = 0, end = text.length, insertEnd = next.length;
  if (editRange && next.startsWith(text.slice(0, editRange.start))
    && next.endsWith(text.slice(editRange.end)) && next.length >= text.length - (editRange.end - editRange.start)) {
    start = editRange.start; end = editRange.end; insertEnd = next.length - (text.length - end);
  } else {
    while (start < text.length && start < next.length && text[start] === next[start]) start++;
    while (end > start && insertEnd > start && text[end - 1] === next[insertEnd - 1]) { end--; insertEnd--; }
  }
  const runs = labelRuns(value, key);
  const style = selectionStyle(value, key, start, start === end ? start : start + 1);
  value[key] = next;
  value.runs = mergeRuns([...sliceRuns(runs, 0, start), {text: next.slice(start, insertEnd), ...style},
    ...sliceRuns(runs, end, text.length)]);
}

export function readSelection(node) {
  const selection = window.getSelection();
  if (!selection?.rangeCount || !node.contains(selection.anchorNode) || !node.contains(selection.focusNode)) return null;
  const range = selection.getRangeAt(0);
  const before = range.cloneRange();
  before.selectNodeContents(node); before.setEnd(range.startContainer, range.startOffset);
  const start = before.toString().length;
  return {start, end: start + range.toString().length};
}

export function restoreSelection(node, saved) {
  if (!saved) return;
  const walker = document.createTreeWalker(node, NodeFilter.SHOW_TEXT);
  const points = [];
  let offset = 0, text;
  while ((text = walker.nextNode())) { points.push({text, offset}); offset += text.length; }
  const point = index => {
    const p = points.find(p => index <= p.offset + p.text.length) ?? points.at(-1);
    return p ? [p.text, Math.max(0, Math.min(p.text.length, index - p.offset))] : [node, 0];
  };
  const range = document.createRange();
  range.setStart(...point(saved.start)); range.setEnd(...point(saved.end));
  const selection = window.getSelection(); selection.removeAllRanges(); selection.addRange(range);
}

export function renderRuns(node, value, key) {
  const runs = labelRuns(value, key);
  const signature = JSON.stringify(runs);
  if (node.dataset.runs === signature && node.textContent === value[key]) return;
  // Restoring a contenteditable range also focuses it in Chromium. Leave focus
  // on a keyboard-activated toolbar button; the editor retains its saved range.
  const saved = document.activeElement === node ? readSelection(node) : null;
  node.replaceChildren(...runs.map(run => {
    const span = document.createElement("span");
    span.textContent = run.text;
    span.style.fontWeight = run.bold ? "bold" : "normal";
    span.style.fontStyle = run.italic ? "italic" : "normal";
    span.style.setProperty("--run-color", run.color);
    return span;
  }));
  node.dataset.runs = signature;
  restoreSelection(node, saved);
}
