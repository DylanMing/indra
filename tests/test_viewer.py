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
