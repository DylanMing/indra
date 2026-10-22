"""The image on the system clipboard, for pasting a screenshot into the viewer.

The page's own ``paste`` event is the normal path: the browser hands the image
over. This is the fallback for the cases where it cannot:

- a webview that does not pass clipboard files to the page (WebKitGTK, which
  pywebview uses on Linux), where the "Paste from clipboard" button asks the
  server instead;
- a browser window that is not in front when the screenshot is taken.

``grab_image()`` returns PNG bytes, or ``None`` when the clipboard holds no
image. Nothing here needs a network: it reads the local clipboard only.
"""

from __future__ import annotations

import io
import shutil
import subprocess
from typing import Any

PNG_MAGIC = b"\x89PNG\r\n\x1a\n"


def grab_image() -> bytes | None:
    """The image on the clipboard as PNG bytes, or None."""
    data = _from_pillow()
    if data:
        return data
    return _from_linux_tools()


def _to_png(im: Any) -> bytes:
    if getattr(im, "mode", "") not in ("RGB", "RGBA"):
        im = im.convert("RGB")
    buf = io.BytesIO()
    im.save(buf, "PNG")
    return buf.getvalue()


def _from_pillow() -> bytes | None:
    """Windows and macOS (and X11, where Pillow shells out to xclip itself)."""
    try:
        from PIL import Image, ImageGrab
    except Exception:  # noqa: BLE001  (Pillow is an optional dependency)
        return None
    try:
        got = ImageGrab.grabclipboard()
    except Exception:  # noqa: BLE001  (headless, no display, no clipboard tool)
        return None
    if got is None:
        return None
    if isinstance(got, list):  # the clipboard holds files: use the first image
        for path in got:
            try:
                return _to_png(Image.open(path))
            except Exception:  # noqa: BLE001  (not an image)
                continue
        return None
    try:
        return _to_png(got)
    except Exception:  # noqa: BLE001
        return None


def _from_linux_tools() -> bytes | None:
    """Wayland and X11 without Pillow's clipboard support."""
    for cmd in (
        ("wl-paste", "-n", "-t", "image/png"),
        ("xclip", "-selection", "clipboard", "-t", "image/png", "-o"),
        ("xsel", "--clipboard", "--output"),
    ):
        if not shutil.which(cmd[0]):
            continue
        try:
            res = subprocess.run(cmd, capture_output=True, timeout=5, check=False)
        except Exception:  # noqa: BLE001  (no server, no permission)
            continue
        if res.returncode == 0 and res.stdout.startswith(PNG_MAGIC):
            return res.stdout
    return None
