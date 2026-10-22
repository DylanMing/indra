# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec: the desktop app as a one-folder build with the models inside.

Build it through packaging/build.py, which stages the models first:

    python packaging/build.py              # console on (development)
    python packaging/build.py --console 0  # no console window (a release)

A one-folder build starts in about a second; a one-file build unpacks ~300 MB
on every start. The frozen app resolves ``models/`` beside the executable (see
indra_ocr/desktop.py: bundled_models), so it needs no network and no Hugging
Face cache.
"""

import os
from pathlib import Path

from PyInstaller.utils.hooks import collect_all, collect_submodules

ROOT = Path(SPECPATH).parent
MODELS = ROOT / "packaging" / "models"

datas, binaries, hiddenimports = [], [], []
for pkg in ("onnxruntime", "cv2", "pypdfium2_raw"):
    d, b, h = collect_all(pkg)
    datas += d
    binaries += b
    hiddenimports += h

# pywebview picks its backend at runtime, so its platform modules are imported
# lazily and no static analysis finds them.
hiddenimports += collect_submodules("webview.platforms")
# Windows only (pythonnet + WebView2); a warning on other platforms is expected.
hiddenimports += ["clr"]

if MODELS.is_dir():
    datas.append((str(MODELS), "models"))

CONSOLE = os.environ.get("INDRA_CONSOLE", "1") != "0"

a = Analysis(
    [str(ROOT / "packaging" / "entry_desktop.py")],
    pathex=[str(ROOT)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        "torch",
        "torchvision",
        "tensorflow",
        "jax",
        "matplotlib",
        "scipy",
        "pandas",
        "IPython",
        "notebook",
        "pytest",
        "tkinter",
        "PySide6",
        "PyQt5",
        "PyQt6",
        "cefpython3",
    ],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="IndraOCR",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=CONSOLE,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="IndraOCR",
)
