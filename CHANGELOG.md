# Changelog

## 1.1.6

Same models (Hugging Face tag `v1.1.0`). One change, and one that was measured and
deliberately not made.

- **OpenCV's video backend is no longer in the Windows bundle.** The Windows
  cv2 wheel ships `opencv_videoio_ffmpeg500_64.dll`, 31 MB, which cv2 loads only
  when a `VideoCapture` or `VideoWriter` is opened — and this app reads PDFs,
  images and the clipboard, never a video. The spec filters that DLL out of the
  finished analysis, before `COLLECT`, so it does not matter whether the copy
  comes from `collect_all("cv2")` or from PyInstaller's cv2 hook. Windows goes
  from 352 MB to 321 MB and the installer from 160 MB to 151 MB; macOS (466 MB)
  and Linux (736 MB) do not carry that DLL and are unchanged. OpenCV itself
  stays, and the self test runs inside each built folder.
- **Replacing OpenCV altogether was tried and rejected.** A Pillow/NumPy
  implementation of the six calls the pipeline makes (`resize`, rotation,
  connected components, decode, encode, draw text) takes 118 MB out of the
  bundle — and reads text identically on seven of eight small rotations of a test
  page — but a page goes from 0.36 s to 0.55 s: the deskew search rotates a
  thumbnail about seventy times and Pillow is 8x slower at that than OpenCV.
  Not worth it for a third of the download, so 1.1.6 keeps OpenCV and records the
  measurement here instead of repeating it later.

## 1.1.5

Same models (Hugging Face tag `v1.1.0`). The first release of this fork to publish
the desktop builds properly.

- **The bundles shipped no licence.** They carry the model weights, which are not
  Apache-2.0: the modified OpenRAIL-M asks that anyone who receives the weights
  receives its text, and Apache-2.0 asks for the notice and a statement of changes.
  Nothing said either. `MODELS-LICENSE.txt` and `THIRD-PARTY-NOTICES.md` are in the
  repository now, and the build copies all three texts into `dist/IndraOCR/` (and
  into `IndraOCR.app/Contents/Resources`, so the `.dmg` carries them). The Windows
  installer shows the notices before it installs (`LicenseFile=`), and calls itself a
  fork build rather than pointing at upstream as the publisher.
- **A release, not a pile of artifacts.** `actions/upload-artifact` needs a GitHub
  account to download and keeps files for 90 days. A tag now also creates a GitHub
  Release, with all four downloads and a `SHA256SUMS`, titled "unofficial fork
  build" and opening with the licence and support situation. The release job asks
  for `contents: write` because a fork's token is read-only by default.
- **The downloads are archives.** The Windows folder is a `.zip` and the Linux one a
  `.tar.gz` made on the runner, so the archive carries the executable bit that
  upload-artifact's own zip drops, and the filename carries the version.
- **The README says it is a fork**, at the top and under *Installing on Windows*,
  with what that means: unofficial, Apache-2.0 code, weights under their own licence.

## 1.1.4

Same models (Hugging Face tag `v1.1.0`). The 1.1.3 tag stays as the snapshot CI
built and verified; these are the fixes it turned up.

- **A startup failure was invisible in the release build.** A windowed build has
  no console, and the three ways the app can stop before showing anything — the
  port is taken, the models are missing, no webview backend — wrote to `stderr`,
  which PyInstaller sets to `None`. The process ended with no window and no word.
  They now print when there is a console and show the same message in a dialog
  when there is not (`desktop.say`, `desktop.fail`), the mechanism the first-run
  check already used.
- **A tag on a fork turned the `publish` job red.** PyPI's trusted publisher names
  `datalab-to/indra`, so the exchange from any fork failed with
  `invalid-publisher`; the tag looked broken when only the publisher was missing.
  The job is now skipped unless the repository is upstream, while the `build` job
  (tests, artifact check, version check) still runs everywhere.
- **The Linux bundle had no window, and the build said it was fine.** The Linux
  runner had no PyGObject, GTK 3 or WebKit2GTK, so PyInstaller logged
  `Typelib file for namespace 'Gtk', version '3.0' not found`, left the GTK half
  out, and the headless `--selftest` passed anyway. The workflow now installs
  `python3-gi`, `gir1.2-gtk-3.0` and `gir1.2-webkit2-4.1` first, which also clears
  pystray's `Namespace Gtk not available`.
- **... and GTK alone was still not a window.** PyInstaller's GI runtime hook sets
  `GI_TYPELIB_PATH` to the bundled `gi_typelibs` and nothing else, while the bundle
  holds GTK but not WebKit2GTK: `gi.require_version("WebKit2", ...)` could not
  resolve, so the GTK backend had no webview. `desktop.system_typelibs()` now
  appends the system typelib folders to that path for a frozen Linux build, so the
  window comes from the host's `libwebkit2gtk` and the rest stays bundled.
- **Neither CI job could have caught it.** `--selftest` is headless by design, so a
  bundle with no window passed. `--windowtest` opens the real window, closes it and
  reports the backend, and the workflow runs it under `xvfb` on Linux: a bundle
  that cannot build a webview now fails the build.
- **Docs**: the measured sizes (a 200 MB `.dmg`, a 160 MB setup), what Windows
  and Linux actually need at run time (WebView2; `libwebkit2gtk` beside the bundled
  GTK), the flags that were only in `--help` (`--port`, `--threads`,
  `--tesseract-lang`, `--width`, `--height`, `--skip-selftest`), explicit exit
  codes, and two sections that were missing: *Upgrading and uninstalling* and
  *Troubleshooting*. The README has a table of contents, `CONTRIBUTING.md` covers
  the development setup, a map of the modules, the app build and what a release
  does, and two tests now fail when the version in `pyproject.toml` and
  `indra_ocr/__init__.py` disagree, or when this file has no section for it.

## 1.1.3

Same models (Hugging Face tag `v1.1.0`).

- **Turning math on after a run without it.** The models download on demand, and a
  first run without `--math` leaves the math models out of the cached snapshot. That
  folder was then trusted for every later run, so turning math on failed with
  `FileNotFoundError: math=True needs the math models in ...`, and retrying never
  recovered (the cached folder is returned before the download is attempted). The
  cached folder is now checked for the files the run needs, the download completes
  it, and a folder that still lacks them raises a `ModelError` naming them
  ([#18](https://github.com/datalab-to/indra/issues/18)).
- **Paste a screenshot into the viewer.** `Ctrl+V` (`Cmd+V` on macOS) reads the
  image on the clipboard through the same path as a dropped file, so a screenshot
  can be OCR'd without saving it first. A copied PDF pastes too, where the
  browser hands the file over. A **Paste from clipboard** button covers webviews
  that do not pass clipboard files to the page (WebKitGTK).
- **A desktop app.** `pip install "indra-ocr[desktop]"` and `indra-ocr-desktop`
  open the viewer in a native window; `packaging/build.py` builds a self-contained
  app with the models inside (no network, no Python install) and checks it with
  a headless `--selftest`. The bundle is built per platform (WebView2/Edge on
  Windows, WKWebView on macOS, WebKitGTK on Linux).
- **Windows.** The desktop app and the bundle were run on Windows 11 (x64): the
  Edge backend, `Ctrl+V` in the page, the clipboard fallback (Pillow's
  `ImageGrab`) and a 352 MB one-folder build that OCRs with its own models and an
  empty Hugging Face cache. Three things only Windows showed:
  - A console or pipe on Windows uses a legacy code page (cp936, cp1252), so one
    character outside it (`•`, a math sign) raised `UnicodeEncodeError` and ended
    the run with the rest of the document lost. Pipes now get UTF-8; a console
    keeps its code page and replaces what it cannot show.
  - A pasted screenshot was named after UTC, so at 16:40 in Shanghai it was
    listed as `clipboard-...T08-40-24.png`; the name now carries local time.
  - `packaging/indra_ocr.spec` bundles pywebview's .NET assemblies for the Edge
    backend, and asks for PyGObject only on Linux; `pip install ".[desktop,build]"`
    now brings PyInstaller, and `build.py --models packaging/models` no longer
    empties the folder it copies from.
- **A Chinese or Japanese Windows could not read an image, or use math.** Two
  places took the machine's code page instead of the file's:
  - `cv2.imread` opens a file with the ANSI code page, so `扫描件.png` came back as
    "not a PDF or a readable image" although the file was fine. The bytes are now
    read by Python and decoded in memory, so any filename Python can open works
    (a test pins that `imread`/`imreadmulti` are not used).
  - `math_meta.json` was read with `Path.read_text()` and no encoding, which is
    cp936 on Chinese Windows: the `°`, `–`, `’` and `⁄` tokens raised
    `UnicodeDecodeError`, so `--math`, `math=True` and the viewer's **Math as
    LaTeX** switch never worked there. Model metadata is read as UTF-8
    (`indra_ocr.models.read_json`), for `meta.json` too.
- **A PDF the CLI read, the viewer refused.** `/upload` looked only at the first
  5 bytes for `%PDF-`, while the pipeline scans 1024 (a header may follow a little
  junk, as Acrobat and mail gateways write it): the CLI read the file and the app
  answered "not a PDF or a readable image". Both use `pipeline.is_pdf_bytes` now.
  An upload dropped by the five-document limit also says so, instead of
  `KeyError: '3f2a…'`.
- **A malformed request left the page waiting forever.** `/upload` and `/page`
  read `Content-Length` before the handler's `try`, so a non-numeric or negative
  header raised out of `BaseHTTPRequestHandler`: the socket closed with no status
  line and the page sat on "Uploading ...". The header is parsed inside the error
  path now and answers 400 with the reason, and a client that disconnects
  mid-request no longer raises a second traceback. `GET /clipboard` (a failed
  clipboard read, say another app holding it) answers the same way instead of
  dropping the connection.
- **A second copy of the app could share the first one's port.** On Windows
  `SO_REUSEADDR` (which `ThreadingHTTPServer` sets) allows binding a port that is
  already listening: two windows on `--port 8799` both printed the URL, and every
  request was served by the first process while the second loaded a whole second
  copy of the models. The server refuses that bind on Windows and names the port.
- **`--dpi` outside 150/200/300 reached the page.** The picker offers only those
  three, so `--dpi 250` left the `<select>` blank, the page sent `dpi: 0`, and the
  document rendered at 200 dpi. The picker now shows the value it was given, and
  the server treats a missing or non-positive `dpi` as 200.
- **An unusable `--out` folder is one line, not a traceback.** Pointing `--out` at
  an existing file, or at a folder without write permission, raised
  `FileExistsError`/`PermissionError` through `main()` with the first input's stack
  and no output. It now names the path, counts the input as failed, and reads the
  next one.
- **Release builds carried a console window.** CI built with `build.py`'s default
  (`--console 1`), so the published app had a console subsystem and left a console
  window behind the GUI; `--console 0` is what the README documents for releases.
  The workflow passes it now.
- **`python -m indra_ocr` reported success when an input failed.** `__main__.py`
  called `main()` and dropped its `return 1`, so a missing or unreadable file
  printed "1 of 1 inputs failed" and exited 0 (the `indra-ocr` script exited 1
  correctly, which is why it went unnoticed). It raises `SystemExit` now.
- **A very large page allocated more for the text-layer check than for its OCR.**
  `Converter.page_scale` caps the render at `MAX_PAGE_PIXELS`, but the check pass
  always asked for 1 px/pt: a 14400 pt plan wanted a 207 MP array before the page
  was even known to have a text layer, 3x its capped OCR render (measured peak
  785 MB in `auto` against 529 MB in `--mode ocr`). The check is scaled like the
  render (`Converter.check_scale`).
- **`--max-pages 1` on a multi-page TIFF decoded every frame first.** A 40-frame
  120 MB TIFF peaked 286 MB above baseline to return one page; the first frame is
  now decoded alone when only one page is wanted (`read_images(..., limit=)`).
- **Stage timings added up to more than `total_ms` on image pages.** The
  orientation pass was added to `orient_ms` after `_read` had summed the stages,
  so `--format json` and the viewer's per-page bar were 6-13% low (scan.png:
  2508 ms reported, 2670 ms of stages). The total counts it now.
- **A PDF with an empty page tree was reported as unopenable.** pdfium answers
  "Failed to load document (PDFium: Success)" for a well-formed file with no
  pages; the CLI passed that on as "cannot open the PDF". It says "the PDF has no
  pages" now. The parallel reader and `Converter` share one `document.open_pdf`,
  which also stopped the message from differing between `--cores 1` and the pool.
- **`indra-ocr-viewer` printed a URL and left the user to paste it.** It opens the
  default browser now, and prints the port it actually bound (so `--port 0` shows
  the real one). `--no-browser` keeps the old behaviour for a headless box or an
  SSH tunnel, where a browser on the far side is useless.
- **The desktop app could not be given a file.** `IndraOCR.exe report.pdf` (what a
  `.pdf` association passes) now opens and reads that file: the window fetches it
  from the local server once (`GET /preload`, the name in `X-Filename`) and runs
  the page as if it had been dropped. A path that does not exist says so and the
  app still starts.
- **The app had no tray, no hotkey, and no first-run check.**
  - Closing the window hid it for good: there was no way back except restarting.
    With `pystray` installed (in `.[desktop]`) the app keeps a tray icon, closing
    the window hides it and the tray's **Open**/**Quit** control it;
    `--tray`/`--no-tray` forces the choice.
  - `--hotkey "ctrl+alt+o"` (the default; `""` for none) shows the window from any
    program, through `RegisterHotKey` in its own thread. A hotkey another program
    already holds is reported, not silently lost.
  - A bundle without its models, or a Windows box without the WebView2 runtime,
    now says so in a dialog on start instead of failing on the first click. What
    the check found goes into `%LOCALAPPDATA%\IndraOCR\state.json` (version, first
    and last run, problems). `INDRA_OCR_DEBUG_PORT=9222` opens a DevTools port on
    the page, to see what the window really renders.
- **The Windows build had no icon, no version, and no installer.** `build.py` now
  stamps a VERSIONINFO resource (`FileVersion` from `indra_ocr.__version__`, so
  Explorer and Add/Remove Programs show "Indra OCR 1.1.3") and the icon drawn by
  `packaging/make_icon.py` (7 sizes, 16-256, no font needed). `--installer`
  compiles `packaging/indra_ocr.iss` with Inno Setup into
  `dist/IndraOCR-1.1.3-setup.exe` (164 MB, lzma2, English and Chinese): a per-user
  install into `%LOCALAPPDATA%\Programs\IndraOCR` with a Start menu shortcut, an
  uninstall entry and an optional `.pdf` association. `desktop.yml` builds it on
  `windows-latest` and uploads it next to the folder; the signing steps are there,
  commented, waiting for a certificate.
- **The version was 1.1.2 while `CHANGELOG.md` had a 1.1.3 section.** `pyproject`
  and `indra_ocr.__version__` say 1.1.3, which is also what the exe and the
  installer now report.
- **An unsigned installer with nothing to check it against.** There is no
  Authenticode certificate, so SmartScreen stops the setup with "Windows 已保护你的
  电脑" and the UAC prompt says 未知发布者, and a user had no way to tell a good
  download from a re-packed one. `build.py --installer` now writes
  `IndraOCR-<version>-setup.exe.sha256` beside the setup (`<hash>  <name>`, the
  `sha256sum` format; `Get-FileHash` and `certutil -hashfile` print the same
  digest), `desktop.yml` uploads it with the installer, and the README's new
  *Installing on Windows* section says what the two prompts are, how to verify the
  hash, and how an organisation can sign its own build so that nobody sees them.
- **macOS had no app bundle and nothing to install.** The macOS build stopped at
  the one-folder output, which Finder cannot launch as an app; there was no
  `Info.plist`, no icon and no disk image. The spec now builds
  `dist/IndraOCR.app` on macOS (name, version, `LSMinimumSystemVersion` 11.0,
  Retina, the icon from the new `packaging/indra_ocr.icns`, which `make_icon.py`
  writes for the 16-512 @1x/2x set), and `build.py --dmg` packs it into
  `dist/IndraOCR-<version>.dmg` (UDZO, HFS+) holding the bundle and an
  `/Applications` link, verified with `hdiutil verify` and shipped with its
  `.sha256`. `--dmg-only` packs the bundle that is already there, so the order can
  be sign → notarise → staple → pack, which `--dmg`-after-build would undo. CI
  builds and uploads the `.dmg` on `macos-latest`; it uploads no `.app`, because
  an artifact download loses the executable bit. The README's *macOS app and .dmg*
  section has the Gatekeeper steps for the unsigned build and the `codesign` +
  `notarytool` + `stapler` lines for when there is a certificate.

## 1.1.2

Same models (Hugging Face tag `v1.1.0`).

- **PDFs with legacy-font text layers.** Many Hindi PDFs use legacy fonts (Kruti Dev, DevLys), whose text layer stores Latin codes in place of Devanagari, so Indra read them as Latin garbage. Before trusting a text layer, Indra now checks the script of a few of its lines against the line images; when the layer is Latin while the page shows another script, OCR reads the page. On such Hindi pages, word accuracy goes from 0.01-0.20 to 0.85-0.89. The same check covers other legacy fonts, such as Bijoy for Bangla. It adds about 5 ms per text-layer page.

## 1.1.1

Same models (Hugging Face tag `v1.1.0`).

- **Right-to-left text layers in visual order** ([#11](https://github.com/datalab-to/indra/issues/11)). Some PDF producers, Chrome among them, store Arabic-script letters partly in visual order, so their text layer read letter-reversed, with spaces inside words. Such a layer is no longer trusted, and OCR reads the page instead. On Chrome-printed Wikipedia pages, word recall goes from 0.17 to 1.00 (Arabic), 0.25 to 0.89 (Persian), 0.22 to 0.95 (Pashto) and 0.28 to 0.98 (Urdu). Hebrew and Yiddish layers in logical order still read as text.
- A right-to-left page is no longer mistaken for vertical writing.
- `examples/quickstart.ipynb` downloads two sample pages (`examples/samples/`) when you have no `scan.png` or `equations.png`, so it runs as is (also in Colab).

## 1.1.0

Models from Hugging Face tag `v1.1.0`. On OmniParseBench (the benchmark's own harness), the headline goes from 62.3 to 66.7, and from 67.0 to 71.4 with `--math`. Handwriting tests 8.3% -> 25.2%, rotated pages 25.3% -> 50.3%, tables 56.3 -> 61.1.

- **Handwriting.** The line detector and the Latin recognizer are trained on real handwritten and filled-form pages.
- **80+ languages on scans.** New recognizers for Chinese, Japanese and Korean; for right-to-left scripts (Arabic, Persian, Urdu, Pashto, Hebrew); and for other scripts (the Indic scripts, Thai, Lao, Khmer, Myanmar, Sinhala, Georgian, Armenian, Ethiopic). A line classifier sends each line to its recognizer, and n-gram language models re-read unsure lines. The Latin recognizer adds the letters of Hausa, Fula, Akan, Azerbaijani and Uzbek and the tone marks of Vietnamese and Yoruba.
- **Pages at any angle.** Tilts up to 45 degrees are straightened, and the orientation model is trained on real turned scans. A sideways table in a PDF's text layer reads upright, and a page turned by its PDF `/Rotate` reads its text layer in order.
- **Light text on dark ground** (slides, dark table headers) reads.
- **Chinese layout.** Chinese text blocks are no longer mistaken for tables.
- **Examples.** `examples/ocr_image.py` (one image file to markdown, text or JSON) and `examples/quickstart.ipynb`.
- `--max-pages` rejects a negative value.
- The default model download is about 76 MB (was 18 MB): 30 MB of networks and 46 MB of language models.
- Speed: about 44 pages per second on 32 x86 cores, and about 16% more time per page than 0.3.2, for the extra work on each OCR page.

## 0.3.2

- Models from Hugging Face tag `v3.1.1`: the same models as `v3.1`, plus
  `config.json` (the file the Hub counts downloads by) and `model.safetensors`
  (the recognizer's weights, for the Hub's parameter count; never downloaded).
- A cached model folder is checked against the Hub at most once a day
  (`CHECK_EVERY_S`); the other runs use the cache with no network, and a
  failed check (offline) keeps the cached models.

## 0.3.1

- A model download that fails (no network, no access) or a model folder with
  missing files raises `indra_ocr.ModelError` with one clear message; the CLI
  and the viewer print it as one line and exit with 1.
- `--version` for `indra-ocr` and `indra-ocr-viewer`.
- `page.skew` is rounded to 0.01 degree.
- Project links on PyPI, and absolute image URLs in the PyPI description, so
  its images show there.
- README: install from PyPI (`pip install indra-ocr`); a Limitations section
  that leads with complex tables, handwriting and scripts outside the OCR list.

## 0.3.0

Models v3 (Hugging Face `datalab-to/indra-ocr`, tag `v3`; `v3.1` adds the math models).

- **Viewer.** A Datalab-styled page with the pipeline options in the page
  (source, math, headers and footers, reading order, OCR inside images, dpi,
  page limit), show/hide for lines, blocks, block labels and reading order, and
  tabs for the rendered markdown, its source, the lines and the JSON.
- `convert_many` no longer hangs when its worker processes cannot start (with
  the spawn start method, code not under `if __name__ == "__main__":`, or code
  from stdin): it warns and reads the remaining inputs in the calling process.
- **Math (opt-in).** `--math` / `load(math=True)`: a line classifier
  (`mathcls.onnx`) and a math recognizer (`math_enc` / `math_dec_init` /
  `math_dec_step.onnx`, attention decoder with cached keys and values) write
  lines with math as text with inline LaTeX. A reading replaces a line only
  with math in it and a mean token probability of 0.9 or more. Omni Parse
  Bench: headline 62.1 -> 66.8, text 41.4 -> 57.5, math tests 14.3 -> 56.5,
  tables 56.4 -> 54.8; median page ~210 -> ~360 ms (x86, 4 cores, auto mode).
  Off by default; the math models download only when it is on.

- **Orientation.** `orient.onnx` turns a page that is turned by a quarter or
  half turn upright before detection (`page.rotation`). A turn needs at least
  95% from the model. Omni Parse Bench: rotated content 3.5% -> 24.3%.
- **All cores.** The CLI and the new `indra_ocr.convert_many` run one
  single-threaded worker process per usable core, one page per task (a single
  PDF too); `--cores` limits them. 40 documents: 30.0 s on 1 core, 8.7 s on 4,
  2.8 s on 16 (one process with ORT threads gained at most 1.2x beyond 4
  cores). The CLI's `--threads` is now an alias of `--cores`.
- **Deskew.** A page tilted by up to 5 degrees is straightened before
  detection (`page.skew`, about 8 ms a page); boxes are mapped back to the
  page as turned. Omni Parse Bench rotation_skew suite: 60.0 -> 76.4.
- **Low-confidence lines get no text.** A recognized line under 0.5 mean
  confidence (empty form fields, checkboxes, rules read as "-", "I", "1")
  keeps its box but no text.
- **Orientation from a broken text layer.** A PDF page OCR'd for a broken font
  map is not turned when its glyphs run upright (orient.onnx turns about half
  of upright Arabic and Hebrew pages).
- **CJK markdown.** Lines of Chinese or Japanese join without a space; a
  bullet detected as its own line starts a list item.
- Table cells escape only `&`, `<` and `>` (no `&#x27;`).
- **Text inside diagrams and charts.** The detector finds 51% of the text
  inside pictures (12.5% before).
- **Right-to-left text layers.** Runs in a right-to-left line are ordered right
  to left.
- **OCR only where it can read.** A text layer in a script the recognizer
  cannot read is kept even when a trust check fails (not for broken font
  maps), and empty lines on such pages are not OCR'd into junk.
- **Layout blocks.** `page.blocks` lists the layout blocks (label, box, text)
  in reading order; the CLI's JSON output includes them.
- **`--keep-furniture`** keeps page headers and footers in the markdown.
- **Optional models:** `script.onnx` + `rec_cjk.onnx` route lines with Chinese
  characters to a Chinese recognizer; `mask.onnx` (CenterMask) masks
  neighbouring lines before recognition. Both run only when present.
- `bench/opb_indra.py`: Omni Parse Bench runner.
- **Robust inputs** (release test: 4,340 benchmark pages, 1,177 documents with
  16,017 pages, 37 edge cases): the file type comes from the file's bytes;
  multi-page TIFFs give every page; pages above 100 MP render at a lower dpi;
  unreadable, corrupt or password-protected files raise `InputError`
  (`password=` / `--password`); a page that fails gives an empty page with
  `source == "error"` instead of ending the document; the CLI continues past
  failed files and exits 1. Text outside a PDF's crop box is not read.
- **Faster on dense pages:** reading-order clustering is O(n^2) instead of
  O(n^3) (a 1,984-line page: 53 s -> 0.45 s).
- **Bounded memory:** ONNX Runtime's CPU arena is off (it grew without bound
  on changing batch shapes; a 40-page large scan: 4.9 GB -> 1.4 GB).

## 0.2.0

Models v2. Blocks and table heads from average-linkage
clustering.

## 0.1.0

First package: ONNX pipeline, PDF text-layer mode, CLI, viewer.
