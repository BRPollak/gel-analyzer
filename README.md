# Agarose Gel Analyzer

Latest tagged release: **0.0.1** (Git tag: `v0.0.1`).

**Current development snapshot: work in progress. The app is not yet fully
functioning as intended.** The well/lane detection, manual border adjustment,
right-edge selection, and buffered cropping workflow still needs debugging and
validation on real gels. Automatic well boundaries can be inaccurate; passing
automated tests and synthetic browser checks does not establish end-to-end
correctness. This snapshot preserves the current code for continued development
and is not a new stable release.

This local app accepts one TIFF gel image (`.tif` or `.tiff`) and automatically
crops the surrounding background before displaying it. **Rotate and Orient**
straightens, reorients, and tightly crops the gel for confirmation. Replace or
clear the image at any time. After confirming orientation, define a line through
selected wells to detect their boundaries and horizontal lanes. Review each
lane's height, choose a shared right edge, and confirm to crop the final gel.
Lane review includes deleting unwanted candidates and adding missing lanes.
After cropping, annotate lanes and two independent sets of groups, then confirm
and download the composed PNG. Optional manual ladder size labels can be placed
above the gel. Automatic band identification and ladder analysis remain later
steps; band contrast already helps refine automatic lane coverage.

## Run locally

Install [uv](https://docs.astral.sh/uv/getting-started/installation/), then run from
this project folder:

```sh
uv sync --locked
./run_local.sh
```

The project uses Python 3.12 in an isolated `.venv`. If needed, uv downloads the
interpreter automatically. The launcher always uses this checkout's `.venv` and
`app.py`, even when invoked from another folder. Open
<http://127.0.0.1:8502>. This checkout defaults to port 8502 because a separate
test checkout uses port 8501; the launcher does not stop or replace that server.
Press Ctrl+C in the terminal to stop this server.

To use another port, run `./run_local.sh --port 8503` or
`GEL_ANALYZER_PORT=8503 ./run_local.sh`. The `--port` option takes precedence.

Use the served app URL for local testing. The files in
`gel_analyzer/annotation_component_frontend/` are embedded Streamlit components;
opening their HTML directly with a `file://` URL does not initialize the app.

## Use

1. Browse for or drop one single-image TIFF into **Open a gel image** on the
   startup screen. No image-type selection is needed.
2. Wait for the automatic crop, then inspect the preview and its cropped pixel
   dimensions. Large images fit the screen's width and height; small images are
   not enlarged. New previews are brought into view automatically.
3. Click **Rotate and Orient** to fit the gel outline and preview its orientation.
4. Inspect the result, then click **Confirm** in the workflow panel beside the preview.
   Both orientation buttons disappear, and the confirmed image stays displayed.
5. Click **Define wells**. Click at the top of the topmost selected well and the
   bottom of the bottommost selected well, with the line passing through the well
   centers. Either click order works. Drag the dots to adjust the dotted line.
6. Optionally enter **Expected number of lanes**, then click **Confirm line and
   detect lanes**. Leave the field blank for automatic counting. Review the
   detected count and numbered well markers and horizontal lane outlines.
7. Click **Adjust lane borders**. Use the trash button to the right of a lane to
   delete it, or **Add lane** to insert one at the bottom of the guide. Drag each
   numbered lane's top and bottom borders independently, then click **Confirm
   lane borders**. **Add lane** is also available when detection finds no wells.
8. Drag the shared right boundary to the farthest point you want to keep.
   Click **Confirm lanes and crop** to create the cropped gel preview.
9. Click a lane label beside the crop and type directly on the preview. The
   formatting controls apply to selected text; with only a caret or no text
   selected, they apply to the whole label. Expand **Lane groups** in the
   workflow panel to create groups in either set. Click
   **Confirm annotations** to compose the final image. **Edit annotations**
   returns to the saved labels and groups. Choose **Annotate ladder** to add
   manual size labels, or **Skip** to continue. **Download annotated PNG** saves
   the confirmed image, including any ladder labels.
10. Expand **Revise analysis** to use **Revise lanes and crop** to adjust the
   existing review, or **Edit well line** to detect again. **Reset points** starts
   a new guide on the same gel.
11. Open **Change image** to choose another TIFF, even if it has the same filename.
   Use **Clear image** or the uploader's remove button there to start again.

All previews adapt to the browser window without changing source pixels, lane
coordinates, or download resolution. The annotation editor defaults to **Fit
screen**; choose a percentage under **Zoom** to inspect it more closely with
scrolling. Each step's controls and continuation action stay to the right of the
image, including in narrow desktop browser panels. Only very narrow phone
screens stack the controls below the image. The annotation panel scrolls its
optional controls while keeping the confirmation actions visible. Ladder photos
use a separate column on wide screens and sit below the gel in compact panels,
so they do not displace the menu on the right.

### Define wells and detect lanes

Well selection is available only on the confirmed, reoriented gel. The endpoints
specify the outside vertical limits of the selected range; the line should cross
the centers of the wells near the left side of the gel, where migration begins.
It may slope slightly. Coincident, too-short, or nearly horizontal selections
cannot be confirmed. The overlay keeps the image's aspect ratio and records
coordinates in confirmed-image pixels, even when the browser preview is scaled.

Detection runs only when you confirm the line. It analyzes narrow strips around
the guide and nearby shifted guides, looking for agreement before recovering a
missed or partial well. Clear wells retain their independently measured sizes
and spacing. A visible well does **not** indicate whether a sample was loaded.
Numbering runs from top to bottom.

**Expected number of lanes** is the only additional input. It is optional and
helps join compatible short fragments and recover faint, supported outlines.
Spacing is a soft preference, not a forced uniform grid. A count mismatch is
reported rather than inventing wells in blank gaps or deleting clear wells.
Changing the count preserves the guide but clears the previous detection and
crop for a fresh confirmation. Guide edits retain the count; a new image or
orientation clears it.

When the first pass finds weak boundaries, a second pass looks for faint,
spatially coherent well walls and recovers shallow interruptions. It preserves
clear separations from the first pass so stronger neighboring wells are not
merged into one lane. If an endpoint cuts slightly into a well, a bounded search
can complete its outline just beyond the endpoint, with a review message. Wells
entirely outside the selected range remain excluded. Review remains necessary
for faint or ambiguous outlines.

Each lane includes its well and extends to the image's right edge. A separate
automatic refinement uses sustained downstream band contrast to expand borders
that would cut through bands. It also borrows typical thickness from several
consistent neighbors for unusually thin, uncertain lanes, while preserving
sharply bounded wells with genuinely different heights. Expansion stops before
neighboring wells; empty lanes remain present. Isolated hot pixels and scratches
that continue across the search window do not establish lane borders.

Half-open lane bounds are `(well_left, lane_top, image_width, lane_bottom)`;
the detected well outline stays separate from the expanded lane. Sloping the
guide does not rotate the lanes. Endpoints, well bounds, centers, and lane
rectangles are session data separate from image pixels. All analysis uses
temporary arrays; the original TIFF bytes and lossless preview, including
16-bit grayscale precision, are preserved.

Editing invalidates the previous result. If no wells are found or boundaries are
uncertain, the app explains the issue and keeps the guide editable. Candidate
results with warnings require review and are not shown as a completed detection.
Replacing, removing, or clearing an upload, or changing its orientation, discards
all well geometry. Events from an older image or an earlier edit are ignored.

Detection works best when both side walls or a filled well have clear contrast
against the adjacent gel. Very faint, broken, or uneven outlines can be missed,
split, or yield imprecise boundaries. Broad wells that exceed the local search
strip, unresolved gaps, nearby artifacts, and wells cut by the selection or the
image edge may also require a retry. The guide is essential: placing it over a
band cannot establish that the feature is a well. Transparent images can still
be uploaded and oriented, but well detection requests an opaque gel image.
This feature proposes image-based geometry; review the outlines before relying
on them. The manual review below adds/removes lanes and adjusts vertical
boundaries and the final right edge; it does not adjust individual well
left/right walls.

### Adjust lane borders and crop

**Adjust lane borders** begins a two-step review after at least one well has
been detected. Candidates with uncertainty warnings can also be reviewed; the
warnings remain visible in the border step. If no wells are found, use **Add
lane** to begin manual recovery, or edit the guide and run detection again.

In the first step, a trash button at the right of each lane deletes that lane
and renumbers the remaining lanes from top to bottom. **Add lane** places a new
lane at the bottom guide endpoint, or below the last lane when that endpoint
is already occupied. Its starting width and height use the median reviewed well
dimensions; an empty review uses a small initial rectangle. The new well follows
the guide's slope, and its placement is kept within the image and shared right
edge. Adjust its borders to cover the intended well and bands. If there is no
room for another lane below the last one, the app explains how to make room.
Deleting every lane is allowed; add at least one before confirming. Trash
buttons support Enter and Space as well as clicking.

Drag the arrow handle on each lane's top or bottom border up
or down. The well marker changes height with its lane. A border cannot cross
its opposite border, overlap a neighboring lane, or leave the image. Focus a
handle and use Up/Down for one-pixel adjustments, or hold Shift for ten pixels.
Click **Confirm lane borders** to continue.

In the second step, drag the shared right boundary horizontally. The shaded
area to its right will be removed. This boundary applies to every lane and
cannot pass through a well; the entire detected well width remains included.
Left/Right arrow keys also adjust it. **Back to lane borders** preserves the
right edge and lets you revise the individual heights.

**Confirm lanes and crop** copies one rectangular region from the confirmed
orientation. Its top and bottom include a buffer outside the outermost reviewed
lanes, and its right is the selected boundary. The left edge is the
leftmost well minus a margin of 1% of the confirmed image width, with a minimum
of three pixels, clipped at the image edge. Spaces between lanes remain in the
image. Above and below the outer lanes, the buffer is 1% of the confirmed image
height, with a minimum of three pixels on each side, clipped to the image edges.

The cropped preview preserves pixel values, color/alpha channels, and unsigned
16-bit precision without resizing or normalization. It is stored separately
from the original TIFF and confirmed orientation. **Revise lanes and crop**
reopens the full confirmed image with your previous adjustments, so even an
expanded revision recovers the original pixels and never crops an earlier crop.
Changing the image/orientation or editing the well guide clears this review and
its final crop. Late events from earlier stages cannot restore old geometry.

### Lane annotations

The app uses a wide workspace. **Change image** opens the replacement and clear
controls; optional detection settings and analysis revisions can be expanded
when needed, leaving more room for the gel.

Crop confirmation opens an annotation editor using the crop's translated lane
coordinates. Click a right-aligned Arial label beside the gel to edit its text
in place. Select a substring to change just its bold, italic (including both
together), or color formatting. With no text range selected, those controls
format the whole label. Mixed formatting is retained during text edits, layout
changes, confirmation, and PNG export. There is no separate lane-text form.
Formatting controls stay outside the final image; the selected label stays
highlighted while you use them. Group creation and membership controls are in
the collapsible **Lane groups** section in the workflow panel.

The initial font size is 80% of the average cropped lane height, rounded to a
whole pixel. It applies to lane and group labels, and can be adjusted from
1–4096 pixels. **Auto size** reapplies that calculation to existing annotations
without changing their text or groups. Saved font choices survive reediting and
crop revisions.

Groups have editable labels and lane memberships. Set 1 appears immediately left
of the lane labels; Set 2 appears farther left, and both remain visible. A bracket
spans the selected lanes' outer bounds, with ticks at the selected lane centers.
Ticks identify membership when the selected lanes are not consecutive. Brackets
and ticks always remain black, independently of the group label's formatting.
Each bracket moves as far right as the visible text in its span permits, with
a consistent gap. Placement uses rendered glyph bounds, including font size,
mixed styles, and italic overhang, rather than the width of an editing box. The group
label sits to the bracket's left, right-aligned and vertically centered. Groups
may be renamed, reformatted, or deleted. Overlapping groups
within a set receive separate horizontal tracks so their labels and brackets
remain distinct.

The left margin grows to fit measured Arial text, including bold/italic overhang.
Outer padding protects annotations near the image edges. Closely spaced labels
use additional horizontal tracks while retaining their font size and lane centers.
Preview zoom only changes the on-screen view: the final gel
region retains its crop dimensions and is never resampled to make room for labels.

**Confirm annotations** captures the same canvas used for the live preview into
a new PNG containing the gel, labels, and brackets. Text-box borders, selection
indicators, and editing controls are excluded. **Edit annotations** keeps every
label, format, and group. Revising crop bounds retains annotations; deleting a
lane removes its label and group membership, and adding a lane creates a new
label. Replacing the image, redefining the well guide, or restarting detection
clears annotations along with the lane geometry.

Composition uses the browser's Arial font and display-color canvas (8-bit RGBA),
not the original 16-bit grayscale data. The original TIFF and lossless crop remain
unchanged. Arial must be installed on the browser's system for exact typography.
All editing and composition stay local to the app/browser session, without an
external service or font download.

### Optional manual ladder annotations

After **Confirm annotations**, choose **Annotate ladder** or **Skip**. Select a
preset, click its horizontal lane (or use **Ladder lane**), and choose **Use this
lane**. Choose a size marker, then click or tap its band in the highlighted lane.
Place any subset of the available markers. Selecting a placed marker lets the
next click move it; **Remove marker** makes that size available again. Clicks
outside the selected lane do not change annotations.

The app includes **100 bp DNA Ladder (NEB)**, **1 kb DNA Ladder (NEB)**, and
**Supercoiled DNA Ladder (NEB)** presets. Selecting one opens its supplied photo
in a collapsible reference panel beside the gel and annotation controls. Enlarge
the photo for a closer look while matching bands to the available size markers.
The reference panel stays separate from the exported annotation image.

Labels appear above the gel, rotated 90° counterclockwise, at the exact clicked
horizontal position. Their normal Arial size is half the calculated default
lane-label size (80% of mean lane height, rounded, then halved), independent of
manual lane font changes. When nearby labels would overlap, all ladder labels
shrink together while keeping their visible bottoms aligned at one level. Moving
markers apart restores the normal size. Lane and group fonts stay unchanged.
Coincident markers or positions too close to fit prompt you to move or remove a
marker before confirming; every placement remains editable.

The top margin reserves space for the preset's longest label at its normal size.
Guide lines begin six native pixels above the gel and stop six native pixels
below the visible label text. They all have the same length, normally 15 native
pixels, with a stroke weight of 1.8 pixels. Oversized lane or group labels move
the entire ladder row upward together and extend all guide lines equally. The
gel itself is never resized for annotation.

**Back** keeps the draft. Changing preset or lane with placed markers asks before
clearing those marker positions. **Cancel** returns to the previous confirmed
image. **Skip ladder** uses the lane-only image; **Remove ladder** does the same
when editing an existing ladder. **Confirm ladder annotations** saves the
combined image, and **Edit ladder** reopens its placements. Lane/group text edits
retain ladder positions on the same crop. Changed crop or lane geometry clears
ladder positions for replacement while retaining normal lane/group annotations.

Use the keyboard lane selector and marker buttons, then **Position with keyboard**
to focus the placement cursor. Arrow keys move one native pixel; Shift moves ten.
Enter places or moves the selected marker, and Escape leaves cursor interaction.
Fit screen and percentage zoom change only the view. Touch scrolling does not
place markers. Selection outlines, cursors, and controls are excluded from the
confirmed PNG and download; both use the same clean canvas.

#### Define your ladder presets

Edit `gel_analyzer/ladder_presets.json` and reload the app. The bundled labels
follow the supplied photos, verified against NEB's [100 bp DNA Ladder](https://www.neb.com/en-us/products/n3231-100-bp-dna-ladder),
[1 kb DNA Ladder](https://www.neb.com/products/n3232-1-kb-dna-ladder), and
[Supercoiled DNA Ladder](https://www.neb.com/en-us/products/n0472-supercoiled-dna-ladder)
references. The 100 bp preset includes the combined **500/517 bp** band; the kb
presets use the rounded sizes printed in their photos. The supercoiled preset
matches the supplied original N0472 ladder, not its later replacement. Add
entries like:

```json
[
  {
    "id": "my-ladder",
    "name": "My ladder",
    "labels": ["5.0 kb", "3.0 kb", "1.0 kb"],
    "referenceImage": "ladder_references/my-ladder.png",
    "referenceNote": "Optional short guidance for reading the reference."
  }
]
```

Keep IDs unique (letters, numbers, hyphens, underscores; at most 80 characters).
Names and labels must be nonempty single lines of at most 200 characters; labels
must be unique within a preset. Up to 100 presets and 200 markers per preset are
supported. Labels appear in file order; their units and sizes are not interpreted.
The optional `referenceImage` points to an image in
`gel_analyzer/annotation_component_frontend/ladder_references/`. Use a filename
of 1–80 letters, numbers, hyphens, or underscores followed by `.webp`, `.gif`,
`.png`, `.jpg`, or `.jpeg`; URLs and nested paths are not supported. Optional
`referenceNote` text must be a nonempty single line of at most 500 characters.
Presets without reference metadata remain supported. The three supplied images
are bundled unchanged, so viewing them requires no external image request.
Missing or invalid configuration explains the problem and still allows skipping.
An active annotation saves a preset snapshot including its reference metadata,
so editing this file does not silently rename markers already placed in that
session. All data remains local
and session-only. Automatic band detection, size inference, and calibration are
not part of this feature.

### Rotate and orient

The button starts from the first cropped image and fits a tilted rectangle to
the outer gel edges. It rotates the image counterclockwise by the measured angle
needed to make the original top and bottom edges vertical, including correction
of existing tilt. At this intermediate stage the original left side is at the
bottom. A vertical flip then moves that side to the top. Finally, the image is
cropped to the transformed rectangle, removing the first crop's margin.

The final edge positions are: original left at the top, original right at the
bottom, original top at the left, and original bottom at the right. This is a
rotation and reflection, without perspective correction.

The transformed image remains a pending preview until **Confirm** accepts it as
the current gel. **Rotate and Orient** remains available before confirmation;
clicking it again starts from the first crop so transformations never accumulate.
Replacing or clearing the upload resets this workflow. If the outline cannot be
estimated reliably, the app explains the failure and keeps the first crop.

Orientation expects one roughly centered, opaque gel with visible outer edges
and a modest tilt. Competing faint or blurred outer edges are treated as
uncertain so a sharper inner boundary cannot silently remove physical gel.

### Automatic crop

The detector looks for one approximately centered rectangular gel that is
darker than its surroundings. It checks sustained contrast along all four edges,
allows slight tilt, and retains a margin of approximately 3% of the gel's shorter
side (with a minimum allowance for detection precision). The rectangular crop
encloses the tilted gel's corners. This initial outer-gel crop has no adjustment
controls; the final lane-based crop is selected later.

Weak background transitions must form a consistent competing edge before they
block cropping. Broad lighting changes that continue beyond the gel are treated
as illumination. Faint or blurred alternatives confined to the gel, and multiple
outer sides suggesting a larger enclosure, still trigger the conservative
fallback. The main gel-edge contrast and support requirements remain unchanged.

If a safe boundary cannot be confirmed, the app retains the full frame and says
so. Examples include ambiguous nested rectangles, very faint edges, strong
rotation, and gels extending outside the photographed frame. This conservative
fallback favors preserving gel content over removing background. Five supplied
real gels and generated cases have been verified, with one real gel reserved
from tuning. This is a small validation set, so broader generalization still
needs additional examples.

The previous preview is replaced by a processing message during upload. Only
the finished crop (or the full-frame fallback) is then shown. The original TIFF
is always retained unchanged in session memory.

An invalid selection clears the previous preview and shows an error. Valid
unsigned grayscale (including 16-bit in either byte order), 8-bit RGB/RGBA,
palette, and bilevel TIFFs are supported. Common TIFF compression such as LZW
and deflate is supported. Multipage TIFFs, floating-point/signed samples, and
high-bit-depth color TIFFs are rejected explicitly rather than selecting a page
or silently reducing precision. PNG is no longer an input format. The standard
Streamlit upload limit is 200 MB; Pillow's decompression protection also rejects
exceptionally large decoded images.

Uploaded bytes are retained unchanged in the current browser session. The app
does not save images to disk or send them to an external processing service.
Refreshing the page or ending the session clears the image. A separate lossless
PNG is generated for the browser, preserving unsigned 16-bit grayscale values.
The decoder honors TIFF orientation metadata. The first automatic crop copies
pixels directly from the decoded source without contrast adjustment,
normalization, or resampling. Rotate and Orient resamples only for straightening;
it preserves 16-bit grayscale precision and does not adjust contrast. Browser
display scaling and orientation never alter the original TIFF bytes.

## Development and verification

```sh
uv run pytest
node --test tests/test_well_component.mjs
node --test tests/test_annotation_layout.mjs
node --test tests/test_preview_fit.mjs
```

The JavaScript unit tests require Node.js 18 or newer. Running the app itself
requires no Node installation or frontend build.

The Streamlit entry point is `app.py`. `gel_analyzer/image_io.py` handles TIFF
validation independently of Streamlit and returns an immutable `GelImage` with
the original bytes, filename, decoded dimensions, mode, crop bounds, and cropped
PNG preview. `gel_analyzer/auto_crop.py` detects edges on a reduced grayscale
analysis copy; normalization is confined to that temporary copy.
`gel_analyzer/orientation.py` fits and transforms the gel rectangle, then flips
and crops the image. `orient_gel_image` stages an immutable replacement from the
lossless first-crop PNG; confirmation makes it the current `GelImage`.
`gel_analyzer/wells.py` validates the guide/count and detects wells independently
of Streamlit. `gel_analyzer/lane_refinement.py` estimates lane coverage from
typical thickness and downstream contrast without changing detected well
outlines. `gel_analyzer/well_component.py` serves the local HTML/JavaScript SVG
overlay in `gel_analyzer/well_component_frontend/`; it has no frontend build or
external service dependency. The app validates tokened, revisioned component
events before accepting geometry, and only a confirmation stages detection.
`gel_analyzer/lane_crop.py` independently validates manual geometry, proposes
appended lanes, and makes a lossless enclosing crop. `gel_analyzer/lane_review_ui.py`
manages the two review stages, lane insertion/deletion, and confirmation callbacks.
`gel_analyzer/annotation_ui.py` retains annotation drafts and confirmed images;
`annotations.py` validates label, group, and PNG events. The local
`annotation_component_frontend/` editor measures and draws the same canvas for
both live preview and final PNG, with token/revision checks guarding stale events.
Structural edits rotate the component token so delayed events cannot restore
deleted lanes or target an outdated lane number. The overlay's `lane_review.mjs`
handles trash buttons and axis-constrained border and extent dragging with the
shared coordinate helpers.

`crop_box` uses Pillow's half-open `(left, top, right, bottom)` coordinates in
the full decoded image after TIFF orientation is applied. `width` and `height`
remain the source dimensions; `preview_width` and `preview_height` describe the
current preview. Before orientation, bounds are rounded outward when mapped from
analysis to source pixels. After orientation, `crop_box` still records the first
crop in source coordinates; `orientation` records the fitted corners relative
to that crop, the counterclockwise angle, and the new preview dimensions.
The separate `LaneCrop.crop_box` refers to the full **confirmed orientation**;
its well/lane coordinates are translated to the cropped preview. The original
`GelImage` metadata continues to describe the retained full confirmed image.

Review each new capability on your own gels before moving to the next one.
Generated fixtures supplement that visual review. Keep private example images
in the ignored `local-gels/` folder if desired.

### Verification

Generated fixtures cover TIFF decoding, original-byte preservation, PNG preview
pixel values, image proportions, and upload/replace/clear behavior. Crop tests
include known gel masks, illumination gradients, wells and bands, tilted corners,
peripheral dark objects, missing edges, nested rectangles, and uncertainty
fallbacks. Sensitivity regressions cover smooth background shading, local
artifacts, faint/blurred outer rectangles, obscured edges, and physical gel
extensions on each side. Integration tests cover exact 16-bit/RGBA crop pixels,
TIFF orientation,
completed-preview rendering, and detection only once per upload.

- `.venv/bin/python -m pytest -q`: **710 passed, 9 skipped**, including crop,
  image I/O, orientation, well detection, automatic lane refinement, count
  lifecycle, manual review, lane insertion/deletion, annotation validation,
  confirmation/editing, and app workflow tests.
  The nine original-TIFF sample cases require `GEL_ANALYZER_EXAMPLE_TIFF`;
  the saved oriented sample was separately checked across all nine guides.
- `node --test tests/test_well_component.mjs`: **9 passed**, checking scaled and
  offset coordinates, edge clipping, endpoint order, handle sizing, constrained
  border/right-edge movement, independent targeting of narrow-lane handles,
  responsive trash buttons, and mouse/keyboard deletion events.
- `node --test tests/test_annotation_layout.mjs`: **28 passed**, checking native
  lane alignment, both group sets, overlapping groups, changing memberships,
  bold/italic text metrics, lane-based font sizing, edge padding, dense lanes,
  clean composition, and rotated ladder geometry, font sizing to prevent collisions,
  and padding.
- `node --test tests/test_ladder_component.mjs`: **14 passed**, checking manual
  marker placement/correction, keyboard/touch behavior, guarded changes, exact
  coordinate conversion, responsive preview height, and ladder reference photos.
- `node --test tests/test_preview_fit.mjs`: **6 passed**, checking portrait and
  landscape fitting, viewport-height budgets, lane-control gutters, native
  pointer coordinates, and protection against iframe resize feedback.
- `node --test tests/test_rich_text.mjs`: **7 passed**, checking selection
  formatting, text edits, undo snapshots, and compatibility with plain labels.
- `node --test tests/test_workspace_viewport.mjs`: **1 passed**, checking that
  expanded controls are brought into view without resetting scroll on edits.
- `node --test tests/*.mjs`: **65 passed** across the JavaScript suites.
- All five supplied 2749 × 2199 TIFFs now crop successfully (previously two of
  five). Four were used for tuning; one was reserved for validation and
  retained its previously accepted bounds. Visual review confirms the visible
  gel remains enclosed in each crop, and decoded preview pixels exactly match
  the source region. Original file hashes and retained upload bytes are unchanged.
- Browser verification covers TIFF upload and replacement, including previously
  rejected gels, plus the full-frame fallback when a reliable boundary is absent.
  No initial outer-crop controls are displayed.

Manual ladder browser verification follows the four-lane fixture from upload
through the optional offer, preset selection, direct lane selection, placement,
and confirmation. Checks include coincident-x labels, keyboard movement and focus
return, outside-lane rejection, guarded lane changes, removal/cancel restoration,
lane-text reediting, Fit screen and percentage zoom, and emulated touch tap versus
scroll. At 420 × 720, the editor has no horizontal page overflow and retains a
usable image while the page scrolls. At 1200 × 900, markers sit beside the image.
The 498 × 265 gel pixels match the browser-decoded crop exactly; the downloaded
PNG's SHA-256 matches the confirmed canvas PNG. Screenshots are in ignored
`output/playwright/ladder-desktop.png` and `output/playwright/ladder-mobile.png`.

Annotation browser verification covers the actual upload → orientation → lane
review → crop → annotation workflow on the generated four-lane fixture. Lane
and group labels were edited, bold and italic combined, colors changed, both
sets displayed together, an overlapping sparse group added/edited/deleted, and
confirmation followed by reediting. A rapid edit followed by crop revision
retained the last text. At a 420-pixel viewport the 377-pixel editor fits the page,
and native-size preview scrolling stays inside the editor.
The 498 × 265 gel remains the same size within the 1051 × 289 composed image;
its rendered pixels match the browser-decoded crop exactly. The confirmed PNG
matches the clean preview pixel for pixel and contains no editing controls.
Screenshots and a downloaded example are in ignored `output/playwright/annotations-*`.

The earlier simplified editor was checked in a 1200-pixel desktop viewport: the
workspace is 1029 pixels wide (previously about 704), and formatting fits in a
single 52-pixel toolbar above the preview (the current layout moves these controls
into the right workflow panel). Direct typing, combined styles,
caret retention, arrow navigation, in-preview group renaming, collapsed group
creation/membership editing, and **Auto size** were exercised in Chrome.
The four-lane fixture averages 25 pixels per lane and uses a 20-pixel font;
128-pixel manual labels were also verified without the former size cap.

Screen-fit verification used a 600 × 3000 portrait TIFF and a 4000 × 700
landscape TIFF, preserving their native dimensions while fitting both desktop
and shorter browser windows. At 900 × 450, clicks on the scaled well overlay
still mapped to the intended source pixels and detected all four fixture lanes.
The annotation editor had no internal scrolling in Fit screen mode at 420 × 720;
100% zoom retained scrolling. Both group sets survived confirmation and reediting,
and the 869 × 289 confirmed PNG matched the native canvas pixel for pixel.
The toolbar fits the 377-pixel mobile content area without page overflow.

Orientation tests cover both tilt directions, fitted boundaries, distinctive
side markers, unsigned 16-bit values, color channels, and uncertain outlines.
App tests cover staged previews, repeated rotation, confirmation, and resetting
the orientation workflow on upload replacement or clearing.
The browser flow was also checked through Rotate and Orient and Confirm. Both
orientation buttons disappear after acceptance while the result stays visible;
the current layout places confirmation in the right workflow panel. All five
local gel crops produce successful orientation previews.

Well detection adds 51 independent detector cases and 37 app workflow cases.
They cover known well and lane bounds, reversed and sloping guides, unequal
spacing/heights/contrast, outlined walls, close gaps, noise, absent wells,
downstream interference, image edges, unsigned 16-bit values, and pixel
preservation. Workflow tests cover confirmation gating, detection only on
confirmation, reset/edit/retry, immediate confirmation after dragging, pending
component events, and replacement/removal/clearing of the image.

The real Chrome browser flow was verified with a synthetic 16-bit TIFF through
upload, Rotate and Orient, confirmation, reversed-order endpoint clicks,
continuous dragging, responsive resizing, line confirmation, edit, reset,
invalid-line rejection, no-well recovery, rapid confirmation after dragging,
same-filename replacement, and removal. The four synthetic lanes matched the
known well heights and left edges exactly and all ended at image x=520. At a
450-pixel browser viewport, the 520-pixel-wide image displayed at 383 pixels;
pointer mapping preserved its image coordinates. Screenshots and local records
are in the ignored `output/well-verification/` folder.

Manual review adds 61 geometry/crop tests and 37 app workflow tests. These cover
independent bounds, nonoverlap, shared extent constraints, translated geometry,
exact crop pixels including 16-bit byte orders and alpha, stage-specific and
stale events, immediate confirmation after dragging, and revisions from the
original confirmed image. Vertical buffer tests also cover proportional sizing,
the three-pixel minimum, and clipping at the image edges. Replacing or clearing the image and redefining the
well guide clear the review and its crop in every stage.

Chrome verification also exercised border dragging on a scaled 450-pixel
viewport, neighbor limits, right-edge dragging and keyboard adjustment, final
confirmation, back/revise actions, and independently draggable handles on a
one-pixel-high lane. Changing the synthetic lanes to outer y bounds 30–300 and
right x=350 originally produced the unbuffered `(22, 30, 350, 300)` crop,
328 × 270 pixels. The vertical-buffer update adds four pixels on each side for
this 360-pixel-high image: `(22, 26, 350, 304)`, or 328 × 278 pixels. Browser
reconfirmation of the unchanged detected bounds produced 498 × 263 pixels,
including four pixels above and below; see `vertical-buffer.png`. Screenshots
from the initial manual review are in `output/lane-review-verification/`. These
initial review checks preceded the detector improvements described below.

To recreate the browser fixture, run:

```sh
uv run python tests/fixtures/create_well_browser_fixture.py
```

Upload the generated TIFF and follow the workflow above. After confirmation,
use endpoints `(36, 36)` and `(36, 291)` on the 520 × 360 gel. The script prints
the four expected well bounds. Resize the browser and drag each dot before
confirming; use an empty strip around x=100 to exercise failure and retry.

For the **initial well detector**, the existing oriented real gels 1–3 were used for tuning;
gel 4 was reserved for validation after the detector was fixed. Gel 5 was not
used for this feature. The three tuning gels each returned eight candidates
with uncertainty warnings; gel 2 still contains missed or split faint outlines.
The reserved 1910 × 1186 gel, with guide `(180, 70)` to `(170, 1140)`, returned
eight candidates with a low-contrast warning. Visual review found imprecise
boundaries, particularly where only one wall was evident. This is a documented
limitation, **not a successful accuracy validation**. Pixels were unchanged in
all four real-image checks. Counts alone do not establish accurate detection;
more independently annotated real gels are needed to measure performance.

The earlier faint-outline recovery was tuned on the supplied
`20251106_pBRP112-117_midipreps.tif` and checked against the earlier real gels for
regressions. Those reused images are no longer an independent held-out set for
this change. In the app's confirmed 1896 × 1179 orientation, guide `(184, 190)`
to `(174, 1130)` encloses the ladder and six plasmid wells. The detector returns
seven separate lanes across nine nearby guide placements (horizontal offsets
of ±3 pixels and vertical offsets of ±5 pixels). Downstream bands originally
served as alignment checks; the new lane refinement also uses downstream image
evidence, so those reused checks are development regressions rather than
independent validation. Keep guide endpoints near the outside well edges; deep
cuts can still omit a well. Low-contrast warnings remain appropriate, and one
tuning image does not establish general accuracy on new gels.

On the saved 1896 × 1179 oriented sample, all nine guide perturbations still
produce seven lanes. Minimum annotated band-core span coverage improved from
89.8% to 100%, and minimum dark band-core pixel inclusion from 90.9% to 100%.
These measurements cover the existing annotated band windows, not every faint
pixel or a new held-out gel. Geometry and per-lane measurements are in ignored
`output/lane-improvement-validation.json`; a preview is in
`output/lane-improvements-preview.png`.

To rerun the private sample checks without committing image data:

```sh
GEL_ANALYZER_EXAMPLE_TIFF='/path/to/20251106_pBRP112-117_midipreps.tif' \
  uv run pytest -q tests/test_well_sample.py
```

Current Chrome checks cover seven-lane detection on this sample, mouse and
keyboard deletion, automatic placement of an added lane, independent border
dragging, right-edge editing, crop/revise, and deleting every lane followed by
manual recovery. At a 420-pixel viewport, trash targets remain separate and
visible. Screenshots are in `output/playwright/`, including
`final-seven-lanes-desktop.png` and `lane-borders-mobile.png`.

The first supplied 2749 × 2199 example still produces a 1301 × 2013 crop with bounds
`(837, 102, 2138, 2115)`, retaining the gel and a small surrounding margin. Private
gel files and generated previews are excluded from Git.

### Version roadmap

1. TIFF upload and display
2. Automatic outer-gel crop and confirmed orientation (implemented)
3. User-guided automatic well/lane detection, adding/removing lanes, and manual
   height adjustment (implemented); lateral wall correction remains future work
4. Shared right-edge selection and confirmed cropping around lanes (implemented)
5. Ladder-band detection, with manual corrections
6. Ladder presets and manual size markings (implemented; automatic inference
   remains future work)
7. Editable lane labels and two group sets (implemented after cropping)
8. Annotated PNG export (implemented at native crop dimensions); selectable
   pixel dimensions and print-resolution metadata (DPI) remain future work

Build and verify one version at a time. Detection versions will use separate
tuning and validation gels. Named gel profiles will remain separate from ladder
presets; gel profiles remain unimplemented.
