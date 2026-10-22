# Gel Analyzer 1.0.4 — Windows and macOS

Version 1.0.4 fixes desktop export filenames and keeps neighboring lane groups
aligned. Both installers use the same application code and support PNG, JPEG,
TIFF, and SVG exports.

## Downloads

| Computer | Installer | Requirements |
| --- | --- | --- |
| Windows PC | [Gel-Analyzer-1.0.4-Windows-x64-Setup.exe](https://github.com/BRPollak/gel-analyzer/releases/download/v1.0.4/Gel-Analyzer-1.0.4-Windows-x64-Setup.exe) | Windows 10 version 22H2 or Windows 11; 64-bit Intel/AMD; .NET Framework 4.8 or later |
| Mac | [Gel-Analyzer-1.0.4-macOS-arm64.dmg](https://github.com/BRPollak/gel-analyzer/releases/download/v1.0.4/Gel-Analyzer-1.0.4-macOS-arm64.dmg) | Apple Silicon (M1 or later); macOS 14 or later |

Downloads are public and require no GitHub account. Python and application
dependencies are included. Windows setup also includes the full WebView2 Runtime
installer. Windows on ARM, 32-bit Windows, and Intel Macs are not supported.

Export your work and close the app before updating. On Windows, run the new
installer. On Mac, open the DMG and replace **Gel Analyzer.app** in Applications.
A Mac ZIP alternative is available under **Assets**. See the
[installation guide](https://github.com/BRPollak/gel-analyzer#install-on-windows)
for detailed instructions. Original images and exported files are retained;
editable analysis lasts only for the current session.

## Changes since 1.0.3

- Desktop save dialogs constrain filenames to the selected image format. A
  missing extension is restored, and an incompatible extension must be corrected
  before saving. JPEG and TIFF filename aliases remain supported.
- Mac exports safely replace the destination approved in the save dialog after
  a successful download. Cancelling or failing a transfer preserves an existing
  export.
- Lane groups in the same annotation column or row keep a common distance from
  the gel. Close brackets may overlap slightly instead of pushing one group's
  bracket and label farther away. This applies to both well orientations.
- Updates the application icon.

## Validation

Completed local checks for the updated application:

- Python: **1,371 passed**, 16 skipped. JavaScript: **146 passed**.
- Native Mac save dialogs: PNG filename without an extension, JPEG filename
  with an incompatible extension, overwrite confirmation, and cancellation.
- Mac app, ZIP, and DMG built from commit
  `bc7578533c5698688b6cc647a585e765ecbee2a9`. All 144 native binaries are arm64
  with minimum OS requirements no newer than macOS 14. Bundle resources,
  ad-hoc signature, ZIP integrity, DMG checksums, mounting, and copying the app
  from the DMG passed. The installed 1.0.4 app opened to the upload screen.

[GitHub workflow 39853384065](https://github.com/BRPollak/gel-analyzer/actions/runs/39853384065)
passed on the same release commit:

- Windows Python: **1,372 passed**, 15 skipped. JavaScript: **146 passed**.
- Mac desktop regressions: **49 passed**, 1 Windows-only test skipped.
- Windows bundle resources, native dependencies, and Microsoft's WebView2
  prerequisite signature verified.
- Installation, simulated upgrade, reinstallation, shortcuts, and uninstall
  passed; the shared WebView2 Runtime was retained.
- Native WebView2 startup and backend cleanup after normal and forced closing
  passed. The frozen app ran from a path containing spaces and non-ASCII text.
- Synthetic PNG/JPEG/16-bit TIFF uploads, interactive controls, and
  PNG/JPEG/TIFF/SVG exports passed.

The simulated upgrade uses this release's application files packaged with an
earlier installer version. Release assets include platform-specific checksums
and validation archives with build manifests, test results, and installer logs.

## Testing limits

**The Windows installer has not yet been manually tested on a separate Windows
10/11 PC.** Automated checks run on GitHub's Windows Server 2022 runner. Native
Windows save dialogs, a clean PC, offline standard-user installation with
WebView2 absent, and the downloaded-file SmartScreen experience remain
unverified. Automated export smoke checks use Chromium against the packaged
backend; they do not exercise the native Windows save dialog.

The Windows installer and app are **unsigned**. The Mac app is ad-hoc signed
and **not notarized by Apple**. See the installation guide for first-launch
security prompts. Mac testing does not establish behavior on a separate clean
Mac, the minimum supported macOS 14, or the downloaded-file Gatekeeper experience.

The [previous release](https://github.com/BRPollak/gel-analyzer/releases/tag/v1.0.3)
remains available. Review automatic well and lane suggestions against your own
images.
