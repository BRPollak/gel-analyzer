# Agarose Gel Analyzer

Version 1 is a local viewer for one PNG gel image. Upload a file, inspect the full
image at its original proportions, replace it, or clear it. Rotation, cropping,
detection, annotations, and export are planned for later versions.

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

1. Browse for or drop one static PNG into **Choose a gel image**.
2. Inspect the preview and its original pixel dimensions. Large images fit the
   page width; small images are not enlarged.
3. Choose another PNG to replace the image, even if it has the same filename.
4. Use **Clear image** or the uploader's remove button to start again.

An invalid selection clears the previous preview and shows an error. Valid
grayscale (including 16-bit), RGB, RGBA, and palette PNGs are supported. Animated
PNGs are rejected. The standard Streamlit upload limit is 200 MB; Pillow's
decompression protection also rejects exceptionally large decoded images.

Uploaded bytes are retained unchanged in the current browser session. The app
does not save images to disk or send them to an external processing service.
Refreshing the page or ending the session clears the image. The preview applies
no contrast adjustment, normalization, rotation, or cropping. Browser display
scaling does not alter the stored source image.

## Development and verification

```sh
uv run pytest
```

The Streamlit entry point is `app.py`. `gel_analyzer/image_io.py` handles PNG
validation independently of Streamlit and returns an immutable `GelImage` with
the original bytes, filename, dimensions, and image mode.

Before advancing to Version 2, review your own gel images in the running app.
Generated fixtures check the mechanics but cannot replace that visual review.
Keep private example images in the ignored `local-gels/` folder if desired.

### Version 1 verification record

- `uv run --locked pytest -q`: 41 passed (36 loader cases and 5 Streamlit
  integration cases).
- Browser checks passed with generated landscape, portrait, square, transparent,
  and 16-bit grayscale PNGs. A 960 × 480 image displayed at 704 × 352 on desktop
  and 358 × 179 in a 390-pixel-wide viewport; smaller images were not enlarged.
- Same-filename replacement, invalid replacement without a stale preview,
  clearing, and reuploading passed in the browser. Automated checks also cover
  uploader removal and a 2000 × 1 image that previously triggered Streamlit's
  implicit preview resampling.
- Visual acceptance using real gel images is still pending. This checkpoint
  implements Version 1 only.

### Version roadmap

1. Upload and display
2. Orientation and basic cropping
3. Automatic well and lane detection, with manual corrections
4. Automatic cropping around selected lanes
5. Ladder-band detection, with manual corrections
6. Ladder presets and size markings
7. Editable lane labels
8. Finished PNG export

Build and verify one version at a time. Detection versions will use separate
tuning and validation gels. Named gel profiles will remain separate from ladder
presets; those systems are not implemented in Version 1.
