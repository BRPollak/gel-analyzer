"""Restrict WebView2 image downloads at the native Save As dialog."""

from __future__ import annotations

import logging
import ntpath

from .desktop_downloads import download_format, export_extensions, valid_export_path


LOGGER = logging.getLogger("gel_analyzer.desktop")


def install_windows_downloads(edgechromium) -> None:
    """Install before EdgeChrome subscribes its DownloadStarting handler."""
    forms = edgechromium.WinForms

    def choose_destination(owner, image_format, suggested_name):
        dialog = None
        validate_filename = None
        validator_attached = False
        try:
            extensions = export_extensions(image_format)
            if not valid_export_path(suggested_name, image_format):
                suggested_name = ntpath.splitext(suggested_name)[0] + "." + extensions[0]

            dialog = forms.SaveFileDialog()
            patterns = ";".join("*." + extension for extension in extensions)
            dialog.Filter = f"{image_format} image ({patterns})|{patterns}"
            dialog.FilterIndex = 1
            dialog.DefaultExt = extensions[0]
            dialog.AddExtension = True
            dialog.OverwritePrompt = True
            dialog.CheckPathExists = True
            dialog.RestoreDirectory = True
            dialog.FileName = suggested_name
            try:
                with edgechromium.winreg.OpenKey(
                    edgechromium.winreg.HKEY_CURRENT_USER,
                    r"Software\Microsoft\Windows\CurrentVersion\Explorer\Shell Folders",
                ) as windows_key:
                    dialog.InitialDirectory = edgechromium.winreg.QueryValueEx(
                        windows_key, "{374DE290-123F-4565-9164-39C4925E467B}"
                    )[0]
            except OSError:
                # Windows retains a useful default if the Downloads key is absent.
                pass

            def validate_filename(sender, event):
                if not valid_export_path(dialog.FileName, image_format):
                    event.Cancel = True
                    allowed = " or ".join("." + extension for extension in extensions)
                    forms.MessageBox.Show(
                        owner,
                        f"This is a {image_format} image. Use a filename ending in {allowed}.",
                        "Save image",
                        forms.MessageBoxButtons.OK,
                        forms.MessageBoxIcon.Information,
                    )

            dialog.FileOk += validate_filename
            validator_attached = True
            if (dialog.ShowDialog(owner) == forms.DialogResult.OK
                    and valid_export_path(dialog.FileName, image_format)):
                # Keep precisely the destination whose overwrite was confirmed.
                return dialog.FileName
            return None
        finally:
            if dialog is not None:
                try:
                    if validator_attached:
                        dialog.FileOk -= validate_filename
                finally:
                    dialog.Dispose()

    def on_download_starting(self, sender, args):
        # WebView2 otherwise may offer a second, unrestricted save dialog.
        args.Handled = True
        args.Cancel = True
        if not edgechromium.webview_settings["ALLOW_DOWNLOADS"]:
            return

        deferral = None
        try:
            suggested_name = ntpath.basename(str(args.ResultFilePath))
            image_format = download_format(args.DownloadOperation.MimeType, suggested_name)
            if image_format is None:
                LOGGER.warning("Cancelled download with an unsupported image format")
                return

            deferral = args.GetDeferral()

            def show_save_dialog():
                try:
                    destination = choose_destination(self.form, image_format, suggested_name)
                    if destination is not None:
                        args.ResultFilePath = destination
                        args.Cancel = False
                except Exception:
                    LOGGER.exception("Unable to save image download")
                finally:
                    deferral.Complete()

            # A modal dialog inside DownloadStarting would reenter WebView2's
            # event loop. Post it to the same UI thread after this event returns,
            # retaining its event arguments until the destination is decided.
            self.form.BeginInvoke(edgechromium.Action(show_save_dialog))
        except Exception:
            LOGGER.exception("Unable to start image download dialog")
            if deferral is not None:
                deferral.Complete()

    edgechromium.EdgeChrome.on_download_starting = on_download_starting
