# Windows validation — November 16, 2026

The annotation focus correction is restricted to the Windows desktop backend.
The source suites and complete installed-app validation pass on both Windows
Server 2022 and 2025. The fixes were merged in
[PR #21](https://github.com/BRPollak/gel-analyzer/pull/21). The Windows assets
on [release 1.0.6](https://github.com/BRPollak/gel-analyzer/releases/tag/v1.0.6)
were refreshed; the Mac assets and original release tag are unchanged.

## Published Windows installer

The published installer was rebuilt from merged main commit
`57d9de543c620b7beb08faae677ce073b9e5e85f` in
[run 43981787159](https://github.com/BRPollak/gel-analyzer/actions/runs/43981787159).
All jobs passed: 1,471 Python tests (15 skipped) and 184 JavaScript tests on
each Windows platform; 49 Mac lifecycle tests (1 skipped); build, simulated
upgrade, and complete installed-app validation on Windows Server 2022 and 2025.
Native typing preserved focus and caret across 28 and 29 autosave reruns.

- File: `Gel-Analyzer-1.0.6-Windows-x64-Setup.exe` (276,990,828 bytes).
- SHA-256: `778aeb6691ea66532bf4792fd07f88ac5b538bbcb7b88632fb1724eddd3be210`.
- The Windows validation archive and checksum file were refreshed alongside
  the installer. Mac asset IDs, sizes, digests, and update times were preserved.
- The `v1.0.6` tag still points to the original release, so its automatic source
  archives retain that source. Use the commit above for the Windows hotfix.

The sections below preserve the earlier candidate's investigation and validation
record. Its installer hash differs from the final rebuild above.

## Exact candidate application under test

- Application commit: `1ed5e7717c64aa90e63fb6c1df1f6ea26321dd90`.
- Installer: `Gel-Analyzer-1.0.6-Windows-x64-Setup.exe` (276,986,773 bytes).
- SHA-256: `9be49d75022b880133149cb469c9c3941ebd9957644d4d8bbb71099090ec85fd`.
- Build/source run: [43975747147](https://github.com/BRPollak/gel-analyzer/actions/runs/43975747147).
- Current native harness: `31ebba5`; native run: [43980028598](https://github.com/BRPollak/gel-analyzer/actions/runs/43980028598).

Native iterations reuse that exact installer. Before installing, CI checks the
installer hash against both its checksum file and build report, checks its
size, and rejects source differences outside workflow, test, documentation,
and the two smoke/installer-test scripts. Harness corrections therefore do
not silently substitute a different application binary.

## Completed evidence

| Check | Result | Evidence |
| --- | --- | --- |
| Windows Server 2022 source suites | 1,467 Python passed; 15 skipped; 184 JavaScript passed | Source run, `windows-unit-tests` and job log |
| Windows Server 2025 source suites | 1,467 Python passed; 15 skipped; 184 JavaScript passed | Source run, `windows-unit-tests-2025` and job log |
| Mac desktop lifecycle regression | 49 passed; 1 skipped | Source run, `macos-regression` job |
| Local macOS Python suite | 1,458 passed; 16 skipped | `output/windows-validation/local-pytest.xml` |
| Frozen Windows build and bundled prerequisite checks | Passed | Source run, `windows-validation/validation.json` |
| Windows 2022 installation, shortcut targets, same-version reinstall | Passed before the original native-harness failure | Source run, `installer-tests/installer-results.json` |
| Simulated 1.0.2 → 1.0.6 upgrade | Passed before the original native-harness failure | Same installer report; the old version uses the current payload, not a historical release |

The original source run's overall installer job failed in native test
automation. Later iterations corrected automation assumptions about Windows
dialog controls, trusted input, and overwrite prompts. Partial runs are not
counted as complete native validation.

## Completed native validation

Both Windows Server 2022 and 2025 passed installation/reinstallation, real
WebView2 startup, annotation typing across autosaves, caret/focus and label
navigation checks, native Open/Save dialogs, cancellation, overwrite handling,
Unicode/spaced paths, PNG/JPEG/TIFF/SVG export checks,
normal/forced shutdown, parent-pipe EOF cleanup, and uninstall cleanup. Both
`installer-results.json` and `installed-smoke/smoke-results.json` report
`passed` in each `native-validation-<runner>` artifact from
[run 43980028598](https://github.com/BRPollak/gel-analyzer/actions/runs/43980028598).
The 19 updated harness unit tests also passed on each runner.

| Runner | Current result |
| --- | --- |
| Windows Server 2022 | Passed: native WebView2 and standalone Chromium |
| Windows Server 2025 | Passed: native WebView2 and standalone Chromium |

Each typing check entered 30 characters across two labels without refocusing
between keystrokes, and asserted caret position, text, iframe identity, zero
unexpected blur events, and Tab/Shift+Tab navigation. Real autosave reruns
occurred during typing. PNG, JPEG, TIFF, and SVG output contents were parsed
and verified; native upload covered PNG, JPEG, and 16-bit TIFF.

## Mac preservation and limits

Both annotation corrections require `sys.platform == "win32"` and the explicit
native-backend marker. Tests check that Mac and ordinary browser behavior keep
their previous paths. Mac packaging, dependency versions, and application
version were not changed. Before/after metadata for all four existing Mac
release assets is identical, including IDs, sizes, timestamps, and SHA-256
digests. No release asset was replaced.

Hosted Windows Server results do not establish physical Windows 10/11 behavior.
Physical keyboard/IME input, independent standard-user testing, SmartScreen,
and clean offline installation with no pre-existing WebView2 runtime remain
untested. Preference files are captured, but restoring native dialog folders
after restarting is not an end-to-end assertion in this harness. Native label
typing uses CDP keyboard events; native file dialogs
are driven through Windows automation. These checks do not establish every
Windows desktop configuration.
