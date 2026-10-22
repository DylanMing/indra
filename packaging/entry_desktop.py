"""PyInstaller entry point: desktop.py uses relative imports, so it cannot be
the entry script itself (PyInstaller runs the script as ``__main__``)."""

from indra_ocr.desktop import main

if __name__ == "__main__":
    raise SystemExit(main())
