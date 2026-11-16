import {navigateLaneLabel} from "./label_navigation.mjs";
import {restoreSelection} from "./rich_text.mjs";

/** Composition owns its candidate keys until the IME has finished committing. */
export function handleLabelKeydown(event, {windowsDesktop = false, composing, node, inputNodes, inputLayer,
  captureSelection, applyFormat, undoRedo}) {
  // Some Windows IMEs send their final key after compositionend, with only
  // the legacy process-key code (229) marking it as part of the composition.
  if (windowsDesktop && (composing || event.isComposing || event.keyCode === 229)) return;
  if (navigateLaneLabel(event, node, inputNodes)) { captureSelection(); return; }
  if ((event.ctrlKey || event.metaKey) && ["b", "i"].includes(event.key.toLowerCase())) {
    event.preventDefault(); applyFormat(event.key.toLowerCase() === "b" ? "bold" : "italic"); return;
  }
  if ((event.ctrlKey || event.metaKey) && ["z", "y"].includes(event.key.toLowerCase())) {
    event.preventDefault();
    undoRedo(event.shiftKey || event.key.toLowerCase() === "y");
    return;
  }
  if (event.key === "Enter") { event.preventDefault(); node.blur(); }
  if ((event.key === "ArrowUp" || event.key === "ArrowDown") && !event.altKey && !event.ctrlKey && !event.metaKey) {
    const nodes = [...inputLayer.querySelectorAll(".image-label")];
    const next = nodes[nodes.indexOf(node) + (event.key === "ArrowUp" ? -1 : 1)];
    if (next) { event.preventDefault(); next.focus(); restoreSelection(next, {start: 0, end: next.textContent.length}); }
  }
}
