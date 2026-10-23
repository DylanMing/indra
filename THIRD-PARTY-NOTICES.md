# Notices for the Indra OCR desktop builds

These builds come from a fork: [DylanMing/indra](https://github.com/DylanMing/indra), based on
[datalab-to/indra](https://github.com/datalab-to/indra). They are **not** releases by Datalab, and
nothing here implies that Datalab endorses them. The upstream project, its documentation and its
model weights are Datalab's.

## Two licences apply, to two different things

**The code is Apache-2.0.** The full text is `LICENSE`, next to this file and in the repository. That
licence permits redistribution and modification, and asks in return that the copyright notices stay,
that the changes are stated (section 4(b), below), and that no trademark or endorsement is implied
(section 6).

**The model weights are not Apache-2.0.** The files in `_internal/models/` (`*.onnx`, `*.npz`,
`meta.json`) are under the *AI PUBS OPEN RAIL-M License (Modified)* published with the weights at
<https://huggingface.co/datalab-to/indra-ocr/blob/main/LICENSE>; the text is `MODELS-LICENSE.txt`,
next to this file. Receiving the weights means receiving that licence, so it travels with every
build. In short, and in the licence's own words: free for research and personal use, and for
organisations that stayed under 20 million USD of revenue and of funding in the prior year, and not
for use in competition with Datalab's API. That summary is not the licence: read `MODELS-LICENSE.txt`
or the pricing page at <https://www.datalab.to/pricing> before commercial use.

## What this fork changed

Generated from `git log --oneline` against the upstream commit these builds are based on. The
upstream tag is recorded in [CHANGELOG.md](https://github.com/DylanMing/indra/blob/main/CHANGELOG.md)
for each release ("Same models (Hugging Face tag `v1.1.0`)").

- `indra_ocr/desktop.py`: a native window around the existing viewer (pywebview), a tray icon and a
  global hotkey, first-run checks, `--selftest` and `--windowtest`.
- `indra_ocr/viewer.py`, `indra_ocr/clipboard.py`: the viewer serves the page from a local port,
  paste from the clipboard, and the preload path for a file the app was opened with.
- `indra_ocr/tray.py`, `indra_ocr/health.py`: tray and hotkey, and the state file under
  `%LOCALAPPDATA%\IndraOCR` (or `~/.local/state/IndraOCR`).
- `packaging/`: `build.py`, `indra_ocr.spec`, the icon generator, the Inno Setup script and the
  `.dmg` staging — the PyInstaller build, the Windows installer and the macOS bundle.
- `tests/`: tests for the above, and for the release rules in `pyproject.toml` and `CHANGELOG.md`.
- Fixes to the pipeline's model download (a partial Hugging Face snapshot no longer hides the math
  models) and to the reading-order code; see the 1.1.x sections of `CHANGELOG.md` for each.

Files from upstream are otherwise unmodified; where one is, the change is listed above.

## Third-party components in the bundle

| component | licence |
| --- | --- |
| ONNX Runtime | MIT |
| pypdfium2 / PDFium | Apache-2.0 / BSD-3-Clause |
| NumPy | BSD-3-Clause |
| Hugging Face Hub | Apache-2.0 |
| pywebview | BSD-3-Clause |
| Pillow | MIT-CMU |
| pystray | LGPL-3.0 |
| PyInstaller (build time) | GPL-2.0 with a bootloader exception |

The Python distributions in `_internal/` each carry their own licence file
(`_internal/<name>-<version>.dist-info/licenses/`), which is where to look for the exact text.

## Where to ask

Upstream bugs and model questions: <https://github.com/datalab-to/indra/issues>. The desktop app,
the installer and the `.dmg`: <https://github.com/DylanMing/indra/issues>.
