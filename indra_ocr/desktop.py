"""Indra OCR as a desktop app: the viewer in a native window, no browser tab.

The models ship next to the app (``models/`` beside the executable, put there by
PyInstaller), so the app reads documents with no network and no Hugging Face
cache. ``--selftest`` runs the whole pipeline headless (upload a generated page,
read it back over HTTP) and exits, which is what a packaged build is checked
with.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import threading
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

from . import __version__
from .health import first_run_problems, record_start, report
from .models import ModelError
from .tray import Hotkey, Tray
from .viewer import Engine, LocalServer, make_handler

TITLE = "Indra OCR"

# What the page starts with; the switches in the page override them per run.
DEFAULTS = {
    "mode": "auto",
    "image_ocr": True,
    "math": False,
    "furniture": False,
    "dpi": 200.0,
    "max_pages": 20,
}


def say(message: str) -> None:
    """Tell the user something: on stderr when there is one, in a dialog when not.

    A release build is windowed, so PyInstaller sets ``sys.stderr`` to None: a
    port that is taken would otherwise end the process with no word at all.
    """
    if sys.stderr is not None:
        print(f"indra-ocr-desktop: {message}", file=sys.stderr, flush=True)
    else:
        report([message])


def fail(message: str) -> int:
    """Report a startup failure and return the exit code."""
    say(message)
    return 1


TYPELIB_DIRS = (
    "/usr/lib/x86_64-linux-gnu/girepository-1.0",
    "/usr/lib/aarch64-linux-gnu/girepository-1.0",
    "/usr/lib/girepository-1.0",
    "/usr/local/lib/girepository-1.0",
)


def system_typelibs() -> None:
    """Let a bundled Linux build see the typelibs the host provides.

    PyInstaller's GI runtime hook sets ``GI_TYPELIB_PATH`` to the bundled
    ``gi_typelibs`` and nothing else. The bundle carries GTK 3, but not
    WebKit2GTK — that is a browser engine with helper processes of its own, not
    something to bundle by accident — so on Linux the window comes from the
    system's ``libwebkit2gtk``. Appending the system folders is what makes the
    GTK backend find it; without this the window cannot open on any machine.
    """
    if not sys.platform.startswith("linux") or not getattr(sys, "frozen", False):
        return
    path = [p for p in os.environ.get("GI_TYPELIB_PATH", "").split(os.pathsep) if p]
    path += [p for p in TYPELIB_DIRS if os.path.isdir(p) and p not in path]
    os.environ["GI_TYPELIB_PATH"] = os.pathsep.join(path)


def _app_dir() -> Path:
    """The folder the app runs from: the executable's folder when frozen."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


def bundled_models() -> Path | None:
    """The models that shipped with the app, if any: ``models/`` beside the app,
    or in PyInstaller's ``_MEIPASS`` (``_internal/`` for a one-folder build)."""
    roots = [_app_dir() / "models", Path(getattr(sys, "_MEIPASS", "")) / "models"]
    for root in roots:
        if (root / "det.onnx").exists() and (root / "rec.onnx").exists():
            return root
    return None


def resolve_models(explicit: str | Path | None) -> Path | None:
    """--model-dir, then INDRA_OCR_MODEL_DIR, then the bundled folder, then None
    (which downloads, the way the CLI does)."""
    if explicit:
        return Path(explicit)
    if os.environ.get("INDRA_OCR_MODEL_DIR"):
        return None
    return bundled_models()


def sample_png(text: str = "Indra OCR desktop") -> bytes:
    """A white page with one line of text: enough for a headless self test."""
    from . import imaging as cv2  # noqa: N813 - kept: the code reads like OpenCV
    import numpy as np

    img = np.full((320, 1000, 3), 255, np.uint8)
    cv2.putText(img, text, (40, 190), cv2.FONT_HERSHEY_SIMPLEX, 2.2, (0, 0, 0), 7, cv2.LINE_AA)
    ok, buf = cv2.imencode(".png", img)
    if not ok:  # pragma: no cover  (encoding a white page never fails)
        raise RuntimeError("could not encode the self-test page")
    return buf.tobytes()


def serve(engine: Engine, port: int = 0) -> tuple[ThreadingHTTPServer, str]:
    """Start the viewer's HTTP server on localhost; returns it and its URL."""
    try:
        srv = LocalServer(("127.0.0.1", port), make_handler(engine))
    except OSError as e:  # --port is already in use
        raise OSError(
            f"cannot listen on 127.0.0.1:{port}: {e.strerror or e}"
        ) from e
    url = f"http://127.0.0.1:{srv.server_address[1]}"
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, url


def _get(url: str) -> dict:
    with urllib.request.urlopen(url, timeout=60) as r:
        return json.load(r)


def _post(url: str, body: bytes) -> dict:
    req = urllib.request.Request(url, data=body, method="POST")
    with urllib.request.urlopen(req, timeout=300) as r:
        return json.load(r)


def selftest(url: str) -> int:
    """The packaged app, checked the way a user uses it: upload, then read page 1."""
    info = _get(url + "/info")
    up = _post(url + "/upload", sample_png())
    page = _post(url + "/page", json.dumps({"id": up["id"], "n": 0, "opts": {}}).encode())
    lines, blocks = len(page.get("lines") or []), len(page.get("blocks") or [])
    print(
        f"self test OK: {TITLE} {info['version']}, {up['pages']} page, "
        f"{lines} lines, {blocks} blocks, {page['timings']['total_ms']:.0f} ms",
        flush=True,
    )
    return 0 if lines else 1


def window_test(webview, url: str) -> int:
    """Open the real window, prove it came up, close it, exit.

    What CI runs under xvfb: ``--selftest`` is headless, so a bundle whose GTK or
    WebKit2 half is missing passes it and then has no window for a user. A GUI
    that hangs instead of failing is why the watchdog exits by itself.
    """
    window = None
    state = {"open": False}
    watchdog = threading.Timer(60.0, os._exit, [3])  # a stuck GUI must not hang CI
    watchdog.daemon = True
    try:
        window = webview.create_window(TITLE, url, width=800, height=600)

        def close() -> None:
            state["open"] = True
            window.destroy()  # lets webview.start() return

        watchdog.start()
        webview.start(close)
    except Exception as e:  # noqa: BLE001  (no display, no GTK, no WebKit2)
        return fail(f"the window could not start ({type(e).__name__}: {e})")
    finally:
        watchdog.cancel()
    if not state["open"]:
        return fail("the window did not open")
    backend = getattr(webview.guilib, "__name__", None) or str(webview.guilib)
    print(f"window test OK: {TITLE} opened on {backend}", flush=True)
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        prog="indra-ocr-desktop",
        description="Indra OCR in a desktop window: paste a screenshot, drop a PDF.",
    )
    ap.add_argument(
        "file",
        nargs="?",
        type=Path,
        help="a PDF or an image to open on start (what a .pdf association passes)",
    )
    ap.add_argument("--model-dir", type=Path, default=None, help="folder with the models")
    ap.add_argument("--port", type=int, default=0, help="localhost port (0: pick a free one)")
    ap.add_argument("--threads", type=int, default=4)
    ap.add_argument("--width", type=int, default=1280)
    ap.add_argument("--height", type=int, default=920)
    ap.add_argument(
        "--tray",
        dest="tray",
        action="store_true",
        default=None,
        help="keep a tray icon and keep running when the window closes",
    )
    ap.add_argument("--no-tray", dest="tray", action="store_false")
    ap.add_argument(
        "--hotkey",
        default="ctrl+alt+o",
        help="global hotkey that shows the window (Windows; empty: none)",
    )
    ap.add_argument(
        "--selftest", action="store_true", help="run the pipeline headless and exit"
    )
    ap.add_argument(
        "--windowtest",
        action="store_true",
        help="open the window, then close it (CI, under xvfb)",
    )
    ap.add_argument("--version", action="version", version=f"indra-ocr {__version__}")
    a = ap.parse_args(argv)

    system_typelibs()
    models = resolve_models(a.model_dir)
    try:
        if a.selftest:
            engine = Engine(models, a.threads, False, "eng", dict(DEFAULTS))
            srv, url = serve(engine, a.port)
            try:
                return selftest(url)
            finally:
                srv.shutdown()
                srv.server_close()
        engine = Engine(models, a.threads, False, "eng", dict(DEFAULTS))
        if a.file is not None:
            # A file handed to us (a .pdf association, "Open with", a drag onto the
            # exe): the page fetches it from /preload once and reads it.
            path = a.file.expanduser().resolve()
            if path.is_file():
                engine.preload = path
            else:
                say(f"{path}: no such file")
        problems = first_run_problems(models)
        record_start(__version__, models, problems)
        if problems:
            report(problems)
        srv, url = serve(engine, a.port)
        print(f"{TITLE} on {url} (models: {models or 'Hugging Face cache'})", flush=True)
        try:
            import webview
        except Exception as e:  # noqa: BLE001  (no webview backend installed)
            srv.shutdown()
            return fail(
                f"no desktop backend ({type(e).__name__}: {e}). "
                f"Install one with pip install pywebview, or open {url} in a browser."
            )
        if a.windowtest:
            # CI, under xvfb: build the real window and close it again. The headless
            # --selftest cannot see a missing GTK or WebKit2, and that is exactly how
            # a Linux bundle without a window got shipped once.
            try:
                return window_test(webview, url)
            finally:
                srv.shutdown()
                srv.server_close()
        try:
            webview.settings["OPEN_EXTERNAL_LINKS_IN_BROWSER"] = True
        except Exception:  # noqa: BLE001  (older pywebview)
            pass
        debug_port = os.environ.get("INDRA_OCR_DEBUG_PORT", "")
        if debug_port.isdigit():
            # Support: a DevTools endpoint on the local page, to read what the
            # window actually shows (WebView2's REMOTE_DEBUGGING_PORT setting).
            try:
                webview.settings["REMOTE_DEBUGGING_PORT"] = int(debug_port)
            except Exception:  # noqa: BLE001
                pass
        window = webview.create_window(
            TITLE, url, width=a.width, height=a.height, min_size=(900, 640)
        )

        state = {"quitting": False}

        def show() -> None:
            try:
                window.show()
                window.restore()  # a minimised or hidden window comes back
            except Exception:  # noqa: BLE001  (the window is gone)
                pass

        def quit_app() -> None:
            state["quitting"] = True
            try:
                window.destroy()
            except Exception:  # noqa: BLE001
                pass

        tray = None
        if a.tray is not False:  # default: on, when pystray is available
            tray = Tray(on_open=show, on_quit=quit_app)
            if tray.start():
                def on_closing() -> bool:
                    if state["quitting"]:
                        return True  # really closing: let it go
                    window.hide()  # Closing the window keeps the app in the tray
                    return False

                window.events.closing += on_closing
                print("tray icon on: closing the window keeps it running", flush=True)
            else:
                error = tray.error
                tray = None
                if a.tray:  # asked for explicitly: say why there is none
                    say(str(error))

        hotkey = None
        if a.hotkey:
            hotkey = Hotkey(a.hotkey, show)
            if hotkey.start():
                print(f"hotkey: {a.hotkey} shows the window", flush=True)
            else:
                say(str(hotkey.error))
                hotkey = None
        try:
            webview.start()
        finally:
            if hotkey is not None:
                hotkey.stop()
            if tray is not None:
                tray.stop()
            srv.shutdown()
            srv.server_close()
        return 0
    except ModelError as e:
        return fail(str(e))
    except OSError as e:  # the port, or a temp folder, is not available
        return fail(str(e))


if __name__ == "__main__":
    raise SystemExit(main())
