# Contributing to Indra OCR

Bug reports, patches and doc fixes are welcome. The [README](README.md) is the manual; this file is the part that only matters if you are changing the code.

## Set up

```shell
git clone https://github.com/datalab-to/indra.git && cd indra
python -m venv .venv
. .venv/bin/activate            # Windows: .venv\Scripts\activate
pip install -e ".[test]"
pytest -q                       # the whole suite: no models, no network, ~10 s
```

The tests need no models and no network: the fixtures are generated in `tmp_path`, and nothing in the suite touches the Hugging Face cache. The extras in `pyproject.toml` are separate on purpose — `[test]` is what the suite needs, `[desktop]` the viewer's window (pywebview, Pillow, pystray), `[build]` PyInstaller, `[tesseract]` the comparison readers the CLI can call.

## The layout

| file | what it holds |
| --- | --- |
| `__init__.py` | the public API — `load()`, `convert_many()`, `usable_cores` — and `__version__` |
| `pipeline.py` | the pipeline on ONNX Runtime: line detection, CTC recognition, reading order; `Engine` is what every front end drives |
| `document.py` | whole documents: the PDF text layer where it can be trusted, OCR for the rest, page by page |
| `textlayer.py` | text-layer runs from pdfium, and the checks that decide whether to trust them |
| `det_post.py`, `line_mask.py`, `rec_preproc.py`, `rtl.py` | detection post-processing, line masking, the recognition crop rule, right-to-left text for a left-to-right recognizer |
| `order_post.py`, `layout_post.py`, `math.py`, `lm.py`, `vocab.py` | reading order, layout heads, the math classifier and reader, the language model, the token vocabulary |
| `parallel.py` | many pages on many cores: a pool of worker processes, one page per task |
| `models.py` | model files: a local folder, or a download from the Hugging Face repo |
| `cli.py`, `viewer.py`, `desktop.py`, `tray.py`, `clipboard.py`, `health.py` | the front ends: command line, local viewer, native window, tray and hotkey, paste, first-run checks |
| `packaging/build.py`, `packaging/indra_ocr.spec` | the PyInstaller build, and the `.exe`/`.app`/`.dmg`/installer around it |

Two conventions are worth knowing. The `*_post.py` and `*_preproc.py` modules are the torch-free half of what the models were trained with — their docstrings say "shared by training and inference" — so a change there has to keep the numbers identical, and the tests pin the behaviour (reading order, line grouping, crops) with hand-checked fixtures. And every front end goes through `Engine`, so a pipeline fix lands in the CLI, the viewer and the app at once.

## Tests

```shell
pytest -q                          # everything
pytest tests/test_textlayer.py -q  # one file
pytest -q -k window                # by name
```

Names are sentences (`test_a_busy_port_is_reported_and_exits_1`), not `test_foo_2`: the failure message is meant to say what broke. A test that needs a platform or a system package skips rather than silently passes — `test_a_missing_webview2_runtime_is_reported` skips off Windows. CI runs the same suite on Python 3.12 (`.github/workflows/publish.yml`).

## The desktop app

There are two ways to run it: `pip install -e ".[desktop]"` then `indra-ocr-desktop`, or the packaged build.

```shell
python packaging/build.py --console 0 --skip-selftest    # build, skip the self test
python packaging/build.py --console 0                    # build, then --selftest the bundle
python packaging/build.py --console 0 --installer        # Windows: Inno Setup after the build
python packaging/build.py --console 0 --dmg              # macOS: dist/IndraOCR.app and the .dmg
```

The build stages the models from the local Hugging Face cache (or `--models DIR`) and takes about a minute. `--windowtest` is the other check, and the one that matters on Linux: it opens the real window, closes it and prints the backend, while `--selftest` is headless and passes on a bundle that has no window at all.

The same check against an installed app, without PyInstaller:

```shell
pip install -e ".[desktop]"
indra-ocr-desktop --windowtest     # needs a display; CI runs it under xvfb
```

`.github/workflows/desktop.yml` builds all three platforms on `workflow_dispatch` and on a version tag, uploads `IndraOCR-<os>`, `IndraOCR-windows-setup` and `IndraOCR-macos-dmg`, and runs `--windowtest` under `xvfb` on Linux. Start it with `gh workflow run desktop`, or Actions → desktop → Run workflow; the artifacts land on the run page.

## Releasing

1. Bump `version` in `pyproject.toml` **and** `__version__` in `indra_ocr/__init__.py` — a test fails if they disagree.
2. Add a `## <version>` section to [CHANGELOG.md](CHANGELOG.md). When the models did not change, say so in the release's first line (recent releases read `Same models (Hugging Face tag v1.1.0).`).
3. Commit, then tag the commit and push the tag:

   ```shell
   git tag v1.1.5 && git push origin v1.1.5
   ```

4. The tag starts both workflows. `desktop` builds the three bundles and the installer. `publish` checks that the tag matches `pyproject.toml`, runs the tests, builds the sdist and the wheel, checks them with `twine` and that nothing is over 20 MB, and then publishes to PyPI — that last job only runs **upstream**: PyPI's trusted publisher names `datalab-to/indra` and the `pypi` environment, so on a fork the publish job is skipped and the build job still runs.

A published version cannot be replaced on PyPI: if the tag and the declared version differ, the job stops before anything is uploaded. To check the flow without publishing, run the `publish` workflow manually — it builds and tests, and stops before the upload.

## Signing

The builds are unsigned, and the README says how to check the SHA256 instead. If you have certificates, the steps are already written in `.github/workflows/desktop.yml`, commented out: `signtool` on the exe and the setup, `codesign` + `notarytool` + `stapler` on the `.app`, driven by `secrets.WINDOWS_CERT`, `secrets.WINDOWS_CERT_PASSWORD` and the macOS equivalents. A signed build removes the SmartScreen prompt and the Gatekeeper warning; an unsigned one still works, with a hash to check.

## Docs

- The README is the manual, and every flag in `--help` should be in it: the tests do not read the docs, so this is on the reviewer.
- Measured numbers carry what they were measured on (cores, page type) — "about 44 pages/s on 32 cores", not "fast".
- A section that answers a support question belongs in *Troubleshooting* (`README.md`), with the message the user will actually see.
- `EXAMPLES.md` holds unedited model output; the `##` lines inside its fenced blocks are the page's headings, not the file's.
