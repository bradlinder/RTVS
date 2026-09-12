# Radio & TV Segmenter — System Architecture & Invariants

This document defines the core architectural rules, module boundaries, and machine learning engine registries for the Radio & TV Segmenter desktop suite.

---

## 1. Machine Learning & Speech Engine Registry

| Subsystem | Primary Engine / Runtime | Execution Location | Notes |
| :--- | :--- | :--- | :--- |
| **Transcription** | `faster-whisper` (CTranslate2) & `sherpa-onnx` (Parakeet TDT) | Core Desktop / Worker | Fast CPU & optional CUDA GPU acceleration |
| **Voice Activity Detection** | `silero-vad` (ONNX) | Core Desktop / Worker | Acoustic story segmentation & silence boundary detection |
| **Speaker Diarization** | `wespeakerruntime` (WeSpeaker ResNet34-LM ONNX) | Core Desktop / Worker | In-memory Fbank computation; no heavy PyTorch PyAnnote dependency |
| **Machine Translation** | `CTranslate2` / Hugging Face MarianMT & NLLB | `plugins/translation/` | Isolated runtime virtual environment |

---

## 2. Unbreakable Architectural Invariants

### 1. Core / Plugin Decoupling
- **Core modules (`RadioTVSegmenter.py`, `processing.py`, `runtime_manager.py`, `prs_shared.py`) MUST NEVER import from `plugins/`.**
- Plugins are optional, modular add-ons that can be uninstalled, disabled, or updated independently without breaking the core application.
- Plugins MAY import from core modules (e.g. `prs_shared.py`, `runtime_manager.py`) and PySide6.

### 2. Frozen App Execution (`sys.frozen`)
- In packaged binary releases (e.g. Windows installer `.exe`, macOS `.app`), **core features (`transcribe`, `diarize`) are bundled directly into the standalone binary**; no virtual environment is created for core tasks.
- **Plugins (`translation`) manage their own isolated virtual environment** in the user application data directory even in frozen builds.

### 3. Asynchronous Provisioning Safety
- Virtual environment creation, wheel downloads, and heavy model verification must **never block the main Qt GUI thread**.
- Long-running operations must run via dedicated `QThread` workers or modal progress handlers.

### 4. AI Studio Web Preview Guard
- The root web scaffolding (`package.json`, `index.html`, `vite.config.ts`, `src/App.tsx`) powers the AI Studio live preview container on port 3000 (serving the interactive changelog).
- Desktop packaging scripts (`build_installer.py`, Inno Setup, GitHub Actions) ignore the web files, keeping the shipped desktop application lightweight and native.

---

## 3. Directory Layout Overview

```text
├── RadioTVSegmenter.py              # Main desktop GUI application entry point
├── prs_shared.py                    # Shared types, UI widgets, constants & branding
├── processing.py                    # Audio transcription, diarization & worker dispatch
├── runtime_manager.py               # Python venv creation, uv management & runtime verification
├── project_export.py                # Broadcast audio, subtitle & document export engines
├── radio_tv_story_segmenter_worker.py # Standalone background AI worker (prs_worker)
├── plugins/                         # Isolated modular add-ons
│   ├── manager.py                   # Plugin discovery, dynamic loading & update sync
│   ├── wordpress/                   # WordPress REST API publisher add-on
│   ├── youtube/                     # YouTube Studio video publisher add-on
│   └── translation/                 # Local neural machine translation add-on
├── installer/                       # Packaging scripts & Inno Setup configs
├── roadmap.txt                      # Future version specifications & milestones
└── CHANGELOG.md                     # Source-of-truth release history
```

---

## 4. Lessons Learned & Technical Guardrails

These rules document solutions to specific historical bugs and must be preserved during all future modifications:

### 1. Windows C-Extension DLL Discovery (`os.add_dll_directory`)
- **Issue**: On Windows, packaged PyInstaller executables (`sys.frozen`) can fail with `ImportError: DLL load failed` when importing compiled native modules (`scipy`, `scikit-learn`, `torch`, `wespeakerruntime`, `onnxruntime`) because Windows 10/11 does not automatically search nested folders for shared OpenMP / BLAS DLLs.
- **Rule**: Never remove or bypass `_setup_windows_dll_directories()` in `RadioTVSegmenter.py` and `radio_tv_story_segmenter_worker.py`, or the runtime hook `torch_dll_hook.py`. Any new native/C++ dependency must register its DLL paths via `os.add_dll_directory()`.

### 2. Windows Path Traversal on Redirected / Cloud Folders (OneDrive / Symlinks)
- **Issue**: When `uv` or Python creates virtual environments in user directories located on OneDrive-synced or redirected corporate profiles, NTFS junctions and symlink creation fail with `os error 448: The path cannot be traversed because it contains an untrusted mount point`.
- **Rule**: Always enforce `UV_LINK_MODE="copy"` in `runtime_manager.py` and use copy-based file operations rather than symlinks or hardlinks on Windows.

### 3. Custom UI Widget Method Forwarding
- **Issue**: Custom PySide6 wrapper widgets (e.g. `ResizableTextEdit` or specialized scroll containers) throw `AttributeError` when callers invoke standard Qt methods (`.setPlaceholderText()`, `.clear()`, `.document()`) if the wrapper is not a direct subclass.
- **Rule**: Any composite or proxy Qt widget in `prs_shared.py` must either inherit directly from the intended base Qt widget or implement dynamic method delegation via `__getattr__`.

### 4. Background Subprocess Pipe Buffering & Streaming
- **Issue**: Spawning background subprocesses (`prs_worker.exe` or `ffmpeg`) with `stdout=subprocess.PIPE` without continuous reading causes the process to freeze indefinitely once the 64 KB OS pipe buffer fills up with progress logs.
- **Rule**: Subprocess execution in `processing.py` and `runtime_manager.py` must always use dedicated reader threads or `QProcess` line-by-line signal streaming (`readyReadStandardOutput`), never blocking `communicate()` on long-running tasks.

### 5. Plugin Upgrade Auto-Sync Across App Updates
- **Issue**: When users upgrade the application, plugins installed in their user data directory (`~/.config` / `AppData`) previously remained stuck on old versions because only the core app binaries were replaced.
- **Rule**: `plugins/manager.py` must automatically detect when a bundled plugin has a higher semantic version than the user-installed copy and perform a clean in-place upgrade on startup.

### 6. Model Cache File-Presence Verification
- **Issue**: Checking only for directory presence or a `.complete` sentinel file during model snapshot downloads causes false positives if downloads are interrupted or files are 0 bytes.
- **Rule**: Model verification routines in `plugins/translation/worker.py` and `radio_tv_story_segmenter_worker.py` must verify the presence and non-zero byte size of actual required weight files (`model.bin`, `tokenizer.json`, ONNX models).

### 7. Model-Specific UI Setting Conditioning
- **Issue**: Autoregressive settings (such as Whisper `beam_size`) cause confusion or invalid CLI flags when displayed while non-autoregressive models (like Parakeet ONNX Fast TDT) are selected.
- **Rule**: In `playback_preferences.py`, model-specific parameters must dynamically show/hide based on the currently selected model architecture.

### 8. YouTube Exporter Chapter Timestamp Sanitization
- **Issue**: YouTube Studio rejects chapter timestamps or fails to generate timeline chapters if timestamps do not begin with `00:00` or have fewer than 3 chapters of at least 10 seconds each.
- **Rule**: `plugins/youtube/` must automatically enforce YouTube's formal chapter rules during story export (guaranteeing `00:00:00 - Introduction` and valid ascending interval formatting).


