# Gel Analyzer 1.0.1

Version 1.0.1 packages the current Gel Analyzer workflow as a standalone Mac app.
Python and all dependencies are included; analysis runs locally.

## Changes since 1.0.0

- **Define boundary wells** guides you through adjusting the first outside well,
  placing a matching last well, and generating the requested total lane count,
  including both boundaries. Lanes are equally spaced with matching widths in
  either workflow orientation and remain individually editable. **Back** retains
  boundary positions; **Cancel** restores the previous arrangement.
- Fractional lane geometry is preserved through cropping and band analysis.
- The author footer stays visible while previews reserve space for it.
- Regression tests are consolidated while retaining image integrity, geometry,
  workflow, export, and desktop lifecycle coverage.

## Download and install

Requires **Apple Silicon (M1 or later) and macOS 14 or later**.

Download from the [v1.0.1 GitHub release](https://github.com/BRPollak/gel-analyzer/releases/tag/v1.0.1):

- `Gel-Analyzer-1.0.1-macOS-arm64.dmg`: open it, drag **Gel Analyzer.app** onto
  **Applications**, eject the disk image, then launch from Applications.
- `Gel-Analyzer-1.0.1-macOS-arm64.zip`: alternatively, extract and move
  **Gel Analyzer.app** into Applications.
- `SHA256SUMS`: SHA-256 checksums for the DMG and ZIP.

The repository is private, so downloading requires GitHub repository access.
The installed app does not require a GitHub account.

This release is **ad-hoc signed and not Apple-notarized**. If macOS blocks first
launch, attempt to open the app, then use **System Settings → Privacy & Security
→ Open Anyway** for Gel Analyzer and confirm. Only do this for the release you
intended to download. See [Apple's guidance](https://support.apple.com/en-us/102445).

## Update from 1.0.0

Export any results you want to keep, quit Gel Analyzer, then replace the app in
Applications with version 1.0.1. Keep source images and exports separately.
Editable analysis exists only in the current session; exported images and CSV
files do not restore it. Project save/open controls and JSON uploads remain absent.

## Validation and limitations

The release build checks the bundle version and ad-hoc signatures, confirms
that bundled native binaries are arm64 with minimum OS requirements no newer
than macOS 14, verifies ZIP integrity and DMG checksums, and tests mounting and
copying the installer. The GitHub release records the completed test results.

Intel builds and Apple notarization are not included. Runtime behavior on
macOS 14, a separate Mac without developer tools, and the downloaded-app
Gatekeeper flow are not independently tested for this release.

Packaging and synthetic tests do not establish scientific accuracy. Review
automatic well/lane boundaries, cropping, band proposals, and ladder-based size
estimates against your gel and correct them as needed. See the
[README](../README.md) for workflow details and scientific limitations.
