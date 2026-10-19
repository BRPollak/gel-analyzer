# Agarose Gel Analyzer

Current project version: **1.0.0**.

[Download the Mac app](https://github.com/BRPollak/gel-analyzer/releases/tag/v1.0.0)
· [Release notes and installation guide](docs/release-1.0.0.md)

The revised **1.0.0** build removes the Project dropdown and JSON uploads and
adds the [Benjamin Pollak | 2026](https://github.com/BRPollak/gel-analyzer) footer.
It replaces the earlier 1.0.0 downloads without changing the displayed version number.

**The analysis workflow remains under development.** The well/lane detection, manual border adjustment,
right-edge selection, and buffered cropping workflow still needs debugging and
validation on real gels. Automatic well boundaries can be inaccurate; passing
automated tests and synthetic browser checks does not establish end-to-end
correctness. Version 1.0.0 adds desktop packaging; it does not establish a new
scientific accuracy claim.

This local app accepts one TIFF (`.tif` or `.tiff`), PNG (`.png`), or JPEG
(`.jpg` or `.jpeg`) gel image and automatically crops the surrounding background
before displaying it. **Rotate and Orient** straightens, reorients, and tightly
crops the gel for confirmation. Replace or clear the image at any time. After
confirming orientation, define a line through
selected wells to detect their boundaries and horizontal lanes. Review each
lane's height, choose a shared right edge, and confirm to crop the final gel.
Lane review includes deleting unwanted candidates and adding missing lanes.
After cropping, annotate lanes and two independent sets of groups, then confirm
and download as PNG, JPEG, TIFF, or SVG. Optional ladder size labels can be placed
above the gel in the default orientation, or to its left in **Wells at top**.
Automatic band proposals, manual corrections, and ladder-calibrated size estimates
are available in either orientation.

## Install the Mac app

The desktop app requires an **Apple Silicon Mac (M1 or later) running macOS 14
or later**. It opens in its own window and includes Python and its dependencies;
users do not need Terminal, `uv`, or a separate browser. Analysis runs locally
and works offline after installation.

1. Download `Gel-Analyzer-1.0.0-macOS-arm64.dmg` from the
   [v1.0.0 release](https://github.com/BRPollak/gel-analyzer/releases/tag/v1.0.0).
2. Open the DMG and drag **Gel Analyzer.app** onto **Applications**. Eject the DMG,
   then open Gel Analyzer from Applications.
3. This release is ad-hoc signed and **not Apple-notarized**. If macOS blocks the
   first launch because the developer cannot be verified, follow
   **System Settings → Privacy & Security → Open Anyway** for Gel Analyzer, then
   confirm opening it. Only do this for the release you intended to download.
   See [Apple's instructions](https://support.apple.com/en-us/102445).

The matching ZIP is an alternative: extract it and move **Gel Analyzer.app** to
Applications. While the repository is private, coworkers need repository access
and must sign in to GitHub to download its release assets.

Keep your source image and export the results you need before quitting. Editable
analysis exists only in the current session; the app has no Project dropdown or
JSON upload. Exported images and CSV files do not restore an editable session.
Updates are manual: export your results, quit the app, and replace the app in
Applications. Download the revised 1.0.0 assets again if you installed the earlier
1.0.0 build. See the [installation guide](docs/release-1.0.0.md) for release
limitations and validation status.

## Wells at top workflow

At the start of **Rotate and orient**, choose **Workflow orientation → Wells at
top**. This setting remains available during manual outline adjustment and is
independent of the rectangle's rotation controls. **Wells at left**
retains the existing workflow described below. New images use that default.

In Wells at top, automatic/manual preparation only straightens the selected
outline and crops it; it does not apply the default quarter-turn or reflection.
Use **Keep displayed orientation** to accept the initial crop without changing
its pixel orientation. The manual editor marks the edge that will become the
top. Rotate the rectangle explicitly if the photographed gel needs turning.

When the complete outline is unclear but enough straight sides agree on the
tilt, **Rotate and Orient** uses those visible sides to straighten the image.
Three visible sides can establish orientation even when the other two corners
are outside the photograph. The partial-edge search also handles off-center gels
and visible side segments that do not pass through the image center.
This fallback retains the entire initial crop, including areas where a gel edge
is missing, and identifies the supporting sides in the preview. It still requires
confirmation; you can draw a manual outline if you want a tighter crop. Images
without enough consistent edge evidence still open the manual outline editor.

1. Define a **horizontal** guide through the wells, from the left edge of the
   first well to the right edge of the last. Detection examines positions along
   that guide and proposes **vertical** lanes numbered left to right.
2. In **Adjust**, edit each lane's left/right borders, add/delete lanes, and
   then choose a shared **bottom edge**. Cropping retains the upstream margin
   above the wells and buffers to the left/right of the outer lanes. It copies
   the displayed source pixels, including unsigned 16-bit data, without resizing.
3. Lane labels appear **above** their lanes. Choose **Lane label angle**:
   **90° clockwise (bottom faces left)** or **45° clockwise**. Group brackets and
   both group sets also appear above the lanes. Measured text bounds expand the
   canvas to prevent clipping. Lane labels keep a shared endpoint height above
   the gel; if their actual rotated text would overlap, their displayed font size
   is reduced together. Fit screen can make long compositions appear smaller,
   so use Zoom to inspect them.
4. Ladder markers remain attached to their selected lane and exact band position.
   Size labels appear **left of the gel**, horizontally readable and aligned with
   the band Y positions. **Detect bands** proposes positions; choose a size and
   a candidate or click the band manually. Markers can be moved or removed.
5. After confirmation, expand **Review bands and estimate sizes**. Automatic
   proposals follow each lane's migration axis. Edit the lane/position table to
   add, remove, or move bands, then **Apply band edits**. The review overlay and
   its PNG download use the same positions; measurements are downloadable as CSV.

Band sizing fits log10(size) against migration using at least two distinct,
decreasing numeric ladder assignments. DNA sizes are normalized to bp and mass
sizes to kDa. Composite labels such as `500/517 bp` do not establish a numeric
calibration. Estimates are reported only inside the marked migration range,
with fit R² shown for review. This simple profile detector and calibration model
need visual review: faint/merged bands, artifacts, uneven backgrounds, curved
lanes, and nonstandard migration can need correction. There is no new independent
real-gel accuracy claim for this feature.

Returning to **Orient** preserves the existing analysis while a change is staged.
**Return to analysis** cancels it. A changed preview displays a reset warning and
requires **Confirm orientation and reset analysis** before discarding downstream
geometry and annotations; simply changing the selector does not discard them.
Confirming an unchanged preview retains existing work. PNG/JPEG/TIFF and vector
SVG use the same annotation geometry as the preview, including both label angles.

Implementation uses shared migration/cross-lane axis adapters for detection and
editing; persisted coordinates remain the displayed image's XY coordinates.
Temporary analysis-axis views never replace the prepared or exported gel.
Validation covers both orientations with synthetic image fixtures, native pixel
comparisons, browser-component interactions, Streamlit workflow/project tests,
and real-browser checks of both label angles, grouping, and ladder placement.

## Version 0.1.1

- Click completed progress steps to revisit orientation, lane review, or annotations.
  Unchanged orientation preserves existing analysis, and navigation retains lane-label
  and group edits.
- Create groups from lane ranges such as `2-5, 8`, with no lane selected by default,
  All/Clear controls, and a more prominent creation form in a wider annotation panel.
- Start ladder marker labels at 80% of the lane-label font size and shrink nearby
  markers as needed to prevent collisions.
- Add manual lanes near the image bottom by fitting the remaining space or making
  a minimal adjustment to trailing boundaries.
- Hide Streamlit deployment/menu controls and refine the upload card, workflow
  controls, and mobile annotation layout.

## Run from source

Install [uv](https://docs.astral.sh/uv/getting-started/installation/), then run from
this project folder. For the desktop window on macOS:

```sh
uv sync --locked --group desktop --group build
uv run --group desktop python desktop_app.py
```

The desktop shell uses pywebview and the system WebKit engine to display the
existing Streamlit interface. It starts a private server bound to `127.0.0.1`
and stops that server when the app quits. PyInstaller bundles the shell, Python,
analysis code, and local frontend assets into the distributable app.

To build the Apple Silicon app, DMG, ZIP, and checksums in `dist/`:

```sh
uv run --frozen --group desktop --group build python scripts/build_macos.py
```

Use `--app-only` for a build without distribution archives. Build on an Apple
Silicon Mac; this release does not include an Intel build. Developer-ID signing
and Apple notarization are not configured for this release.

For development in a browser:

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

1. Browse for or drop one single-image TIFF, PNG, or JPEG into **Open a gel image**
   on the startup screen. No image-type selection is needed.
2. Wait for the automatic crop, then inspect the preview and its cropped pixel
   dimensions. Large images fit the screen's width and height; small images are
   not enlarged. Scrolling and ordinary edits keep the preview size and page position stable.
3. Click **Rotate and Orient** to fit the gel outline and preview its orientation.
   If only part of the outline is clear, agreeing visible edges can set the tilt
   while retaining the full initial crop. Confirm the preview or adjust manually.
4. If detection fails, draw the gel outline in the manual editor. If the automatic
   result needs adjusting, click **Adjust outline manually**. Drag to draw a
   rectangle, move it from inside, resize its corners, and rotate it with the round
   handle or angle controls. Click **Preview manual orientation**, inspect the
   result, then click **Confirm** in the workflow panel beside the preview.
   **Automatic orientation** is available during manual adjustment and after a
   manual preview. Orientation controls disappear after confirmation, and the
   confirmed image stays displayed.
5. Click **Define wells**. Click at the top of the topmost selected well and the
   bottom of the bottommost selected well, with the line passing through the well
   centers. Either click order works. The dotted line stays vertical; drag either
   dot to adjust its height or move the whole guide sideways. Detection is automatic
   by default. Enter **Number of wells (optional)** to require exactly that many
   wells and lanes. Clear the field to return to automatic counting.
6. Click **Confirm** to detect wells. The result has three actions: **Confirm**
   continues directly to the shared right edge, **Adjust** opens well and lane
   adjustments, and **Back** returns to the guide.
7. In **Adjust**, use the trash button to the right of a lane to delete it, or
   **Add lane** to insert one at the bottom of the guide. Drag each lane's top
   and bottom borders independently, then click **Confirm** to continue.
   **Edit well line** returns to the guide; **Back** returns to the detected
   summary and retains your adjustments. **Adjust** is available even when no
   wells were detected, so you can add lanes manually.
8. Drag the shared right boundary to the farthest point you want to keep.
   Click **Confirm lanes and crop** to create the cropped gel preview.
9. Click a lane label beside the crop and type directly on the preview. The
   formatting controls apply to selected text; with only a caret or no text
   selected, they apply to the whole label. Expand **Create lane groups** in the
   workflow panel to create groups in either set. Click
   **Confirm annotations** to compose the final image. **Edit annotations**
   returns to the saved labels and groups. Choose **Annotate ladder** to add
   manual size labels, or **Skip** to continue. Choose **Image file type** and
   **Resolution (DPI)**, then download the confirmed image, including any ladder
   labels. SVG uses vector annotations and does not need a DPI setting.
10. Expand **Revise analysis** to use **Revise lanes and crop** to adjust the
   existing review, or **Edit well line** to detect again. In the guide editor,
   **Back** leaves the editor and preserves your points; **Define wells** reopens
   them for further adjustment.
11. Open **Change image** to choose another TIFF, PNG, or JPEG, even if it has
   the same filename.
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
The line stays vertical. Selecting the second endpoint retains the first
endpoint's horizontal position. Dragging either endpoint sideways moves the
whole line; Up/Down changes that endpoint's height, and Left/Right moves the
line horizontally. Coincident or too-short selections cannot be confirmed.
The overlay keeps the image's aspect ratio and records
coordinates in confirmed-image pixels, even when the browser preview is scaled.

Detection runs only when you confirm the line. It analyzes narrow strips around
the guide and nearby shifted guides, looking for agreement before recovering a
missed or partial well. Clear wells retain their independently measured sizes
and spacing. A visible well does **not** indicate whether a sample was loaded.
Numbering runs from top to bottom.

The app determines the initial well count automatically when **Number of wells**
is blank. Entering a number requires exactly that many proposed wells and lanes.
The fit uses visible outlines where possible and infers missing positions from
the selected range and neighboring wells. If the image does not support the
whole requested count, the review explains that positions were inferred; check
or adjust them before confirming. A count too large to fit distinct pixel-wide
lanes in the selected range produces an explicit error rather than a different
count. The original image is unchanged.

The detection summary
provides only **Confirm**, **Adjust**, and **Back**. **Confirm** proceeds directly
to the shared right edge. **Adjust** lets you add or delete lanes and edit their
vertical borders, and **Back** lets you revise the guide and detect again.

When the first pass finds weak boundaries, a second pass looks for faint,
spatially coherent well walls and recovers shallow interruptions. It preserves
clear separations from the first pass so stronger neighboring wells are not
merged into one lane. If an endpoint cuts slightly into a well, a bounded search
can complete its outline just beyond the endpoint. Wells
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
the detected well outline stays separate from the expanded lane. Endpoints,
well bounds, centers, and lane
rectangles are session data separate from image pixels. All analysis uses
temporary arrays; the original image bytes and lossless preview, including
16-bit grayscale precision, are preserved.

Editing the guide invalidates the previous result. Detection results freeze the
guide until you choose **Back** or **Edit well line**, including when no wells
are found or boundaries are uncertain. Count-driven results show uncertainty
messages so inferred positions are clear. Other detection uncertainty messages are not
displayed; the outlines remain available for your review and adjustment. An
empty result enables **Adjust** and **Back**, while **Confirm** stays disabled
until at least one lane has been added.
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

**Adjust** opens the well and lane border editor from the detected summary,
including an empty result. If no wells are found, use **Add lane** there to begin
manual recovery, or **Edit well line** to revise the guide and detect again.
**Confirm** on the detected summary skips this optional adjustment step and
opens the shared right-edge editor directly.

In the first step, a trash button at the right of each lane deletes that lane
and renumbers the remaining lanes from top to bottom. **Add lane** places a new
lane at the bottom guide endpoint, or below the last lane when that endpoint
is already occupied. Its starting width and height use the median reviewed well
dimensions; an empty review uses a small initial rectangle. The new well aligns
with the vertical guide, and its placement is kept within the image and shared right
edge. Adjust its borders to cover the intended well and bands. When little
space remains below the last lane, the added lane starts smaller. If the last
lane reaches the image bottom, its lower border moves up one pixel to make
room; a contiguous tail of one-pixel lanes shifts up only as needed. Existing
lanes stay unchanged whenever any space remains below them.
Deleting every lane is allowed; add at least one before confirming. Trash
buttons support Enter and Space as well as clicking.

Drag the arrow handle on each lane's top or bottom border up
or down. The well marker changes height with its lane. A border cannot cross
its opposite border, overlap a neighboring lane, or leave the image. Focus a
handle and use Up/Down for one-pixel adjustments, or hold Shift for ten pixels.
Click **Confirm** to continue. **Back** returns to the detected summary while
retaining your lane additions, deletions, and border adjustments.

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
from the original image and confirmed orientation. **Revise lanes and crop**
reopens the full confirmed image with your previous adjustments, so even an
expanded revision recovers the original pixels and never crops an earlier crop.
Changing the image/orientation or editing the well guide clears this review and
its final crop. Late events from earlier stages cannot restore old geometry.

### Lane annotations

The app uses a wide workspace. **Change image** opens the replacement and clear
controls; optional annotation settings and analysis revisions can be expanded
when needed, leaving more room for the gel.

Crop confirmation opens an annotation editor using the crop's translated lane
coordinates. Click a right-aligned Arial label beside the gel to edit its text
in place. Select a substring to change just its bold, italic (including both
together), or color formatting. Choose from eight color presets: black, gray,
red, orange, yellow, green, blue, and purple. The toolbar shows whether formatting
applies to **selected text** or the **whole label**, and keeps the highlighted
substring selected when you click a color or style. With no text range selected,
those controls format the whole label. Mixed formatting is retained during text edits, layout
changes, confirmation, and all export formats. There is no separate lane-text form.
Formatting controls stay outside the final image; the selected label stays
highlighted while you use them. Group creation and membership controls are in
the **Create lane groups** section at the top of the wider workflow panel.
New groups start with no lanes selected. Enter lane numbers or ranges such as
`2-5, 8`, use **All lanes** / **Clear**, or expand **Choose individual lanes**
for a compact picker. The **Create group** button keeps the form open with empty
fields for the next group. Existing groups can be renamed in the form and their
memberships update as you enter valid lane numbers.

The progress buttons at the top return to completed analysis steps. **Define
lanes** reopens the boundaries, while **Annotate** returns to the lane-label editor.
Returning to **Orient** reviews the existing orientation; **Return to analysis**
keeps the later work. Confirming a changed orientation resets downstream geometry,
while reconfirming the unchanged orientation preserves it. Unreached steps remain
disabled so required confirmations cannot be skipped.

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

**Confirm annotations** saves the clean preview and its vector annotation geometry.
Choose PNG, JPEG, TIFF, or SVG under **Image file type** before downloading.
PNG and TIFF preserve the display image losslessly; JPEG uses lossy compression.
The **Resolution (DPI)** choices depend on the selected format and set real print
resolution metadata without changing pixel dimensions or resampling the gel.
SVG embeds the native-resolution gel image and keeps labels, brackets, and ladder
leaders as vectors; its DPI control is disabled. Text-box borders, selection
indicators, and editing controls are excluded. **Edit annotations** keeps every
label, format, and group. Revising crop bounds retains annotations; deleting a
lane removes its label and group membership, and adding a lane creates a new
label. Replacing the image, redefining the well guide, or restarting detection
clears annotations along with the lane geometry.

Composition uses the browser's Arial font and display-color canvas (8-bit RGBA),
not the original 16-bit grayscale data. The original image and lossless crop remain
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
horizontal position. Their normal Arial size is 80% of the current lane-label
font size, including any manual font changes. When nearby labels would overlap, all ladder labels
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
confirmed image and every download format. Raster exports use the clean canvas;
SVG uses the same positions and font styles with the embedded gel image.

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
If two corners are cut off but three sides remain visible, their observed
segments determine the rotation instead. The app retains the full initial crop
on an expanded canvas rather than estimating the missing crop boundary. This
fallback works in both workflow orientations, including off-center gels and
sides close to the photograph's edges.

The final edge positions are: original left at the top, original right at the
bottom, original top at the left, and original bottom at the right. This is a
rotation and reflection, without perspective correction.

The transformed image remains a pending preview until **Confirm** accepts it as
the current gel. A successful automatic preview offers confirmation and manual
adjustment. The manual editor and a completed manual preview also offer
**Automatic orientation**, which starts again from the first crop so
transformations never accumulate.
Replacing or clearing the upload resets this workflow. If the outline cannot be
estimated reliably, the app opens a manual outline editor on the first crop.
**Draw outline manually** also opens this editor before running detection, and
**Adjust outline manually** opens it with the current outline after a successful
automatic or manual preview.

Press and drag across the image to draw a rectangle in either direction. Drag
inside to move it, use its corner handles to resize it, and drag the round handle
to rotate it. The angle field and quarter-turn buttons also adjust rotation.
The gold edge becomes the top of the oriented image, making the subsequent
rotation and flip visible in the selection. **Draw new rectangle** clears the
selection so it can be replaced. The rectangle must stay inside the image and
have sides of at least two pixels. Out-of-bounds rotations keep the previous
selection and explain how to make room.

The editor always shows the initial crop, even after automatic rotation, so
edges and tilt can be corrected against the original pixels. **Preview manual
orientation** bypasses edge detection and applies the same rotation, flip, and
crop using the selected rectangle. Every preview samples that initial crop
once; editing never repeatedly resamples a previous preview. **Cancel manual
adjustment** returns to the previous preview, and **Retry automatic detection**
discards the manual selection and runs detection again. A preview must still be
confirmed before defining wells.

Complete-outline fitting prefers one roughly centered, opaque gel with visible
outer edges and a modest tilt. When that fit fails, the partial-edge search scans
the full frame for consistent, visible side segments. Competing faint or blurred
outer edges do not establish a tight crop; without a reliable shared angle, the
app opens manual adjustment.

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
the finished crop (or the full-frame fallback) is then shown. The original image
is always retained unchanged in session memory.

An invalid selection clears the previous preview and shows an error. Valid
unsigned grayscale (including 16-bit in either byte order), 8-bit RGB/RGBA,
palette, and bilevel TIFFs are supported. Common TIFF compression such as LZW
and deflate is supported. Multipage TIFFs, floating-point/signed samples, and
high-bit-depth color TIFFs are rejected explicitly rather than selecting a page
or silently reducing precision. PNG supports common 8-bit grayscale, color,
alpha, palette, and bilevel images, plus unsigned 16-bit grayscale. Animated or
multiframe PNGs and 16-bit color PNGs are rejected. JPEG supports grayscale and
RGB images; CMYK JPEGs are converted to RGB for the preview. The standard
Streamlit upload limit is 200 MB; Pillow's decompression protection also rejects
exceptionally large decoded images.

Uploaded bytes are retained unchanged in the current browser session. The app
does not save images to disk or send them to an external processing service.
Refreshing the page or ending the session clears the image.
A separate lossless PNG is generated for the browser, preserving
unsigned 16-bit grayscale values. Using a PNG preview avoids additional JPEG
compression; it cannot recover detail already lost in a JPEG source.
The decoder honors TIFF orientation metadata and PNG/JPEG EXIF orientation once,
before cropping. The first automatic crop copies pixels directly from the
decoded source without contrast adjustment, normalization, or resampling.
Rotate and Orient resamples only for straightening;
it preserves 16-bit grayscale precision and does not adjust contrast. Browser
display scaling and orientation never alter the original uploaded bytes.

## Development and verification

```sh
uv run pytest
node --test tests/test_well_component.mjs
node --test tests/test_annotation_layout.mjs
node --test tests/test_preview_fit.mjs
```

The JavaScript unit tests require Node.js 18 or newer. Running the app itself
requires no Node installation or frontend build.

The Streamlit entry point is `app.py`. `gel_analyzer/image_io.py` validates TIFF,
PNG, and JPEG through `load_image` independently of Streamlit and returns an
immutable `GelImage` with the original bytes, filename, decoded dimensions, mode,
crop bounds, and cropped PNG preview. `load_tiff` remains available for callers
that require TIFF input.
`gel_analyzer/auto_crop.py` detects edges on a reduced grayscale
analysis copy; normalization is confined to that temporary copy.
`gel_analyzer/orientation.py` fits and transforms the gel rectangle, then flips
and crops the image. `orient_gel_image` stages an immutable replacement from the
lossless first-crop PNG; confirmation makes it the current `GelImage`.
`gel_analyzer/orientation_ui.py` manages manual review and preview staging;
`gel_analyzer/orientation_component.py` serves its local SVG rectangle editor.
Manual selection events use image coordinates with session tokens and revisions
to reject stale geometry after retries, cancellation, or upload replacement.
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
`annotations.py` validates label, group, and PNG events. `annotation_exports.py`
validates inert SVG geometry, embeds the current crop, and produces raster files
with the selected DPI metadata. The local `annotation_component_frontend/` editor
measures and draws the same canvas for the live preview and raster downloads;
its SVG serializer uses that geometry for vector annotations. Token/revision
checks guard stale events.
Structural edits rotate the component token so delayed events cannot restore
deleted lanes or target an outdated lane number. The overlay's `lane_review.mjs`
handles trash buttons and axis-constrained border and extent dragging with the
shared coordinate helpers.

`crop_box` uses Pillow's half-open `(left, top, right, bottom)` coordinates in
the full decoded image after input orientation metadata is applied. `width` and
`height` remain the source dimensions; `preview_width` and `preview_height`
describe the current preview. Before orientation, bounds are rounded outward when mapped from
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

- `.venv/bin/python -m pytest -q`: **868 passed, 9 skipped**, including crop,
  image I/O, orientation, well detection, automatic lane refinement, count
  lifecycle, manual review, lane insertion/deletion, annotation validation,
  confirmation/editing, backward progress navigation, and app workflow tests.
  The nine original-TIFF sample cases require `GEL_ANALYZER_EXAMPLE_TIFF`;
  the saved oriented sample was separately checked across all nine guides.
- `node --test tests/*.mjs`: **100 passed** across the browser component suites below.
- `node --test tests/test_annotation_groups.mjs`: **11 passed**, checking empty
  defaults, lane ranges, All/Clear, individual selections, keyboard creation,
  group editing, rich-text preservation, and invalid-input handling.
- `node --test tests/test_well_component.mjs`: **11 passed**, checking scaled and
  offset coordinates, edge clipping, endpoint order, handle sizing, constrained
  border/right-edge movement, independent targeting of narrow-lane handles,
  responsive trash buttons, and mouse/keyboard deletion events.
- `node --test tests/test_annotation_layout.mjs`: **29 passed**, checking native
  lane alignment, both group sets, overlapping groups, changing memberships,
  bold/italic text metrics, lane-based font sizing, edge padding, dense lanes,
  clean composition, and rotated ladder geometry, font sizing to prevent collisions,
  and padding.
- `node --test tests/test_ladder_component.mjs`: **14 passed**, checking manual
  marker placement/correction, keyboard/touch behavior, guarded changes, exact
  coordinate conversion, responsive preview height, and ladder reference photos.
- `node --test tests/test_preview_fit.mjs`: **7 passed**, checking portrait and
  landscape fitting, viewport-height budgets, lane-control gutters, native
  pointer coordinates, and protection against iframe resize feedback.
- `node --test tests/test_rich_text.mjs`: **10 passed**, checking selection
  formatting, mixed-label caret toggles, keyboard toolbar focus, text edits,
  undo snapshots, and compatibility with plain labels.
- `node --test tests/test_orientation_component.mjs`: **15 passed**, checking
  rectangle geometry, pointer and keyboard controls, cancellation, and stale events.
- `node --test tests/test_workspace_viewport.mjs`: **3 passed**, checking header
  and control space, resizing, and stable preview size and scrolling during edits.
- `node --test tests/*.mjs`: **89 passed** across the JavaScript suites.
- All five supplied 2749 × 2199 TIFFs now crop successfully (previously two of
  five). Four were used for tuning; one was reserved for validation and
  retained its previously accepted bounds. Visual review confirms the visible
  gel remains enclosed in each crop, and decoded preview pixels exactly match
  the source region. Original file hashes and retained upload bytes are unchanged.
- Browser verification covers TIFF upload and replacement, including previously
  rejected gels, plus the full-frame fallback when a reliable boundary is absent.
  No initial outer-crop controls are displayed.

#### Earlier validation records

These records describe earlier development snapshots. References to removed
controls, sloping guides, displayed uncertainty warnings, and per-feature test
counts are historical; the current workflow is described in **Use** above.

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

1. TIFF, PNG, and JPEG upload and display (implemented)
2. Automatic outer-gel crop and confirmed orientation (implemented)
3. User-guided automatic well/lane detection, adding/removing lanes, and manual
   height adjustment (implemented); lateral wall correction remains future work
4. Shared right-edge selection and confirmed cropping around lanes (implemented)
5. Migration-axis band proposals and manual corrections (implemented; review
   remains necessary, and real-gel accuracy validation is ongoing)
6. Ladder presets, manual size markings, and log-linear calibration within the
   marked range (implemented; ladder size assignment remains explicit)
7. Editable lane labels and two group sets (implemented after cropping)
8. Annotated PNG, JPEG, TIFF, and SVG export (implemented). Raster exports retain
   native pixel dimensions with selectable print-resolution metadata (DPI); SVG
   keeps annotations as vectors and embeds the raster gel. Resampling to selectable
   pixel dimensions remains future work.

Build and verify one version at a time. Detection versions will use separate
tuning and validation gels. Named gel profiles will remain separate from ladder
presets; gel profiles remain unimplemented.
