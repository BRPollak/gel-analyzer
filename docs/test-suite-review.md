# Test suite review — October 19, 2026

Reviewed all 37 Python test modules and eight JavaScript test modules. The
cleanup changes tests and documentation only; existing application changes
were left in place.

| Area | Cases before | Cases after | Main changes |
| --- | ---: | ---: | --- |
| Crop, orientation, wells, and lane geometry | 636 | 577 | Combine repeated fits; remove crop scenarios already checked by crop-plus-orientation tests; reduce independent parameter products. |
| Annotation, ladders, exports, bands, and projects | 319 | 287 | Combine editing/confirmation/reopening lifecycles and rejected-event checks; trim duplicate validation representatives. |
| Upload, app navigation, lane workflows, image I/O, and desktop | 341 | 250 | Share the well/lane harness; combine upload lifecycle checks and invalid-event sequences; remove duplicate UI smoke checks. |
| JavaScript components and layout | 117 | 107 | Combine formatting, bracket, ladder-reference, and viewport checks; remove arbitrary styling and source-string assertions. |
| **Total** | **1,413** | **1,221** | **192 fewer collected cases (13.6%).** |

Counts include parameterized cases and nine optional private-image cases. A
lower case count does not imply that each removed case lost its assertions:
many now run together within one behavioral test, avoiding repeated app setup.

## Consolidation decisions

- The well and lane app suites now use the function-scoped `well_workflow`
  fixture in `tests/conftest.py`. Browser events and detector calls remain
  observable, while real app callbacks still execute.
- Upload, replacement, clear, removal, and reupload share one lifecycle test
  covering TIFF, PNG, JPEG, same-name replacement, and mixed-case suffixes.
  Supported uploader extensions are checked together. Decoder tests retain
  the format-specific pixel and corruption checks.
- Rejected well, lane, annotation, and ladder events reuse an editor. Each
  iteration checks that both data and revision remain unchanged, so one bad
  event cannot cause later cases to pass merely by making them stale.
- Annotation edit/confirm/reopen, ladder draft/navigation/confirmation, and
  band add/invalid-edit/move/remove now follow coherent lifecycles. Band
  rejection is checked against populated data rather than an empty table.
- Orientation fitting and transformation use the same generated image and
  retain both sets of assertions. Faint outer edges and blurred extensions
  remain covered by combined tests that first check crop enclosure and then
  the accepted orientation.
- Independent dimensions use representative combinations: image mode versus
  aspect ratio, shared numeric validation versus selection field, and source
  format versus project orientation. Distinct values, transform directions,
  and error categories remain represented.
- Removed tests of dataclass immutability, exception inheritance, exact footer
  text, a fixed ladder leader length, and an unrelated object's identity after
  project loading. These mostly asserted library behavior, presentation
  choices, or state that the operation never received. Viewport tests now
  check scroll preservation directly instead of inspecting CSS/JS strings.

## Coverage retained deliberately

The review retained the scientific and integrity regressions: native 16-bit
values and endian/codec combinations, exact crop pixels, EXIF orientation,
one-byte TIFF truncation, unsupported precision, corrupted/animated images,
noise seed sweeps, faint and ambiguous edges, exact requested well counts,
fractional boundaries, one-pixel lanes, overlap prevention, and both migration
axes. The optional real-image cases still require
`GEL_ANALYZER_EXAMPLE_TIFF`.

App tests still distinguish pending browser edits from already processed
events, stale tokens from revisions, draft from confirmed state, and unchanged
from changed orientation. The real count-constrained workflow, wells-at-top
workflow, partial-orientation navigation, boundary generation, and boundary
project restoration suites were retained because they exercise integration
that isolated geometry tests cannot establish.

SVG active-content rejection, lossless embedded crops, raster DPI and alpha,
project validation, rich-text integrity, marker membership, keyboard/pointer
interactions, and narrow-lane hit targets remain covered. Desktop tests retain
real startup, occupied-port retry, timeout/early-exit cleanup, parent death,
local-only configuration, and shutdown checks.

## Verification

Run the complete suites from the repository root:

```sh
.venv/bin/python -m pytest -q
node --test tests/*.mjs
```

Desktop integration tests require permission to bind local loopback ports.
The initial sandboxed baseline had four permission-related failures, 1,283
passes, and nine private-image skips; those failures were not removed or
converted into skips as part of this cleanup.

Final verification with loopback access: **1,105 Python tests passed and nine
private-image cases skipped in 61.03 seconds; all 107 JavaScript tests passed.**
The final one-byte TIFF truncation checks also passed separately for all three
codecs. `git diff --check` passed. Timing is a local observation, not a benchmark:
the baseline and final runs differed in sandbox permissions.
