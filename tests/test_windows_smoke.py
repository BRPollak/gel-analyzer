"""Temporary WebView2 inspection policy must leave machine settings intact."""

from copy import deepcopy
from pathlib import Path

import pytest

from scripts import smoke_windows


POLICY = r"SOFTWARE\Policies\Microsoft\Edge\WebView2"
ARGUMENTS = POLICY + r"\AdditionalBrowserArguments"
PROFILE = POLICY + r"\UserDataFolder"
APPLICATION = "Gel Analyzer.exe"


class RegistryKey:
    def __init__(self, path):
        self.path = path

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def Close(self):
        pass


class FakeRegistry:
    HKEY_LOCAL_MACHINE = object()
    KEY_READ = 0x20019
    KEY_WRITE = 0x20006
    KEY_WOW64_64KEY = 0x100
    REG_SZ = 1
    REG_EXPAND_SZ = 2

    def __init__(self):
        parts = POLICY.split("\\")
        self.keys = {"\\".join(parts[:end]): {} for end in range(1, len(parts) + 1)}
        self.fail_next_set = None

    def OpenKey(self, root, path, reserved=0, access=0):
        assert root is self.HKEY_LOCAL_MACHINE
        assert access & self.KEY_WOW64_64KEY
        if path not in self.keys:
            raise FileNotFoundError(path)
        return RegistryKey(path)

    def CreateKeyEx(self, root, path, reserved=0, access=0):
        assert root is self.HKEY_LOCAL_MACHINE
        assert access & self.KEY_WOW64_64KEY
        self.keys.setdefault(path, {})
        return RegistryKey(path)

    def QueryValueEx(self, key, name):
        try:
            return self.keys[key.path][name]
        except KeyError:
            raise FileNotFoundError(name) from None

    def SetValueEx(self, key, name, reserved, value_type, value):
        if self.fail_next_set == key.path:
            self.fail_next_set = None
            raise PermissionError("Simulated policy write failure")
        self.keys[key.path][name] = (value, value_type)

    def DeleteValue(self, key, name):
        try:
            del self.keys[key.path][name]
        except KeyError:
            raise FileNotFoundError(name) from None

    def QueryInfoKey(self, key):
        prefix = key.path + "\\"
        children = {path[len(prefix):].split("\\")[0] for path in self.keys
                    if path.startswith(prefix)}
        return len(children), len(self.keys[key.path]), 0

    def DeleteKeyEx(self, root, path, access, reserved=0):
        assert root is self.HKEY_LOCAL_MACHINE
        assert access == self.KEY_WOW64_64KEY
        if any(candidate.startswith(path + "\\") for candidate in self.keys):
            raise OSError("Registry key has children")
        del self.keys[path]


def test_temporary_policy_restores_existing_values_and_types():
    registry = FakeRegistry()
    registry.keys[ARGUMENTS] = {
        APPLICATION: ("--existing-argument", registry.REG_EXPAND_SZ),
        "Other App.exe": ("--other-argument", registry.REG_SZ),
    }
    registry.keys[PROFILE] = {APPLICATION: ("%LOCALAPPDATA%\\Existing", registry.REG_EXPAND_SZ)}
    before = deepcopy(registry.keys)
    profile = Path("temporary-profile")

    with smoke_windows.temporary_webview2_policy(registry, APPLICATION, 49152, profile):
        assert registry.keys[ARGUMENTS][APPLICATION] == ("--remote-debugging-port=49152", registry.REG_SZ)
        assert registry.keys[PROFILE][APPLICATION] == (str(profile), registry.REG_SZ)
        assert registry.keys[ARGUMENTS]["Other App.exe"] == before[ARGUMENTS]["Other App.exe"]

    assert registry.keys == before


def test_temporary_policy_rolls_back_when_smoke_body_fails():
    registry = FakeRegistry()
    registry.keys[ARGUMENTS] = {APPLICATION: ("--existing-argument", registry.REG_SZ)}
    before = deepcopy(registry.keys)

    with pytest.raises(RuntimeError, match="Native smoke failed"):
        with smoke_windows.temporary_webview2_policy(registry, APPLICATION, 49152, Path("profile")):
            raise RuntimeError("Native smoke failed")

    assert registry.keys == before


def test_temporary_policy_rolls_back_partial_setup_failure():
    registry = FakeRegistry()
    registry.keys[ARGUMENTS] = {APPLICATION: ("--existing-argument", registry.REG_EXPAND_SZ)}
    registry.fail_next_set = PROFILE
    before = deepcopy(registry.keys)

    with pytest.raises(PermissionError, match="Simulated policy write failure"):
        with smoke_windows.temporary_webview2_policy(registry, APPLICATION, 49152, Path("profile")):
            pytest.fail("A failed policy setup must not launch the smoke test")

    assert registry.keys == before


def test_temporary_policy_removes_created_empty_keys():
    registry = FakeRegistry()
    before = deepcopy(registry.keys)

    with smoke_windows.temporary_webview2_policy(registry, APPLICATION, 49152, Path("profile")):
        assert ARGUMENTS in registry.keys
        assert PROFILE in registry.keys

    assert registry.keys == before


def test_temporary_policy_removes_new_empty_parent_hierarchy():
    registry = FakeRegistry()
    registry.keys = {"SOFTWARE": {}}
    before = deepcopy(registry.keys)

    with smoke_windows.temporary_webview2_policy(registry, APPLICATION, 49152, Path("profile")):
        assert ARGUMENTS in registry.keys
        assert PROFILE in registry.keys

    assert registry.keys == before


def test_temporary_policy_keeps_preexisting_empty_keys():
    registry = FakeRegistry()
    registry.keys[ARGUMENTS] = {}
    registry.keys[PROFILE] = {}
    before = deepcopy(registry.keys)

    with smoke_windows.temporary_webview2_policy(registry, APPLICATION, 49152, Path("profile")):
        pass

    assert registry.keys == before


def test_temporary_policy_preserves_unrelated_values_added_during_smoke():
    registry = FakeRegistry()
    before = deepcopy(registry.keys)

    with smoke_windows.temporary_webview2_policy(registry, APPLICATION, 49152, Path("profile")):
        registry.keys[ARGUMENTS]["Other App.exe"] = ("--other-argument", registry.REG_SZ)

    assert registry.keys == {
        **before,
        ARGUMENTS: {"Other App.exe": ("--other-argument", registry.REG_SZ)},
    }
