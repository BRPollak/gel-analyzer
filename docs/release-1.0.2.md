# Gel Analyzer 1.0.2

Version 1.0.2 improves well detection, manual lane editing, and gel annotations.
The standalone Mac app includes Python and all dependencies and runs locally.

## Changes since 1.0.1

- Well detection now requires the total number of wells, including unloaded
  wells, and uses regular spacing, well-wall contrast, and downstream bands to
  help recover faint, merged, or partial wells.
- Manual well adjustment uses stable lane colors, staggered handles, and
  numbered delete buttons to make dense lanes easier to distinguish and edit.
- Manual ladder annotations support custom labels, such as `500 bp` or
  `25 kDa`, with editable, movable, and removable markers.
- Command-click or Ctrl-click selects multiple sample labels for shared bold,
  italic, and text-color formatting.
- Returning through the well summary preserves existing annotations when the
  gel geometry is unchanged.
- The workflow finishes with annotated-image export; optional automatic
  band-analysis and quantification controls have been removed from the UI.
- The README now provides a beginner guide to installation and the full
  image-labeling workflow.

## Download and install

Requires **Apple Silicon (M1 or later) and macOS 14 or later**.

Download from the [v1.0.2 GitHub release](https://github.com/BRPollak/gel-analyzer/releases/tag/v1.0.2):

- `Gel-Analyzer-1.0.2-macOS-arm64.dmg`: open it, drag **Gel Analyzer.app** onto
  **Applications**, eject the disk image, then launch from Applications.
- `Gel-Analyzer-1.0.2-macOS-arm64.zip`: alternatively, extract and move
  **Gel Analyzer.app** into Applications.
- `SHA256SUMS`: SHA-256 checksums for the DMG and ZIP.

The repository is private, so downloading requires GitHub repository access.
The installed app does not require a GitHub account.

This release is **ad-hoc signed and not Apple-notarized**. If macOS blocks first
launch, follow the app-specific opening steps in the
[README](https://github.com/BRPollak/gel-analyzer/blob/v1.0.2/README.md).

## Update from an earlier version

Export any results you want to keep, quit Gel Analyzer, then replace the app in
Applications with version 1.0.2. Keep source images and exports separately.
Editable work exists only in the current session; an exported image cannot
restore it.

## Validation and limitations

The release build checks bundle versions and ad-hoc signatures, confirms that
bundled native binaries are arm64 with minimum OS requirements no newer than
macOS 14, verifies ZIP integrity and DMG checksums, and tests mounting and
copying the installer. The GitHub release records the completed test results.

Intel builds and Apple notarization are not included. Runtime behavior on
macOS 14, a separate Mac without developer tools, and the downloaded-app
Gatekeeper flow are not independently tested for this release.

Review automatic well and lane boundaries, cropping, and annotations against
your gel and correct them as needed. Packaging and synthetic tests do not
establish scientific accuracy.
