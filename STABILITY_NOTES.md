## v2.1.6 packaging fix

The Windows frozen build now creates and installs a dedicated `workers/prs_worker.exe`
with its complete PyInstaller `_internal` runtime. The GUI no longer falls back to
executing itself as the AI worker. Both the GUI and worker are smoke-tested during
the build for PyTorch, `torch._C`, CTranslate2, Transformers and Silero VAD.

The Windows build scripts also re-install and verify CPU-only PyTorch 2.3.1 after
normal dependency resolution so a CUDA-enabled PyPI wheel cannot silently enter the
release build.

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
