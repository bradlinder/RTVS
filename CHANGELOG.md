# Changelog

## v1.9.1

- Renamed user-facing Speaker Diarization references to **Detect Speakers**.
- Added an optional speaker-estimate prompt before non-batch speaker detection jobs, with a Preferences > Detection setting to ask every time or automatically use Auto-Detect.
- Open Media, Open Document, and Open Project dialogs now remember the last folder used.
- Renamed the Batch Processing translation option to **Translate** and made the selected English→Spanish, Spanish→English, or Auto-Detect direction control the actual translation output.

## v1.9.0

- Diarization engine overhaul: replaced the "Speaker Detection Sensitivity" slider (which `diarize` 0.1.2's embedding/clustering never actually read) with a "Default Expected Speakers" setting (Auto-Detect / 1 / 2 / 3+), also selectable per batch job.
- Added a solo fast-path: with 1 expected speaker, Speaker Detection now runs Silero VAD only (no WeSpeaker embedding or clustering) and, when a transcript already exists, can skip the local worker process entirely and label everything "Speaker 1" in-memory (~0.01s instead of a full detection pass).
- Speaker labels are now normalized to "Speaker 1", "Speaker 2", etc. in order of first appearance, instead of the diarize package's raw internal ids.
- Clamped OMP/ONNX Runtime thread pools (capped at 8, based on physical cores) before onnxruntime/torch/diarize are imported, to stop CPU oversubscription slowing down detection on high-thread-count machines.
- FFmpeg audio normalization for diarization now explicitly discards video/subtitle/data streams (`-vn -sn -dn -map 0:a:0?`) before decoding.
- Batch Processing dialog: "Diarize Speakers" renamed to "Speaker Detection" with an inline Expected Speakers selector; Story Detection gained inline Silence Gap / Lead-in Padding fields; "Spanish Translation" renamed to "Translation" with an explicit direction selector (Auto-Detect flips between English and Spanish based on the transcript's detected language, or force English→Spanish / Spanish→English).
- Existing projects saved by older builds that still have a `speaker_sensitivity` value load fine; the setting just falls back to "Auto-Detect" since it no longer maps to anything.

## v1.8.6
- Added a startup check for the sherpa-onnx Parakeet runtime; source/portable Python builds automatically install `sherpa-onnx>=1.13,<2` when it is missing.
- Updated the Windows/PyInstaller build to bundle the sherpa-onnx runtime.
- Fixed Parakeet token parsing so leading-space tokens are split into real words, preserving per-word timestamps and creating multiple transcript segments for speaker diarization.
- Improved Parakeet segment timing with sentence, word-count, and speech-gap boundaries so its transcript follows the same general timestamp/segment behavior as Whisper.
- Cleared the Speaker Detection progress-stage label when diarization finishes.

## 1.8.5

- Fixed persistent Transcription Model preferences so the selection survives application restart and is not overwritten by project files. Restore Defaults explicitly resets it to Small.
- Reworked Parakeet ONNX transcription to use the sherpa-onnx TDT runtime with the required encoder/decoder/joiner model bundle and automatic 80/128-feature detection.
- Activity Log exports now append the current date to the filename (`activity_log_YYYY-MM-DD.txt`).

## 1.8

- High-Speed Transcription Upgrade: Implemented dynamic CPU thread scaling for faster-whisper/CTranslate2, aligning thread pools with physical core counts to prevent hyperthread contention and SMT performance stalls.
- Configurable Greedy Decoding (`beam_size=1`): Added Transcription Speed / Quality mode selector in AI Models preferences for ultra-fast, greedy-decoding transcription passes alongside standard quality beam-search decoding (`beam_size=5`).
- Native Distil-Whisper Support: Integrated `distil-whisper/distil-medium.en` and `distil-whisper/distil-large-v3`, providing 4x to 6x faster inference on CPU with minimal accuracy trade-off.
- Parakeet / FastConformer ONNX Support: Integrated non-autoregressive NVIDIA FastConformer / Parakeet ONNX models for high-throughput speech-to-text.
- Enhanced Batch Progress Status & Dual ETAs: The batch processing progress indicator at the top of the window now displays relative progress (e.g. "File 1 of 3" or "1/3") accompanied by real-time estimated completion times for both the active file and the entire batch job.
- Batch Processing Drag and Drop: Users can now drag and drop one or more audio/video files or folders directly into the batch dialog list or input area.
- Persistent Batch Export Defaults: The app remembers last-used batch export options across sessions, with quick "Save Options as Default" and "Reset to Factory Defaults" controls in the batch dialog and Preferences.
- Native `.rtvs` Project File Association: Registered `.rtvs` project file associations across Windows (Registry progid), macOS (Info.plist), and Linux (shared-mime-info). Opening or double-clicking an `.rtvs` file directly launches and opens the project in Radio & TV Segmenter.
- Resolved Waveform Cleanup & Project Load Crash: Fixed an `AttributeError: 'TimelineCanvas' object has no attribute 'set_background_generation_active'` during project opening, media reloads, and application shutdown.
- Unified application version to 1.8 across all installers, package builders, update manifests, metadata, and documentation.

## 1.7

- Enhanced Transcript Selection Ergonomics: Distinguish between single click (move playback cursor / seek) and click-and-drag (select text range), preventing accidental word snapping or unwanted selections.
- Added Right-Click Drag Selection: Support selecting text by clicking and dragging with the right mouse button in addition to the left mouse button.
- Added "Clear Selection" Context Menu Action: Users can now un-select active transcript highlights directly from the right-click context menu or by pressing `Esc`.
- Configurable Multi-Selection Workflow: Added "New Text Selection Behavior" preference under Settings > Preferences > Playback & Timeline to choose between replacing previous selections (Single Selection) or preserving multiple concurrent selections (creating separate stories for each selected section).
- Translation Language Selector Fix: Resolved an issue where the transcript drop-down only displayed "English (Original)" after completing a translation. Fixed premature stale-status invalidation, enabled seamless switching between English, Español (Translation), and Bilingual (Split) views, and preserved translation state across project loads and undo actions.
- Unified application version to 1.7 across all platform installers, update manifests, metadata, and documentation.

## 1.63

- Streamlined Linux packaging: Added dedicated Debian/Ubuntu package builder (`RadioTVSegmenter-1.63-Linux-amd64.deb`) with complete FreeDesktop desktop launcher, system MIME-type handlers, application icons, and maintainer scripts.
- Solved Linux release asset size constraints (<2GB GitHub release limit): Enforced explicit CPU-only PyTorch wheel resolution to eliminate accidental multi-gigabyte CUDA runtime inclusions during Linux CI builds.
- Added aggressive non-runtime asset pruning (C++ headers, unit tests, debug symbols, type stubs) and Linux ELF binary stripping (`strip --strip-unneeded`) to reduce package footprint.
- Enhanced in-app updater to prioritize `.deb` package downloads on Debian/Ubuntu systems with native system package manager integration (`xdg-open`).
- Unified application version to 1.63 across all platform installers, update manifests, metadata, and documentation.

## 1.6.1

- Fixed: a custom AI model storage directory set in Preferences was not honored on the next app launch — startup always reset the Hugging Face cache location (`HF_HOME`) back to the default app-data folder, so new model downloads (and the Manage Models listing) could silently disagree with the configured directory.
- Fixed: closing the "Check for Updates" dialog while the initial GitHub check was still in flight could cause its background worker to emit into an already-closed dialog.
- Fixed: launching the downloaded installer on Windows no longer goes through `cmd.exe` (`shell=True`), avoiding a class of path-quoting risk.
- Fixed: removing a speaker label now only reassigns diarization data that actually belonged to the removed speaker in that time window, instead of any diarization segment that merely overlapped it (which could mislabel a different speaker's audio during cross-talk).

## 1.5

- Added integrated "Check for Updates" feature querying GitHub releases with automatic OS binary matching (.exe for Windows, .dmg for macOS, .tar.gz for Linux).
- Non-blocking download and automatic installer execution with safe application shutdown.
- Configurable model download and storage directory in Preferences, with direct link from Manage Models dialog.
- Redesigned Preferences dialog with a clean category tree on the left and settings panels on the right (inspired by Reaper Preferences layout).
- Relocated Language selection to the top-level Settings menu for easier discovery.
- Enhanced speaker label removal logic: removing a speaker label reassigns all audio and segments in that speaker's turn/section to the previous speaker without creating extra speaker labels.
- Streamlined "Change Speaker Label" dialog to only show "Rename All Instances", "Rename This Instance Only", and "Cancel".
- Added dynamic visual mode indicator to Edit/View Transcript button (highlighted active styling and text toggle).
- Optimized GitHub Actions CI/CD workflow: default to Windows builds and automatic release publishing, and fixed macOS arm64 FFmpeg runner compatibility.

## 1.4

- Windows taskbar icon integration and application icon resolution improvements.
- Build system synchronization and documentation updates.

- Established CPU-only as the default/base distribution target.
- Kept NVIDIA CUDA acceleration optional and installable after the base application is installed.
- Added a bundled Windows `uv` runtime manager so optional GPU environments do not require a system Python installation.
- Disabled the NVIDIA CUDA menu item on macOS, where CUDA is not supported.
- Renamed the GPU settings label to make the NVIDIA/CUDA limitation explicit.
- Restricted PySide6 packaging to QtCore, QtGui, QtWidgets, QtMultimedia and QtMultimediaWidgets.
- Added explicit exclusions for unused Qt modules to reduce PyInstaller output size.
- Added the missing Windows Inno Setup installer definition.
- Added the missing macOS `.app`/DMG packaging, signing and optional notarization script.
- Preserved per-user application data during application uninstall/update.
- Bumped the application version in `prs_shared.py` to 1.1.1.

## 1.1

- Install-oriented beta stabilization build.
