import {restoreSelection} from "./rich_text.mjs";

/** Keep Tab within the logical lane sequence, then leave its boundaries to the browser. */
export function navigateLaneLabel(event, node, inputNodes) {
  if (event.key !== "Tab" || event.altKey || event.ctrlKey || event.metaKey
    || event.isComposing || event.defaultPrevented) return false;
  const lanes = [...inputNodes].filter(([key, candidate]) => /^lane:\d+$/.test(key)
    && candidate.contentEditable === "true" && !candidate.hidden)
    .sort(([a], [b]) => Number(a.slice(5)) - Number(b.slice(5)));
  const index = lanes.findIndex(([, candidate]) => candidate === node);
  if (index < 0) return false;
  const next = lanes[index + (event.shiftKey ? -1 : 1)]?.[1];
  if (!next) return false;
  event.preventDefault();
  next.focus();
  restoreSelection(next, {start: 0, end: next.textContent.length});
  return true;
}
