"""The viewer page: an image pasted from the clipboard takes the dropped-file path."""

import base64
import json
import tempfile
import threading
import urllib.request
from http.server import ThreadingHTTPServer

import pytest

from indra_ocr.viewer import KEPT_UPLOADS, Engine, PAGE, make_handler

# 1x1 red PNG: what a clipboard paste hands over (raw bytes, no file name).
PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
)


class FakeEngine:
    """The handler only calls upload() and page(); no models needed here."""

    preload = None

    def upload(self, data: bytes) -> dict:
        assert data.startswith(b"\x89PNG\r\n\x1a\n"), "the pasted bytes must arrive whole"
        return {"id": "abc123", "pages": 1}

    def page(self, did: str, n: int, opts: dict) -> dict:
        assert did == "abc123"
        return {"page": n + 1, "lines": [], "blocks": [], "markdown": "", "json": {}}


def test_page_has_a_paste_handler_and_says_so():
    assert "addEventListener('paste'" in PAGE
    assert "function pasted(" in PAGE
    assert "start(f)" in PAGE
    assert "or paste with Ctrl+V" in PAGE  # drop zone hint
    assert "Ctrl+V (Cmd+V)" in PAGE  # empty state


def _engine() -> Engine:
    """An Engine with no models: upload()/eviction need none of them."""
    e = Engine.__new__(Engine)
    e.docs, e.pdfs = {}, set()
    e.lock = threading.Lock()
    e.tmp = tempfile.TemporaryDirectory(prefix="indra_ocr_test_")
    return e


def test_a_pdf_with_a_little_junk_before_the_header_uploads(tmp_path):
    """The CLI scans 1024 bytes for %PDF- (is_pdf); the viewer now agrees, so a
    PDF that Acrobat or a mail gateway prefixed is not called "not an image"."""
    import pypdfium2 as pdfium

    doc = pdfium.PdfDocument.new()
    page = doc.new_page(200, 300)
    page.close()
    path = tmp_path / "plain.pdf"
    doc.save(str(path))
    doc.close()
    e = _engine()
    res = e.upload(b"\n\n  " + path.read_bytes())
    assert res["pages"] == 1
    assert res["id"] in e.pdfs


def test_an_evicted_upload_says_so_instead_of_a_key_error():
    e = _engine()
    first = e.upload(PNG)["id"]
    for _ in range(KEPT_UPLOADS):
        e.upload(PNG)
    assert first not in e.docs
    with pytest.raises(ValueError, match="no longer held"):
        e.page(first, 0, {})


def test_a_pasted_name_carries_local_time():
    # toISOString() is UTC: a screenshot taken at 16:40 in Shanghai was listed
    # as 08:40, eight hours before the user took it.
    assert "toISOString" not in PAGE
    assert "getHours" in PAGE and "getFullYear" in PAGE


def test_pasted_image_bytes_go_through_upload_and_page():
    srv = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(FakeEngine()))
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    base = f"http://127.0.0.1:{srv.server_address[1]}"
    try:
        req = urllib.request.Request(base + "/upload", data=PNG, method="POST")
        with urllib.request.urlopen(req, timeout=10) as r:
            up = json.load(r)
        assert up == {"id": "abc123", "pages": 1}

        body = json.dumps({"id": up["id"], "n": 0, "opts": {"mode": "auto"}}).encode()
        req = urllib.request.Request(base + "/page", data=body, method="POST")
        with urllib.request.urlopen(req, timeout=10) as r:
            page = json.load(r)
        assert page["page"] == 1
    finally:
        srv.shutdown()
        srv.server_close()
        t.join(timeout=5)


def _raw(port: int, request: bytes) -> bytes:
    import socket

    with socket.create_connection(("127.0.0.1", port), timeout=10) as s:
        s.sendall(request)
        s.shutdown(socket.SHUT_WR)
        chunks = []
        while True:
            chunk = s.recv(65536)
            if not chunk:
                break
            chunks.append(chunk)
    return b"".join(chunks)


def test_a_malformed_content_length_gets_a_400_not_a_dropped_socket():
    """A bad header escaped BaseHTTPRequestHandler, which closed the socket with no
    status line; the page's fetch() then waited forever on "Uploading ..."."""
    srv = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(FakeEngine()))
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    port = srv.server_address[1]
    try:
        for header in (b"abc", b"-5"):
            raw = _raw(
                port,
                b"POST /upload HTTP/1.1\r\nHost: x\r\nContent-Length: "
                + header
                + b"\r\n\r\n",
            )
            head = raw.split(b"\r\n", 1)[0]
            assert b" 400 " in head, (header, raw[:160])
            assert b'"error"' in raw
    finally:
        srv.shutdown()
        srv.server_close()


def test_the_page_shows_a_dpi_the_picker_does_not_offer():
    # --dpi 250 left the <select> blank, so the page asked for dpi 0 -> 200.
    assert "s.add(new Option(" in PAGE


def test_a_clipboard_failure_answers_instead_of_dropping_the_connection(monkeypatch):
    """grab_image() raises when another app holds the clipboard on Windows."""
    import indra_ocr.viewer as viewer_mod

    def boom():
        raise OSError("clipboard is busy")

    monkeypatch.setattr(viewer_mod, "grab_image", boom)
    srv = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(FakeEngine()))
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        raw = _raw(srv.server_address[1], b"GET /clipboard HTTP/1.1\r\nHost: x\r\n\r\n")
        assert b" 400 " in raw.split(b"\r\n", 1)[0]
        assert b"clipboard is busy" in raw
    finally:
        srv.shutdown()
        srv.server_close()


def test_the_viewer_opens_a_browser_unless_told_not_to(monkeypatch, capsys):
    """`indra-ocr-viewer` printed the URL and left the user to paste it."""
    import sys

    import indra_ocr.viewer as v

    opened = []
    monkeypatch.setattr(v, "Engine", lambda *a, **k: object())
    monkeypatch.setattr(v.webbrowser, "open", opened.append)

    class FakeServer:
        def __init__(self, addr, handler):
            self.server_address = ("127.0.0.1", 8788)  # --port 0: the bound port

        def serve_forever(self):
            pass

    monkeypatch.setattr(v, "LocalServer", FakeServer)
    monkeypatch.setattr(sys, "argv", ["indra-ocr-viewer"])
    v._main()
    assert opened == ["http://localhost:8788"]
    assert "http://localhost:8788" in capsys.readouterr().out

    monkeypatch.setattr(sys, "argv", ["indra-ocr-viewer", "--no-browser"])
    v._main()
    assert opened == ["http://localhost:8788"], "no second window"


def test_a_machine_with_no_browser_is_not_an_error(monkeypatch):
    """A headless box has nothing to open: the URL is printed anyway."""
    import indra_ocr.viewer as v

    def boom(url):
        raise Exception("no browser here")

    monkeypatch.setattr(v.webbrowser, "open", boom)
    v._open_browser("http://localhost:8788")  # does not raise


def test_the_file_the_app_was_started_with_is_served_once(monkeypatch, tmp_path):
    """`IndraOCR.exe report.pdf` (and a .pdf association): the page asks for the
    bytes on load and uploads them itself."""
    path = tmp_path / "报告 2026.pdf"
    path.write_bytes(b"%PDF-1.4 test")
    engine = FakeEngine()
    engine.preload = path

    srv = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(engine))
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        raw = _raw(srv.server_address[1], b"GET /preload HTTP/1.1\r\nHost: x\r\n\r\n")
        head, _, body = raw.partition(b"\r\n\r\n")
        assert b" 200 " in head.split(b"\r\n", 1)[0]
        assert body == b"%PDF-1.4 test"
        # the name goes in a header the page can decode (it is not ASCII)
        assert b"X-Filename: %E6%8A%A5%E5%91%8A%202026.pdf" in head

        engine.preload = None
        raw = _raw(srv.server_address[1], b"GET /preload HTTP/1.1\r\nHost: x\r\n\r\n")
        assert b" 204 " in raw.split(b"\r\n", 1)[0]
    finally:
        srv.shutdown()
        srv.server_close()
