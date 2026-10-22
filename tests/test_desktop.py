"""The desktop shell: where it finds the models, and the headless self test."""

import base64
import os

import pytest

from indra_ocr import desktop

PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
)


class FakeEngine:
    """The handler and the self test only call upload() and page()."""

    defaults = {}
    tesseract = None

    def upload(self, data: bytes) -> dict:
        assert data.startswith(b"\x89PNG\r\n\x1a\n")
        return {"id": "abc123", "pages": 1}

    def page(self, did: str, n: int, opts: dict) -> dict:
        return {
            "page": n + 1,
            "lines": [{"box": [0, 0, 10, 10], "text": "hello", "conf": 0.9}],
            "blocks": [],
            "timings": {"total_ms": 12.3},
        }


def test_bundled_models_beside_the_app(tmp_path, monkeypatch):
    models = tmp_path / "models"
    models.mkdir()
    (models / "det.onnx").touch()
    (models / "rec.onnx").touch()
    monkeypatch.setattr(desktop, "_app_dir", lambda: tmp_path)
    monkeypatch.setattr(desktop.sys, "_MEIPASS", str(tmp_path / "absent"), raising=False)
    assert desktop.bundled_models() == models


def test_bundled_models_is_none_without_one(tmp_path, monkeypatch):
    monkeypatch.setattr(desktop, "_app_dir", lambda: tmp_path)
    monkeypatch.setattr(desktop.sys, "_MEIPASS", str(tmp_path / "absent"), raising=False)
    assert desktop.bundled_models() is None


def test_resolve_models_order(tmp_path, monkeypatch):
    bundled = tmp_path / "bundled"
    explicit = tmp_path / "explicit"
    monkeypatch.setattr(desktop, "bundled_models", lambda: bundled)
    assert desktop.resolve_models(explicit) == explicit  # --model-dir wins
    monkeypatch.setenv("INDRA_OCR_MODEL_DIR", str(tmp_path / "env"))
    # None: model_dir() reads INDRA_OCR_MODEL_DIR itself
    assert desktop.resolve_models(None) is None
    monkeypatch.delenv("INDRA_OCR_MODEL_DIR")
    assert desktop.resolve_models(None) == bundled  # then the shipped folder


def test_selftest_reads_a_page_through_the_server(capsys):
    srv, url = desktop.serve(FakeEngine(), 0)
    try:
        assert desktop.selftest(url) == 0
    finally:
        srv.shutdown()
        srv.server_close()
    out = capsys.readouterr().out
    assert "self test OK" in out
    assert "1 lines" in out


def test_sample_png_is_a_png():
    assert desktop.sample_png().startswith(PNG[:8])


def test_clipboard_endpoint_serves_the_image(monkeypatch):
    import indra_ocr.viewer as viewer

    srv, url = desktop.serve(FakeEngine(), 0)
    monkeypatch.setattr(viewer, "grab_image", lambda: PNG)
    try:
        with __import__("urllib.request").request.urlopen(url + "/clipboard", timeout=10) as r:
            assert r.status == 200
            assert r.headers["Content-Type"] == "image/png"
            assert r.read() == PNG
    finally:
        srv.shutdown()
        srv.server_close()


def test_clipboard_endpoint_says_when_there_is_no_image(monkeypatch):
    import urllib.request

    import indra_ocr.viewer as viewer

    srv, url = desktop.serve(FakeEngine(), 0)
    monkeypatch.setattr(viewer, "grab_image", lambda: None)
    try:
        with urllib.request.urlopen(url + "/clipboard", timeout=10) as r:
            assert r.status == 204  # no image: the page then says so
            assert r.read() == b""
    finally:
        srv.shutdown()
        srv.server_close()


def test_say_goes_to_stderr_when_there_is_one(capsys):
    desktop.say("cannot listen on 127.0.0.1:8899")
    assert "indra-ocr-desktop: cannot listen on 127.0.0.1:8899" in capsys.readouterr().err


def test_say_shows_a_dialog_when_the_build_has_no_console(monkeypatch):
    # A release build is windowed: PyInstaller sets sys.stderr to None, so a
    # message there would be lost and the app would end without a word.
    shown = []
    monkeypatch.setattr(desktop, "report", lambda problems: shown.append(problems))
    monkeypatch.setattr(desktop.sys, "stderr", None)

    desktop.say("cannot listen on 127.0.0.1:8899")

    assert shown == [["cannot listen on 127.0.0.1:8899"]]


def test_a_busy_port_is_reported_and_exits_1(monkeypatch):
    shown = []

    class Engine:
        def __init__(self, *a, **k):
            pass

    def busy(*a, **k):
        raise OSError("cannot listen on 127.0.0.1:8899: Address already in use")

    monkeypatch.setattr(desktop, "resolve_models", lambda explicit: None)
    monkeypatch.setattr(desktop, "Engine", Engine)
    monkeypatch.setattr(desktop, "first_run_problems", lambda models: [])
    monkeypatch.setattr(desktop, "record_start", lambda *a: None)
    monkeypatch.setattr(desktop, "serve", busy)
    monkeypatch.setattr(desktop, "report", lambda problems: shown.append(problems))
    monkeypatch.setattr(desktop.sys, "stderr", None)

    assert desktop.main(["--port", "8899"]) == 1
    assert shown and "8899" in shown[0][0] and "already in use" in shown[0][0]


def test_a_running_build_keeps_the_typelib_path_alone(monkeypatch):
    # Only a frozen Linux build gets its typelib path extended.
    monkeypatch.setenv("GI_TYPELIB_PATH", "/bundle/gi_typelibs")
    desktop.system_typelibs()
    assert os.environ["GI_TYPELIB_PATH"] == "/bundle/gi_typelibs"


def test_a_frozen_linux_build_adds_the_system_typelibs(monkeypatch, tmp_path):
    # The bundle carries GTK, not WebKit2GTK: the window comes from the host, so
    # the host's typelib folders have to stay reachable.
    host = tmp_path / "girepository-1.0"
    host.mkdir()
    monkeypatch.setattr(desktop.sys, "platform", "linux")
    monkeypatch.setattr(desktop.sys, "frozen", True, raising=False)
    monkeypatch.setattr(desktop, "TYPELIB_DIRS", ("/definitely/not/here", str(host)))
    monkeypatch.setenv("GI_TYPELIB_PATH", "/bundle/gi_typelibs")

    desktop.system_typelibs()

    parts = os.environ["GI_TYPELIB_PATH"].split(os.pathsep)
    assert parts == ["/bundle/gi_typelibs", str(host)]


def test_window_test_closes_the_window(capsys):
    class Window:
        destroyed = False

        def destroy(self):
            self.destroyed = True

    class Webview:
        guilib = "gtk"
        window = Window()

        def create_window(self, *a, **k):
            return self.window

        def start(self, callback=None):
            callback()

    assert desktop.window_test(Webview(), "http://127.0.0.1:1") == 0
    assert Webview.window.destroyed is True
    out = capsys.readouterr().out
    assert "window test OK" in out and "gtk" in out


def test_window_test_fails_when_the_window_cannot_start(monkeypatch):
    shown = []
    monkeypatch.setattr(desktop, "report", lambda problems: shown.append(problems))
    monkeypatch.setattr(desktop.sys, "stderr", None)

    class Webview:
        guilib = "gtk"

        def create_window(self, *a, **k):
            raise RuntimeError("could not open display")

    assert desktop.window_test(Webview(), "http://127.0.0.1:1") == 1
    assert shown and "could not open display" in shown[0][0]
