import {pointInImage} from "./ladder_geometry.mjs";

/** Annotation geometry is expressed in native cropped-image pixels. */
const OUTER = 12;
const COLUMN_GAP = 16;
const IMAGE_GAP = 14;
const BRACKET_DEPTH = 9;
const MIN_BRACKET_GAP = 18;
const VERTICAL_GAP = 4;
const LADDER_GEL_GAP = 6;
const LADDER_LEADER = 15;
const LADDER_STROKE = 1.8;
const LADDER_TEXT_GAP = 6;
const LADDER_LABEL_GAP = 2;
const LADDER_INK_PADDING = 2;

let measuringContext;

function browserMeasure(text, font) {
  if (!measuringContext) {
    const canvas = globalThis.document?.createElement("canvas");
    measuringContext = canvas?.getContext("2d");
  }
  if (!measuringContext) throw new Error("The browser could not prepare the label text. Reload the page and try again.");
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

function textStyle(value, fallback = {}) {
  return {bold: Boolean(value?.bold ?? fallback.bold), italic: Boolean(value?.italic ?? fallback.italic),
    color: /^#[\da-f]{6}$/i.test(value?.color ?? "") ? value.color : fallback.color ?? "#000000"};
}

function textSpec(value, text, fontSize, measure) {
  const style = textStyle(value);
  const font = annotationFont(style, fontSize);
  // Plain text remains the canonical label. Ignore stale run data instead of
  // silently rendering a different string from the label being edited.
  const sourceRuns = Array.isArray(value?.runs) && value.runs.length
    && value.runs.every(run => run && typeof run.text === "string")
    && value.runs.map(run => oneLine(run.text)).join("") === text
    ? value.runs : [{text, ...style}];
  let advance = 0;
  let inkOffsetLeft = Infinity;
  let inkOffsetRight = -Infinity;
  let ascent = -Infinity;
  let descent = -Infinity;
  const runs = sourceRuns.map(value => {
    const runText = oneLine(value.text);
    const runStyle = textStyle(value, style);
    const runFont = annotationFont(runStyle, fontSize);
    const metrics = measure(runText || "Mg", runFont);
    const width = runText ? Math.max(0, finite(metrics.width, 0)) : 0;
    const left = finite(metrics.actualBoundingBoxLeft, 0);
    const right = finite(metrics.actualBoundingBoxRight, width);
    const runAscent = finite(metrics.actualBoundingBoxAscent, fontSize * 0.8);
    const runDescent = finite(metrics.actualBoundingBoxDescent, fontSize * 0.2);
    const hasInk = Boolean(runText.trim()) && left + right > 0;
    if (hasInk) {
      inkOffsetLeft = Math.min(inkOffsetLeft, advance - left);
      inkOffsetRight = Math.max(inkOffsetRight, advance + right);
      ascent = Math.max(ascent, runAscent);
      descent = Math.max(descent, runDescent);
    }
    const run = {text: runText, ...runStyle, font: runFont, offset: advance, advance: width};
    advance += width;
    return run;
  });
  const hasInk = Number.isFinite(inkOffsetLeft);
  if (!hasInk) {
    inkOffsetLeft = inkOffsetRight = 0;
    const metrics = measure("Mg", font);
    ascent = finite(metrics.actualBoundingBoxAscent, fontSize * 0.8);
    descent = finite(metrics.actualBoundingBoxDescent, fontSize * 0.2);
  }
  // Reserve italic overhang and use the union of each run's actual glyph ink.
  // Negative ascent/descent is meaningful for punctuation above/below baseline.
  const overhangLeft = Math.max(0, -inkOffsetLeft);
  const overhangRight = Math.max(0, inkOffsetRight - advance);
  const boxHeight = Math.ceil(Math.max(8, fontSize * 1.05, ascent + descent + 4));
  return {text, ...style, font, fontSize, runs, ascent, descent, advance, hasInk,
    inkOffsetLeft, inkOffsetRight, overhangLeft, overhangRight, boxHeight,
    measuredWidth: Math.ceil(Math.max(80, advance + overhangLeft + overhangRight + 10))};
}

function inkBounds(label) {
  const start = label.x - label.advance;
  const halfHeight = (label.ascent + label.descent) / 2;
  return {left: start + label.inkOffsetLeft, right: start + label.inkOffsetRight,
    top: label.y - halfHeight, bottom: label.y + halfHeight};
}

function overlapsVertically(top, bottom, otherTop, otherBottom) {
  return top < otherBottom + VERTICAL_GAP && bottom > otherTop - VERTICAL_GAP;
}

/** Greedy interval partitioning keeps overlapping lane labels in separate columns. */
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

/** Rotated ladder labels keep their ink centers at the clicked native x. */
function layoutLadder(ladder, laneFontSize, annotationTop, measure) {
  if (!ladder) return {labels: [], guides: [], top: 0, tiers: 0};
  const labels = ladder.preset?.labels;
  if (!Array.isArray(labels) || !labels.length || labels.some(text => typeof text !== "string")) {
    throw new Error("Choose a ladder preset with size labels.");
  }
  const preferredFontSize = laneFontSize * 0.8;
  function labelSpec(value, fontSize) {
    const font = annotationFont({}, fontSize);
    const text = oneLine(value);
    const metrics = measure(text, font);
    const ascent = finite(metrics.actualBoundingBoxAscent, fontSize * 0.8);
    const descent = finite(metrics.actualBoundingBoxDescent, fontSize * 0.2);
    const inkLeft = finite(metrics.actualBoundingBoxLeft, 0);
    const inkRight = finite(metrics.actualBoundingBoxRight, finite(metrics.width, 0));
    return {text, font, fontSize, color: "#202020", rotation: -Math.PI / 2,
      ascent, descent, textInkLeft: inkLeft,
      inkWidth: Math.max(0, ascent + descent), inkHeight: Math.max(0, inkLeft + inkRight)};
  }
  const specs = labels.map(value => labelSpec(value, preferredFontSize));
  const longest = Math.max(...specs.map(spec => spec.inkHeight));
  // Reserve the preferred-size preset gutter even when text shrinks, so placing
  // a close marker never moves the gel or raises the shared label row.
  const firstBottom = Math.min(-LADDER_GEL_GAP - LADDER_LEADER - LADDER_TEXT_GAP,
    annotationTop - LADDER_TEXT_GAP - LADDER_INK_PADDING);
  const placements = ladder.placements ?? [];
  for (const placement of placements) {
    if (!Number.isInteger(placement.markerIndex) || !specs[placement.markerIndex]
      || !Number.isFinite(placement.x) || !Number.isFinite(placement.y)) {
      throw new Error("A ladder marker could not be drawn. Choose its size and place it again.");
    }
  }
  const ordered = [...placements].sort((a, b) => a.x - b.x || a.markerIndex - b.markerIndex);
  if (ordered.some((placement, index) => index > 0 && placement.x === ordered[index - 1].x)) {
    throw new Error("Two ladder markers are at the same position. Move or remove one marker.");
  }
  function atSize(fontSize) {
    const scale = fontSize / preferredFontSize;
    const padding = LADDER_INK_PADDING * scale;
    const placed = placements.map(placement => {
      const spec = fontSize === preferredFontSize ? specs[placement.markerIndex]
        : labelSpec(labels[placement.markerIndex], fontSize);
      return {...spec, markerIndex: placement.markerIndex, cropX: placement.x, cropY: placement.y,
        x: placement.x, left: placement.x - spec.inkWidth / 2 - padding,
        right: placement.x + spec.inkWidth / 2 + padding};
    });
    const sorted = [...placed].sort((a, b) => a.x - b.x || a.markerIndex - b.markerIndex);
    return {placed, fits: sorted.every((label, index) => index === 0
      || sorted[index - 1].right + LADDER_LABEL_GAP * scale <= label.left)};
  }
  let fitted = atSize(preferredFontSize);
  if (!fitted.fits) {
    // Remeasure actual glyph ink at each size: browser font metrics need not
    // scale linearly, especially for small text. Backing padding scales too.
    let lower = Math.min(0.01, preferredFontSize);
    let upper = preferredFontSize;
    fitted = atSize(lower);
    if (!fitted.fits) {
      throw new Error("These ladder markers are too close to label. Move or remove one marker.");
    }
    for (let step = 0; step < 24; step++) {
      const middle = (lower + upper) / 2;
      const candidate = atSize(middle);
      if (candidate.fits) { lower = middle; fitted = candidate; }
      else upper = middle;
    }
  }
  const placed = fitted.placed;
  for (const label of placed) {
    label.tier = 0;
    label.inkBottom = firstBottom;
    label.inkTop = label.inkBottom - label.inkHeight;
    label.inkLeft = label.x - label.inkWidth / 2;
    label.inkRight = label.x + label.inkWidth / 2;
    label.top = label.inkTop - LADDER_INK_PADDING;
    label.bottom = label.inkBottom + LADDER_INK_PADDING;
    // Rotation maps (u, v) to (v, -u). Account for real ink rather than
    // aligning the alphabetic baseline, which would shift text to the left.
    label.baselineX = label.x + (label.ascent - label.descent) / 2;
    label.baselineY = label.inkBottom - label.textInkLeft;
  }
  return {labels: placed, tiers: 1,
    top: firstBottom - longest - LADDER_INK_PADDING,
    guides: placed.map(label => ({markerIndex: label.markerIndex, x: label.x,
      startY: -LADDER_GEL_GAP, endY: label.inkBottom + LADDER_TEXT_GAP, color: label.color}))};
}

/**
 * Labels use x as their right-aligned text anchor and y as their visual center.
 * An editor box fits at (x - width, y - boxHeight / 2). Coordinates already
 * include gelX/gelY, which are the original gel's offset in the final canvas.
 * measureText can be injected for tests; its signature is (text, font).
 */
export function layoutAnnotations({width, height, lanes = [], annotations = {}, ladder = null, extractedBands = [], workflow_orientation = "wells_left"}, measureText = browserMeasure) {
  if (ladder?.mode === "manual") {
    const preset = manualLadderAsPreset(ladder, width, height);
    const layout = layoutAnnotations({width, height, lanes, annotations, ladder: preset, extractedBands, workflow_orientation}, measureText);
    // Editing metadata belongs to the saved native point. Every visible label
    // and dash uses precisely the same gutter geometry as a preset marker.
    for (const label of layout.ladderLabels) {
      const placement = ladder.placements[label.markerIndex];
      Object.assign(label, {manual: true, id: placement.id,
        pointX: layout.gelX + placement.x, pointY: layout.gelY + placement.y});
    }
    for (const guide of layout.guides) {
      Object.assign(guide, {manual: true, id: ladder.placements[guide.markerIndex].id});
    }
    return layout;
  }
  if (workflow_orientation === "wells_top") {
    return layoutTopAnnotations({width, height, lanes, annotations, ladder, extractedBands}, measureText);
  }
  if (!Number.isInteger(width) || width < 1 || !Number.isInteger(height) || height < 1) {
    throw new Error("The cropped image could not be loaded. Return to the crop step and try again.");
  }
  const measure = typeof measureText === "function" ? measureText : (text, font) => {
    measureText.font = font;
    measureText.textAlign = "left";
    measureText.textBaseline = "alphabetic";
    return measureText.measureText(text);
  };
  const laneGeometry = lanes.map((lane, index) => {
    if (!Array.isArray(lane) || lane.length !== 4 || !lane.every(Number.isFinite)) {
      throw new Error(`Lane ${index + 1} could not be drawn. Return to the lane step and adjust it.`);
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
  // A font-relative buffer stays visible when a high-resolution gel is fitted to the
  // screen. Measure from actual glyph ink, including italic overhang.
  const bracketGap = Math.max(MIN_BRACKET_GAP, fontSize * 0.4);
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
      index, set: group.set === 1 ? 1 : 0, track: 0, label, lanes: membership, top, bottom, y,
      ticks: selected.map(lane => lane.y),
      start: Math.min(top - 1, y - spec.boxHeight / 2),
      end: Math.max(bottom + 1, y + spec.boxHeight / 2)});
  }
  const groupSets = [0, 1].map(set => groupLabels.filter(group => group.set === set));
  let left = -IMAGE_GAP;
  for (const track of laneTracks) {
    for (const label of track.items) {
      label.x = left - label.overhangRight;
      label.width = track.width - label.overhangRight;
    }
    left -= track.width + COLUMN_GAP;
  }
  const brackets = [];
  const placedLabels = [...laneLabels];
  for (const groups of groupSets) {
    // A selected set is one column. Fit the whole column against nearby lane
    // ink and the preceding group column before placing any of its members.
    // Within-set brackets/text may touch or overlap; they must never stagger.
    let boundary = -IMAGE_GAP;
    for (const label of groups) {
      const top = Math.min(label.top, label.y - (label.ascent + label.descent) / 2);
      const bottom = Math.max(label.bottom, label.y + (label.ascent + label.descent) / 2);
      for (const other of placedLabels) {
        if (!other.hasInk) continue;
        const ink = inkBounds(other);
        if (other.kind === "group" || overlapsVertically(top, bottom, ink.top, ink.bottom)) {
          boundary = Math.min(boundary, ink.left);
        }
      }
    }
    for (const other of brackets) boundary = Math.min(boundary, other.x);
    const bracketX = boundary - bracketGap - BRACKET_DEPTH;
    for (const label of groups) {
      label.x = bracketX - bracketGap - label.overhangRight;
      label.width = label.measuredWidth - label.overhangRight;
      brackets.push({id: label.id, set: label.set, track: label.track,
        x: bracketX, top: label.top, bottom: label.bottom, ticks: [...label.ticks],
        depth: BRACKET_DEPTH, color: "#000000"});
    }
    placedLabels.push(...groups);
  }
  const allLabels = [...laneLabels, ...groupLabels];
  const annotationTop = Math.min(0, ...allLabels.map(label => label.start));
  const ladderLayout = layoutLadder(ladder, fontSize, annotationTop, measure);
  const ladderLabels = ladderLayout.labels;
  const guides = ladderLayout.guides;
  const minX = Math.min(0, ...allLabels.map(label => label.x - label.width),
    ...ladderLabels.map(label => label.left));
  const minY = Math.min(annotationTop, ladderLayout.top);
  const maxY = Math.max(height, ...allLabels.map(label => label.end));
  const gelX = Math.ceil(OUTER - minX);
  const gelY = Math.ceil(OUTER - minY);
  for (const label of allLabels) {
    label.x += gelX;
    label.y += gelY;
    label.start += gelY;
    label.end += gelY;
    label.baseline = label.y + (label.ascent - label.descent) / 2;
    const ink = inkBounds(label);
    label.inkLeft = ink.left;
    label.inkRight = ink.right;
    label.inkTop = ink.top;
    label.inkBottom = ink.bottom;
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
  for (const label of ladderLabels) {
    for (const key of ["x", "left", "right", "inkLeft", "inkRight", "baselineX"]) label[key] += gelX;
    for (const key of ["top", "bottom", "inkTop", "inkBottom", "baselineY"]) label[key] += gelY;
  }
  for (const guide of guides) {
    guide.x += gelX;
    guide.startY += gelY;
    guide.endY += gelY;
  }
  const outputWidth = Math.ceil(Math.max(gelX + width, ...ladderLabels.map(label => label.right)) + OUTER);
  const outputHeight = Math.ceil(gelY + maxY + OUTER);
  if (outputWidth > 32767 || outputHeight > 32767 || outputWidth * outputHeight > 64_000_000) {
    throw new Error("The annotated image is too large to render. Shorten labels, reduce the font size or overlapping groups, or use a smaller cropped image.");
  }
  return {width: outputWidth, height: outputHeight,
    imageWidth: width, imageHeight: height, gelX, gelY, fontSize, requestedFontSize,
    denseFallback: laneTracks.length > 1, reducedFont: fontSize < requestedFontSize, bracketGap,
    laneLabels, groupLabels, brackets, labels: allLabels,
    ladderLabels, guides, ladderTiers: ladderLayout.tiers,
    extractedBands: extractedBands.map(band => ({...band}))};
}

/** Adapt custom text to the preset renderer without changing saved snapshots. */
function manualLadderAsPreset(ladder, width, height) {
  if (!Array.isArray(ladder.placements)) throw new Error("The manual ladder markers could not be drawn.");
  const ids = new Set();
  const labels = [];
  const placements = ladder.placements.map((placement, markerIndex) => {
    if (!placement || typeof placement.id !== "string" || !placement.id.trim() || ids.has(placement.id)
      || typeof placement.label !== "string" || !placement.label.trim()
      || !pointInImage(placement, width, height)) {
      throw new Error("A manual ladder marker could not be drawn. Edit its label or place it inside the gel image.");
    }
    ids.add(placement.id);
    labels.push(placement.label);
    return {markerIndex, x: placement.x, y: placement.y};
  });
  return placements.length ? {preset: {labels}, placements} : null;
}

/** Reuse measured text, lane membership and group semantics for the top gutter.
 * Geometry changes, while the native gel pixels and saved XY coordinates do not.
 */
function layoutTopAnnotations({width, height, lanes, annotations, ladder, extractedBands}, measureText) {
  const source = layoutAnnotations({width: height, height: width,
    lanes: lanes.map(([x0, y0, x1, y1]) => [y0, x0, y1, x1]), annotations}, measureText);
  const angle = annotations.laneLabelAngle === 45 ? 45 : 90;
  const rotation = angle * Math.PI / 180;
  const cos = Math.cos(rotation), sin = Math.sin(rotation);
  const rotate = (u, v) => ({x: cos * u - sin * v, y: sin * u + cos * v});
  const labels = source.labels;
  const measure = typeof measureText === "function" ? measureText : (text, font) => {
    measureText.font = font; measureText.textAlign = "left"; measureText.textBaseline = "alphabetic";
    return measureText.measureText(text);
  };
  function prepare(label, anchor) {
    label.width = label.measuredWidth - label.overhangRight;
    label.rotation = rotation;
    label.rotationDegrees = angle;
    label.anchor = anchor;
    const end = rotate(label.inkOffsetRight - label.advance, (label.descent - label.ascent) / 2);
    label.baselineX = anchor - end.x;
    label.endOffsetY = end.y;
    const corners = [[label.inkOffsetLeft - label.advance, -label.ascent],
      [label.inkOffsetRight - label.advance, -label.ascent],
      [label.inkOffsetLeft - label.advance, label.descent],
      [label.inkOffsetRight - label.advance, label.descent]].map(([u, v]) => rotate(u, v));
    label.localTop = Math.min(...corners.map(point => point.y));
    label.localBottom = Math.max(...corners.map(point => point.y));
    label.inkLeft = label.baselineX + Math.min(...corners.map(point => point.x));
    label.inkRight = label.baselineX + Math.max(...corners.map(point => point.x));
    // Include empty editable labels in fitting and exported canvas bounds.
    label.editorBaseline = (label.boxHeight + label.ascent - label.descent) / 2;
    const editorCorners = [[-label.width, -label.editorBaseline], [0, -label.editorBaseline],
      [-label.width, label.boxHeight - label.editorBaseline], [0, label.boxHeight - label.editorBaseline]]
      .map(([u,v]) => rotate(u,v));
    label.editorLeft = label.baselineX + Math.min(...editorCorners.map(point => point.x));
    label.editorRight = label.baselineX + Math.max(...editorCorners.map(point => point.x));
    label.editorLocalTop = Math.min(...editorCorners.map(point => point.y));
    label.editorLocalBottom = Math.max(...editorCorners.map(point => point.y));
    label.start = Math.min(label.inkLeft, label.editorLeft);
    label.end = Math.max(label.inkRight, label.editorRight);
  }
  function atBaseline(label, baselineY) {
    label.baselineY = baselineY;
    label.inkTop = label.baselineY + label.localTop;
    label.inkBottom = label.baselineY + label.localBottom;
    label.editorTop = label.baselineY + label.editorLocalTop;
    label.editorBottom = label.baselineY + label.editorLocalBottom;
  }
  for (const label of labels) prepare(label, label.y - source.gelY);

  // Every lane label ends at its lane center on one shared horizontal line.
  // Axis-aligned boxes overestimate collisions for parallel diagonal text:
  // their horizontal projections overlap even when the glyphs are separated.
  // Compare intervals in the shared rotated text axes instead. Include the
  // editable text boxes so a dense label never covers another's click target.
  function fitLaneLabels(fontSize) {
    for (const label of source.laneLabels) {
      const value = annotations.labels?.[label.index] ?? {};
      Object.assign(label, textSpec(value, oneLine(value.text), fontSize, measure));
      // A fixed native-pixel hit-box minimum would reject valid low-resolution
      // gels even after their text fits. Keep caret padding proportional to the
      // rendered font; zoom scales both the text and its editable target.
      label.boxHeight = Math.max(fontSize * 1.05, label.ascent + label.descent + fontSize * 0.2);
      prepare(label, (lanes[label.index][0] + lanes[label.index][2]) / 2);
    }
    const anchorY = -IMAGE_GAP - Math.max(0, ...source.laneLabels.map(label =>
      Math.max(label.localBottom, label.editorLocalBottom) - label.endOffsetY));
    const boxes = source.laneLabels.map(label => {
      label.anchorY = anchorY;
      atBaseline(label, anchorY - label.endOffsetY);
      const u = cos * label.baselineX + sin * label.baselineY;
      const v = -sin * label.baselineX + cos * label.baselineY;
      return {left: u + Math.min(-label.width, label.inkOffsetLeft - label.advance),
        right: u + Math.max(0, label.inkOffsetRight - label.advance),
        top: v + Math.min(-label.ascent, -label.editorBaseline),
        bottom: v + Math.max(label.descent, label.boxHeight - label.editorBaseline)};
    });
    const gap = Math.min(2, fontSize * 0.1);
    return boxes.every((box, index) => boxes.slice(index + 1).every(other =>
      box.right + gap <= other.left || other.right + gap <= box.left
      || box.bottom + gap <= other.top || other.bottom + gap <= box.top));
  }
  let laneFontSize = source.fontSize;
  if (!fitLaneLabels(laneFontSize)) {
    let lower = Math.min(0.01, laneFontSize), upper = laneFontSize;
    if (!fitLaneLabels(lower)) {
      throw new Error("These lane labels are too close to fit above their lanes. Increase lane spacing or use a larger source image.");
    }
    // Remeasure real browser glyphs rather than assuming linear font metrics.
    // Keep the user's requested size intact for editing and project roundtrips.
    for (let step = 0; step < 24; step++) {
      const middle = (lower + upper) / 2;
      if (fitLaneLabels(middle)) lower = middle;
      else upper = middle;
    }
    laneFontSize = lower;
    fitLaneLabels(laneFontSize);
  }
  const placed = [...source.laneLabels];
  const brackets = [];
  // Each selected set is one row, just as it is one column with wells at left.
  // Resolve clearance for all members together without staggering close groups.
  for (const set of [0, 1]) {
    const groups = source.groupLabels.filter(label => label.set === set);
    let boundary = -IMAGE_GAP;
    for (const label of groups) {
      const left = Math.min(...label.lanes.map(index => lanes[index][0]));
      const right = Math.max(...label.lanes.map(index => lanes[index][2]));
      const spanLeft = Math.min(left, label.start), spanRight = Math.max(right, label.end);
      for (const other of placed) {
        if (other.kind === "group"
          || (other.start < spanRight + VERTICAL_GAP && other.end > spanLeft - VERTICAL_GAP)) {
          boundary = Math.min(boundary, other.inkTop, other.editorTop);
        }
      }
    }
    for (const other of brackets) boundary = Math.min(boundary, other.y);
    const y = boundary - source.bracketGap - BRACKET_DEPTH;
    const anchorY = y - source.bracketGap - Math.max(0, ...groups.map(label =>
      Math.max(label.localBottom, label.editorLocalBottom) - label.endOffsetY));
    for (const label of groups) {
      const left = Math.min(...label.lanes.map(index => lanes[index][0]));
      const right = Math.max(...label.lanes.map(index => lanes[index][2]));
      brackets.push({id: label.id, set, track: label.track, horizontal: true,
        left, right, y, ticks: label.lanes.map(index => (lanes[index][0] + lanes[index][2]) / 2),
        depth: BRACKET_DEPTH, color: "#000000"});
      label.anchorY = anchorY;
      atBaseline(label, anchorY - label.endOffsetY);
    }
    placed.push(...groups);
  }
  // The existing ladder fitter measures collision spacing along migration.
  // Transpose its positional geometry, then render horizontal readable text.
  const transposeLadder = ladder ? {...ladder, placements: (ladder.placements ?? [])
    .map(placement => ({...placement, x: placement.y, y: placement.x}))} : null;
  let ladderLayout = layoutLadder(transposeLadder, source.fontSize, 0, measure);
  const ladderTop = Math.min(0, ...ladderLayout.labels.map(label => label.left));
  const ladderBottom = Math.max(height, ...ladderLayout.labels.map(label => label.right));
  const leftBoundary = Math.min(0, ...labels.filter(label =>
    label.editorTop < ladderBottom + VERTICAL_GAP && label.editorBottom > ladderTop - VERTICAL_GAP)
    .map(label => label.editorLeft));
  if (leftBoundary < 0) ladderLayout = layoutLadder(transposeLadder, source.fontSize, leftBoundary, measure);
  const ladderLabels = ladderLayout.labels.map(label => ({...label,
    cropX: label.cropY, cropY: label.cropX, rotation: 0, rotationDegrees: 0,
    left: label.top, right: label.bottom, top: label.left, bottom: label.right,
    inkLeft: label.inkTop, inkRight: label.inkBottom,
    inkTop: label.inkLeft, inkBottom: label.inkRight,
    baselineX: label.inkTop + label.textInkLeft,
    baselineY: label.x + (label.ascent - label.descent) / 2,
  }));
  const guides = ladderLayout.guides.map(guide => ({...guide, horizontal: true,
    y: guide.x, startX: guide.startY, endX: guide.endY}));
  const minX = Math.min(0, ladderLayout.top, ...labels.map(label => label.editorLeft),
    ...labels.map(label => label.inkLeft), ...ladderLabels.map(label => label.left));
  const minY = Math.min(0, ...labels.map(label => label.editorTop),
    ...labels.map(label => label.inkTop), ...ladderLabels.map(label => label.top));
  const maxX = Math.max(width, ...labels.map(label => label.editorRight),
    ...labels.map(label => label.inkRight), ...ladderLabels.map(label => label.right));
  const maxY = Math.max(height, ...ladderLabels.map(label => label.bottom));
  const gelX = Math.ceil(OUTER - minX), gelY = Math.ceil(OUTER - minY);
  for (const label of labels) {
    for (const key of ["baselineX", "anchor", "inkLeft", "inkRight", "editorLeft", "editorRight", "start", "end"]) label[key] += gelX;
    for (const key of ["baselineY", "inkTop", "inkBottom", "editorTop", "editorBottom"]) label[key] += gelY;
    label.anchorY += gelY;
  }
  for (const bracket of brackets) {
    bracket.left += gelX; bracket.right += gelX; bracket.y += gelY;
    bracket.ticks = bracket.ticks.map(x => x + gelX);
  }
  for (const label of ladderLabels) {
    for (const key of ["left", "right", "inkLeft", "inkRight", "baselineX"]) label[key] += gelX;
    for (const key of ["top", "bottom", "inkTop", "inkBottom", "baselineY"]) label[key] += gelY;
  }
  for (const guide of guides) { guide.y += gelY; guide.startX += gelX; guide.endX += gelX; }
  const outputWidth = Math.ceil(gelX + maxX + OUTER), outputHeight = Math.ceil(gelY + maxY + OUTER);
  if (outputWidth > 32767 || outputHeight > 32767 || outputWidth * outputHeight > 64_000_000) {
    throw new Error("The annotated image is too large to render. Shorten labels, reduce the font size or overlapping groups, or use a smaller cropped image.");
  }
  return {...source, width: outputWidth, height: outputHeight, imageWidth: width, imageHeight: height,
    gelX, gelY, workflow_orientation: "wells_top", laneLabelAngle: angle,
    denseFallback: false, laneFontSize, reducedFont: laneFontSize < source.fontSize - 0.01,
    labels, brackets, ladderLabels, guides, ladderTiers: ladderLayout.tiers,
    extractedBands: extractedBands.map(band => ({...band}))};
}

/** Paint only exportable pixels: white margin, gel, labels, brackets and band outlines. */
export function drawAnnotations(canvas, image, layout, _annotations) {
  canvas.width = layout.width;
  canvas.height = layout.height;
  const context = canvas.getContext("2d");
  if (!context) throw new Error("The browser could not draw the preview. Reload the page and try again.");
  context.fillStyle = "#ffffff";
  context.fillRect(0, 0, layout.width, layout.height);
  // The three-argument form preserves the source gel's pixel dimensions.
  context.drawImage(image, layout.gelX, layout.gelY);
  context.lineWidth = 2;
  context.strokeStyle = "#dc2626";
  context.lineCap = "butt";
  for (const band of layout.extractedBands ?? []) {
    const x = layout.gelX + band.x, y = layout.gelY + band.y;
    context.beginPath();
    context.moveTo(x, y);
    context.lineTo(x + band.width, y);
    context.lineTo(x + band.width, y + band.height);
    context.lineTo(x, y + band.height);
    context.lineTo(x, y);
    context.stroke();
  }
  context.lineWidth = 1.5;
  context.lineCap = "butt";
  for (const bracket of layout.brackets) {
    context.strokeStyle = "#000000";
    context.beginPath();
    if (bracket.horizontal) {
      context.moveTo(bracket.left, bracket.y + bracket.depth);
      context.lineTo(bracket.left, bracket.y);
      context.lineTo(bracket.right, bracket.y);
      context.lineTo(bracket.right, bracket.y + bracket.depth);
      for (const x of bracket.ticks) {
        context.moveTo(x, bracket.y); context.lineTo(x, bracket.y + bracket.depth * 0.6);
      }
      context.stroke();
      continue;
    }
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
    if (label.rotation) {
      context.save();
      context.translate(label.baselineX, label.baselineY);
      context.rotate(label.rotation);
      context.textAlign = "left";
      for (const run of label.runs) {
        context.font = run.font; context.fillStyle = run.color;
        context.fillText(run.text, -label.advance + run.offset, 0);
      }
      context.restore();
      continue;
    }
    if (label.runs.length === 1) {
      context.font = label.runs[0].font;
      context.fillStyle = label.runs[0].color;
      context.textAlign = "right";
      context.fillText(label.text, label.x, label.baseline);
    } else {
      context.textAlign = "left";
      for (const run of label.runs) {
        if (!run.text) continue;
        context.font = run.font;
        context.fillStyle = run.color;
        context.fillText(run.text, label.x - label.advance + run.offset, label.baseline);
      }
    }
  }
  // Leaders retain their native anchors. Backings and text are drawn last,
  // identically in the preview and exported image.
  context.lineWidth = LADDER_STROKE;
  for (const guide of layout.guides ?? []) {
    context.strokeStyle = guide.color;
    context.beginPath();
    context.moveTo(guide.horizontal ? guide.startX : guide.x, guide.horizontal ? guide.y : guide.startY);
    context.lineTo(guide.horizontal ? guide.endX : guide.x, guide.horizontal ? guide.y : guide.endY);
    context.stroke();
  }
  context.fillStyle = "#ffffff";
  for (const label of layout.ladderLabels ?? []) {
    context.fillRect(label.left, label.top, label.right - label.left, label.bottom - label.top);
  }
  for (const label of layout.ladderLabels ?? []) {
    context.save();
    context.translate(label.baselineX, label.baselineY);
    context.rotate(label.rotation);
    context.font = label.font;
    context.fillStyle = label.color;
    context.textAlign = "left";
    context.textBaseline = "alphabetic";
    context.fillText(label.text, 0, 0);
    context.restore();
  }
  return layout;
}
