// Electron proof of concept for Indra OCR: the window is Chromium (not the OS
// webview), and everything else stays where it is — the page, the five HTTP
// endpoints and the OCR engine are the same Python process as before, started
// here as a child and stopped with the window.
//
//   npm install && npm start          the app
//   npm run smoke                     open the window, prove it loaded, exit 0
//
// A packaged build would put the PyInstaller folder in resources/ (see the
// README): the shell is ~150 MB, the Python side is the 352 MB bundle we already
// build, so this doubles the footprint per platform. That is the trade.
const { app, BrowserWindow, dialog } = require("electron");
const { spawn } = require("child_process");
const path = require("path");
const readline = require("readline");

const SMOKE = process.argv.includes("--smoke");
const SMOKE_TIMEOUT_MS = 180_000;

let sidecar = null;
let window = null;
let exitCode = 0;

function sidecarCommand() {
  // A file on the command line (`electron . report.pdf`) is opened on start: the
  // viewer serves it once at /preload and the page uploads it itself.
  const files = process.argv
    .slice(1)
    .filter((a) => !a.startsWith("-") && a !== ".")
    .flatMap((f) => ["--open", f]);
  // Set INDRA_SIDECAR to point at a built IndraOCR.exe, or let it guess.
  if (process.env.INDRA_SIDECAR) {
    return { cmd: process.env.INDRA_SIDECAR, args: files, cwd: undefined };
  }
  if (app.isPackaged) {
    const folder = path.join(process.resourcesPath, "IndraOCR");
    const exe = process.platform === "win32" ? "IndraOCR.exe" : "IndraOCR";
    return { cmd: path.join(folder, exe), args: files, cwd: folder };
  }
  const root = path.join(__dirname, "..");
  const py =
    process.platform === "win32"
      ? path.join(root, ".venv", "Scripts", "python.exe")
      : path.join(root, ".venv", "bin", "python");
  return { cmd: py, args: ["-m", "indra_ocr.viewer", ...files], cwd: root };
}

function startSidecar() {
  const { cmd, args, cwd } = sidecarCommand();
  return new Promise((resolve, reject) => {
    let settled = false;
    const fail = (why) => {
      if (!settled) {
        settled = true;
        reject(new Error(why));
      }
    };
    try {
      sidecar = spawn(cmd, [...args, "--print-port", "--port", "0", "--no-browser"], {
        cwd,
        stdio: ["ignore", "pipe", "pipe"],
      });
    } catch (e) {
      fail(`cannot start ${cmd}: ${e.message}`);
      return;
    }
    sidecar.on("error", (e) => fail(`cannot start ${cmd}: ${e.message}`));
    sidecar.on("exit", (code, signal) => {
      if (!settled) fail(`the OCR process exited (${code ?? signal}) before it listened`);
      else if (!SMOKE && window) {
        dialog.showErrorBox("Indra OCR", "The OCR process stopped.");
        app.quit();
      }
    });
    sidecar.stderr.on("data", (d) => process.stderr.write(d));
    readline
      .createInterface({ input: sidecar.stdout })
      .on("line", (line) => {
        // The first line is {"port": N, "url": "..."} — see --print-port.
        if (settled) {
          process.stdout.write(`sidecar: ${line}\n`);
          return;
        }
        try {
          const { url } = JSON.parse(line);
          settled = true;
          resolve(url);
        } catch {
          process.stdout.write(`sidecar: ${line}\n`);
        }
      });
  });
}

async function main() {
  const url = await startSidecar();
  console.log(`sidecar on ${url}`);
  if (SMOKE) {
    // Armed before the load: a load that never finishes must fail, not hang.
    setTimeout(() => {
      console.error("smoke FAILED: the window never finished loading");
      app.exit(1);
    }, SMOKE_TIMEOUT_MS);
  }

  window = new BrowserWindow({
    width: 1280,
    height: 860,
    minWidth: 900,
    minHeight: 600,
    title: "Indra OCR",
    backgroundColor: "#f6f5f2",
    webPreferences: {
      // The page is served over HTTP and needs nothing from Node.
      nodeIntegration: false,
      contextIsolation: true,
      sandbox: true,
    },
  });
  window.setMenuBarVisibility(false);
  // The page is upstream's and titles itself "Indra OCR viewer · Datalab"; this
  // build is the fork's, so the window keeps the app name.
  window.on("page-title-updated", (e) => e.preventDefault());

  window.webContents.on("did-fail-load", (_e, code, desc, failedUrl) => {
    console.error(`load failed: ${desc} (${code}) ${failedUrl}`);
    if (SMOKE) {
      exitCode = 1;
      app.exit(1);
    }
  });

  window.webContents.on("did-finish-load", async () => {
    if (!SMOKE) return;
    // The page uploads the file itself on load (via /preload), so wait for the
    // card it renders: that proves window, page, JavaScript and OCR together.
    const deadline = Date.now() + SMOKE_TIMEOUT_MS - 5_000;
    let cards = 0;
    while (Date.now() < deadline) {
      cards = await window.webContents.executeJavaScript(
        "document.querySelectorAll('#out .card').length",
      );
      if (cards > 0) break;
      await new Promise((r) => setTimeout(r, 500));
    }
    const title = await window.webContents.executeJavaScript("document.title");
    const sample = await window.webContents.executeJavaScript(
      "(document.querySelector('#out .card .ln-row .t')||{}).textContent||''",
    );
    if (cards > 0) {
      console.log(`smoke OK: window loaded, ${cards} page(s), first line "${sample}"`);
      app.exit(0);
    } else {
      console.error(`smoke FAILED: nothing was OCRed (title "${title}")`);
      app.exit(1);
    }
  });

  await window.loadURL(url);
}

function stopSidecar() {
  if (sidecar && !sidecar.killed) {
    sidecar.kill();
    sidecar = null;
  }
}

app.on("window-all-closed", () => app.exit(exitCode));
// app.exit() skips before-quit, so the child is stopped from here instead:
// otherwise the OCR process outlives the window and the terminal that started it.
app.on("will-quit", stopSidecar);
process.on("exit", stopSidecar);

app.whenReady().then(main).catch((e) => {
  console.error(`smoke FAILED: ${e.message}`);
  if (SMOKE) app.exit(1);
  else {
    dialog.showErrorBox("Indra OCR", e.message);
    app.exit(1);
  }
});
