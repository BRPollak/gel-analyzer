# Gel Analyzer 1.0.5 — Windows and macOS

Version 1.0.5 makes lane labels faster to edit with the keyboard and adds
rectangular outlines for extracted bands. Both installers use the same
application code and support PNG, JPEG, TIFF, and SVG exports.

## Downloads

| Computer | Installer | Requirements |
| --- | --- | --- |
| Windows PC | [Gel-Analyzer-1.0.5-Windows-x64-Setup.exe](https://github.com/BRPollak/gel-analyzer/releases/download/v1.0.5/Gel-Analyzer-1.0.5-Windows-x64-Setup.exe) | Windows 10 version 22H2 or Windows 11; 64-bit Intel/AMD; .NET Framework 4.8 or later |
| Mac | [Gel-Analyzer-1.0.5-macOS-arm64.dmg](https://github.com/BRPollak/gel-analyzer/releases/download/v1.0.5/Gel-Analyzer-1.0.5-macOS-arm64.dmg) | Apple Silicon (M1 or later); macOS 14 or later |

Downloads are public and require no GitHub account. Python and application
dependencies are included. Windows setup also includes the full WebView2 Runtime
installer. Windows on ARM, 32-bit Windows, and Intel Macs are not supported.
A Mac ZIP alternative is available under **Assets**.

## Changes since 1.0.4

- **Tab and Shift+Tab select the entire next or previous lane label.** Typing
  immediately replaces the selected name. Lane order is preserved, and keyboard
  navigation continues normally beyond the first and last labels.
- **Mark extracted bands** becomes available after completing or skipping
  ladder annotation. Drag in any direction to draw multiple thin red rectangles
  with transparent interiors. The outlines stay aligned when the preview resizes
  or changes zoom.
- Each rectangle has a **Remove** button. **Done marking** saves the marks and
  returns to export; **Cancel** restores the previously saved marks. Escape
  cancels an unfinished rectangle.
- Drawing uses a separate editing mode so it does not interfere with lane or
  ladder annotation. Confirmed marks remain in image exports and survive label
  or ladder edits; changing the crop clears marks tied to the old geometry.

## Updating

Export your work and close the app before updating. On Windows, run the new
installer. On Mac, open the DMG and replace **Gel Analyzer.app** in Applications.
Original images and exported files are retained; editable analysis lasts only
for the current session. See the
[installation guide](https://github.com/BRPollak/gel-analyzer#install-on-windows)
for detailed instructions. The
[previous release](https://github.com/BRPollak/gel-analyzer/releases/tag/v1.0.4)
remains available.

## Validation

Browser checks cover full-label selection and typing replacement in both
directions, native keyboard navigation at lane boundaries, drawing-button
availability after both ladder paths, rectangle creation and removal, resizing,
cancellation, persistence, and PNG/SVG exports. Automated tests cover native
coordinate geometry, both gel orientations, isolated annotation modes, stale
events, project persistence, and rendering.

Platform-specific validation archives and checksums accompany the installers.
They record build identity, automated test results, packaging checks, and
installation checks. The Windows workflow includes installation, simulated
upgrade, native startup and cleanup, uploads, exports, and uninstall checks.
The simulated upgrade packages this release's files with an earlier installer
version; it is not a historical Windows build.

## Testing limits

Windows automated checks run on GitHub's Windows Server 2022 runner. This does
not establish behavior on a separate Windows 10/11 PC, native Windows save
dialogs, a clean offline standard-user installation without WebView2, or the
downloaded-file SmartScreen experience. Automated export smoke checks use
Chromium against the packaged backend.

The Windows installer is unsigned. The Mac app is ad-hoc signed and not
notarized by Apple. Mac checks do not establish behavior on a separate clean
Mac, the minimum supported macOS 14, or the downloaded-file Gatekeeper
experience. Review automatic well and lane suggestions against your images.
