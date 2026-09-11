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
        root = os.environ.get("LOCALAPPDATA") or os.environ.get("APPDATA")
        base = Path(root) if root else Path.home() / "AppData" / "Local"
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support"
    else:
        base = Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local" / "share")
    p = base / "RadioTVStorySegmenter"
    p.mkdir(parents=True, exist_ok=True)
    return p

def get_legacy_models_storage_dirs() -> list[Path]:
    """Return historical fallback model storage directories to recognize previously downloaded models."""
    candidates = []
    if sys.platform == "win32":
        for env_var, sub in [("APPDATA", "Roaming"), ("LOCALAPPDATA", "Local")]:
            root = os.environ.get(env_var)
            base = Path(root) if root else Path.home() / "AppData" / sub
            candidates.append(base / "RadioTVSegmenter" / "models")
            candidates.append(base / "RadioTVStorySegmenter" / "models")
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support"
        candidates.append(base / "RadioTVSegmenter" / "models")
        candidates.append(base / "RadioTVStorySegmenter" / "models")
    else:
        base = Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local" / "share")
        candidates.append(base / "RadioTVSegmenter" / "models")
        candidates.append(base / "RadioTVStorySegmenter" / "models")
    return [c for c in candidates if c.is_dir()]

def get_models_storage_dir() -> Path:
    # 1. Direct environment override
    env_override = os.environ.get("RTVS_MODELS_DIR")
    if env_override and env_override.strip():
        p = Path(env_override.strip())
        try:
            p.mkdir(parents=True, exist_ok=True)
            return p
        except Exception:
            pass

    # 2. QSettings persistent preference
    if QSettings is not None:
        for org in ("RadioTVSegmenter", "RadioTVStorySegmenter"):
            try:
                settings = QSettings(org, "RadioTVStorySegmenter")
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

    # 3. Default canonical storage
    p = get_app_data_dir() / "models"
    p.mkdir(parents=True, exist_ok=True)
    return p

def _has_required_model_files(model_dir: Path) -> bool:
    required = ["config.json", "tokenizer_config.json", "source.spm", "target.spm"]
    if not all((model_dir / name).is_file() and (model_dir / name).stat().st_size > 0 for name in required):
        return False
    weights = [model_dir / "model.safetensors", model_dir / "pytorch_model.bin"]
    return any(p.is_file() and p.stat().st_size > 0 for p in weights)

def model_is_installed(from_code: str, to_code: str, variant: str = "tiny") -> bool:
    """Check if an OPUS-MT translation model is installed on disk without loading ML libraries."""
    import shutil
    model_dir = get_models_storage_dir() / f"opus-mt-{variant}" / f"{from_code}-{to_code}"
    marker = model_dir / ".complete"

    if marker.is_file() and _has_required_model_files(model_dir):
        return True
    if _has_required_model_files(model_dir):
        try:
            marker.write_text("verified\n", encoding="utf-8")
            return True
        except Exception:
            return True

    # Check historical/legacy paths and adopt if valid
    for legacy_root in get_legacy_models_storage_dirs():
        legacy_dir = legacy_root / f"opus-mt-{variant}" / f"{from_code}-{to_code}"
        if legacy_dir.is_dir() and _has_required_model_files(legacy_dir):
            try:
                model_dir.parent.mkdir(parents=True, exist_ok=True)
                shutil.copytree(str(legacy_dir), str(model_dir), dirs_exist_ok=True)
                (model_dir / ".complete").write_text("migrated\n", encoding="utf-8")
                return True
            except Exception:
                return True
    return False

def setup_windows_dll_directories() -> None:
    os.environ["KMP_DUPLICATE_LIB_OK"] = "TRUE"
    os.environ["HF_HUB_DISABLE_SYMLINKS_WARNING"] = "1"
    os.environ["HF_HUB_DISABLE_PROGRESS_BARS"] = "1"
    os.environ["TQDM_DISABLE"] = "1"
    os.environ["TOKENIZERS_PARALLELISM"] = "false"

    class NullWriter:
        def write(self, *args, **kwargs): pass
        def flush(self, *args, **kwargs): pass
        def isatty(self): return False

    if getattr(sys, "stdout", None) is None:
        sys.stdout = NullWriter()
    if getattr(sys, "stderr", None) is None:
        sys.stderr = NullWriter()

    try:
        from huggingface_hub.utils import disable_progress_bars
        disable_progress_bars()
    except Exception:
        pass

    if sys.platform != "win32":
        return
    try:
        dll = Path(sys.prefix) / "Library" / "bin"
        if dll.is_dir() and hasattr(os, "add_dll_directory"):
            os.add_dll_directory(str(dll))
    except Exception:
        pass
