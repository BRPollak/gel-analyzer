# Agarose Gel Analyzer

Turn a photo of a gel—a material used to separate DNA pieces by size—into a
labeled image and a table of results. Straighten and crop images, label samples,
find **bands** (visible stripes), and estimate their sizes using a reference
sample. Analysis runs on your computer.

## Install and open the Mac app

Requires an **Apple Silicon Mac (M1 or later) with macOS 14 or later**. Check
**Apple menu → About This Mac**. Python and everything else the app needs are
included.

1. Open the [Mac download page](https://github.com/BRPollak/gel-analyzer/releases/tag/v1.0.1).
   Under **Assets**, download `Gel-Analyzer-1.0.1-macOS-arm64.dmg`.
2. Double-click the downloaded DMG, then drag **Gel Analyzer.app** onto
   **Applications** in the window that opens.
3. Eject the disk image in Finder. Open **Applications** and double-click
   **Gel Analyzer**.

### If macOS blocks the app

The app is **not notarized by Apple**, so macOS may say the developer cannot be
verified or Apple cannot check it for malicious software. Proceed only if you
trust the download source and are sure the app has not been altered.

1. Try opening **Gel Analyzer** from Applications, then dismiss the warning.
2. Open **Apple menu → System Settings → Privacy & Security** and scroll to
   **Security**. If **Allow apps downloaded from** is set to **App Store** only,
   select **App Store and identified developers**.
3. Find the message about **Gel Analyzer** and click **Open Anyway** (some macOS
   versions show **Open** first). Confirm opening it and enter your Mac login
   password if asked. This saves an exception for this app.

If the option is missing, try opening the app again and return to these settings
within an hour. On a managed work or school Mac, you may need your administrator's
help. See [Apple's security guidance](https://support.apple.com/en-us/102445) and
[app-specific opening steps](https://support.apple.com/guide/mac-help/open-a-mac-app-from-an-unknown-developer-mh40616/mac).

## Use the app

These steps work in both versions. Check automatic suggestions against your
image and correct them before relying on the results.

1. **Open an image.** Under **Open a gel image**, click **Upload** and choose one
   TIFF, PNG, or JPEG file. The app crops the surrounding background when it can.
2. **Orient it.** **Wells** are the small pockets where samples were loaded.
   Set **Workflow orientation** to **Wells at left** or **Wells at top** for the
   arrangement you want. Click **Rotate and Orient**, inspect the preview, then
   **Confirm**. To fix an outline, use **Adjust outline manually**; this editor
   also opens if detection fails. Drag to draw a rectangle if none appears,
   drag inside to move it, use corners to resize and the round handle to rotate.
   Click **Preview manual orientation**, then **Confirm**.
3. **Find the samples.** Click **Define wells**. Click two points spanning the
   outside edges of the first and last wells, with the guide passing through
   their centers: vertically for wells at left, horizontally for wells at top.
   Enter **Number of wells (optional)** if you know the count; otherwise leave
   it blank. Click **Confirm**.
4. **Check and crop.** Each **lane** is one sample's path through the gel.
   Click **Confirm** if the proposed lanes look right, or **Adjust** to drag
   their borders, remove one with its trash button, or **Add lane**, then
   **Confirm**. Drag the shared right edge (wells at left) or bottom edge
   (wells at top) to include the bands you want. Click **Confirm lanes and crop**.
5. **Label samples.** Click a lane label on the image and type a name. Optionally
   use **Create lane groups** to label related samples together. Click
   **Confirm annotations**.
6. **Add a size reference, if available.** A **ladder** is a reference sample
   with bands of known sizes. Choose **Annotate ladder**, select the
   **Ladder preset** matching your experiment, and click **Continue**. Select
   **Ladder lane**, click **Use this lane**, then choose each size and click its
   matching band. Finish with **Confirm ladder annotations**. Without a matching
   ladder, choose **Skip** at the initial offer or **Skip ladder** in the editor.
   DNA sizes use **bp** (base pairs, a measure of DNA length).
   Size estimates need at least two different known
   sizes, with smaller pieces farther along the lane; estimates are limited
   to the range between marked bands.
7. **Review measurements, if needed.** Expand **Review bands and estimate
   sizes** to inspect the proposed bands. Edit **Lane** or **Migration (px)**
   (distance in image pixels from the crop's left or top edge), then click
   **Apply band edits**. **Download band measurements (CSV)** saves a table
   you can open in a spreadsheet; **Download band review (PNG)** saves the
   image with detected bands marked.
8. **Save your labeled image.** Choose **Image file type**: PNG, JPEG, TIFF, or
   SVG. PNG is a simple choice for sharing. Leave **Resolution (DPI)** at its
   default unless you need a particular print setting, then click
   **Download annotated PNG** (the button name follows your chosen format).
   Use **Edit annotations** if labels need correcting.

**Export before closing the app or changing images.** Editable work lasts only
for the current session; exported images and CSV files cannot reopen that work.
Keep your original gel image. Use **Change image** to start another gel.

## Run locally in a browser

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
