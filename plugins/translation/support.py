"""Small dependency-light helpers shared by the translation plugin runtime."""
from __future__ import annotations
import os, sys
from pathlib import Path
try:
    from PySide6.QtCore import QSettings
except ImportError:
    QSettings = None

def get_app_data_dir() -> Path:
    if sys.platform == "win32":
        base = Path(os.environ.get("APPDATA") or Path.home() / "AppData" / "Roaming")
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support"
    else:
        base = Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local" / "share")
    p = base / "RadioTVSegmenter"
    p.mkdir(parents=True, exist_ok=True)
    return p

def get_models_storage_dir() -> Path:
    if QSettings is not None:
        try:
            settings = QSettings("RadioTVSegmenter", "RadioTVStorySegmenter")
            custom = settings.value("models_dir", "")
            if custom and isinstance(custom, str) and custom.strip():
                p = Path(custom.strip())
                try:
                    p.mkdir(parents=True, exist_ok=True)
                    return p
                except Exception:
                    pass
        except Exception:
            pass
    p = get_app_data_dir() / "models"
    p.mkdir(parents=True, exist_ok=True)
    return p

def model_is_installed(from_code: str, to_code: str, variant: str = "tiny") -> bool:
    """Check if an OPUS-MT translation model is installed on disk without loading ML libraries."""
    model_dir = get_models_storage_dir() / f"opus-mt-{variant}" / f"{from_code}-{to_code}"
    marker = model_dir / ".complete"
    if not marker.is_file():
        return False
    required = ["config.json", "tokenizer_config.json", "source.spm", "target.spm"]
    if not all((model_dir / name).is_file() and (model_dir / name).stat().st_size > 0 for name in required):
        return False
    weights = [model_dir / "model.safetensors", model_dir / "pytorch_model.bin"]
    return any(p.is_file() and p.stat().st_size > 0 for p in weights)

def setup_windows_dll_directories() -> None:
    os.environ["KMP_DUPLICATE_LIB_OK"] = "TRUE"
    os.environ["HF_HUB_DISABLE_SYMLINKS_WARNING"] = "1"
    os.environ["TOKENIZERS_PARALLELISM"] = "false"
    if sys.platform != "win32":
        return
    try:
        dll = Path(sys.prefix) / "Library" / "bin"
        if dll.is_dir() and hasattr(os, "add_dll_directory"):
            os.add_dll_directory(str(dll))
    except Exception:
        pass
