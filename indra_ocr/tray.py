"""A tray icon and a global hotkey for the desktop app.

Both are optional.  pystray missing (or a Linux session without a tray) means no
icon; the hotkey uses Windows' ``RegisterHotKey``, so other platforms get none.
The app works without either: the tray only changes what closing the window does.
"""

from __future__ import annotations

import ctypes
import os
import threading
from typing import Callable

TITLE = "Indra OCR"

# RegisterHotKey modifiers
MOD_ALT, MOD_CTRL, MOD_SHIFT, MOD_WIN = 0x0001, 0x0002, 0x0004, 0x0008
WM_HOTKEY, WM_QUIT = 0x0312, 0x0012

NAMED = {
    "space": 0x20,
    "enter": 0x0D,
    "return": 0x0D,
    "tab": 0x09,
    "esc": 0x1B,
    "escape": 0x1B,
    "printscreen": 0x2C,
    "insert": 0x2D,
}


def parse_hotkey(spec: str) -> tuple[int, int] | None:
    """``"ctrl+alt+o"`` -> (modifiers, virtual-key code), or None if unusable.

    At least one modifier is required: a bare key would take that key away from
    every other program.
    """
    parts = [p.strip().lower() for p in spec.replace(" ", "").split("+") if p.strip()]
    if len(parts) < 2:
        return None
    mods = 0
    for name in parts[:-1]:
        bit = {"ctrl": MOD_CTRL, "control": MOD_CTRL, "alt": MOD_ALT,
               "shift": MOD_SHIFT, "win": MOD_WIN, "cmd": MOD_WIN}.get(name)
        if bit is None:
            return None
        mods |= bit
    key = parts[-1]
    if len(key) == 1 and key.isalnum():
        vk = ord(key.upper())
    elif key.startswith("f") and key[1:].isdigit() and 1 <= int(key[1:]) <= 24:
        vk = 0x70 + int(key[1:]) - 1
    else:
        vk = NAMED.get(key)
    if not vk:
        return None
    return mods, vk


class Hotkey:
    """A global hotkey in its own thread, with a message loop to receive it."""

    def __init__(self, spec: str, callback: Callable[[], None]):
        self.spec = spec
        self.callback = callback
        self.error: str | None = None
        self.ok = False
        self._ready = threading.Event()
        self._thread: threading.Thread | None = None
        self._thread_id = 0

    def start(self) -> bool:
        if os.name != "nt":
            self.error = "global hotkeys are Windows-only for now"
            return False
        parsed = parse_hotkey(self.spec)
        if parsed is None:
            self.error = f"cannot use {self.spec!r} as a hotkey (try ctrl+alt+o)"
            return False
        self._thread = threading.Thread(target=self._run, args=parsed, daemon=True)
        self._thread.start()
        self._ready.wait(3)
        return self.ok

    def _run(self, mods: int, vk: int) -> None:
        from ctypes import wintypes

        user32 = ctypes.windll.user32
        self._thread_id = ctypes.windll.kernel32.GetCurrentThreadId()
        if not user32.RegisterHotKey(None, 1, mods, vk):
            self.error = f"{self.spec} is already taken by another program"
            self._ready.set()
            return
        self.ok = True
        self._ready.set()
        msg = wintypes.MSG()
        try:
            while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
                if msg.message == WM_HOTKEY:
                    try:
                        self.callback()
                    except Exception:  # noqa: BLE001  (a dead window is not fatal)
                        pass
        finally:
            user32.UnregisterHotKey(None, 1)

    def stop(self) -> None:
        if not self.ok or not self._thread_id:
            return
        ctypes.windll.user32.PostThreadMessageW(self._thread_id, WM_QUIT, 0, 0)
        if self._thread is not None:
            self._thread.join(timeout=3)


def icon_image(size: int = 64):
    """The app icon, drawn with Pillow: pystray wants an image, not a path."""
    from PIL import Image, ImageDraw

    im = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.rounded_rectangle((0, 0, size - 1, size - 1), radius=size * 0.22, fill=(79, 70, 229, 255))
    m = size / 16
    d.rounded_rectangle((4 * m, 3 * m, 12 * m, 13 * m), radius=1.2 * m, fill=(255, 255, 255, 255))
    lines = [(5, 11, 190), (5, 9, 150), (5, 11, 150), (5, 8, 255)]
    for i, (x0, x1, alpha) in enumerate(lines):
        y = 5.2 * m + i * 2.1 * m
        colour = (6, 182, 212, 255) if alpha == 255 else (17, 24, 39, alpha)
        d.rounded_rectangle((x0 * m, y, x1 * m, y + 0.8 * m), radius=0.4 * m, fill=colour)
    return im


class Tray:
    """A tray icon with Open and Quit; ``start()`` says whether it is running."""

    def __init__(self, on_open: Callable[[], None], on_quit: Callable[[], None]):
        self._on_open, self._on_quit = on_open, on_quit
        self._icon = None
        self.error: str | None = None

    def start(self) -> bool:
        try:
            import pystray
        except Exception as e:  # noqa: BLE001  (not installed, or no backend here)
            self.error = f"no tray icon ({type(e).__name__}: {e})"
            return False
        try:
            menu = pystray.Menu(
                pystray.MenuItem("Open", self._open, default=True),
                pystray.MenuItem("Quit", self._quit),
            )
            self._icon = pystray.Icon("indra-ocr", icon_image(), TITLE, menu)
            threading.Thread(target=self._icon.run, daemon=True).start()
        except Exception as e:  # noqa: BLE001
            self.error = f"no tray icon ({type(e).__name__}: {e})"
            return False
        return True

    def _open(self, *_args) -> None:
        self._on_open()

    def _quit(self, *_args) -> None:
        self._on_quit()

    def running(self) -> bool:
        return self._icon is not None

    def stop(self) -> None:
        if self._icon is not None:
            try:
                self._icon.stop()
            except Exception:  # noqa: BLE001
                pass
