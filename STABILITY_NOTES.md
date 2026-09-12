## v2.9.2 stability notes

The core desktop application and standalone AI worker (`workers/prs_worker.exe`)
are built CPU-first with Faster-Whisper, Silero VAD, CTranslate2, PyTorch, and
WeSpeaker ONNX (`wespeakerruntime`).

- Post-Plugin Modular Architecture: Heavy machine translation (Hugging Face `Transformers`,
  MarianMT, and Seq2Seq models) runs strictly in an isolated, on-demand virtual environment
  managed by the `plugins/translation/` add-on rather than the core frozen runtime.
- Diarization Runtime: Speaker diarization utilizes the native ONNX WeSpeaker ResNet34-LM
  embedding engine (`wespeakerruntime`) with in-memory Fbank computation, eliminating
  heavy PyTorch PyAnnote dependencies from core runtime packaging.
- GPU Acceleration: On Windows, optional NVIDIA CUDA acceleration is provisioned on demand
  via `uv` and remains completely isolated from the base installer.


# Release hardening notes — 1.1.1

This build is intended as the installable release candidate.

- CPU-only is the default and is the only AI stack bundled into the base installer.
- FFmpeg/ffprobe remain private application runtimes; users do not need to install them.
- PySide6 collection is restricted to QtCore, QtGui, QtWidgets, QtMultimedia and QtMultimediaWidgets.
- Unused Qt modules are explicitly excluded during PyInstaller packaging.
- Windows can ship the small `uv` runtime manager so optional NVIDIA CUDA support can provision its own Python environment without requiring the user to install Python.
- NVIDIA CUDA support remains optional and is not bundled with the base installer.
- macOS keeps GPU acceleration disabled because the current optional backend is NVIDIA CUDA, which is not available on macOS.
- User data, models, logs and optional runtimes remain outside the installation directory so application uninstall/update does not remove them.
- The Windows Inno Setup script and macOS app/DMG script are included in this release tree.
