# Gel Analyzer icon

`GelAnalyzer.png` is the canonical artwork. The pale glass gel, thin teal rim,
and dark bands preserve the electrophoresis motif with a lighter, modern finish.
It replaces the original flat SVG. The `GelAnalyzer-cartoon` files are separate,
unused concept artwork.

Regenerate the macOS icon on a Mac with
`python scripts/generate_macos_icon.py`, then regenerate the Windows icon with
`python scripts/generate_windows_icon.py` on any platform. Both scripts use the
project's Pillow environment, preserve transparency, and read the same PNG.

Artwork created with the built-in image generation tool, editing the previous
light-gel icon. The final generation prompt was:

Use case: style-transfer. Asset type: production macOS and Windows app icon for Gel Analyzer, a modern scientific analysis application. Input image: edit target, the existing icon. Redesign the visual styling substantially while retaining its recognizable gel electrophoresis motif and light-gel / dark-band polarity. Create a beautifully refined contemporary desktop icon with a smooth softly rounded square silhouette and a pale icy-blue glass/ceramic gel face. Remove the heavy dark navy frame and the dated thick outlines around individual bands; use a very slender deep teal rim, subtle dimensional edge, extremely restrained soft shading and a clean luminous face. The gel should fill most of the rounded tile. Keep an orderly four-lane composition: four small loading wells across the top, six regularly spaced short ladder bands in the left lane, and three clearly separated short sample bands at differing heights in each of the other three lanes. All bands are dark ink teal with crisp smooth rounded ends and clear strong contrast; no neon glowing bands. Use generous precise spacing, restrained depth, strong silhouette, impeccable optical balance, a pale blue-white surface with soft cool aqua shading near the bottom edge. View straight-on, no isometric tilt. The icon should be immediately legible at 32 pixels, with enough richness at 1024 pixels to feel like premium contemporary scientific software. Render one centered finished icon, NOT a presentation or mockup. The tile occupies roughly 84% of a square canvas, evenly padded on all sides. Outside the rounded tile and its very subtle contact shadow must be actual alpha transparency. No text, letters, numbers, badges, sparkles, atoms, microscopes, DNA helix, pencils, extra symbols, scenic background, or watermark.
