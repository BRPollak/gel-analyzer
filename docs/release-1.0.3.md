# Gel Analyzer 1.0.3

Version 1.0.3 adds a standalone Windows app and offline installer. Analysis
features and exported-file formats are unchanged from 1.0.2.

## Download and install

Requires **Windows 10 version 22H2 or Windows 11, 64-bit Intel/AMD**, with
**.NET Framework 4.8 or later**. Windows on ARM and 32-bit Windows are excluded.

- `Gel-Analyzer-1.0.3-Windows-x64-Setup.exe`: download and double-click to install
  for your Windows account, then open **Gel Analyzer** from the Start menu.
- `SHA256SUMS-windows.txt`: SHA-256 checksum for the installer.
- Windows validation records: build identity and automated test evidence.

Python and analysis dependencies are included. The installer includes the full
Microsoft WebView2 Runtime installer and installs it if missing. Setup and
analysis work offline; no terminal, administrator rights, or GitHub account is
required to run the app. Downloading from this private repository requires
repository access.

The installer and app are **unsigned**. Windows may display SmartScreen or
unknown-publisher warnings. Follow the installation guidance in the
[README](https://github.com/BRPollak/gel-analyzer/blob/v1.0.3/README.md) only if you
trust the download source. Organization policies may require administrator
assistance.

The existing Apple Silicon Mac installer remains available in
[v1.0.2](https://github.com/BRPollak/gel-analyzer/releases/tag/v1.0.2).

## Updates and removal

Export results and close the app before running an updated installer. Uninstall
through **Settings → Apps → Gel Analyzer**. Original images, exports, and the
shared WebView2 Runtime are retained. Logs are in
`%LOCALAPPDATA%\Gel Analyzer\Logs`.

Editable analysis remains session-only. Export before closing the app or
replacing an image.

## Validation and limitations

The release workflow checks the locked Python and JavaScript suites, macOS
desktop regressions, Windows bundle resources and native dependencies,
Microsoft's prerequisite signature, installation, reinstallation, simulated
earlier-version upgrade, shortcuts, and uninstall. Frozen-app tests cover
startup, process cleanup, synthetic image upload, interactive components, and
image export. Attached validation records identify the completed checks.

The upgrade fixture contains the current application with an earlier installer
version; no earlier Windows release exists. Automated Windows checks run on
GitHub's Windows Server 2022 runner.

A separate clean Windows 10/11 PC, standard-user installation with WebView2
absent and networking disabled, the downloaded-file SmartScreen experience,
and native save dialogs have not been independently tested. Review automated
well and lane suggestions against your own images.
