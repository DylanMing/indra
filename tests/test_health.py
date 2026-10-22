"""First-run checks: the two failures worth a dialog, and the state file."""

import json
import os

import pytest

from indra_ocr import health


def test_an_empty_hugging_face_cache_is_not_a_problem():
    # models=None means "download on first use": nothing to check yet.
    assert health.model_problems(None) == []


def test_a_model_folder_without_the_files_says_which(tmp_path):
    (tmp_path / "det.onnx").write_bytes(b"x")
    problems = health.model_problems(tmp_path)
    assert len(problems) == 1
    assert "rec.onnx" in problems[0] and "order.onnx" in problems[0]
    assert str(tmp_path) in problems[0]


def test_a_complete_model_folder_is_fine(tmp_path):
    for name in health.NEEDED:
        (tmp_path / name).write_bytes(b"x")
    assert health.model_problems(tmp_path) == []


def test_a_missing_webview2_runtime_is_reported(monkeypatch):
    if os.name != "nt":
        pytest.skip("WebView2 is a Windows runtime")
    import winreg

    def no_key(*a, **k):
        raise FileNotFoundError("no such registry key")

    monkeypatch.setattr(winreg, "OpenKey", no_key)
    problem = health.webview2_problem()
    assert problem and "WebView2" in problem


def test_the_state_file_keeps_the_first_run_and_counts_runs(monkeypatch, tmp_path):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path))
    path = health.record_start("1.1.3", None, [])
    assert path is not None and path.is_file()
    first = json.loads(path.read_text(encoding="utf-8"))
    assert first["version"] == "1.1.3" and first["runs"] == 1

    health.record_start("1.1.3", None, ["a problem"])
    second = json.loads(path.read_text(encoding="utf-8"))
    assert second["runs"] == 2
    assert second["first_run"] == first["first_run"]
    assert second["problems"] == ["a problem"]


def test_an_unwritable_state_folder_is_not_fatal(monkeypatch, tmp_path):
    blocker = tmp_path / "file"
    blocker.write_text("x", encoding="utf-8")
    monkeypatch.setenv("LOCALAPPDATA", str(blocker))
    monkeypatch.setenv("XDG_STATE_HOME", str(blocker))
    assert health.record_start("1.1.3", None, []) is None
