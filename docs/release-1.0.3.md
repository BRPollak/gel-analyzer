# Gel Analyzer 1.0.3 — Windows and macOS

**Both downloads are Gel Analyzer 1.0.3**, built from the same application code,
with the same analysis features and PNG, JPEG, TIFF, and SVG export formats.
Choose the installer for your computer below.

> [!WARNING]
> **The Windows installer has not yet been manually tested on a Windows 10/11 PC.**
> Automated build, installation, and app checks passed on GitHub's Windows Server
> runner. Installation and everyday use on a separate Windows PC, including native
> save dialogs, still need manual testing.

## Downloads

| Computer | Installer | Requirements |
| --- | --- | --- |
| Windows PC | [Gel-Analyzer-1.0.3-Windows-x64-Setup.exe](https://github.com/BRPollak/gel-analyzer/releases/download/v1.0.3/Gel-Analyzer-1.0.3-Windows-x64-Setup.exe) | Windows 10 version 22H2 or Windows 11; 64-bit Intel/AMD; .NET Framework 4.8 or later |
| Mac | [Gel-Analyzer-1.0.3-macOS-arm64.dmg](https://github.com/BRPollak/gel-analyzer/releases/download/v1.0.3/Gel-Analyzer-1.0.3-macOS-arm64.dmg) | Apple Silicon (M1 or later); macOS 14 or later |

Windows on ARM, 32-bit Windows, and Intel Macs are not supported by these installers.
Downloading requires access to this private GitHub repository. Once downloaded,
the apps include Python and their dependencies and can run offline without a
GitHub account or terminal commands.

## Install on Windows

1. Download the `.exe` above. You do not need the source-code ZIP or validation archive.
2. Double-click it and follow the setup prompts. It installs for your Windows
   account without administrator rights and offers an optional desktop shortcut.
   The full Microsoft WebView2 Runtime installer is included and runs if needed.
3. Open **Gel Analyzer** from the Start menu.

The Windows installer and app are **unsigned**. Windows may show SmartScreen or
unknown-publisher warnings. Follow the
[Windows installation guide](https://github.com/BRPollak/gel-analyzer#install-on-windows)
only if you trust the download source. Organization policies may require IT assistance.
**Manual installation and use on a Windows PC remain unverified.**

## Install on Mac

1. Download and open the `.dmg` above.
2. Drag **Gel Analyzer.app** onto **Applications**.
3. Eject the disk image and open **Gel Analyzer** from Applications.

The Mac app is ad-hoc signed and **not notarized by Apple**. See the
[Mac installation guide](https://github.com/BRPollak/gel-analyzer#install-on-mac)
for first-launch security prompts. A `.zip` alternative is also available under
**Assets**. The [previous Mac 1.0.2 release](https://github.com/BRPollak/gel-analyzer/releases/tag/v1.0.2)
remains available.

## Changes since 1.0.2

- Adds the Windows app and offline installer alongside the Mac app.
- Preserves pending well-guide edits when a desktop component reloads.
- Clarifies installation, updates, removal, and testing status in the README.

Analysis features and exported-file formats are unchanged. Both platforms now
share the 1.0.3 version number.

## Updates, removal, and logs

Export your results and close the app before updating. On Windows, run the newer
installer. On Mac, replace the app in Applications using the newer DMG.
Editable analysis is session-only: export before closing or replacing an image.

To uninstall, use **Settings → Apps → Gel Analyzer → Uninstall** on Windows,
or quit the app and move it from Applications to the Trash on Mac. Original
images and exported files are retained. Windows uninstall also retains the
shared WebView2 Runtime.

Logs: `%LOCALAPPDATA%\Gel Analyzer\Logs` on Windows;
`~/Library/Logs/Gel Analyzer/` on Mac.

## Completed automated checks

Windows [workflow 39485383345](https://github.com/BRPollak/gel-analyzer/actions/runs/39485383345)
passed on application source commit `3ae4ac2312d54f28ba5261447e42e3cd6eaddf5b`:

- Python: **1,315 passed**, 15 private-image tests skipped. JavaScript: **143 passed**.
- macOS desktop regression job: **49 passed**, 1 Windows-only test skipped.
- Bundle resources, native dependencies, and Microsoft's prerequisite signature verified.
- Installation, simulated upgrade, reinstallation, shortcuts, and uninstall passed;
  the shared WebView2 Runtime was retained.
- Native WebView2 rendering and backend cleanup after normal and forced closing passed.
- Frozen app ran from a path containing spaces and non-ASCII characters.
- Synthetic PNG/JPEG/16-bit TIFF uploads, interactive components, and PNG/JPEG/TIFF/SVG exports passed.

The simulated upgrade uses the current application packaged with an earlier
installer version; there is no historical Windows release. These tests ran on
GitHub's **Windows Server 2022** runner.

The Mac 1.0.3 package was built on Apple Silicon with macOS 26.6.2 and locked
Python 3.12 dependencies. It contains the same application code as the Windows
release. Mac packaging commit `949ddc5501145c0efdf9887063d6599418c460dc` adds
supplemental dependency license notices without changing application code.

- Python: **1,314 passed**, 15 private-image tests and 1 Windows-only test skipped.
- JavaScript: **143 passed**.
- All **143 native binaries** are arm64 with minimum OS requirements no newer than macOS 14.
- Bundle version, resources, dependency notices, and ad-hoc signature verified.
- ZIP integrity, DMG checksums, mounting, and copying the app from the DMG passed.
- Native Cocoa startup rendered the workspace from a path containing spaces and non-ASCII characters.
- Closing the native window and forcibly terminating a separate GUI launch both
  stopped the backend and closed its listener.
- Synthetic uploads, interactive components, and PNG/JPEG/TIFF/SVG exports passed
  through a browser connected to the packaged backend.

Native save-dialog behavior was not tested. The export checks above use browser
downloads against the frozen backend.

## What still needs testing

**The Windows installer has not yet been manually tested on a Windows 10/11 PC.**
Outstanding checks include installation on a clean PC, offline standard-user
installation with WebView2 absent, the downloaded-file SmartScreen experience,
native save dialogs, and everyday use.

Mac testing does not establish behavior on a separate clean Mac, the minimum
supported macOS 14, or the downloaded-file Gatekeeper experience. Review automatic
well and lane suggestions against your own images.

## Checksums and validation records

The installer files are all most users need. Additional assets provide build evidence:

- `SHA256SUMS-windows.txt`: checksums for the Windows installer and validation archive.
- `Gel-Analyzer-1.0.3-Windows-validation.zip`: Windows manifests, test results,
  installer logs, and screenshots.
- `SHA256SUMS-macos.txt`: checksums for the Mac DMG, ZIP, and validation archive.
- `Gel-Analyzer-1.0.3-macOS-validation.zip`: Mac build and test records.
