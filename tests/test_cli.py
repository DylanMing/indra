"""The CLI writes a document to stdout: it must survive a legacy code page."""

import os
import subprocess
import sys

from indra_ocr import cli


class FakeStream:
    def __init__(self, encoding, isatty):
        self.encoding = encoding
        self._isatty = isatty
        self.reconfigured = None
        self.written = []

    def isatty(self):
        return self._isatty

    def reconfigure(self, **kw):
        self.reconfigured = dict(self.reconfigured or {}, **kw)
        if "encoding" in kw:
            self.encoding = kw["encoding"]

    def write(self, s):
        self.written.append(s)

    def flush(self):
        pass


def test_a_pipe_gets_utf8(monkeypatch):
    out, err = FakeStream("cp936", False), FakeStream("cp936", False)
    monkeypatch.setattr(cli.sys, "stdout", out)
    monkeypatch.setattr(cli.sys, "stderr", err)
    cli._text_stdio()
    assert out.encoding == "utf-8" and out.reconfigured["errors"] == "replace"
    assert err.encoding == "utf-8"


def test_a_console_keeps_its_code_page(monkeypatch):
    # UTF-8 on a cp936 console would show Chinese as mojibake: replace instead.
    out = FakeStream("cp936", True)
    monkeypatch.setattr(cli.sys, "stdout", out)
    monkeypatch.setattr(cli.sys, "stderr", FakeStream("utf-8", True))
    cli._text_stdio()
    assert out.encoding == "cp936"
    assert out.reconfigured == {"errors": "replace"}


def test_utf8_streams_are_left_alone(monkeypatch):
    out = FakeStream("utf-8", False)
    monkeypatch.setattr(cli.sys, "stdout", out)
    monkeypatch.setattr(cli.sys, "stderr", FakeStream("UTF-8", True))
    cli._text_stdio()
    assert out.reconfigured is None


def test_main_makes_the_streams_safe(monkeypatch):
    seen = []
    monkeypatch.setattr(cli, "_text_stdio", lambda: seen.append("stdio"))
    monkeypatch.setattr(cli, "_main", lambda argv: seen.append("main") or 0)
    assert cli.main(["x.png"]) == 0
    assert seen == ["stdio", "main"]


def test_a_bullet_survives_a_cp936_pipe():
    """The regression itself: a character outside the code page ended the run."""
    code = (
        "from indra_ocr.cli import _text_stdio; _text_stdio(); "
        "import sys; sys.stdout.write('a \u2022 b'); sys.stdout.flush()"
    )
    env = dict(os.environ, PYTHONIOENCODING="cp936")
    r = subprocess.run([sys.executable, "-c", code], capture_output=True, env=env)
    assert r.returncode == 0, r.stderr.decode("utf-8", "replace")
    assert r.stdout.decode("utf-8") == "a \u2022 b"
