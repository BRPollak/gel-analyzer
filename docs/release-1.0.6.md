# Gel Analyzer 1.0.6 — Windows and macOS

Version 1.0.6 simplifies manual ladder annotation, separates crowded controls,
and remembers desktop upload and save folders. Both installers use the same
analysis features and support PNG, JPEG, TIFF, and SVG exports.

## Windows annotation hotfix — November 16, 2026

The Windows 1.0.6 installer has been refreshed to preserve label focus during
autosave and prevent IME candidate keys from invoking label shortcuts. These
corrections are enabled only in the Windows desktop app. Existing Windows
users can close the app and rerun the updated installer to apply the fix.

The Mac 1.0.6 installer, ZIP, checksums, validation archive, and the `v1.0.6`
tag are unchanged. The automatic source archives for that tag retain the
original release source. The refreshed Windows installer was built from
[`57d9de5`](https://github.com/BRPollak/gel-analyzer/commit/57d9de543c620b7beb08faae677ce073b9e5e85f),
which includes [PR #21](https://github.com/BRPollak/gel-analyzer/pull/21).

[Windows build and validation run](https://github.com/BRPollak/gel-analyzer/actions/runs/43981787159)
records the source suites and packaged tests on Windows Server 2022 and 2025.
Each Windows platform passed 1,471 Python tests (15 skipped) and all 184
JavaScript tests; the Mac lifecycle regression passed 49 tests (1 skipped).
Native WebView2 checks cover typing across autosaves without losing focus or
caret, PNG/JPEG/16-bit TIFF uploads, native Open/Save cancellation, overwrite,
Unicode paths, all four export formats, normal/forced shutdown, and uninstall.
The Windows validation archive and checksum file identify the refreshed
installer. Its SHA-256 is
`778aeb6691ea66532bf4792fd07f88ac5b538bbcb7b88632fb1724eddd3be210`.
Physical Windows 10/11 and real IME input remain unverified.

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

The original Mac installer and the superseded Windows installer were built from source commit
[`a9a5482`](https://github.com/BRPollak/gel-analyzer/commit/a9a5482442066cae7bccdc21c33a00500b8fa581)
with the locked dependencies.

- **Mac:** 1,431 Python tests passed (16 skipped); all 180 JavaScript tests passed.
  The standard CPython 3.12.13 build passed signature, version, resource,
  144 arm64 binary, ZIP, DMG, and fresh installation-copy checks. The packaged
  app passed synthetic PNG/JPEG/16-bit TIFF uploads, the analysis workflow,
  PNG/JPEG/TIFF/SVG exports, and backend cleanup after normal process termination
  and forced termination. The installed 1.0.6 app reached its upload screen.
- **Original Windows build (superseded by the hotfix above):** 1,432 Python tests passed (15 skipped); all 180 JavaScript tests
  passed. The installer passed build validation, installation, simulated
  upgrade, reinstallation, shortcuts, native startup, backend cleanup, uploads,
  exports, and uninstall checks on Windows Server 2022.
- **Feature checks:** ladder controls were checked from 360 to 1440 pixels wide,
  with manual marker placement and no automatic ladder detection controls.
  Native Mac upload/save checks confirmed 600 DPI export and independent folder
  memory. The native dialog checks used a QA build of these application changes;
  the final release build was separately installed and opened.

The [release build workflow](https://github.com/BRPollak/gel-analyzer/actions/runs/43938868788)
and platform-specific validation archives record the build and test evidence.
SHA-256 checksum files accompany the installers. The simulated Windows upgrade
uses the current application files with an earlier installer version.

## Testing limits

Windows manual testing on a separate Windows 10/11 PC is pending. Automated
Windows checks run on GitHub's Windows Server 2022 and 2025 runners, including
real WebView2 and native file dialogs. They do not establish behavior on a
separate Windows PC, physical keyboard/IME input, a clean offline standard-user
installation without WebView2, or the downloaded-file SmartScreen experience.

The Windows installer is unsigned. The Mac app is ad-hoc signed and not
notarized by Apple. Mac checks do not establish behavior on a separate clean
Mac, the minimum supported macOS 14, or the downloaded-file Gatekeeper
experience. Review automatic well and lane suggestions against your images.
