"""The tray icon and the global hotkey: the parts that work without a desktop."""

import os

import pytest

from indra_ocr import tray


def test_hotkeys_are_parsed_into_modifiers_and_a_key():
    assert tray.parse_hotkey("ctrl+alt+o") == (tray.MOD_CTRL | tray.MOD_ALT, ord("O"))
    assert tray.parse_hotkey("Shift+F5") == (tray.MOD_SHIFT, 0x74)
    assert tray.parse_hotkey("ctrl+alt+space") == (
        tray.MOD_CTRL | tray.MOD_ALT,
        0x20,
    )
    assert tray.parse_hotkey("win+1") == (tray.MOD_WIN, ord("1"))


@pytest.mark.parametrize("spec", ["o", "", "ctrl", "ctrl+nope", "ctrl++", "ctrl+alt"])
def test_a_hotkey_without_a_usable_key_is_rejected(spec):
    # A bare key would take that key away from every other program.
    assert tray.parse_hotkey(spec) is None


def test_the_tray_icon_is_drawn_with_the_cyan_line():
    im = tray.icon_image(64)
    assert im.size == (64, 64) and im.mode == "RGBA"
    raw = im.tobytes()
    pixels = [raw[i : i + 4] for i in range(0, len(raw), 4)]
    assert any(p[3] == 255 and p[2] > 150 and p[0] < 90 for p in pixels)  # cyan
    assert im.getpixel((0, 0))[3] == 0  # rounded corner


def test_a_hotkey_on_another_platform_says_so(monkeypatch):
    monkeypatch.setattr(tray.os, "name", "posix")
    key = tray.Hotkey("ctrl+alt+o", lambda: None)
    assert key.start() is False
    assert "Windows-only" in key.error


def test_an_unusable_hotkey_reports_the_spec(monkeypatch):
    if os.name != "nt":
        pytest.skip("RegisterHotKey is Windows-only")
    key = tray.Hotkey("nonsense", lambda: None)
    assert key.start() is False
    assert "nonsense" in key.error
