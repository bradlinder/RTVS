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


def setup_windows_dll_directories() -> None:
    """Register native DLL directories (PyTorch, CTranslate2, ONNX Runtime, etc.)
    on Windows before importing C-extensions or ML frameworks.

    Python 3.8+ on Windows does not search PATH for DLL dependencies of .pyd files,
    requiring os.add_dll_directory() to be called explicitly on directory paths
    containing dependent DLLs (such as torch/lib, ctranslate2, onnxruntime, etc.).
    """
    if sys.platform != "win32":
        return

    candidate_dirs = set()

    # 1. PyInstaller frozen application locations
    if getattr(sys, "frozen", False):
        meipass = getattr(sys, "_MEIPASS", None)
        if meipass:
            meipass_path = Path(meipass)
            candidate_dirs.add(meipass_path)
            candidate_dirs.add(meipass_path / "torch" / "lib")
            candidate_dirs.add(meipass_path / "torch")
            candidate_dirs.add(meipass_path / "torchaudio" / "lib")
            candidate_dirs.add(meipass_path / "ctranslate2")
            candidate_dirs.add(meipass_path / "onnxruntime" / "capi")
            candidate_dirs.add(meipass_path / "sherpa_onnx" / "lib")
            candidate_dirs.add(meipass_path / "sherpa_onnx")

        exe_dir = Path(sys.executable).parent
        candidate_dirs.add(exe_dir)
        candidate_dirs.add(exe_dir / "_internal")
        candidate_dirs.add(exe_dir / "_internal" / "torch" / "lib")
        candidate_dirs.add(exe_dir / "_internal" / "torch")
        candidate_dirs.add(exe_dir / "_internal" / "torchaudio" / "lib")
        candidate_dirs.add(exe_dir / "torch" / "lib")
        candidate_dirs.add(exe_dir / "torch")

    # 2. Check sys.path entries for package lib directories without importing them
    for entry in list(sys.path):
        if not entry:
            continue
        try:
            p = Path(entry)
            if not p.is_dir():
                continue
            candidate_dirs.add(p)
            candidate_dirs.add(p / "torch" / "lib")
            candidate_dirs.add(p / "torch")
            candidate_dirs.add(p / "torchaudio" / "lib")
            candidate_dirs.add(p / "ctranslate2")
            candidate_dirs.add(p / "onnxruntime" / "capi")
            candidate_dirs.add(p / "sherpa_onnx" / "lib")
            candidate_dirs.add(p / "sherpa_onnx")
        except Exception:
            continue

    # 3. Check sys.prefix and executable parent site-packages
    try:
        prefix = Path(sys.prefix)
        candidate_dirs.add(prefix / "bin")
        candidate_dirs.add(prefix / "Library" / "bin")
        candidate_dirs.add(prefix / "Lib" / "site-packages" / "torch" / "lib")
        candidate_dirs.add(prefix / "Lib" / "site-packages" / "torchaudio" / "lib")
        candidate_dirs.add(prefix / "Lib" / "site-packages" / "ctranslate2")
        candidate_dirs.add(prefix / "Lib" / "site-packages" / "onnxruntime" / "capi")
    except Exception:
        pass

    # 4. Also use importlib.util.find_spec to locate torch/lib if possible without importing
    try:
        spec = importlib.util.find_spec("torch")
        if spec and spec.origin:
            torch_root = Path(spec.origin).parent
            candidate_dirs.add(torch_root / "lib")
            candidate_dirs.add(torch_root)
    except Exception:
        pass

    # 5. Add all existing directories to os.add_dll_directory and PATH
    added_paths = []
    for d in candidate_dirs:
        try:
            resolved = d.resolve()
            if resolved.is_dir():
                str_path = str(resolved)
                if hasattr(os, "add_dll_directory"):
                    try:
                        os.add_dll_directory(str_path)
                    except Exception:
                        pass
                added_paths.append(str_path)
        except Exception:
            continue

    if added_paths:
        current_path = os.environ.get("PATH", "")
        os.environ["PATH"] = os.pathsep.join(added_paths) + os.pathsep + current_path


def configure_runtime_environment() -> Path:
    """Prepare writable user data and model-cache locations before imports."""
    setup_windows_dll_directories()
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
        creationflags = subprocess.CREATE_NO_WINDOW if sys.platform == 'win32' else 0
        subprocess.run(
            [sys.executable, "-m", "pip", "install", "--upgrade", package_spec],
            check=True,
            creationflags=creationflags,
        )
        return importlib.util.find_spec(module_name) is not None
    except Exception as exc:
        print(f"[STARTUP] Could not install sherpa-onnx automatically: {exc}", file=sys.stderr)
        return False

def ensure_keyring_runtime():
    """Ensure keyring (and pywin32-ctypes on Windows) is installed for secure credential storage."""
    missing = []
    if importlib.util.find_spec("keyring") is None:
        missing.append("keyring>=24.0.0")
    if sys.platform == "win32" and importlib.util.find_spec("win32ctypes") is None:
        missing.append("pywin32-ctypes>=0.2.2")

    if not missing:
        return True

    if getattr(sys, "frozen", False):
        print(f"[STARTUP] Keyring dependencies missing in packaged build: {missing}", file=sys.stderr)
        return False

    print(f"[STARTUP] Installing missing credential dependencies: {', '.join(missing)}...", flush=True)
    try:
        creationflags = subprocess.CREATE_NO_WINDOW if sys.platform == 'win32' else 0
        subprocess.run(
            [sys.executable, "-m", "pip", "install", "--upgrade", *missing],
            check=True,
            creationflags=creationflags,
        )
        return importlib.util.find_spec("keyring") is not None
    except Exception as exc:
        print(f"[STARTUP] Could not install keyring dependencies automatically: {exc}", file=sys.stderr)
        return False

def check_and_install_core():
    """Backward-compatible startup dependency check."""
    configure_runtime_environment()
    return ensure_sherpa_onnx_runtime()

if __name__ == "__main__":
    configure_runtime_environment()
