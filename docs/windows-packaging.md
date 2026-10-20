# Windows packaging and verification

The Windows installer is built natively on x64 Windows with Python 3.12,
PyInstaller, and Inno Setup 6. It wraps a one-folder, windowed executable in a
per-user installer. The Python environment is pinned by `uv.lock`.

## Build

Install uv and Inno Setup 6 on the build computer, then run from the repository:

```powershell
uv sync --locked --group desktop --group build
New-Item -ItemType Directory -Force build/windows/prerequisites
curl.exe --fail --location --output build/windows/prerequisites/MicrosoftEdgeWebView2RuntimeInstallerX64.exe "https://go.microsoft.com/fwlink/?linkid=2124701"
uv run --locked --group desktop --group build python scripts/build_windows.py --webview2-installer build/windows/prerequisites/MicrosoftEdgeWebView2RuntimeInstallerX64.exe
```

The Microsoft link supplies the **x64 Evergreen Standalone Installer**, not the
online bootstrapper. The build checks its Authenticode signature and Microsoft
publisher, and records its SHA-256 and version. The runtime is embedded in the
application installer, so an end user's installation does not need a download.
See [Microsoft's distribution instructions](https://learn.microsoft.com/en-us/microsoft-edge/webview2/concepts/distribution).

Use `--iscc PATH` if the Inno Setup compiler is not found automatically.
`--app-only` builds and checks the application folder without creating an
installer. Build outputs are:

- `dist/windows/Gel Analyzer/Gel Analyzer.exe` and its bundled dependencies.
- `dist/windows/Gel-Analyzer-<version>-Windows-x64-Setup.exe`.
- `dist/windows/SHA256SUMS-windows.txt`.
- `build/windows/validation.json`, recording the source revision, dependency
  versions, prerequisite identity, and bundle checks.

The installer and application are unsigned. The Microsoft prerequisite retains
its own Microsoft signature. The installer uses a stable application ID for
upgrades, stores the app in `%LOCALAPPDATA%\Programs\Gel Analyzer`, and retains
the shared WebView2 runtime during uninstall. .NET Framework 4.8 is required
rather than installed, because it is included in the supported Windows versions
and repairing it can require administrator rights.

Only explicitly selected application resources and dependencies enter the
bundle. Do not collect the repository root or add private gel images as build
inputs. `test-smoke` dependencies are excluded from the shipped application.

## Automated verification

The **Windows installer** GitHub Actions workflow runs the Python and JavaScript
suites, verifies macOS desktop regressions in a separate job, builds on
`windows-2022`, and tests installation and the frozen application. Artifacts
contain the installer, checksums, and validation records. The workflow does not
publish a GitHub release automatically.

To run the Windows smoke tests locally:

```powershell
uv sync --locked --group desktop --group build --group test-smoke
uv run --locked --group desktop --group build --group test-smoke python -m playwright install chromium
uv run --locked --group desktop --group build --group test-smoke pytest -q
$tests = Get-ChildItem tests -Filter "*.mjs" | ForEach-Object { $_.FullName }
node --test $tests
uv run --locked --group desktop --group build --group test-smoke python scripts/smoke_windows.py --exe "dist/windows/Gel Analyzer/Gel Analyzer.exe" --output "build/windows/smoke"
./scripts/test_windows_installer.ps1 -Installer "dist/windows/Gel-Analyzer-1.0.3-Windows-x64-Setup.exe" -Version 1.0.3 -OutputDirectory "build/windows/installer-tests"
```

The installer test installs and removes Gel Analyzer for the current Windows
account. Run it only on a disposable test account or CI runner without an
existing installation or unsaved Gel Analyzer session.

For native-window inspection, the smoke harness enables WebView2 debugging only
for its test launch. On an elevated runner, it temporarily sets app-specific
machine policies for the debugging port and test profile, then restores them.
This uses Microsoft's supported mechanism for elevated WebView2 hosts; normal
application launches do not enable debugging.

CI also compiles an installer fixture with the same payload but version 1.0.2,
then upgrades it to 1.0.3. This verifies versioned installer replacement and
uninstall registration; it is not a historical Windows release. Pass this
fixture through `-PreviousInstaller` to reproduce that test.

The hosted Windows Server runner is not a clean Windows 10/11 end-user PC.
Release notes must distinguish automated results from independent standard-user,
offline installation without an existing WebView2 runtime, SmartScreen, and
native save-dialog testing.

## Release

After all three workflow jobs pass on the release commit, download the
`windows-installer`, `windows-unit-tests`, and `windows-validation` artifacts. Verify the installer
against `SHA256SUMS-windows.txt`. Publish the installer, checksums, and validation
records with the version tag matching `pyproject.toml`, using the release notes
in `docs/release-<version>.md`. Do not replace existing macOS release assets.
