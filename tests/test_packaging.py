"""The packaging scripts: the version resource and the setup script."""

import hashlib
import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def load_build():
    spec = importlib.util.spec_from_file_location(
        "indra_build", ROOT / "packaging" / "build.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class Rec:
    """Stands in for PyInstaller's version_info classes: records the arguments."""

    def __init__(self, *args, **kwargs):
        self.args, self.kwargs = args, kwargs


def test_the_version_resource_says_what_explorer_shows(tmp_path):
    build = load_build()
    out = build.write_version_info("1.1.3", tmp_path / "version_info.txt")
    text = out.read_text(encoding="utf-8")
    assert "VSVersionInfo" in text

    classes = {
        name: Rec
        for name in (
            "VSVersionInfo",
            "FixedFileInfo",
            "StringFileInfo",
            "StringTable",
            "StringStruct",
            "VarFileInfo",
            "VarStruct",
        )
    }
    node = eval(text, classes)  # noqa: S307  (a Python literal we just wrote)
    fixed = node.kwargs["ffi"]
    assert fixed.kwargs["filevers"] == (1, 1, 3, 0)
    assert fixed.kwargs["prodvers"] == (1, 1, 3, 0)

    table = node.kwargs["kids"][0].args[0][0]
    strings = {s.args[0]: s.args[1] for s in table.args[1]}
    assert strings["ProductName"] == "Indra OCR"
    assert strings["FileVersion"] == strings["ProductVersion"] == "1.1.3.0"
    assert strings["OriginalFilename"] == "IndraOCR.exe"


def test_the_setup_script_is_there_and_takes_the_defines():
    build = load_build()
    text = build.ISS.read_text(encoding="utf-8")
    assert "OutputBaseFilename=IndraOCR-{#AppVersion}-setup" in text
    assert "{#SourceDir}" in text
    # per-user install, so no admin prompt for a 350 MB OCR app
    assert "PrivilegesRequired=lowest" in text
    assert build.ICON.is_file()


def test_the_installer_is_found_or_reported(monkeypatch):
    build = load_build()
    monkeypatch.setattr(build.shutil, "which", lambda name: None)
    for var in ("LOCALAPPDATA", "ProgramFiles(x86)", "ProgramFiles"):
        monkeypatch.setenv(var, "Z:\\nowhere")
    assert build.find_iscc() is None


def test_the_checksum_file_is_the_sha256sum_format(tmp_path):
    """The installer is unsigned: this file is how a download is checked."""
    build = load_build()
    setup = tmp_path / "IndraOCR-1.1.3-setup.exe"
    setup.write_bytes(b"a pretend installer" * 5000)
    out = build.write_checksum(setup)

    assert out.name == "IndraOCR-1.1.3-setup.exe.sha256"
    expected = hashlib.sha256(setup.read_bytes()).hexdigest()
    # "<hash>  <name>": sha256sum reads it, Get-FileHash prints the same hash
    assert out.read_text(encoding="utf-8") == f"{expected}  {setup.name}\n"
