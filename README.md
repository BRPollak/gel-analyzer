# Gel Analyzer

Turn a gel photo into a labeled image for your lab notebook. Straighten and crop
it, label samples, and optionally mark a ladder with known sizes. Analysis runs
on your computer. Export your finished image as PNG, JPEG, TIFF, or SVG.

## Download Gel Analyzer 1.0.5

**Windows and Mac are the same app version: 1.0.5**, with the same analysis
features and export formats. Choose the installer for your computer:

| Computer | Download | Requirements |
| --- | --- | --- |
| Windows PC | [Download Windows installer (.exe)](https://github.com/BRPollak/gel-analyzer/releases/download/v1.0.5/Gel-Analyzer-1.0.5-Windows-x64-Setup.exe) | Windows 10 version 22H2 or Windows 11; 64-bit Intel/AMD; .NET Framework 4.8 or later |
| Mac | [Download Mac installer (.dmg)](https://github.com/BRPollak/gel-analyzer/releases/download/v1.0.5/Gel-Analyzer-1.0.5-macOS-arm64.dmg) | Apple Silicon (M1 or later); macOS 14 or later |

> [!WARNING]
> **The Windows installer has not yet been manually tested on a Windows 10/11 PC.**
> Automated build, installation, and app checks run on GitHub's Windows Server
> runner; see the release notes for results. Installation and everyday use on a
> separate Windows PC, including native save dialogs, still need manual testing.

Both downloads are on the [same v1.0.5 release page](https://github.com/BRPollak/gel-analyzer/releases/tag/v1.0.5).
This repository and its downloads are public. Anyone can download and use the
app without a GitHub account or sign-in. After downloading, installation and
use can work offline. You do not need Python or terminal commands to run the
installed app.

[Windows installation](#install-on-windows) · [Mac installation](#install-on-mac) ·
[How to use the app](#use-the-app) · [Testing status](#testing-status)

## Install on Windows

**Manual Windows PC testing is still pending; see the notice above.**
Windows on ARM and 32-bit Windows are not supported. The required .NET Framework
4.8 or later is included with the supported Windows versions.

1. **Download** [Gel-Analyzer-1.0.5-Windows-x64-Setup.exe](https://github.com/BRPollak/gel-analyzer/releases/download/v1.0.5/Gel-Analyzer-1.0.5-Windows-x64-Setup.exe).
   If you use the release page instead, find this exact file under **Assets**.
   You only need the `.exe`; the source-code ZIP and validation files are for developers.
2. **Install.** Double-click the downloaded file and follow the setup prompts.
   It installs for your Windows account without administrator rights. You can
   choose to add a desktop shortcut. Allow setup to finish if it needs to install
   Microsoft's WebView2 Runtime; the complete runtime installer is included.
3. **Open.** In the Start menu, search for **Gel Analyzer** and open it.
   Wait for the image upload screen, then follow [Use the app](#use-the-app).

### If Windows displays a security warning

The installer and app are **unsigned**. Windows may show an unknown-publisher
warning or **Windows protected your PC**. Check that the download came from
this repository's release page and that you trust its source. If available,
choose **More info → Run anyway** to continue. On a managed work or school
computer, policy may block installation; ask your administrator for help.

### Update, uninstall, or find logs

- **Update:** export your work, close Gel Analyzer, then run the newer installer.
  It updates the existing installation.
- **Uninstall:** open **Settings → Apps**, find **Gel Analyzer**, and choose
  **Uninstall**. Your original images and exports are retained. The shared
  Microsoft WebView2 Runtime is also retained because other apps may use it.
- **Find logs:** paste `%LOCALAPPDATA%\Gel Analyzer\Logs` into File Explorer's
  address bar. These logs can help diagnose startup problems.
- **WebView2 error:** close the app and rerun the installer. If the error remains,
  share the logs when asking for help. WebView2 can update itself when online.
  A missing or damaged .NET Framework may require Windows repair or administrator help.

## Install on Mac

Requires an **Apple Silicon Mac (M1 or later) with macOS 14 or later**. Check
**Apple menu → About This Mac**. Intel Macs are not supported by this installer.

1. **Download** [Gel-Analyzer-1.0.5-macOS-arm64.dmg](https://github.com/BRPollak/gel-analyzer/releases/download/v1.0.5/Gel-Analyzer-1.0.5-macOS-arm64.dmg).
2. **Install.** Double-click the downloaded DMG, then drag **Gel Analyzer.app**
   onto **Applications** in the window that opens.
3. **Open.** Eject the disk image in Finder. Open **Applications** and
   double-click **Gel Analyzer**.

### If macOS blocks the app

The app is **not notarized by Apple**, so macOS may say the developer cannot be
verified or Apple cannot check it for malicious software. Proceed only if you
trust the download source and are sure the app has not been altered.

1. Try opening **Gel Analyzer** from Applications, then dismiss the warning.
2. Open **Apple menu → System Settings → Privacy & Security** and scroll to
   **Security**. If **Allow apps downloaded from** is set to **App Store** only,
   select **App Store and identified developers**.
3. Find the message about **Gel Analyzer**, click **Open Anyway**, and confirm.
   Enter your Mac login password if asked. This saves an exception for this app.

If the option is missing, try opening the app again and return to these settings
within an hour. On a managed computer, your administrator may need to help.
See [Apple's security guidance](https://support.apple.com/en-us/102445).

### Update, uninstall, or find logs

- **Update:** export your work and quit Gel Analyzer, then install the newer DMG
  and replace the existing app in Applications when Finder asks.
- **Uninstall:** quit Gel Analyzer and move it from Applications to the Trash.
  Keep your original images and exported files separately.
- **Find logs:** in Finder, choose **Go → Go to Folder** and paste
  `~/Library/Logs/Gel Analyzer/`.

The previous Windows and Mac 1.0.4 downloads remain available in the
[older release](https://github.com/BRPollak/gel-analyzer/releases/tag/v1.0.4).

## Use the app

The steps are the same on Windows and Mac. Check automatic suggestions against
your image and correct them before relying on the results.

1. **Open an image.** Under **Open a gel image**, click **Upload** and choose one
   TIFF, PNG, or JPEG file. The app crops surrounding background when it can.
2. **Orient it.** Wells are the small pockets where samples were loaded. Set
   **Workflow orientation** to **Wells at left** or **Wells at top**, then click
   **Rotate and Orient**. Inspect the preview. If it looks right, click **Confirm**;
   otherwise, use **Adjust outline manually**: draw or move the rectangle,
   resize with its corners, and rotate with the round handle. Click
   **Preview manual orientation**, then **Confirm**.
3. **Find the samples.** Click **Define wells**. Click two points spanning the
   outside edges of the first and last wells, with the guide passing through
   their centers. Enter the required **Number of wells**, including unloaded
   wells, then click **Confirm**.
4. **Check the lanes and crop.** Each lane is one sample's path through the gel.
   Accept the proposed lanes with **Confirm**, or use **Adjust** to move their
   borders, delete a lane, or **Add lane**, then click **Confirm**.
   Drag the shared right edge (wells at left) or bottom edge (wells at top)
   to include the bands you want. Click
   **Confirm lanes and crop**.
5. **Label samples.** Click a lane label and type a name. Ctrl-click on Windows
   or Command-click on Mac to select multiple labels and format them together.
   Tab selects all text in the next lane label; Shift+Tab does the same for the
   previous label, so typing replaces its name immediately.
   Use **Create lane groups** for related samples, then **Confirm annotations**.
6. **Add a ladder, if needed.** A ladder is a reference sample with known band
   sizes. Choose **Annotate ladder**, select a **Ladder preset**, and **Continue**.
   Select the **Ladder lane**, click **Use this lane**, and match each size to its
   band. Or choose **Manual ladder** to enter labels such as **500 bp** or
   **25 kDa** yourself. Select a manual label to edit or delete it; use
   **Move marker** to reposition it. Finish with **Confirm ladder annotations**,
   or choose **Skip** / **Skip ladder** if you do not need a reference.
7. **Mark extracted bands, if needed.** After completing or skipping the ladder,
   choose **Mark extracted bands** and drag rectangles around bands in any
   direction. Red outlines leave the bands visible. Use a band's **Remove**
   button to correct a rectangle, then **Done marking** to include the marks in
   the final image. **Cancel** discards the current drawing session's changes.
8. **Save the image.** Choose **Image file type**: PNG, JPEG, TIFF, or SVG.
   PNG is a simple choice for a lab notebook. Leave **Print setting (DPI)** at
   its default unless you need a particular print setting. Click
   **Download annotated PNG** (the name follows your chosen format), then choose
   where to save it. The desktop save dialog keeps the filename extension
   consistent with the selected format. Use **Edit annotations** if labels need
   correcting.

> [!IMPORTANT]
> **Export before closing the app or replacing the image.** Editable work lasts
> only for the current session; an exported image cannot reopen that work.
> Keep your original gel image. **Replace image** starts over and discards the
> current lanes, crop, and labels.

## Testing status

**Windows manual testing is pending.** The automated suite checks installation,
reinstallation, a simulated upgrade, shortcuts, uninstall, native-window startup,
backend cleanup, synthetic image uploads, interactive controls, and exports
on GitHub's Windows Server runner. See the release notes for the current build
results. A clean Windows 10/11 PC, installation without an existing WebView2
runtime while offline, the downloaded file's SmartScreen experience, and native
save dialogs have not been manually verified. The installer should be treated
as awaiting real-PC validation.

The [v1.0.5 release notes](https://github.com/BRPollak/gel-analyzer/releases/tag/v1.0.5)
list the completed checks and remaining limits for each platform, including
Mac native save-dialog checks for the export fix. Release assets include
validation records and checksums for inspecting the build evidence.

## Optional: run locally in a browser

The installers above are the easiest way to use Gel Analyzer. If you prefer to
run from source, expand the instructions below.

<details>
<summary>Browser setup with terminal commands (macOS or Windows)</summary>

Use this alternative on macOS or Windows with an internet connection for setup
and a web browser. Install **uv** below; it downloads Python 3.12 and the app's
supporting software for you.

### First-time setup

1. Open the [repository](https://github.com/BRPollak/gel-analyzer) and select
   **Code → Download ZIP**. On macOS, double-click the ZIP;
   on Windows, right-click it and choose **Extract All**. Keep the extracted
   folder somewhere you can find again. Use the folder containing `app.py`
   and `pyproject.toml`, which may be inside another folder on Windows.
2. Install uv using the instructions for your computer below. Paste each command
   into the specified app and press Return (Mac) or Enter (Windows).

**macOS**

Open **Terminal** from **Applications → Utilities** and run:

```sh
curl -LsSf https://astral.sh/uv/install.sh | sh
```

Quit and reopen Terminal. Type `cd` followed by a space, drag the extracted
folder containing `app.py` from Finder into Terminal, then press Return.
This tells Terminal which folder to use.

**Windows**

Open the Start menu, search for **PowerShell**, and open it. Run:

```powershell
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

The policy option applies only to this installer process. Close PowerShell.
In File Explorer, open the extracted folder containing `app.py`, click the
address bar, type `powershell`, and press Enter to open a new window in that
folder.

These are the [official uv installer commands](https://docs.astral.sh/uv/getting-started/installation/).
If `uv` is not recognized, close and reopen Terminal or PowerShell and return
to the extracted folder as described above.

**Both macOS and Windows**

Run this in that folder and wait for it to finish:

```sh
uv sync --locked --no-dev
```

### Launch the app, now and next time

Open Terminal or PowerShell in the extracted folder using the steps above.
After the first setup, you only need this command:

```sh
uv run --locked --no-dev python -m streamlit run app.py --server.address 127.0.0.1 --server.port 8502 --server.headless true
```

Leave that window open. Open [http://127.0.0.1:8502](http://127.0.0.1:8502) in
your browser and follow **Use the app** above. This address connects to the app
running on your own computer.

To stop, export your results, return to Terminal or PowerShell, and press
**Ctrl+C** (Control, not Command, on Mac). Closing the browser tab alone does
not stop the app. If startup says port 8502 is already in use, change `8502`
to `8503` in the launch command and open `http://127.0.0.1:8503` instead.

</details>

## Build the app

See [Windows packaging and verification](docs/windows-packaging.md) for Windows
build instructions. On an Apple Silicon Mac, use the locked Python 3.12 environment:

```sh
uv run --locked --group desktop --group build python scripts/build_macos.py
```

Build outputs are placed in `dist/`. These commands are for developers;
normal installation uses the downloads above.
