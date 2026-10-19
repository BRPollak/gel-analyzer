import {formattingStyle, formatSelection} from "./rich_text.mjs";

/** Selection is editor-only state: it never writes into a saved label. */
export function selectLabelKeys(current, key, additive = false) {
  if (!additive || !key.startsWith("lane:")) return [key];
  const lanes = current.filter(value => value.startsWith("lane:"));
  return lanes.includes(key) ? lanes.filter(value => value !== key) : [...lanes, key];
}

export function selectedFormatting(targets, range = null) {
  const styles = targets.map(({label, field}) => formattingStyle(label, field, targets.length === 1 ? range : null));
  if (!styles.length) return {};
  return {bold: styles.every(style => style.bold), italic: styles.every(style => style.italic),
    color: styles[0].color,
    mixedColor: styles.some(style => style.mixedColor || style.color !== styles[0].color)};
}

/** Mixed toggles first turn the style on for every selected label. */
export function formatSelectedLabels(targets, range, name, explicitValue) {
  const value = explicitValue ?? !selectedFormatting(targets, range)[name];
  for (const {label, field} of targets) {
    formatSelection(label, field, targets.length === 1 ? range : null, name, value);
  }
}
