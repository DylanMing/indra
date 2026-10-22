#!/usr/bin/env python3
"""Stage the models and build the desktop app (one folder) with PyInstaller.

    python packaging/build.py                  # models from the local HF cache
    python packaging/build.py --models DIR     # or from a folder copied earlier
    python packaging/build.py --console 0      # release: no console window
    python packaging/build.py --installer      # ... and a Windows setup .exe

The build lands in ``dist/IndraOCR/`` and is checked with ``--selftest`` (the
whole pipeline, headless, against the models inside the build), so a broken
bundle fails here rather than on a user's machine.  On Windows ``--installer``
then compiles ``packaging/indra_ocr.iss`` with Inno Setup into
``dist/IndraOCR-<version>-setup.exe``: a per-user install with a Start menu
shortcut, an uninstall entry and an optional .pdf association, with the SHA256
written next to it (``.sha256``): the installer is not code signed, so that is
what a user checks.
"""

from __future__ import annotations

import argparse
import hashlib
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SPEC = ROOT / "packaging" / "indra_ocr.spec"
MODELS = ROOT / "packaging" / "models"
ICON = ROOT / "packaging" / "indra_ocr.ico"
ISS = ROOT / "packaging" / "indra_ocr.iss"
APP = "IndraOCR"

# Everything model_dir(math=True) promises: the recognizers and the math models.
NEEDED = (
    "det.onnx",
    "rec.onnx",
    "order.onnx",
    "meta.json",
    "mathcls.onnx",
    "math_enc.onnx",
    "math_dec_init.onnx",
    "math_dec_step.onnx",
    "math_meta.json",
)


def stage_models(src: Path) -> Path:
    src = src.expanduser().resolve()
    missing = [f for f in NEEDED if not (src / f).is_file()]
    if missing:
        raise SystemExit(
            f"{src} is not a complete model folder: missing {', '.join(missing)}"
        )
    if src == MODELS.resolve():
        # --models packaging/models: already staged, and copying onto itself
        # would empty the folder first.
        print(f"models already staged in {MODELS}", flush=True)
        return MODELS
    if MODELS.exists():
        shutil.rmtree(MODELS)
    MODELS.mkdir(parents=True)
    for f in sorted(src.iterdir()):
        if f.is_file():
            shutil.copy2(f, MODELS / f.name)  # copy2 follows the cache's symlinks
    return MODELS


def write_version_info(version: str, out: Path | None = None) -> Path:
    """The VERSIONINFO resource PyInstaller stamps into the exe.

    Without it Explorer shows no name and no version, and Add/Remove Programs
    lists the app as "IndraOCR" with a blank version.
    """
    parts = [int(p) for p in (version.split("+")[0].split(".") + ["0", "0", "0"])[:4]]
    dotted = ".".join(str(p) for p in parts)
    out = out or ROOT / "build" / "version_info.txt"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        f"""VSVersionInfo(
  ffi=FixedFileInfo(
    filevers={tuple(parts)}, prodvers={tuple(parts)},
    mask=0x3f, flags=0x0, OS=0x40004, fileType=0x1, subtype=0x0, date=(0, 0)),
  kids=[
    StringFileInfo([StringTable('040904B0', [
      StringStruct('CompanyName', 'Indra OCR'),
      StringStruct('FileDescription', 'Indra OCR - local OCR desktop app'),
      StringStruct('FileVersion', '{dotted}'),
      StringStruct('InternalName', 'IndraOCR'),
      StringStruct('LegalCopyright', 'Apache-2.0'),
      StringStruct('OriginalFilename', 'IndraOCR.exe'),
      StringStruct('ProductName', 'Indra OCR'),
      StringStruct('ProductVersion', '{dotted}')])]),
    VarFileInfo([VarStruct('Translation', [1033, 1200])])])
""",
        encoding="utf-8",
    )
    return out


def find_iscc() -> Path | None:
    """Inno Setup's command-line compiler, from PATH or the usual install spots."""
    found = shutil.which("iscc")
    if found:
        return Path(found)
    for base in (
        Path(os.environ.get("LOCALAPPDATA", "")) / "Programs",
        Path(os.environ.get("ProgramFiles(x86)", "C:/Program Files (x86)")),
        Path(os.environ.get("ProgramFiles", "C:/Program Files")),
    ):
        for name in ("Inno Setup 6", "Inno Setup 5"):
            candidate = base / name / "ISCC.exe"
            if candidate.is_file():
                return candidate
    return None


def write_checksum(path: Path) -> Path:
    """Write ``<file>.sha256`` beside a release file.

    The installer is not code signed, so this is how a user can tell that the
    164 MB they downloaded is the one this build produced: same format as
    ``sha256sum``, and ``Get-FileHash -Algorithm SHA256`` prints the same digest.
    """
    digest = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            digest.update(chunk)
    out = path.with_name(path.name + ".sha256")
    out.write_text(f"{digest.hexdigest()}  {path.name}\n", encoding="utf-8")
    print(f"sha256 {digest.hexdigest()}  {path.name}", flush=True)
    return out


def build_installer(version: str, dist: Path) -> Path:
    """Compile the Inno Setup script; returns the .exe it wrote."""
    iscc = find_iscc()
    if iscc is None:
        raise SystemExit(
            "Inno Setup is not installed: winget install JRSoftware.InnoSetup"
        )
    # ISCC resolves a relative SourceDir against the .iss file, not this process.
    dist = Path(dist).resolve()
    if not dist.is_dir():
        raise SystemExit(f"nothing to install from {dist}: build it first")
    cmd = [
        str(iscc),
        f"/DAppVersion={version}",
        f"/DSourceDir={dist}",
        str(ISS),
    ]
    print(f"installer: {' '.join(cmd)}", flush=True)
    subprocess.run(cmd, check=True)
    setup = ROOT / "dist" / f"IndraOCR-{version}-setup.exe"
    if not setup.is_file():
        raise SystemExit(f"the installer was not written to {setup}")
    print(f"installer {setup} ({setup.stat().st_size / 1e6:.0f} MB)", flush=True)
    write_checksum(setup)
    return setup


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--models",
        type=Path,
        help="folder with the model files (default: the local Hugging Face cache)",
    )
    ap.add_argument(
        "--console",
        choices=("0", "1"),
        default="1",
        help="1: keep the console window (development), 0: a release build",
    )
    ap.add_argument("--skip-selftest", action="store_true")
    ap.add_argument(
        "--installer",
        action="store_true",
        help="also build the Windows setup .exe with Inno Setup",
    )
    a = ap.parse_args()

    from indra_ocr import __version__

    src = a.models
    if src is None:
        from indra_ocr.models import model_dir

        src = Path(model_dir(math=True))
    print(f"models: {src}", flush=True)
    staged = stage_models(src)
    print(f"staged {len(list(staged.iterdir()))} files in {staged}", flush=True)

    version_file = write_version_info(__version__)
    env = dict(
        os.environ,
        INDRA_CONSOLE=a.console,
        INDRA_VERSION_FILE=str(version_file),
        INDRA_ICON=str(ICON) if ICON.is_file() else "",
    )
    # On Linux the webview backend is gi/GTK from the system, not from the venv:
    # let PyInstaller find it, so a Linux bundle opens a window too.
    try:
        import gi  # noqa: F401
    except ImportError:
        system = Path("/usr/lib/python3/dist-packages")
        if system.is_dir():
            env["PYTHONPATH"] = os.pathsep.join(
                [str(system), env.get("PYTHONPATH", "")]
            ).rstrip(os.pathsep)
    cmd = [
        sys.executable,
        "-m",
        "PyInstaller",
        str(SPEC),
        "--noconfirm",
        "--distpath",
        str(ROOT / "dist"),
        "--workpath",
        str(ROOT / "build"),
    ]
    print("building ...", flush=True)
    subprocess.run(cmd, check=True, env=env)

    app = ROOT / "dist" / APP
    exe = app / (APP + (".exe" if os.name == "nt" else ""))
    if not exe.is_file():
        raise SystemExit(f"build finished but {exe} is missing")
    size = sum(f.stat().st_size for f in app.rglob("*") if f.is_file())
    print(f"built {app} ({size / 1e6:.0f} MB)", flush=True)

    if not a.skip_selftest:
        print("checking the build (--selftest) ...", flush=True)
        r = subprocess.run(
            [str(exe), "--selftest"], capture_output=True, text=True, timeout=900
        )
        print((r.stdout or r.stderr).strip(), flush=True)
        if r.returncode != 0:
            print("self test FAILED", flush=True)
            return r.returncode

    if a.installer:
        if os.name != "nt":
            raise SystemExit("--installer builds a Windows setup: run it on Windows")
        build_installer(__version__, app)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
