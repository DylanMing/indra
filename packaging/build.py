#!/usr/bin/env python3
"""Stage the models and build the desktop app (one folder) with PyInstaller.

    python packaging/build.py                  # models from the local HF cache
    python packaging/build.py --models DIR     # or from a folder copied earlier
    python packaging/build.py --console 0      # release: no console window

The build lands in ``dist/IndraOCR/`` and is checked with ``--selftest`` (the
whole pipeline, headless, against the models inside the build), so a broken
bundle fails here rather than on a user's machine.
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SPEC = ROOT / "packaging" / "indra_ocr.spec"
MODELS = ROOT / "packaging" / "models"
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
    a = ap.parse_args()

    src = a.models
    if src is None:
        from indra_ocr.models import model_dir

        src = Path(model_dir(math=True))
    print(f"models: {src}", flush=True)
    staged = stage_models(src)
    print(f"staged {len(list(staged.iterdir()))} files in {staged}", flush=True)

    env = dict(os.environ, INDRA_CONSOLE=a.console)
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
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
