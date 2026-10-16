/** Serialize the same native geometry used by the canvas, with vector text.
 * The server adds the original crop to the image element after validation.
 */
function xml(value) {
  return String(value).replace(/[&<>"']/g, char => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&apos;",
  })[char]);
}

function text(value, x, y, style, size, anchor = "start", transform = "") {
  return `<text x="${x}" y="${y}" font-family="Arial" font-size="${size}" font-weight="${style.bold ? "bold" : "normal"}" font-style="${style.italic ? "italic" : "normal"}" fill="${xml(style.color)}" text-anchor="${anchor}" xml:space="preserve"${transform ? ` transform="${transform}"` : ""}>${xml(value)}</text>`;
}

export function annotationSvg(layout) {
  const parts = [
    `<svg xmlns="http://www.w3.org/2000/svg" width="${layout.width}" height="${layout.height}" viewBox="0 0 ${layout.width} ${layout.height}">`,
    `<rect x="0" y="0" width="${layout.width}" height="${layout.height}" fill="#ffffff"/>`,
    `<image x="${layout.gelX}" y="${layout.gelY}" width="${layout.imageWidth}" height="${layout.imageHeight}"/>`,
  ];
  for (const bracket of layout.brackets) {
    let path = `M ${bracket.x + bracket.depth} ${bracket.top} L ${bracket.x} ${bracket.top} L ${bracket.x} ${bracket.bottom} L ${bracket.x + bracket.depth} ${bracket.bottom}`;
    for (const y of bracket.ticks) path += ` M ${bracket.x} ${y} L ${bracket.x + bracket.depth * 0.6} ${y}`;
    parts.push(`<path d="${path}" fill="none" stroke="#000000" stroke-width="1.5" stroke-linecap="butt"/>`);
  }
  for (const label of layout.labels) {
    if (!label.text) continue;
    if (label.runs.length === 1) {
      parts.push(text(label.text, label.x, label.baseline, label.runs[0], label.fontSize, "end"));
    } else {
      for (const run of label.runs) if (run.text) {
        parts.push(text(run.text, label.x - label.advance + run.offset, label.baseline, run, label.fontSize));
      }
    }
  }
  for (const guide of layout.guides ?? []) {
    parts.push(`<path d="M ${guide.x} ${guide.startY} L ${guide.x} ${guide.endY}" fill="none" stroke="${xml(guide.color)}" stroke-width="1.8" stroke-linecap="butt"/>`);
  }
  for (const label of layout.ladderLabels ?? []) {
    parts.push(`<rect x="${label.left}" y="${label.top}" width="${label.right - label.left}" height="${label.bottom - label.top}" fill="#ffffff"/>`);
  }
  for (const label of layout.ladderLabels ?? []) {
    parts.push(text(label.text, 0, 0, label, label.fontSize, "start",
      `translate(${label.baselineX} ${label.baselineY}) rotate(-90)`));
  }
  parts.push("</svg>");
  return parts.join("");
}
