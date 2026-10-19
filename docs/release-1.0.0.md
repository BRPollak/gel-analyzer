# Gel Analyzer 1.0.0

Version 1.0.0 packages Gel Analyzer as a Mac app with its own window. Python,
Streamlit, the analysis code, and the local image editors are included, so users
do not need to install Python or use Terminal. The interface uses pywebview and
macOS WebKit; processing stays on the Mac and works offline after installation.

The release retains TIFF, PNG, and JPEG input; both workflow orientations;
lane/group/ladder annotations; PNG, JPEG, TIFF, and SVG exports; band-review PNG
and measurement CSV exports.

## Revised 1.0.0 build

This rebuild removes the Project dropdown and JSON uploads and adds a small
**Benjamin Pollak | 2026** footer with a [GitHub](https://github.com/BRPollak/gel-analyzer)
link that opens in the default browser. The version remains
**1.0.0**; the DMG, ZIP, and checksums replace the earlier 1.0.0 assets. If you
already installed that version, download it again and replace the installed app.

## Download and install

Requires **Apple Silicon (M1 or later), macOS 14 or later**. Intel Macs are not
included in this release.

Get the files from the [v1.0.0 GitHub release](https://github.com/BRPollak/gel-analyzer/releases/tag/v1.0.0):

- `Gel-Analyzer-1.0.0-macOS-arm64.dmg`: open it, drag **Gel Analyzer.app** onto
  **Applications**, eject the DMG, then launch from Applications.
- `Gel-Analyzer-1.0.0-macOS-arm64.zip`: extract it and move **Gel Analyzer.app** to
  Applications, then launch it there.
- `SHA256SUMS`: checksums for the downloadable DMG and ZIP.

While the repository is private, coworkers must have repository access and sign
in to GitHub to download these assets. The app itself does not require a GitHub
account once installed.

This build is **ad-hoc signed, not signed with an Apple Developer ID, and not
Apple-notarized**. If macOS blocks the first launch because the developer cannot
be verified, attempt to open the app once, then open **System Settings → Privacy
& Security** and select **Open Anyway** for Gel Analyzer. Confirm the next prompt.
Only grant this exception for the release you intended to download. Managed Macs
may require assistance from their administrator. See
[Apple's guidance](https://support.apple.com/en-us/102445).

## Export results and update

Keep the original image and export the results you need before quitting. Editable
analysis exists only in the current session and is lost when the app closes.
The app no longer exposes project save/open controls or accepts JSON uploads.
Exported images and CSV files preserve outputs, not an editable session.

Updates are manual. Export your results, quit Gel Analyzer, download the updated
assets, and replace **Gel Analyzer.app** in Applications. Keep your source images
and exported files in a separate folder. The same replacement procedure applies
to this rebuild even though the displayed application version remains 1.0.0.

## Limitations

Desktop packaging does not establish scientific accuracy. Well/lane detection,
manual borders, right-edge selection, and buffered cropping still need debugging
and validation on real gels. Inspect automatic results and correct them before
using the outputs. Existing automated and synthetic checks do not establish
end-to-end correctness on real experiments.

Band proposals and ladder-calibrated sizes require visual review. Faint or merged
bands, artifacts, uneven backgrounds, curved lanes, and unusual migration can
need correction. Estimates are limited to the marked calibration range. The
[README](../README.md) describes the supported input formats, pixel preservation,
export behavior, and scientific limitations in more detail.

## Release validation

The revised packaged app was checked on **Apple Silicon, macOS 26.6.2**:

- All 1,180 Python tests passed (9 private-image tests skipped), and all 113
  JavaScript tests passed. The lockfile is unchanged at version 1.0.0.
- The Project dropdown and JSON upload controls are absent.
- The footer renders on the start screen and after importing a 16-bit PNG.
- The GitHub link opens the repository in the default browser while preserving
  the local app window and analysis session.
- The quit dialog reminds users to export results before closing.

The records below describe the original desktop build at commit `a9e3fae`, before
the Project controls were removed. They are retained as historical evidence;
the full original native workflow was not repeated for this interface change.

That build was validated on **Apple Silicon, macOS 26.6.2**, using Python 3.12.14,
PyInstaller 6.22.3, and pywebview 6.2.1. Packaging does not establish scientific
accuracy.

- **Automated tests:** 1,186 Python tests passed, 9 existing private-image tests
  skipped; all 113 JavaScript tests passed.
- **Native app:** imported 8-bit and 16-bit TIFF, 16-bit PNG, and JPEG; exercised
  orientation, four-lane detection, keyboard boundary adjustment, cropping,
  annotation editing, ladder preset/reference controls, and wells-at-top project
  editing. Native save dialogs produced annotated PNG/JPEG/TIFF/SVG, band-review
  PNG, and measurement CSV files; image dimensions and decoded output were checked.
- **Former Project UI (original build only):** saved an edited wells-at-top project
  through the native dialog, validated its source/annotations/confirmed export, replaced the active image,
  and reopened the project at the export step. These controls are absent from
  the revised build.
- **Lifecycle:** verified quit cancellation preserves the session, quitting stops
  the server, relaunch works, occupied ports are retried, startup failures and
  timeouts are handled, and parent-process death stops the bundled backend.
- **Self-contained/offline backend:** ran the frozen executable from a temporary
  directory with Python/virtual-environment variables removed and only system
  tools on PATH. The bundled app executed successfully over its local WebSocket.
  A separate sandbox check denied non-loopback networking and still served the
  app, frontend JavaScript, and editor assets. A fully disconnected native GUI
  session was not separately tested.
- **Packaging:** all 149 native binaries are arm64 and declare minimum macOS
  versions no later than 14.0; bundle version and ad-hoc signatures verified.
  ZIP integrity, DMG checksums/mounting, the Applications shortcut, and a copied
  installation outside the checkout were checked. Release assets include
  SHA-256 checksums.

**Not independently tested:** runtime behavior on macOS 14, a separate Mac without
developer tools installed, and the downloaded-app Gatekeeper first-launch flow.
The minimum OS is checked against bundled binary requirements, not a macOS 14
runtime test. Notarization and Intel builds are intentionally deferred.
