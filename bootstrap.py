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
    # the protected application-install directory.
    os.environ.setdefault("HF_HOME", str(models / "huggingface"))
    os.environ.setdefault("HF_HUB_DISABLE_TELEMETRY", "1")
    return root


def check_and_install_core():
    """Backward-compatible name; dependencies are bundled by the installer."""
    return configure_runtime_environment()

if __name__ == "__main__":
    configure_runtime_environment()
