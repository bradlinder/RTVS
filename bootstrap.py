"""Install-safe startup environment configuration for Radio & TV Segmenter.

APP_NAME is intentionally left as "RadioTVStorySegmenter" (the original
project name) rather than renamed -- it's the per-user app-data folder name,
and changing it would orphan existing users' settings and downloaded model
cache on upgrade to 1.1. Only user-facing branding changed; see prs_shared.py
(APP_DISPLAY_NAME / INTERNAL_APP_ID).
"""
from __future__ import annotations

import os
import sys
import importlib.util
import subprocess
from pathlib import Path

APP_NAME = "RadioTVStorySegmenter"

def app_data_dir() -> Path:
    if sys.platform == "win32":
        root = os.environ.get("LOCALAPPDATA") or os.environ.get("APPDATA")
        base = Path(root) if root else Path.home() / "AppData" / "Local"
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support"
    else:
        base = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))
    path = base / APP_NAME
    path.mkdir(parents=True, exist_ok=True)
    return path


def configure_runtime_environment() -> Path:
    """Prepare writable user data and model-cache locations before imports."""
    root = app_data_dir()
    models = root / "models"
    models.mkdir(parents=True, exist_ok=True)
    # Keep Hugging Face downloads out of the user's generic cache and out of
    # the protected application-install directory. This is only the
    # *default* location; a user-configured custom model directory
    # (Preferences > Processing) is applied later, after QApplication
    # exists and QSettings is safe to use -- see get_models_storage_dir()
    # in prs_shared.py and its use in processing.py/model_management.py.
    os.environ.setdefault("HF_HOME", str(models / "huggingface"))
    os.environ.setdefault("HF_HUB_DISABLE_TELEMETRY", "1")
    return root


def ensure_sherpa_onnx_runtime():
    """Make sure the Parakeet runtime is importable before the GUI starts.

    Source/portable Python runs may not have installed requirements yet.  In
    that case install the same constrained sherpa-onnx package used by the
    application.  A frozen build should already contain the package; the
    build script explicitly collects it so this check is also a useful
    diagnostic rather than attempting to pip-install into a PyInstaller EXE.
    """
    module_name = "sherpa_onnx"
    package_spec = "sherpa-onnx>=1.13,<2"

    if importlib.util.find_spec(module_name) is not None:
        return True

    if getattr(sys, "frozen", False):
        print("[STARTUP] sherpa-onnx is missing from the packaged application.", file=sys.stderr)
        return False

    print("[STARTUP] sherpa-onnx is not installed; installing it now...", flush=True)
    try:
        subprocess.run(
            [sys.executable, "-m", "pip", "install", "--upgrade", package_spec],
            check=True,
        )
        return importlib.util.find_spec(module_name) is not None
    except Exception as exc:
        print(f"[STARTUP] Could not install sherpa-onnx automatically: {exc}", file=sys.stderr)
        return False


def check_and_install_core():
    """Backward-compatible startup dependency check."""
    configure_runtime_environment()
    return ensure_sherpa_onnx_runtime()

if __name__ == "__main__":
    configure_runtime_environment()
