# Agarose Gel Analyzer

Current version: **0.0.1** (Git tag: `v0.0.1`).

This local app accepts one TIFF gel image (`.tif` or `.tiff`) and automatically
crops the surrounding background before displaying it. **Rotate and Orient**
straightens, reorients, and tightly crops the gel for confirmation. Replace or
clear the image at any time. Lane/band detection, annotations, and export remain
later steps. Final annotated output will be PNG with selectable resolution.

## Run locally

Install [uv](https://docs.astral.sh/uv/getting-started/installation/), then run from
this project folder:

```sh
uv sync --locked
uv run streamlit run app.py
```

The project uses Python 3.12 in an isolated `.venv`. If needed, uv downloads the
interpreter automatically. Open <http://127.0.0.1:8501>. Press Ctrl+C in the
terminal to stop the server.

## Use

1. Browse for or drop one single-image TIFF into **Choose a gel image**.
2. Wait for the automatic crop, then inspect the preview and its cropped pixel
   dimensions. Large images fit the page width; small images are not enlarged.
3. Click **Rotate and Orient** to fit the gel outline and preview its orientation.
4. Inspect the result, then click **Confirm** at the bottom left of the preview.
   Both orientation buttons disappear, and the confirmed image stays displayed.
5. Choose another TIFF to replace the image, even if it has the same filename.
6. Use **Clear image** or the uploader's remove button to start again.

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
encloses the tilted gel's corners. There are no crop adjustment controls.

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
```

The Streamlit entry point is `app.py`. `gel_analyzer/image_io.py` handles TIFF
validation independently of Streamlit and returns an immutable `GelImage` with
the original bytes, filename, decoded dimensions, mode, crop bounds, and cropped
PNG preview. `gel_analyzer/auto_crop.py` detects edges on a reduced grayscale
analysis copy; normalization is confined to that temporary copy.
`gel_analyzer/orientation.py` fits and transforms the gel rectangle, then flips
and crops the image. `orient_gel_image` stages an immutable replacement from the
lossless first-crop PNG; confirmation makes it the current `GelImage`.

`crop_box` uses Pillow's half-open `(left, top, right, bottom)` coordinates in
the full decoded image after TIFF orientation is applied. `width` and `height`
remain the source dimensions; `preview_width` and `preview_height` describe the
current preview. Before orientation, bounds are rounded outward when mapped from
analysis to source pixels. After orientation, `crop_box` still records the first
crop in source coordinates; `orientation` records the fitted corners relative
to that crop, the counterclockwise angle, and the new preview dimensions.

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

- `.venv/bin/python -m pytest -q`: 212 passed, including crop, image I/O,
  orientation, and app tests.
- All five supplied 2749 × 2199 TIFFs now crop successfully (previously two of
  five). Four were used for tuning; one was reserved for validation and
  retained its previously accepted bounds. Visual review confirms the visible
  gel remains enclosed in each crop, and decoded preview pixels exactly match
  the source region. Original file hashes and retained upload bytes are unchanged.
- Browser verification covers TIFF upload and replacement, including previously
  rejected gels, plus the full-frame fallback when a reliable boundary is absent.
  No crop controls are displayed.

Orientation tests cover both tilt directions, fitted boundaries, distinctive
side markers, unsigned 16-bit values, color channels, and uncertain outlines.
App tests cover staged previews, repeated rotation, confirmation, and resetting
the orientation workflow on upload replacement or clearing.
The browser flow was also checked through Rotate and Orient and Confirm: the
confirmation control appears below the image at the left, and both orientation
buttons disappear after acceptance while the result stays visible. All five
local gel crops produce successful orientation previews.

The first supplied 2749 × 2199 example still produces a 1301 × 2013 crop with bounds
`(837, 102, 2138, 2115)`, retaining the gel and a small surrounding margin. Private
gel files and generated previews are excluded from Git.

### Version roadmap

1. TIFF upload and display
2. Automatic outer-gel crop and confirmed orientation (implemented)
3. Automatic well and lane detection, with manual corrections
4. Automatic cropping around selected lanes
5. Ladder-band detection, with manual corrections
6. Ladder presets and size markings
7. Editable lane labels
8. Finished PNG export of the adjusted and annotated image, with selectable
   pixel dimensions and print-resolution metadata (DPI)

Build and verify one version at a time. Detection versions will use separate
tuning and validation gels. Named gel profiles will remain separate from ladder
presets; those systems are not implemented in Version 1.
