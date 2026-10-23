"""The packaging scripts: the version resource and the setup script."""

import hashlib
import importlib.util
from pathlib import Path

import pytest

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


def test_the_installer_shows_the_licences():
    """The weights are not Apache-2.0: the user has to see that before installing."""
    build = load_build()
    text = build.ISS.read_text(encoding="utf-8")
    assert "LicenseFile={#SourceDir}\\THIRD-PARTY-NOTICES.md" in text
    # a fork build does not present itself as the upstream publisher
    assert "datalab-to/indra" not in text.split("AppPublisherURL=")[1].splitlines()[0]


def test_the_licences_travel_with_the_bundle(tmp_path):
    build = load_build()
    written = build.copy_licenses(tmp_path)
    names = {p.name for p in written}
    assert names == {"LICENSE", "MODELS-LICENSE.txt", "THIRD-PARTY-NOTICES.md"}
    assert all(p.is_file() and p.stat().st_size > 1000 for p in written)
    model = (tmp_path / "MODELS-LICENSE.txt").read_text(encoding="utf-8")
    assert "OPEN RAIL-M" in model and "twenty million" in model


def test_the_build_refuses_to_ship_a_bundle_without_its_licences(tmp_path, monkeypatch):
    build = load_build()
    monkeypatch.setattr(build, "ROOT", tmp_path)  # no LICENSE here
    with pytest.raises(SystemExit) as err:
        build.copy_licenses(tmp_path / "dist")
    assert "LICENSE" in str(err.value)


def test_the_release_attaches_the_four_downloads():
    """A tag has to produce something a user can download without an account."""
    workflow = (ROOT / ".github" / "workflows" / "desktop.yml").read_text(encoding="utf-8")
    assert "\n  release:\n" in workflow
    assert "needs: build" in workflow
    assert 'if: startsWith(github.ref, \'refs/tags/\')' in workflow
    # a fork's GITHUB_TOKEN is read-only unless the job asks for more
    assert "permissions:\n      contents: write" in workflow
    assert "gh release create" in workflow
    assert "SHA256SUMS" in workflow
    assert "unofficial fork build" in workflow
    # the archives are made on the runner, so the executable bit survives
    assert "IndraOCR-$v-windows-x64.zip" in workflow
    assert "IndraOCR-$v-linux-x64.tar.gz" in workflow


def test_the_fork_says_it_is_a_fork():
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    head = readme.split("\n## ")[0]
    assert "This repository is a fork" in head
    assert "THIRD-PARTY-NOTICES.md" in head
    notices = (ROOT / "THIRD-PARTY-NOTICES.md").read_text(encoding="utf-8")
    assert "Apache-2.0" in notices and "OPEN RAIL-M" in notices
    assert "not" in notices and "Datalab" in notices


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


def test_the_dmg_shows_the_app_beside_a_link_to_applications(tmp_path):
    """The mounted image is the whole install UI: drag the app onto the link."""
    import os

    build = load_build()
    app = tmp_path / "IndraOCR.app"
    (app / "Contents" / "MacOS").mkdir(parents=True)
    (app / "Contents" / "Info.plist").write_text("<plist/>", encoding="utf-8")
    (app / "Contents" / "MacOS" / "IndraOCR").write_bytes(b"#!binary")

    stage = build.stage_dmg_folder(app, tmp_path / "stage")

    copy = stage / "IndraOCR.app"
    assert (copy / "Contents" / "Info.plist").read_text(encoding="utf-8") == "<plist/>"
    assert (copy / "Contents" / "MacOS" / "IndraOCR").read_bytes() == b"#!binary"
    link = stage / "Applications"
    assert link.is_symlink() and os.readlink(link) == "/Applications"


def test_the_dmg_step_refuses_to_run_off_macos(tmp_path):
    build = load_build()
    if build.sys.platform == "darwin":
        return  # nothing to refuse there
    try:
        build.build_dmg("1.1.3", tmp_path / "IndraOCR.app")
    except SystemExit as e:
        assert "macOS" in str(e)
    else:
        raise AssertionError("build_dmg should refuse to run here")


def test_dmg_only_packs_without_rebuilding(monkeypatch):
    """The sign-then-pack flow must not run PyInstaller over the signature."""
    from indra_ocr import __version__

    build = load_build()
    called = {}
    monkeypatch.setattr(build, "build_dmg", lambda v, app: called.update(v=v, app=app))
    monkeypatch.setattr(build.subprocess, "run", lambda *a, **k: called.update(ran=True))
    assert build.main(["--dmg-only"]) == 0
    assert called["v"] == __version__
    assert called["app"].name == "IndraOCR.app"
    assert "ran" not in called  # no PyInstaller, no selftest


def test_the_macos_bundle_is_in_the_spec():
    """A .dmg needs a .app: the spec wraps the one-folder build on darwin only."""
    spec = (ROOT / "packaging" / "indra_ocr.spec").read_text(encoding="utf-8")
    assert 'if sys.platform == "darwin":' in spec
    assert "BUNDLE(" in spec
    assert 'CFBundleShortVersionString' in spec
    assert 'name="IndraOCR.app"' in spec


def test_the_icns_is_a_real_macos_icon():
    icns = ROOT / "packaging" / "indra_ocr.icns"
    assert icns.read_bytes()[:4] == b"icns"
    from PIL import Image

    with Image.open(icns) as im:
        assert im.format == "ICNS"
        # 16..512 at 1x and 2x, which is what Finder and the Dock pick from
        sizes = {s[0] for s in im.info["sizes"]}
        assert {16, 32, 128, 256, 512} <= sizes


def test_the_version_is_declared_in_both_places():
    """A release bumps pyproject.toml and __init__.py; the two must agree.

    The tag is checked against pyproject.toml by the publish workflow, so a
    missed second bump would ship wheels that call themselves something else.
    """
    import re

    from indra_ocr import __version__

    text = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    declared = re.search(r'^version = "([^"]+)"', text, re.M)
    assert declared, "no version in pyproject.toml"
    assert declared.group(1) == __version__


def test_the_changelog_has_a_section_for_the_release():
    from indra_ocr import __version__

    changelog = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    assert f"\n## {__version__}\n" in changelog
