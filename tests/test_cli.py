"""The CLI writes a document to stdout: it must survive a legacy code page."""

import os
import subprocess
import sys

import pytest

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


class FakePage:
    source, note, markdown, text = "ocr", "", "read me", "read me"
    lines: list = []
    blocks: list = []
    rotation, skew, vertical = 0, 0.0, False
    timings: dict = {}


def test_a_bad_output_folder_is_one_line_not_a_traceback(tmp_path, capsys):
    # --out names an existing file: the folder cannot be made.
    blocker = tmp_path / "out.txt"
    blocker.write_text("x")
    rc = cli.main(["missing.pdf", "--out", str(blocker)])
    err = capsys.readouterr().err
    assert rc == 1
    assert "cannot use" in err and "Traceback" not in err


def test_a_failed_write_names_the_file_and_keeps_going(monkeypatch, tmp_path, capsys):
    """A read-only folder, a locked file or a path over MAX_PATH: say which file,
    count the input as failed, and read the next one."""
    import pathlib

    monkeypatch.setattr(
        cli, "convert_many", lambda *a, **k: iter([(str(tmp_path / "in.pdf"), [(0, FakePage())])])
    )
    real = pathlib.Path.write_text

    def refuse(self, *a, **k):
        if self.suffix == ".md":
            raise PermissionError(13, "Permission denied")
        return real(self, *a, **k)

    monkeypatch.setattr(pathlib.Path, "write_text", refuse)
    out = tmp_path / "out"
    rc = cli.main(["in.pdf", "--out", str(out)])
    err = capsys.readouterr().err
    assert rc == 1
    assert "cannot write" in err and "in.md" in err
    assert "1 of 1 inputs failed" in err


def test_python_m_indra_ocr_keeps_the_exit_code(monkeypatch):
    """`python -m indra_ocr bad.pdf` said "1 of 1 inputs failed" and exited 0:
    __main__.py dropped main()'s return value."""
    import runpy

    monkeypatch.setattr(cli, "main", lambda argv=None: 1)
    with pytest.raises(SystemExit) as exc:
        runpy.run_module("indra_ocr", run_name="__main__")
    assert exc.value.code == 1
