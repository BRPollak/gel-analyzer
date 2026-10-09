/** Annotation geometry is expressed in native cropped-image pixels. */
const OUTER = 12;
const COLUMN_GAP = 16;
const IMAGE_GAP = 14;
const BRACKET_DEPTH = 9;
const LABEL_BRACKET_GAP = 10;
const VERTICAL_GAP = 4;

let measuringContext;

function browserMeasure(text, font) {
  if (!measuringContext) {
    const canvas = globalThis.document?.createElement("canvas");
    measuringContext = canvas?.getContext("2d");
  }
  if (!measuringContext) throw new Error("Canvas text measurement is unavailable.");
  measuringContext.font = font;
  measuringContext.textAlign = "left";
  measuringContext.textBaseline = "alphabetic";
  return measuringContext.measureText(text);
}

function finite(value, fallback) {
  return Number.isFinite(value) ? value : fallback;
}

export function annotationFont(style, fontSize) {
  return `${style.italic ? "italic " : ""}${style.bold ? "bold " : ""}${fontSize}px Arial`;
}

function textSpec(value, text, fontSize, measure) {
  const style = {bold: Boolean(value?.bold), italic: Boolean(value?.italic),
    color: /^#[\da-f]{6}$/i.test(value?.color ?? "") ? value.color : "#000000"};
  const font = annotationFont(style, fontSize);
  const metrics = measure(text || "Mg", font);
  const advance = text ? Math.max(0, finite(metrics.width, 0)) : 0;
  // Canvas metrics include italic overhang and ascenders/descenders. Reserve
  // both, and center the actual glyph ink rather than its alphabetic baseline.
  // Either value can legitimately be negative for punctuation lying entirely
  // above or below the baseline (for example an underscore or apostrophe).
  const ascent = finite(metrics.actualBoundingBoxAscent, fontSize * 0.8);
  const descent = finite(metrics.actualBoundingBoxDescent, fontSize * 0.2);
  const overhangLeft = text ? Math.max(0, finite(metrics.actualBoundingBoxLeft, 0)) : 0;
  const overhangRight = text ? Math.max(0, finite(metrics.actualBoundingBoxRight, advance) - advance) : 0;
  const boxHeight = Math.ceil(Math.max(8, fontSize * 1.05, ascent + descent + 4));
  return {text, ...style, font, fontSize, ascent, descent, advance,
    overhangLeft, overhangRight, boxHeight,
    measuredWidth: Math.ceil(Math.max(80, advance + overhangLeft + overhangRight + 10))};
}

/** Greedy interval partitioning keeps overlapping groups in separate columns. */
function partitionTracks(items) {
  const tracks = [];
  for (const item of [...items].sort((a, b) => a.start - b.start || a.end - b.end)) {
    let track = tracks.findIndex(candidate => candidate.end + VERTICAL_GAP <= item.start);
    if (track === -1) {
      track = tracks.length;
      tracks.push({end: -Infinity, width: 0, items: []});
    }
    item.track = track;
    tracks[track].end = item.end;
    tracks[track].width = Math.max(tracks[track].width, item.measuredWidth);
    tracks[track].items.push(item);
  }
  return tracks;
}

function oneLine(value) {
  return String(value ?? "").replace(/[\r\n\t]/g, " ");
}

/**
 * Labels use x as their right-aligned text anchor and y as their visual center.
 * An editor box fits at (x - width, y - boxHeight / 2). Coordinates already
 * include gelX/gelY, which are the original gel's offset in the final canvas.
 * measureText can be injected for tests; its signature is (text, font).
 */
export function layoutAnnotations({width, height, lanes = [], annotations = {}}, measureText = browserMeasure) {
  if (!Number.isInteger(width) || width < 1 || !Number.isInteger(height) || height < 1) {
    throw new Error("The cropped image must have positive integer dimensions.");
  }
  const measure = typeof measureText === "function" ? measureText : (text, font) => {
    measureText.font = font;
    measureText.textAlign = "left";
    measureText.textBaseline = "alphabetic";
    return measureText.measureText(text);
  };
  const laneGeometry = lanes.map((lane, index) => {
    if (!Array.isArray(lane) || lane.length !== 4 || !lane.every(Number.isFinite)) {
      throw new Error(`Lane ${index + 1} has invalid coordinates.`);
    }
    const top = Math.max(0, Math.min(height, lane[1]));
    const bottom = Math.max(top, Math.min(height, lane[3]));
    return {index, top, bottom, y: (top + bottom) / 2};
  });
  const laneHeights = laneGeometry.map(lane => lane.bottom - lane.top).filter(value => value > 0);
  const defaultFontSize = laneHeights.length
    ? Math.round(0.8 * laneHeights.reduce((sum, value) => sum + value, 0) / laneHeights.length) : 18;
  const requestedFontSize = Math.min(4096, Math.max(1,
    finite(Number(annotations.fontSize ?? defaultFontSize), defaultFontSize)));
  // Preserve the chosen size even when individual lanes are unusually close.
  // Only labels whose vertical extents collide need another horizontal column.
  const fontSize = requestedFontSize;
  const laneLabels = laneGeometry.map(lane => {
    const value = annotations.labels?.[lane.index] ?? {};
    const spec = textSpec(value, oneLine(value.text), fontSize, measure);
    return {...lane, ...spec, kind: "lane", start: lane.y - spec.boxHeight / 2,
      end: lane.y + spec.boxHeight / 2};
  });
  const laneTracks = partitionTracks(laneLabels);
  const groupLabels = [];
  for (const [index, group] of (annotations.groups ?? []).entries()) {
    const membership = [...new Set(group.lanes ?? [])].filter(value =>
      Number.isInteger(value) && value >= 0 && value < laneGeometry.length).sort((a, b) => a - b);
    if (!membership.length) continue;
    const selected = membership.map(index => laneGeometry[index]);
    let top = Math.min(...selected.map(lane => lane.top));
    let bottom = Math.max(...selected.map(lane => lane.bottom));
    const y = (top + bottom) / 2;
    if (bottom - top < 6) { top = y - 3; bottom = y + 3; }
    const label = oneLine(group.label ?? group.text);
    const spec = textSpec(group, label, requestedFontSize, measure);
    groupLabels.push({...spec, kind: "group", id: String(group.id ?? `group-${index}`),
      index, set: group.set === 1 ? 1 : 0, label, lanes: membership, top, bottom, y,
      ticks: selected.map(lane => lane.y),
      start: Math.min(top - 1, y - spec.boxHeight / 2),
      end: Math.max(bottom + 1, y + spec.boxHeight / 2)});
  }
  const groupTracks = [0, 1].map(set => partitionTracks(groupLabels.filter(group => group.set === set)));
  let left = -IMAGE_GAP;
  for (const track of laneTracks) {
    for (const label of track.items) {
      label.x = left - label.overhangRight;
      label.width = track.width - label.overhangRight;
    }
    left -= track.width + COLUMN_GAP;
  }
  const brackets = [];
  for (const tracks of groupTracks) {
    for (const track of tracks) {
      const bracketX = left - BRACKET_DEPTH;
      for (const label of track.items) {
        label.x = bracketX - LABEL_BRACKET_GAP - label.overhangRight;
        label.width = track.width - label.overhangRight;
        brackets.push({id: label.id, set: label.set, track: label.track,
          x: bracketX, top: label.top, bottom: label.bottom, ticks: [...label.ticks],
          depth: BRACKET_DEPTH, color: label.color});
      }
      left -= BRACKET_DEPTH + LABEL_BRACKET_GAP + track.width + COLUMN_GAP;
    }
  }
  const allLabels = [...laneLabels, ...groupLabels];
  const minX = allLabels.length ? Math.min(...allLabels.map(label => label.x - label.width)) : 0;
  const minY = Math.min(0, ...allLabels.map(label => label.start));
  const maxY = Math.max(height, ...allLabels.map(label => label.end));
  const gelX = Math.ceil(OUTER - minX);
  const gelY = Math.ceil(OUTER - minY);
  for (const label of allLabels) {
    label.x += gelX;
    label.y += gelY;
    label.start += gelY;
    label.end += gelY;
    label.baseline = label.y + (label.ascent - label.descent) / 2;
    if (label.kind === "group") {
      label.top += gelY;
      label.bottom += gelY;
      label.ticks = label.ticks.map(y => y + gelY);
    }
  }
  for (const bracket of brackets) {
    bracket.x += gelX;
    bracket.top += gelY;
    bracket.bottom += gelY;
    bracket.ticks = bracket.ticks.map(y => y + gelY);
  }
  const outputWidth = gelX + width + OUTER;
  const outputHeight = Math.ceil(gelY + maxY + OUTER);
  if (outputWidth > 32767 || outputHeight > 32767 || outputWidth * outputHeight > 64_000_000) {
    throw new Error("The annotated image is too large to render. Shorten labels, reduce the font size or overlapping groups, or use a smaller cropped image.");
  }
  return {width: outputWidth, height: outputHeight,
    imageWidth: width, imageHeight: height, gelX, gelY, fontSize, requestedFontSize,
    denseFallback: laneTracks.length > 1, reducedFont: fontSize < requestedFontSize,
    laneLabels, groupLabels, brackets, labels: allLabels};
}

/** Paint only exportable pixels: white margin, unchanged gel, labels, brackets. */
export function drawAnnotations(canvas, image, layout, _annotations) {
  canvas.width = layout.width;
  canvas.height = layout.height;
  const context = canvas.getContext("2d");
  if (!context) throw new Error("Canvas rendering is unavailable.");
  context.fillStyle = "#ffffff";
  context.fillRect(0, 0, layout.width, layout.height);
  // The three-argument form preserves the source gel's pixel dimensions.
  context.drawImage(image, layout.gelX, layout.gelY);
  context.lineWidth = 1.5;
  context.lineCap = "butt";
  for (const bracket of layout.brackets) {
    context.strokeStyle = bracket.color;
    context.beginPath();
    context.moveTo(bracket.x + bracket.depth, bracket.top);
    context.lineTo(bracket.x, bracket.top);
    context.lineTo(bracket.x, bracket.bottom);
    context.lineTo(bracket.x + bracket.depth, bracket.bottom);
    for (const y of bracket.ticks) {
      context.moveTo(bracket.x, y);
      context.lineTo(bracket.x + bracket.depth * 0.6, y);
    }
    context.stroke();
  }
  context.textAlign = "right";
  context.textBaseline = "alphabetic";
  for (const label of layout.labels) {
    if (!label.text) continue;
    context.font = label.font;
    context.fillStyle = label.color;
    context.fillText(label.text, label.x, label.baseline);
  }
  return layout;
}
