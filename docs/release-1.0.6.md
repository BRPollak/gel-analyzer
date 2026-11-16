# Gel Analyzer 1.0.6 — Windows and macOS

Version 1.0.6 simplifies manual ladder annotation, separates crowded controls,
and remembers desktop upload and save folders. Both installers use the same
application code and support PNG, JPEG, TIFF, and SVG exports.

## Downloads

| Computer | Installer | Requirements |
| --- | --- | --- |
| Windows PC | [Gel-Analyzer-1.0.6-Windows-x64-Setup.exe](https://github.com/BRPollak/gel-analyzer/releases/download/v1.0.6/Gel-Analyzer-1.0.6-Windows-x64-Setup.exe) | Windows 10 version 22H2 or Windows 11; 64-bit Intel/AMD; .NET Framework 4.8 or later |
| Mac | [Gel-Analyzer-1.0.6-macOS-arm64.dmg](https://github.com/BRPollak/gel-analyzer/releases/download/v1.0.6/Gel-Analyzer-1.0.6-macOS-arm64.dmg) | Apple Silicon (M1 or later); macOS 14 or later |

Downloads are public and require no GitHub account. Python and application
dependencies are included. Windows setup also includes the full WebView2 Runtime
installer. Windows on ARM, 32-bit Windows, and Intel Macs are not supported.

## Changes since 1.0.5

- **Ladder placement is manual.** The **Detect bands** button, automatic band
  proposals, candidate guides, and detector invocation have been removed from
  the ladder annotator. Choose a preset size and click its band, use keyboard
  positioning, or choose **Manual ladder** to enter your own labels.
- **Ladder controls have separate rows and spacing.** In **Select the ladder
  lane**, **Back** sits below the dropdown and **Use this lane**. The **Place
  ladder size markers** panel separates marker controls, placement count, and
  navigation to prevent collisions when the window narrows.
- **Print setting (DPI) defaults to 600.** The other DPI options remain
  available for PNG, JPEG, and TIFF. The unnecessary instruction to leave the
  print setting unchanged has been removed.
- **Desktop upload and save folders are remembered independently.** The next
  image picker starts in the last upload folder, and the next export starts in
  the last successful save folder. Preferences persist after restarting the
  app. Browser mode continues to use the browser's folder behavior.

## Updating

Export your work and close the app before updating. On Windows, run the new
installer. On Mac, open the DMG and replace **Gel Analyzer.app** in Applications.
Original images and exported files are retained; editable analysis lasts only
for the current session. See the
[installation guide](https://github.com/BRPollak/gel-analyzer#install-on-windows)
for detailed instructions. The
[previous release](https://github.com/BRPollak/gel-analyzer/releases/tag/v1.0.5)
remains available.

## Validation

Completed source-level checks:

- Python suite: **1,431 passed, 16 skipped**.
- JavaScript suite: **180 passed**.
- Responsive browser checks covered the ladder lane and marker panels,
  including narrow layouts, manual marker placement, and the absence of
  automatic detection controls.
- Native Mac upload and save dialogs were exercised. Automated preference
  checks cover independent upload/save folders and persistence after reload.

The source test results above are separate from packaged release validation.
Platform-specific build, installation, upgrade, startup, export, and uninstall
results are supplied in the release validation archives and
[GitHub release notes](https://github.com/BRPollak/gel-analyzer/releases/tag/v1.0.6).

## Testing limits

Windows manual testing on a separate Windows 10/11 PC is pending. Automated
Windows checks run on GitHub's Windows Server runner. They do not establish
behavior on a separate Windows PC, native Windows dialogs, a clean offline
standard-user installation without WebView2, or the downloaded-file SmartScreen
experience. Automated export smoke checks use Chromium against the packaged
backend.

The Windows installer is unsigned. The Mac app is ad-hoc signed and not
notarized by Apple. Mac checks do not establish behavior on a separate clean
Mac, the minimum supported macOS 14, or the downloaded-file Gatekeeper
experience. Review automatic well and lane suggestions against your images.
