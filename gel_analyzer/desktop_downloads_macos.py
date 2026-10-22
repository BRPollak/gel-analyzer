"""Format-constrained Cocoa downloads for the supported pywebview 6 backend."""

import logging
from pathlib import Path
from tempfile import TemporaryDirectory

from .desktop_downloads import download_format, export_extensions, valid_export_path


LOGGER = logging.getLogger("gel_analyzer.desktop")


class PendingDownload:
    """WKDownload needs a nonexistent file, even after the user chose Replace."""

    def __init__(self, destination: str):
        self.destination = Path(destination)
        self.directory = TemporaryDirectory(prefix=".gel-analyzer-", dir=self.destination.parent)
        self.path = Path(self.directory.name) / self.destination.name

    def finish(self) -> None:
        # Stage on the same volume so replacement is atomic. An interrupted
        # transfer never deletes or truncates an existing user-approved image.
        try:
            self.path.replace(self.destination)
        finally:
            self.cancel()

    def cancel(self) -> None:
        self.directory.cleanup()


def report_download_error(cocoa) -> None:
    alert = cocoa.AppKit.NSAlert.alloc().init()
    alert.setMessageText_("Unable to save image")
    alert.setInformativeText_("The image could not be saved. Please download it again.")
    alert.runModal()


def save_destination(cocoa, response, suggested_filename: str):
    """Return only the exact URL approved by a type-constrained save panel."""
    image_format = download_format(response.MIMEType(), suggested_filename)
    if image_format is None or not cocoa.webview_settings["ALLOW_DOWNLOADS"]:
        return None

    from UniformTypeIdentifiers import UTType

    extension = export_extensions(image_format)[0]
    panel = cocoa.AppKit.NSSavePanel.savePanel()
    panel.setTitle_(f"Save annotated {image_format}")
    panel.setAllowedContentTypes_([UTType.typeWithFilenameExtension_(extension)])
    panel.setAllowsOtherFileTypes_(False)
    panel.setCanSelectHiddenExtension_(False)
    panel.setExtensionHidden_(False)
    directory = cocoa.Foundation.NSSearchPathForDirectoriesInDomains(
        cocoa.Foundation.NSDownloadsDirectory, cocoa.Foundation.NSUserDomainMask, True,
    )[0]
    panel.setDirectoryURL_(cocoa.Foundation.NSURL.fileURLWithPath_(directory))
    filename = Path(suggested_filename).name or "annotated"
    if not valid_export_path(filename, image_format):
        filename = f"{filename.rstrip('.')}.{extension}"
    panel.setNameFieldStringValue_(filename)

    while panel.runModal() == cocoa.AppKit.NSFileHandlingPanelOKButton:
        url = panel.URL()
        if valid_export_path(str(url.path()), image_format):
            return url
        # Normally AppKit adds/enforces the suffix itself. If it ever returns an
        # invalid name, re-present the corrected name for native overwrite
        # confirmation; never silently change the destination after approval.
        filename = Path(str(url.path())).name.rstrip(".")
        panel.setNameFieldStringValue_(f"{filename}.{extension}")
    return None


def install_macos_downloads(cocoa) -> None:
    if getattr(cocoa, "_gel_downloads_installed", False):
        return
    original_browser_delegate = cocoa.BrowserView.BrowserDelegate

    class GelAnalyzerDownloadDelegate(cocoa.BrowserView.DownloadDelegate):
        def download_decideDestinationUsingResponse_suggestedFilename_completionHandler_(
            self, download, response, suggested_filename, completion_handler,
        ):
            self.pending_download = None
            try:
                destination = save_destination(cocoa, response, suggested_filename)
                if destination is None:
                    completion_handler(None)
                    return
                self.pending_download = PendingDownload(str(destination.path()))
                url = cocoa.Foundation.NSURL.fileURLWithPath_(str(self.pending_download.path))
            except Exception:
                LOGGER.exception("Unable to prepare image download")
                completion_handler(None)
                report_download_error(cocoa)
                return
            completion_handler(url)

        def downloadDidFinish_(self, download):
            pending = self.pending_download
            self.pending_download = None
            if pending is not None:
                try:
                    pending.finish()
                except Exception:
                    LOGGER.exception("Unable to finish image download")
                    report_download_error(cocoa)

        def download_didFailWithError_resumeData_(self, download, error, resume_data):
            pending = self.pending_download
            self.pending_download = None
            if pending is not None:
                pending.cancel()
                LOGGER.error("Image download failed: %s", error)
                report_download_error(cocoa)

    class GelAnalyzerBrowserDelegate(original_browser_delegate):
        def webView_decidePolicyForNavigationResponse_decisionHandler_(
            self, webview, navigation_response, decision_handler,
        ):
            if navigation_response.canShowMIMEType():
                return original_browser_delegate.webView_decidePolicyForNavigationResponse_decisionHandler_(
                    self, webview, navigation_response, decision_handler,
                )
            response = navigation_response.response()
            if (cocoa.webview_settings["ALLOW_DOWNLOADS"]
                    and download_format(response.MIMEType(), response.suggestedFilename())):
                # Use the same WKDownload destination callback for attachments
                # and download links, avoiding pywebview's unfiltered fallback.
                decision_handler(cocoa.WebKit.WKNavigationResponsePolicyDownload)
            else:
                decision_handler(cocoa.WebKit.WKNavigationResponsePolicyCancel)

        def webView_navigationResponse_didBecomeDownload_(
            self, webview, navigation_response, download,
        ):
            download.setDelegate_(cocoa.BrowserView.DownloadDelegate.alloc().init().retain())

    cocoa.BrowserView.DownloadDelegate = GelAnalyzerDownloadDelegate
    cocoa.BrowserView.BrowserDelegate = GelAnalyzerBrowserDelegate
    cocoa._gel_downloads_installed = True
