"""Native Windows save behavior without requiring a Windows desktop."""

import ntpath
from types import SimpleNamespace

import pytest

from gel_analyzer.desktop_downloads_windows import install_windows_downloads


class Event:
    def __init__(self):
        self.callbacks = []

    def __iadd__(self, callback):
        self.callbacks.append(callback)
        return self

    def __isub__(self, callback):
        self.callbacks.remove(callback)
        return self


class SaveDialog:
    def __init__(self, selections, *, disposal_error=False):
        self.selections = selections
        self.FileOk = Event()
        self.disposed = False
        self.rejected = []
        self.shown = False
        self.disposal_error = disposal_error

    def ShowDialog(self, owner):
        self.shown = True
        for selection in self.selections:
            if selection is None:
                return "Cancel"
            if isinstance(selection, Exception):
                raise selection
            self.FileName = selection
            # Emulate the documented native addition before the FileOk callback.
            if self.AddExtension and not ntpath.splitext(self.FileName)[1]:
                self.FileName += "." + self.DefaultExt
            event = SimpleNamespace(Cancel=False)
            for callback in self.FileOk.callbacks:
                callback(self, event)
            if not event.Cancel:
                return "OK"
            self.rejected.append(self.FileName)
        return "Cancel"

    def Dispose(self):
        self.disposed = True
        if self.disposal_error:
            raise RuntimeError("native disposal failed")


class Deferral:
    def __init__(self):
        self.requested = False
        self.completed = 0

    def get(self):
        self.requested = True
        return self

    def Complete(self):
        self.completed += 1


def handler(selections, *, mime="image/png", suggested="original.png", enabled=True,
            dispatch_error=False, disposal_error=False, dispatch=True):
    dialog = SaveDialog(selections, disposal_error=disposal_error)
    messages = []
    created_dialogs = []
    queued_actions = []
    deferral = Deferral()

    def create_dialog():
        created_dialogs.append(dialog)
        return dialog

    def no_registry_key(*_):
        raise FileNotFoundError

    def begin_invoke(action):
        if dispatch_error:
            raise RuntimeError("window was closed")
        queued_actions.append(action)

    edge = SimpleNamespace(
        EdgeChrome=type("EdgeChrome", (), {}),
        webview_settings={"ALLOW_DOWNLOADS": enabled},
        Action=lambda callback: callback,
        WinForms=SimpleNamespace(
            SaveFileDialog=create_dialog,
            DialogResult=SimpleNamespace(OK="OK"),
            MessageBox=SimpleNamespace(Show=lambda *args: messages.append(args)),
            MessageBoxButtons=SimpleNamespace(OK="OK"),
            MessageBoxIcon=SimpleNamespace(Information="Information"),
        ),
        winreg=SimpleNamespace(HKEY_CURRENT_USER="user", OpenKey=no_registry_key),
    )
    install_windows_downloads(edge)
    browser = edge.EdgeChrome()
    browser.form = SimpleNamespace(BeginInvoke=begin_invoke)
    args = SimpleNamespace(
        DownloadOperation=SimpleNamespace(MimeType=mime),
        ResultFilePath=rf"C:\Downloads\{suggested}", Cancel=False, Handled=False,
        GetDeferral=deferral.get, deferral=deferral, queued_actions=queued_actions,
    )
    browser.on_download_starting(None, args)
    assert not created_dialogs  # Never open modal UI during DownloadStarting.
    if dispatch:
        for action in queued_actions:
            action()
        assert deferral.completed == int(deferral.requested)
    return args, dialog, messages, created_dialogs


def test_windows_restores_omitted_extension_before_confirming_destination():
    args, dialog, messages, _ = handler([r"C:\Gels\Gibson-PCR"])
    assert args.ResultFilePath == r"C:\Gels\Gibson-PCR.png"
    assert args.Handled and not args.Cancel
    assert dialog.Filter == "PNG image (*.png)|*.png"
    assert dialog.DefaultExt == "png"
    assert dialog.AddExtension and dialog.OverwritePrompt and dialog.CheckPathExists
    assert dialog.disposed and not dialog.FileOk.callbacks
    assert not messages


def test_windows_rejects_mismatched_suffix_before_corrected_destination_is_confirmed():
    args, dialog, messages, _ = handler([r"C:\Gels\gel.jpg", r"C:\Gels\gel.png"])
    assert dialog.rejected == [r"C:\Gels\gel.jpg"]
    assert args.ResultFilePath == r"C:\Gels\gel.png"
    assert not args.Cancel
    assert len(messages) == 1 and ".png" in messages[0][1]


@pytest.mark.parametrize(("mime", "extension"), [
    ("image/png", "PNG"), ("image/jpeg", "jpg"), ("image/jpeg", "JPEG"),
    ("image/tiff", "tiff"), ("image/tiff", "TIF"), ("image/svg+xml", "SVG"),
])
def test_windows_keeps_confirmed_destination_and_valid_aliases(mime, extension):
    destination = rf"C:\Gels\gel.{extension}"
    args, dialog, messages, _ = handler([destination], mime=mime)
    assert args.ResultFilePath == destination
    assert not args.Cancel and not messages
    assert dialog.OverwritePrompt and dialog.disposed


@pytest.mark.parametrize("selections", [[None], [r"C:\Gels\gel.txt", None]])
def test_windows_cancel_never_changes_download_destination(selections):
    args, dialog, _, _ = handler(selections)
    assert args.Cancel and args.Handled
    assert args.ResultFilePath == r"C:\Downloads\original.png"
    assert dialog.disposed


@pytest.mark.parametrize(("mime", "suggested", "enabled"), [
    ("text/plain", "looks-valid.png", True), ("", "unknown", True),
    ("image/png", "image.png", False),
])
def test_windows_cancels_unsupported_or_disabled_download_without_save_dialog(mime, suggested, enabled):
    args, _, _, created = handler([], mime=mime, suggested=suggested, enabled=enabled)
    assert args.Cancel and args.Handled
    assert not created


def test_windows_cancels_and_disposes_when_native_dialog_fails():
    args, dialog, _, _ = handler([RuntimeError("native dialog failed")])
    assert args.Cancel and args.Handled
    assert args.ResultFilePath == r"C:\Downloads\original.png"
    assert dialog.disposed and not dialog.FileOk.callbacks


def test_windows_defers_until_native_ui_queue_runs_after_event_returns():
    args, dialog, _, created = handler([r"C:\Gels\gel.png"], dispatch=False)
    assert args.deferral.requested and args.deferral.completed == 0
    assert args.Cancel and not created and not dialog.shown
    assert len(args.queued_actions) == 1
    args.queued_actions[0]()
    assert args.deferral.completed == 1
    assert not args.Cancel and dialog.shown and dialog.disposed
    assert args.ResultFilePath == r"C:\Gels\gel.png"


def test_windows_completes_cancelled_deferral_if_ui_dispatch_fails():
    args, dialog, _, created = handler([r"C:\Gels\gel.png"], dispatch_error=True)
    assert args.deferral.requested and args.deferral.completed == 1
    assert args.Cancel and not created and not dialog.shown


def test_windows_completes_deferral_even_if_native_cleanup_throws():
    args, dialog, _, _ = handler([r"C:\Gels\gel.png"], disposal_error=True)
    assert args.deferral.completed == 1
    assert args.Cancel and dialog.disposed
    assert args.ResultFilePath == r"C:\Downloads\original.png"
