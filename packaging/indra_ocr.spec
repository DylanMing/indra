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
import sys
from pathlib import Path

from PyInstaller.utils.hooks import collect_all, collect_data_files, collect_submodules

ROOT = Path(SPECPATH).parent
MODELS = ROOT / "packaging" / "models"

datas, binaries, hiddenimports = [], [], []
# cv2 used to be here: collect_all("cv2") dragged in 30 MB of ffmpeg, and nothing
# in the app imports it any more (indra_ocr/imaging.py does the pixel work).
for pkg in ("onnxruntime", "pypdfium2_raw"):
    d, b, h = collect_all(pkg)
    datas += d
    binaries += b
    hiddenimports += h

# pywebview picks its backend at runtime, so its platform modules are imported
# lazily and no static analysis finds them.
hiddenimports += collect_submodules("webview.platforms")

if sys.platform == "win32":
    # The Edge backend is pythonnet + WebView2: it loads the .NET assemblies and
    # the WebView2 loader from webview/lib at runtime, and imports clr by name.
    hiddenimports += ["clr", "webview.platforms.edgechromium"]
    datas += collect_data_files("webview")
elif sys.platform == "linux":
    # Linux: pywebview's GTK backend, when the system provides PyGObject (build.py
    # puts /usr/lib/python3/dist-packages on the path for the analysis).
    hiddenimports += ["gi", "gi.repository.Gtk", "gi.repository.WebKit2"]

if MODELS.is_dir():
    datas.append((str(MODELS), "models"))

# The tray icon imports pystray and Pillow inside a function (so the app still
# starts without them), which static analysis cannot see.
hiddenimports += ["pystray", "PIL.Image", "PIL.ImageDraw"]
if sys.platform == "win32":
    hiddenimports += ["pystray._win32"]

CONSOLE = os.environ.get("INDRA_CONSOLE", "1") != "0"
# build.py writes these: the app icon and the VERSIONINFO resource (so the exe
# shows a name and a version in Explorer and in Add/Remove Programs).
ICON = os.environ.get("INDRA_ICON") or None
ICNS = os.environ.get("INDRA_ICNS") or None
VERSION = os.environ.get("INDRA_VERSION") or "0.0.0"
VERSION_FILE = os.environ.get("INDRA_VERSION_FILE") or None

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
        # the imaging layer replaced OpenCV: 117 MB of cv2 and its ffmpeg
        "cv2",
        "opencv",
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
    icon=ICON,
    version=VERSION_FILE,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="IndraOCR",
)

# macOS: a real .app bundle, which is what Finder launches and what a .dmg
# contains.  The one-folder build above stays next to it, for --selftest and for
# anyone who would rather run the executable.
if sys.platform == "darwin":
    app = BUNDLE(
        coll,
        name="IndraOCR.app",
        icon=ICNS or ICON,
        bundle_identifier="to.indra.ocr",
        version=VERSION,
        info_plist={
            "CFBundleName": "Indra OCR",
            "CFBundleDisplayName": "Indra OCR",
            "CFBundleShortVersionString": VERSION,
            "CFBundleVersion": VERSION,
            "CFBundleInfoDictionaryVersion": "6.0",
            "LSMinimumSystemVersion": "11.0",
            "NSHighResolutionCapable": True,
            "NSRequiresAquaSystemAppearance": False,
            "NSHumanReadableCopyright": "Apache-2.0",
        },
    )
