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

    # Preload the core PyTorch DLL chain in dependency order when present.
    # Failure is deliberately non-fatal; Python will report the real import
    # error if a required dependency is absent.
    for dll_name in ("c10.dll", "torch_cpu.dll", "fbgemm.dll", "libiomp5md.dll", "ctranslate2.dll", "onnxruntime.dll"):
        for directory in paths:
            candidate = Path(directory) / dll_name
            if candidate.is_file():
                try:
                    ctypes.CDLL(str(candidate))
                    break
                except OSError:
                    continue
