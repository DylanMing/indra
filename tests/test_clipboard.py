"""Reading the image on the clipboard, for the viewer's fallback button."""

import subprocess

from indra_ocr import clipboard

PNG = clipboard.PNG_MAGIC + b"0" * 16


def test_no_clipboard_means_none(monkeypatch):
    monkeypatch.setattr(clipboard, "_from_pillow", lambda: None)
    monkeypatch.setattr(clipboard.shutil, "which", lambda *a, **k: None)
    assert clipboard.grab_image() is None


def test_wl_paste_is_used_when_pillow_has_nothing(monkeypatch):
    monkeypatch.setattr(clipboard, "_from_pillow", lambda: None)
    monkeypatch.setattr(
        clipboard.shutil, "which", lambda n: "/usr/bin/" + n if n == "wl-paste" else None
    )
    calls = []

    def run(cmd, **kw):
        calls.append(cmd)
        return subprocess.CompletedProcess(cmd, 0, PNG, b"")

    monkeypatch.setattr(clipboard.subprocess, "run", run)
    assert clipboard.grab_image() == PNG
    assert calls and calls[0][0] == "wl-paste"


def test_text_on_the_clipboard_is_not_an_image(monkeypatch):
    monkeypatch.setattr(clipboard, "_from_pillow", lambda: None)
    monkeypatch.setattr(
        clipboard.shutil, "which", lambda n: "/usr/bin/" + n if n == "xclip" else None
    )
    monkeypatch.setattr(
        clipboard.subprocess,
        "run",
        lambda cmd, **kw: subprocess.CompletedProcess(cmd, 0, b"just text", b""),
    )
    assert clipboard.grab_image() is None


def test_a_failing_tool_is_skipped(monkeypatch):
    monkeypatch.setattr(clipboard, "_from_pillow", lambda: None)
    monkeypatch.setattr(clipboard.shutil, "which", lambda n: "/usr/bin/" + n)

    def run(cmd, **kw):
        if cmd[0] == "wl-paste":
            raise OSError("no wayland")
        return subprocess.CompletedProcess(cmd, 0, PNG, b"")

    monkeypatch.setattr(clipboard.subprocess, "run", run)
    assert clipboard.grab_image() == PNG
