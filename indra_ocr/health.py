"""What a fresh install needs before it can OCR, and a small state file.

The desktop app checks these on start: a bundle whose models are missing and a
Windows box without the WebView2 runtime are the two failures worth a dialog
before the window opens, instead of a stack trace or an empty window.
"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime
from pathlib import Path

# Every run needs these; the math models are downloaded on first --math use, so
# their absence is not a first-run blocker.
NEEDED = ("det.onnx", "rec.onnx", "order.onnx", "meta.json")

# The WebView2 runtime's EdgeUpdate client id.
WEBVIEW2_GUID = "{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}"


def model_problems(models: Path | None) -> list[str]:
    """Missing files in an explicit or bundled model folder.

    ``None`` means "the Hugging Face cache": it is downloaded on first use, so
    an empty cache is not a problem.
    """
    if models is None:
        return []
    models = Path(models)
    missing = [f for f in NEEDED if not (models / f).is_file()]
    if not missing:
        return []
    return [
        f"the model files are missing from {models}: {', '.join(missing)}. "
        "Reinstall the app, or start it with --model-dir pointing at a full folder."
    ]


def webview2_problem() -> str | None:
    """Windows only: pywebview draws with the WebView2 runtime (Edge)."""
    if os.name != "nt":
        return None
    import winreg

    keys = (
        (
            winreg.HKEY_LOCAL_MACHINE,
            rf"SOFTWARE\WOW6432Node\Microsoft\EdgeUpdate\Clients\{WEBVIEW2_GUID}",
        ),
        (winreg.HKEY_LOCAL_MACHINE, rf"SOFTWARE\Microsoft\EdgeUpdate\Clients\{WEBVIEW2_GUID}"),
        (winreg.HKEY_CURRENT_USER, rf"Software\Microsoft\EdgeUpdate\Clients\{WEBVIEW2_GUID}"),
    )
    for root, sub in keys:
        try:
            with winreg.OpenKey(root, sub) as key:
                version, _ = winreg.QueryValueEx(key, "pv")
        except OSError:
            continue
        if version and version != "0.0.0.0":
            return None
    return (
        "the Microsoft WebView2 runtime is not installed, so the window cannot "
        "open. Install it from "
        "https://developer.microsoft.com/microsoft-edge/webview2/ and start the "
        "app again."
    )


def first_run_problems(models: Path | None) -> list[str]:
    """The reasons the app would not work, in the order to fix them."""
    problems = model_problems(models)
    runtime = webview2_problem()
    if runtime:
        problems.append(runtime)
    return problems


def state_dir() -> Path:
    """Where the app keeps its own small files (the state file, later the config)."""
    if os.name == "nt":
        base = Path(os.environ.get("LOCALAPPDATA") or Path.home() / "AppData" / "Local")
    else:
        base = Path(os.environ.get("XDG_STATE_HOME") or Path.home() / ".local" / "state")
    return base / "IndraOCR"


def record_start(version: str, models: Path | None, problems: list[str]) -> Path | None:
    """Write state.json: the version, when the app was first and last started, and
    the problems the checks found.  Support has something to read; nothing is sent."""
    try:
        folder = state_dir()
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / "state.json"
        previous: dict = {}
        if path.is_file():
            try:
                previous = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                previous = {}
        now = datetime.now().astimezone().isoformat(timespec="seconds")
        data = {
            "version": version,
            "first_run": previous.get("first_run") or now,
            "last_run": now,
            "runs": int(previous.get("runs") or 0) + 1,
            "models": str(models or "Hugging Face cache"),
            "problems": problems,
        }
        path.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
        return path
    except OSError:  # a read-only profile is not a reason to refuse to start
        return None


def report(problems: list[str], title: str = "Indra OCR") -> None:
    """Tell the user: a message box on Windows, stderr everywhere."""
    text = "Indra OCR found a problem:\n\n" + "\n\n".join(f"- {p}" for p in problems)
    print(text, file=sys.stderr, flush=True)
    if os.name != "nt":
        return
    try:
        import ctypes

        ctypes.windll.user32.MessageBoxW(None, text, title, 0x10)  # MB_ICONERROR
    except Exception:  # noqa: BLE001  (no window station, e.g. a service)
        pass
