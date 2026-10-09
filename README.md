# Agarose Gel Analyzer

This local app accepts one TIFF gel image (`.tif` or `.tiff`) and automatically
crops the surrounding background before displaying it. Replace or clear the
image at any time. Rotation, lane/band detection, annotations, and export remain
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
3. Choose another TIFF to replace the image, even if it has the same filename.
4. Use **Clear image** or the uploader's remove button to start again.

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
The decoder honors TIFF orientation metadata. Cropping copies pixels directly
from the decoded source without applying contrast adjustment, normalization,
resampling, or additional rotation. Browser display scaling does not alter the
original TIFF.

## Development and verification

```sh
uv run pytest
```

The Streamlit entry point is `app.py`. `gel_analyzer/image_io.py` handles TIFF
validation independently of Streamlit and returns an immutable `GelImage` with
the original bytes, filename, decoded dimensions, mode, crop bounds, and cropped
PNG preview. `gel_analyzer/auto_crop.py` detects edges on a reduced grayscale
analysis copy; normalization is confined to that temporary copy. Later image
adjustments and analysis must derive from the original TIFF.

`crop_box` uses Pillow's half-open `(left, top, right, bottom)` coordinates in
the full decoded image after TIFF orientation is applied. `width` and `height`
remain the source dimensions; `preview_width` and `preview_height` describe the
crop. Bounds are rounded outward when mapped from analysis to source pixels.

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

- `uv run --locked pytest -q`: 158 passed.
- All five supplied 2749 × 2199 TIFFs now crop successfully (previously two of
  five). Four were used for tuning; one was reserved for validation and
  retained its previously accepted bounds. Visual review confirms the visible
  gel remains enclosed in each crop, and decoded preview pixels exactly match
  the source region. Original file hashes and retained upload bytes are unchanged.
- Browser verification covers TIFF upload and replacement, including previously
  rejected gels, plus the full-frame fallback when a reliable boundary is absent.
  No crop controls are displayed.

The first supplied 2749 × 2199 example still produces a 1301 × 2013 crop with bounds
`(837, 102, 2138, 2115)`, retaining the gel and a small surrounding margin. Private
gel files and generated previews are excluded from Git.

### Version roadmap

1. TIFF upload and display
2. Automatic outer-gel crop (implemented); orientation controls remain future work
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
