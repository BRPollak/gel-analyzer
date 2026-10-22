"""Export type recognition and Cocoa destination/adapter regressions."""

import sys
from types import SimpleNamespace

import pytest

from gel_analyzer.desktop_downloads import configure_downloads, download_format, valid_export_path
from gel_analyzer.desktop_downloads_macos import PendingDownload, install_macos_downloads, save_destination


@pytest.mark.parametrize("mime,name,expected", [
    ("image/png", "missing extension", "PNG"),
    ("IMAGE/JPEG; charset=binary", "wrong.png", "JPEG"),
    ("image/tiff", "wrong.svg", "TIFF"),
    ("image/svg+xml", "wrong.jpg", "SVG"),
    (None, "gel.TIF", "TIFF"),
    ("application/octet-stream", "gel.JPEG", "JPEG"),
    ("application/pdf", "misleading.png", None),
    ("text/html", "misleading.svg", None),
    ("", "extensionless", None),
    ("application/octet-stream", "unknown.txt", None),
])
def test_download_format_uses_response_type_before_filename(mime, name, expected):
    assert download_format(mime, name) == expected


@pytest.mark.parametrize("name", ["gel", "gel.", "gel.jpg", "gel.png.txt", "gel.png ", ".png"])
def test_png_destination_rejects_missing_or_mismatched_extension(name):
    assert not valid_export_path(name, "PNG")


@pytest.mark.parametrize("renderer,backend,adapter", [
    ("wkwebview", "cocoa", "macos"), ("edgechromium", "edgechromium", "windows"),
])
@pytest.mark.parametrize("fail", [True, False])
def test_downloads_only_enable_after_native_adapter_is_installed(monkeypatch, renderer, backend, adapter, fail):
    settings = {"ALLOW_DOWNLOADS": True}
    native = object()
    monkeypatch.setitem(sys.modules, "webview", SimpleNamespace(settings=settings))
    monkeypatch.setitem(sys.modules, "webview.platforms", SimpleNamespace(**{backend: native}))
    calls = []

    def install(module):
        assert settings["ALLOW_DOWNLOADS"] is False
        calls.append(module)
        if fail:
            raise RuntimeError("Test adapter failure")

    monkeypatch.setattr(f"gel_analyzer.desktop_downloads_{adapter}.install_{adapter}_downloads", install)
    if fail:
        with pytest.raises(RuntimeError, match="Test adapter failure"):
            configure_downloads(renderer)
    else:
        configure_downloads(renderer)
    assert calls == [native]
    assert settings["ALLOW_DOWNLOADS"] is (not fail)


class SavePanel:
    def __init__(self, selections):
        self.selections = iter(selections)
        self.names = []
        self.selected = None
        self.calls = []

    def setNameFieldStringValue_(self, name):
        self.names.append(name)

    def __getattr__(self, name):
        if name.startswith("set"):
            return lambda value: self.calls.append((name, value))
        raise AttributeError(name)

    def runModal(self):
        selection = next(self.selections)
        if selection is None:
            return 0
        self.selected = SimpleNamespace(path=lambda: selection)
        return 1

    def URL(self):
        return self.selected


@pytest.fixture
def cocoa(monkeypatch):
    monkeypatch.setitem(sys.modules, "UniformTypeIdentifiers", SimpleNamespace(
        UTType=SimpleNamespace(typeWithFilenameExtension_=lambda extension: extension),
    ))
    return SimpleNamespace(
        webview_settings={"ALLOW_DOWNLOADS": True},
        AppKit=SimpleNamespace(NSFileHandlingPanelOKButton=1),
        Foundation=SimpleNamespace(
            NSDownloadsDirectory=15, NSUserDomainMask=1,
            NSSearchPathForDirectoriesInDomains=lambda *_: ["/Downloads"],
            NSURL=SimpleNamespace(fileURLWithPath_=lambda path: path),
        ),
    )


@pytest.mark.parametrize("mime,name,extension", [
    ("image/png", "Gibson-PCR", "png"), ("image/jpeg", "gel", "jpg"),
    ("image/tiff", "gel", "tiff"), ("image/svg+xml", "gel", "svg"),
])
def test_cocoa_constrains_type_and_shows_extension(cocoa, mime, name, extension):
    panel = SavePanel([f"/Gels/{name}.{extension}"])
    cocoa.AppKit.NSSavePanel = SimpleNamespace(savePanel=lambda: panel)
    response = SimpleNamespace(MIMEType=lambda: mime)
    url = save_destination(cocoa, response, name)
    assert url is panel.selected
    assert panel.names == [f"{name}.{extension}"]
    assert ("setAllowedContentTypes_", [extension]) in panel.calls
    assert ("setAllowsOtherFileTypes_", False) in panel.calls
    assert ("setCanSelectHiddenExtension_", False) in panel.calls
    assert ("setExtensionHidden_", False) in panel.calls


@pytest.mark.parametrize("mime,name", [
    ("image/png", "gel.PNG"), ("image/jpeg", "gel.JPEG"),
    ("image/tiff", "gel.TIF"), ("image/svg+xml", "gel.SVG"),
])
def test_cocoa_keeps_exact_confirmed_url_and_valid_alias(cocoa, mime, name):
    panel = SavePanel([f"/Gels/{name}"])
    cocoa.AppKit.NSSavePanel = SimpleNamespace(savePanel=lambda: panel)
    url = save_destination(cocoa, SimpleNamespace(MIMEType=lambda: mime), name)
    assert url is panel.selected
    assert panel.names == [name]


@pytest.mark.parametrize("invalid", ["gel", "gel.", "gel.jpg"])
@pytest.mark.parametrize("cancel", [True, False])
def test_cocoa_rechecks_overwrite_at_corrected_path_if_native_panel_returns_invalid_name(cocoa, invalid, cancel):
    corrected = invalid.rstrip(".") + ".png"
    panel = SavePanel([f"/Gels/{invalid}", None if cancel else f"/Gels/{corrected}"])
    cocoa.AppKit.NSSavePanel = SimpleNamespace(savePanel=lambda: panel)
    url = save_destination(cocoa, SimpleNamespace(MIMEType=lambda: "image/png"), "original.png")
    assert panel.names == ["original.png", corrected]
    assert url is (None if cancel else panel.selected)


def test_cocoa_cancellation_does_not_return_a_destination(cocoa):
    panel = SavePanel([None])
    cocoa.AppKit.NSSavePanel = SimpleNamespace(savePanel=lambda: panel)
    assert save_destination(cocoa, SimpleNamespace(MIMEType=lambda: "image/png"), "gel.png") is None


@pytest.mark.parametrize("mime,enabled", [("text/plain", True), ("image/png", False)])
def test_cocoa_cancels_unsupported_or_disabled_download_without_opening_panel(cocoa, mime, enabled):
    cocoa.webview_settings["ALLOW_DOWNLOADS"] = enabled
    assert save_destination(cocoa, SimpleNamespace(MIMEType=lambda: mime), "looks-valid.png") is None


def test_cocoa_attachment_and_link_downloads_share_constrained_destination(cocoa, monkeypatch, tmp_path):
    calls = []

    class DownloadDelegate:
        @classmethod
        def alloc(cls):
            return cls()

        def init(self):
            return self

        def retain(self):
            return self

    class BrowserDelegate:
        def webView_decidePolicyForNavigationResponse_decisionHandler_(self, view, response, handler):
            calls.append("normal navigation")
            handler(1)

    cocoa.BrowserView = SimpleNamespace(DownloadDelegate=DownloadDelegate, BrowserDelegate=BrowserDelegate)
    cocoa.WebKit = SimpleNamespace(WKNavigationResponsePolicyDownload=2, WKNavigationResponsePolicyCancel=0)
    install_macos_downloads(cocoa)
    installed = cocoa.BrowserView.DownloadDelegate
    install_macos_downloads(cocoa)
    assert cocoa.BrowserView.DownloadDelegate is installed
    browser = cocoa.BrowserView.BrowserDelegate()
    for mime, showable, expected in [("image/png", True, 1), ("image/tiff", False, 2), ("text/plain", False, 0)]:
        response = SimpleNamespace(MIMEType=lambda: mime, suggestedFilename=lambda: "image.tiff")
        navigation = SimpleNamespace(canShowMIMEType=lambda: showable, response=lambda: response)
        browser.webView_decidePolicyForNavigationResponse_decisionHandler_(None, navigation, calls.append)
        assert calls[-1] == expected
    delegates = []
    browser.webView_navigationResponse_didBecomeDownload_(None, None, SimpleNamespace(setDelegate_=delegates.append))
    assert isinstance(delegates[0], installed)
    destination = tmp_path / "gel.png"
    destination.write_bytes(b"previous export")
    sentinel = SimpleNamespace(path=lambda: str(destination))
    monkeypatch.setattr("gel_analyzer.desktop_downloads_macos.save_destination", lambda *_: sentinel)
    delegate = installed()
    delegate.download_decideDestinationUsingResponse_suggestedFilename_completionHandler_(None, None, "gel.png", calls.append)
    staged = delegate.pending_download.path
    assert calls[-1] == str(staged)
    assert not staged.exists(), "WebKit requires a destination that does not exist"
    assert destination.read_bytes() == b"previous export"
    staged.write_bytes(b"new export")
    delegate.downloadDidFinish_(None)
    assert destination.read_bytes() == b"new export"
    assert not staged.parent.exists()

    delegate.download_decideDestinationUsingResponse_suggestedFilename_completionHandler_(None, None, "gel.png", calls.append)
    staged = delegate.pending_download.path
    staged.write_bytes(b"partial transfer")
    monkeypatch.setattr("gel_analyzer.desktop_downloads_macos.report_download_error", lambda _: calls.append("error shown"))
    delegate.download_didFailWithError_resumeData_(None, "test failure", None)
    assert destination.read_bytes() == b"new export"
    assert not staged.parent.exists()
    assert calls[-1] == "error shown"


def test_failed_cocoa_transfer_preserves_existing_export_and_removes_partial_file(tmp_path):
    destination = tmp_path / "gel.png"
    destination.write_bytes(b"previous image")
    pending = PendingDownload(str(destination))
    assert not pending.path.exists()
    pending.path.write_bytes(b"incomplete image")
    pending.cancel()
    assert destination.read_bytes() == b"previous image"
    assert not pending.path.parent.exists()


def test_failed_cocoa_replacement_preserves_existing_export_and_cleans_staging(tmp_path, monkeypatch):
    destination = tmp_path / "gel.png"
    destination.write_bytes(b"previous image")
    pending = PendingDownload(str(destination))
    pending.path.write_bytes(b"new image")

    def fail(*_):
        raise PermissionError("Destination is not writable")

    monkeypatch.setattr(type(pending.path), "replace", fail)
    with pytest.raises(PermissionError):
        pending.finish()
    assert destination.read_bytes() == b"previous image"
    assert not pending.path.parent.exists()
