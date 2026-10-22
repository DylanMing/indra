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
from .models import ModelError
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
    import cv2
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


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        prog="indra-ocr-desktop",
        description="Indra OCR in a desktop window: paste a screenshot, drop a PDF.",
    )
    ap.add_argument("--model-dir", type=Path, default=None, help="folder with the models")
    ap.add_argument("--port", type=int, default=0, help="localhost port (0: pick a free one)")
    ap.add_argument("--threads", type=int, default=4)
    ap.add_argument("--width", type=int, default=1280)
    ap.add_argument("--height", type=int, default=920)
    ap.add_argument(
        "--selftest", action="store_true", help="run the pipeline headless and exit"
    )
    ap.add_argument("--version", action="version", version=f"indra-ocr {__version__}")
    a = ap.parse_args(argv)

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
        srv, url = serve(engine, a.port)
        print(f"{TITLE} on {url} (models: {models or 'Hugging Face cache'})", flush=True)
        try:
            import webview
        except Exception as e:  # noqa: BLE001  (no webview backend installed)
            srv.shutdown()
            print(
                f"indra-ocr-desktop: no desktop backend ({type(e).__name__}: {e}). "
                f"Install one with pip install pywebview, or open {url} in a browser.",
                file=sys.stderr,
            )
            return 1
        try:
            webview.settings["OPEN_EXTERNAL_LINKS_IN_BROWSER"] = True
        except Exception:  # noqa: BLE001  (older pywebview)
            pass
        webview.create_window(
            TITLE, url, width=a.width, height=a.height, min_size=(900, 640)
        )
        try:
            webview.start()
        finally:
            srv.shutdown()
            srv.server_close()
        return 0
    except ModelError as e:
        print(f"indra-ocr-desktop: {e}", flush=True)
        return 1
    except OSError as e:  # the port, or a temp folder, is not available
        print(f"indra-ocr-desktop: {e}", flush=True)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
