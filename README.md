# Agarose Gel Analyzer

Version 1 is a local viewer for one TIFF gel image (`.tif` or `.tiff`). Upload a file, inspect the full
image at its original proportions, replace it, or clear it. Rotation, cropping,
detection, annotations, and export are planned for later versions. The final
annotated output will remain PNG, with selectable output resolution.

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
2. Inspect the preview and its original pixel dimensions. Large images fit the
   page width; small images are not enlarged.
3. Choose another TIFF to replace the image, even if it has the same filename.
4. Use **Clear image** or the uploader's remove button to start again.

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
The decoder honors TIFF orientation metadata; the app applies no additional
rotation, contrast adjustment, normalization, or cropping. Browser display
scaling does not alter the original TIFF.

## Development and verification

```sh
uv run pytest
```

The Streamlit entry point is `app.py`. `gel_analyzer/image_io.py` handles TIFF
validation independently of Streamlit and returns an immutable `GelImage` with
the original bytes, filename, decoded dimensions, image mode, and a separate PNG
preview. Later image adjustments and analysis must derive from the original
TIFF, keeping this preview separate from the processing source.

Before advancing to Version 2, review your own gel images in the running app.
Generated fixtures check the mechanics but cannot replace that visual review.
Keep private example images in the ignored `local-gels/` folder if desired.

### Version 1 verification

Generated fixtures cover TIFF decoding, original-byte preservation, PNG preview
pixel values, image proportions, and upload/replace/clear behavior. Visual
acceptance using real gel images is still pending; this checkpoint implements
Version 1 only.

- `uv run --locked pytest -q`: 72 passed.
- Browser checks passed for LZW-compressed `.tif`, 16-bit big-endian `.tiff`,
  replacement, invalid-file rejection without a stale preview, and recovery.
- A 960 × 480 TIFF renders as a 704 × 352 PNG preview in the desktop layout,
  preserving its proportions and keeping the original TIFF unchanged.

### Version roadmap

1. TIFF upload and display
2. Orientation and basic cropping
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
