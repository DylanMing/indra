# Electron proof of concept

An Electron shell around the Indra OCR viewer, built to answer one question with
measurements instead of opinions: **is it worth replacing pywebview with Electron?**

It is **not** part of the shipped app. The desktop builds still come from
`indra_ocr/desktop.py` + `packaging/`; nothing here is in the PyInstaller spec, and
the branch that holds it is exploratory.

## What it does

The window is Chromium instead of the OS webview. Everything else is unchanged: the
page, the five HTTP endpoints and the OCR engine are the same Python process, started
here as a child (`sidecar`) and stopped with the window.

```
Electron main process ──spawn──> python -m indra_ocr.viewer --print-port --port 0 --no-browser
        │                                     │
        │  reads {"port": N, "url": ...}      │  serves /, /info, /upload, /page, /clipboard, /preload
        └──────── loadURL(url) ───────────────┘
```

Two small additions to `indra_ocr/viewer.py` make the handshake possible, both tested:

- `--print-port` prints **one** JSON line (`{"port": 51324, "url": "http://localhost:51324"}`)
  instead of a sentence, so the wrapper has something to parse, and never opens a browser.
- `--open FILE` sets the preload, so `electron . report.pdf` behaves like the desktop app
  does when the user double-clicks a file.

## Run it

```sh
# a checkout with .venv built and the models already in the Hugging Face cache
cd electron-poc
npm install
npm start                       # the window
npm run smoke -- ../a.pdf       # open the window, OCR the file, exit 0 or 1
```

`INDRA_SIDECAR=/path/to/IndraOCR.exe` points the shell at a PyInstaller build instead
of the venv; a packaged shell looks for `resources/IndraOCR/IndraOCR[.exe]` by default.

## What it proved (measured, Windows 11, local machine)

`npm run smoke -- poc.png`, where the PNG holds two lines of text:

```
sidecar on http://localhost:56871
sidecar: page 1: ocr, 2 lines, 2 blocks, 128 ms (auto)
smoke OK: window loaded, 1 page(s), first line "HELLO ELECTRON"
```

That is the whole path in Electron: window → page → JavaScript → HTTP → OCR → the card
in the DOM. **5 s** from launch to result, model load included.

| number | value |
| --- | --- |
| the shell itself | **6 KB** of JavaScript (`main.js`); no framework, no bundler |
| Electron 33.4.11 runtime, unpacked | **281 MB** (`electron.exe` alone is 189 MB) |
| Python side, unchanged | the 352 MB Windows bundle we already ship |
| models inside it | 96 MB |
| most of the rest | OpenCV 117 MB, ONNX Runtime 44 MB |

## The size question, which is the whole question

| | today (pywebview) | with Electron |
| --- | --- | --- |
| Windows, installed | 352 MB | **~633 MB** (352 + 281) |
| Windows, setup | 154 MB | **~230–250 MB** (estimate: Electron's 281 MB compresses to ~70–90 MB in NSIS) |
| macOS, installed | 466 MB | ~747 MB |
| macOS, dmg | 199 MB | ~330 MB |
| Linux, installed | 736 MB | ~900 MB (the 122 MB of GTK/WebKitGTK bundling goes away, Chromium comes in) |

An earlier estimate in this project said Electron costs "about 150 MB". **That was
wrong by a factor of two**: the runtime is 281 MB unpacked. So Electron roughly
**doubles** the Windows download for a CPU OCR app whose selling point is being small.

## Verdict

Not worth it on these numbers unless one of these is a hard requirement:

1. a **front end that needs a bundler** (framework, components, hot reload);
2. **auto-update** or crash reporting (`electron-updater` is a first-class thing);
3. shipping on **Linux without `libwebkit2gtk-4.1-0`** (AppImage/deb for machines we do
   not control) — Electron's Chromium makes that problem disappear;
4. consistent rendering across platforms, so the page is written once against one
   engine rather than WebView2 + WKWebView + WebKitGTK.

The cheaper wins first, in order: trim `cv2` (117 MB of the bundle is OpenCV's DNN,
video and contrib code we never call), split the models into a base package and an
optional math package (96 → ~40 MB for most users), and only then reconsider the shell.
Those two get Windows to **200–240 MB**, below today's 352 MB, without a second runtime.

## If it is picked up for real

1. `packaging/` gains an Electron variant: `electron-builder` with
   `extraResources: [{ from: "dist/IndraOCR", to: "IndraOCR" }]`, NSIS + dmg +
   AppImage/deb targets, and `asar: true` for the 6 KB of shell.
2. Two binaries get signed and notarised (the shell and the Python sidecar); macOS
   notarises both bundles in one `notarytool submit`.
3. Tray, global hotkey and single-instance move to Electron (`Tray`,
   `globalShortcut`, `requestSingleInstanceLock`) — this is the one part that gets
   *simpler*, since `indra_ocr/tray.py` is pystray plus a `RegisterHotKey` ctypes shim.
4. The smoke test here becomes a CI step: `xvfb-run -a npx electron . --smoke fixture.png`
   on Ubuntu, which is the same trick as `--windowtest` in `desktop.yml`.
5. `--serve-only`/`--print-port` stays useful either way: it is also how the app can be
   driven from a script or a tunnel today.
6. Keep the pywebview path — it is the smaller, single-process build, and the two can
   share `indra_ocr/viewer.py`, `desktop.py`'s checks and the same models.
