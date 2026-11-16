# Annotation focus investigation

Users reported that typing in labels loses the cursor and requires another
click. This concerns focus loss, not the desktop window closing.

## Cause and correction

The annotation editor posts its current state every 120 ms while editing.
Each accepted update reruns the Streamlit page. Previously, `app.py` issued
`st.empty()` at the preview's location before replacing it with a container.
If those updates were sent separately, the browser removed the focused editor
iframe. Keeping the component key unchanged could not preserve a removed DOM
node. Streamlit's message queue explicitly permits this split; coalescing the
two updates is only an optimization.

Windows desktop reruns now use a stable, keyed preview container. The native
Windows backend sets an explicit runtime marker; both that marker and the
Windows platform are required to enable the fix. Mac and ordinary browser
launches retain their previous behavior. Image replacement and orientation
processing retain the clearing placeholder because their old preview must be
removed intentionally.

Separately, Windows desktop label keyboard commands now leave composition
events to the input method. Enter and arrow keys used to choose IME candidates
must not blur the label or navigate to another label. The same explicit
Windows desktop flag gates this correction, preserving Mac keyboard behavior.

## Evidence

- A regression test captured both autosave reruns clearing the editor's
  ancestor before the fix. The same test passes with the stable container.
- In a temporary copy of the actual app, a 250 ms delay immediately after
  creating the preview slot forced separate delivery of the updates. Real
  browser typing lost focus after the first `W` before the fix.
- With the same delay after the fix, 30 characters across two labels retained
  focus, text, caret position, and iframe identity. Tab and Shift+Tab worked.
  PNG, JPEG, TIFF, and SVG exports passed.
- The normal local browser also passed the typing and export checks. The
  targeted Python suite passed 157 tests; the JavaScript suite passed 31.

The original timing reproduction ran in Chromium on macOS. The fixes were
then restricted to Windows desktop, built into a Windows installer, and
validated on Windows Server 2022 and 2025. The prevalence of the original
issue among users has not been measured. See
[the Windows validation report](windows-validation-2026-11-16.md) for the
source suites, native test results, installer identity, and remaining limits.

## Regression coverage

`tests/test_annotation_app.py` inspects uncoalesced outgoing messages so the
container race is caught without relying on machine speed.
`tests/test_label_keyboard.mjs` covers composition and ordinary shortcuts.
`scripts/smoke_windows.py` now types using raw keyboard events across autosave
updates, without refocusing labels between characters. Both standalone
Chromium and the normal-close WebView2 smoke path use this check. WebView2
inspection uses CDP; physical Windows keyboard input still needs a device check.
