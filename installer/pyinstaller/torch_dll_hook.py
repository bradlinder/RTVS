"""PyInstaller runtime hook for Windows ML/native DLL resolution.

This runs before the application imports torch, torchaudio, CTranslate2 or
ONNX Runtime.  Frozen applications cannot rely on the normal Python PATH/DLL
search rules for .pyd dependencies, so register the packaged native-library
folders explicitly and keep the handles alive for the process lifetime.
"""
from __future__ import annotations

import ctypes
import os
import sys
from pathlib import Path

_HANDLES = []

if sys.platform == "win32":
    root = Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
    dirs = [
        root,
        root / "torch" / "lib",
        root / "torch",
        root / "torchaudio" / "lib",
        root / "ctranslate2",
        root / "onnxruntime" / "capi",
        root / "sherpa_onnx" / "lib",
        root / "sherpa_onnx",
    ]
    paths = []
    for directory in dirs:
        try:
            directory = directory.resolve()
            if not directory.is_dir():
                continue
            text = str(directory)
            if text not in paths:
                paths.append(text)
            if hasattr(os, "add_dll_directory"):
                try:
                    _HANDLES.append(os.add_dll_directory(text))
                except OSError:
                    pass
        except OSError:
            pass

    if paths:
        os.environ["PATH"] = os.pathsep.join(paths) + os.pathsep + os.environ.get("PATH", "")

    # Do not eagerly ctypes-load PyTorch DLLs here.  Loading torch_cpu/torch_python
    # manually before Python imports torch can change initialization order.  The
    # explicit DLL directories above are sufficient; torch._C will load its
    # native dependency chain normally.
