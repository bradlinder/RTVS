# Changelog

## v2.5.2

### Timeline Video Thumbnails Layout & Vertical Resizing
- **Thumbnails Positioned Below Waveform**: Relocated the video thumbnail track in `TimelineCanvas` so that thumbnails render cleanly beneath the audio waveform rather than above or overlaying it.
- **Dynamic Vertical Resizing**: Replaced the static thumbnail scaling constraints with dynamic aspect-ratio-aware dimensions that automatically expand and contract proportionally as the user resizes the timeline widget vertically.
- **Track Separation**: Added a subtle boundary divider between the audio waveform and video thumbnail strips for clear visual segmentation.
- **Higher Resolution Thumbnails**: Increased thumbnail extraction scale to 320px width (`scale=320:-2`) to keep video frames sharp and clear on high-DPI displays and enlarged timeline heights.
- **Preferences Configuration**: Added a "Thumbnail Placement" option under Preferences (Playback & Timeline) allowing users to choose between "Below audio waveform" (default) or "Above audio waveform".

### Automated Windows Installer & Version Synchronization
- **Strict Version Synchronization**: Updated `build_installer.py` with `sync_installer_scripts()` to automatically rewrite and verify the `#define MyAppVersion` directive in `installer/Windows/RadioTVStorySegmenter.iss` from the project's single source of truth (`PROJECT_VERSION` in `prs_shared.py`).
- **Direct Inno Setup Compilation Support**: Integrated automated detection and invocation of `ISCC.exe` into `build_installer.py`, compiling the Windows installer executable with `/DMyAppVersion="{PROJECT_VERSION}"` without relying on manual command-line flags.
- **Resilient Batch Extraction**: Hardened `build_windows.bat` to detect and use the active `!PYTHON_EXE!` runtime with regex extraction directly from `prs_shared.py`, preventing fallback issues when executing the Inno Setup compiler.
- **Version Bump**: Bumped version to `2.5.2` across `prs_shared.py`, `RadioTVSegmenter.py`, `media_batch.py`, `playback_preferences.py`, `updater.py`, `build_installer.py`, `build_windows.bat`, `build_linux.sh`, `installer/Windows/RadioTVStorySegmenter.iss`, `installer/Linux/build_deb.sh`, `installer/macOS/build_app.sh`, and `.github/workflows/build.yml`.

## v2.5.1

### Version Bump & Maintenance
- **Version Alignment**: Bumped project version to `2.5.1` across core modules, packaging scripts, and CI workflows.

## v2.4.2

### Timeline Interaction & Boundary Protection
- **Protected Timeline Boundary Handles**: Disabled accidental boundary modifications caused by left-clicking and dragging story edge handles in the timeline. Left-clicks across the timeline now exclusively handle playback seeking and audio scrubbing.
- **Explicit Right-Click & Button Boundary Adjustments**: Timeline boundary adjustments now require deliberate user actions:
  - Right-clicking and dragging a story's boundary handle directly resizes that boundary with undo/redo snapshotting.
  - Right-clicking and dragging across any timeline segment creates a selection region that can be quickly assigned with "Set Story Start" or "Set Story End".
  - Hovering over a story boundary handle displays an informative tooltip (`Right-click and drag to adjust`).
- **Version Synchronization**: Bumped version to `2.4.2` across `prs_shared.py`, `RadioTVSegmenter.py`, `build_installer.py`, `updater.py`, `package.json`, Windows Inno Setup, Linux Debian packaging, macOS bundling, and GitHub Actions CI workflows.

## v2.4.1

### Features & Story Boundary Controls
- **Set Story Start & End Buttons**: Restored dedicated "Set Story Start" and "Set Story End" action buttons in the Stories & Segments widget.
- **Contextual Timestamp Snapping**: Pressing either button sets the story's start or end boundary to match the current interaction position across the transcript and timeline:
  - Active timeline drag selections and highlighted transcript text ranges are prioritized.
  - Active transcript cursor positions and playback/waveform playhead locations are seamlessly detected and converted into precise story boundaries.
- **Dynamic Resizing & Contextual Visibility**: The boundary buttons appear cleanly above the Add, Select All, Delete, and Export buttons exclusively when a single story is selected. When multiple stories or no stories are selected, the buttons and their container are collapsed entirely with zero dead vertical space.
- **Full Undo/Redo & State Integration**: Boundary adjustments are committed into the unified project undo/redo stack (`Ctrl+Z` / `Ctrl+Shift+Z`), immediately refreshing the story list, time range inputs, timeline story regions, and autosave state.
- **Version Synchronization**: Bumped version to `2.4.1` across `prs_shared.py`, `RadioTVSegmenter.py`, `build_installer.py`, `updater.py`, `package.json`, build scripts, and CI workflows.

## v2.4

### Bug Fixes & Stability
- **Startup Crash Fix**: Fixed `NameError: name 'ffprobe_path' is not defined` in `ui_layout.py` by properly importing `ffprobe_path` from `prs_shared.py`, preventing an application crash during external dependency initialization.
- **Dependency Manifest Alignment**: Added `torchaudio>=2.0,<2.4` and `soundfile>=0.12.1` to `requirements.txt` to ensure standalone/manual Python environment installations include all packages directly imported by the application.

### CI/CD & Build Pipeline Security
- **GitHub Actions Script Injection Fix**: Eliminated the script injection vulnerability in `.github/workflows/build.yml` by routing the workflow's `${{ inputs.release_tag }}` input safely through environment variables (`env:`) rather than inline shell script string interpolation.
- **Release Integrity Guard**: Updated the `publish-release` job condition to require `!contains(needs.*.result, 'failure')`, ensuring GitHub Releases are never published if any platform build (Windows, macOS, Linux) fails.
- **Windows Build Timeout Margin**: Increased the Windows CI build job timeout to 75 minutes to provide a reliable buffer against runner timeouts.
- **Balanced Inno Setup Compression**: Optimized Windows installer packaging in `RadioTVStorySegmenter.iss` using `lzma2/max` with a 16MB dictionary size, delivering 50–70% faster Windows compression times on CI runners while retaining a compact installer binary.
- **Version Synchronization**: Unified version `2.4` across all core application modules, installer configurations, build scripts, and package descriptors.

## v2.3

### Installer Size & Package Optimization
- **Shared Runtime Architecture**: Eliminated the duplicate `_internal` distribution previously bundled inside `workers/`, deduplicating hundreds of megabytes of identical PyTorch, Transformers, CTranslate2, and ONNX Runtime runtimes into a unified application core shared seamlessly by both the GUI application and the AI worker (`prs_worker`).
- **Enhanced Pruning Pipeline**:
  - Removed unneeded C/C++ development headers, build artifacts, and package metadata (`torch/include`, `torchaudio/include`, `scipy/include`, `PySide6/include`, `onnxruntime/include`, etc.).
  - Stripped unused PySide6 runtime plugins (e.g., `sqldrivers`, `sensorgestures`, `qmltooling`, `geometryloaders`, `position`, `scenegraph`) and translation tables.
  - Purged `.pdb`, `.pyi`, `.c`, `.cpp`, `.h`, `.hpp`, `.pyx`, `.pxd` source and debug files, along with internal test and benchmark suites across all bundled packages.
  - Enabled binary symbol stripping on Linux (`strip --strip-unneeded`) and macOS (`strip -x`).
- **Maximum Installer Compression**:
  - **Windows**: Upgraded Inno Setup packaging to `lzma2/ultra64` compression with separate 64-bit multi-threaded compression process and maximum dictionary size (64MB).
  - **Linux**: Upgraded Debian packaging (`build_deb.sh`) to `dpkg-deb -z9` (maximum XZ compression) and distributable tarball packaging to `GZIP=-9`.
  - **macOS**: Upgraded DMG image generation (`build_app.sh`) with `hdiutil` maximum compression (`-imagekey zlib-level=9`).

### Codebase Cleanup & Conflict Prevention
- **Eliminated Duplicate Methods**: Removed the redundant `_check_external_dependencies` implementation in `RadioTVSegmenter.py` and unified dependency validation in `ui_layout.py`.
- **Dynamic Application Metadata**: Refactored the "About" dialog to use dynamic version and application name constants (`APP_DISPLAY_NAME`, `PROJECT_VERSION`) from `prs_shared.py` instead of hardcoded strings.
- **Dependency Manifest Cleanup**: Removed duplicate `keyring` package declaration from `requirements.txt`.
- **Version Synchronization**: Unified v2.3 versioning across `prs_shared.py`, `RadioTVSegmenter.py`, `transcript_story.py`, `updater.py`, `build_installer.py`, `build_windows.bat`, `build_linux.sh`, `installer/Windows/RadioTVStorySegmenter.iss`, `installer/Linux/build_deb.sh`, `installer/macOS/build_app.sh`, and `.github/workflows/build.yml`.

## v2.2

### Enhancements
- Updated application and installer versioning to v2.2 across Python core modules, build scripts, Windows Inno Setup scripts, and GitHub Actions workflows.

## v2.1.6

### Windows packaging/runtime reliability
- Build a dedicated `prs_worker` PyInstaller executable instead of falling back to the GUI executable for local AI processing.
- Add a PyInstaller Windows runtime hook for PyTorch, CTranslate2, ONNX Runtime, and related native DLL search paths.
- Add frozen-build AI self-tests for PyTorch, its `_C` native extension, CTranslate2, Transformers, and Silero VAD.
- Make the build fail before creating an installer when the frozen AI runtime cannot initialize.
- Preserve the complete worker `_internal` runtime instead of pruning native ML libraries from it.

## v2.1-stable

- **Timeline now themes with Light and High Contrast modes** (previously covered in the earlier changelog entry).
- **Fixed**: opening a new media file skipped an intended immediate duration probe (`probed_duration` was always `None`, dead code left over from an earlier refactor) -- the timeline could briefly show a stale or zero duration until the media player's own async duration signal arrived a moment later. Restored the probe and reduced its worst-case timeout from 15s to 5s.
- **Fixed**: `safe_filename()` (used for exported story/project folder and file names) didn't guard against an input that sanitizes down to nothing but dots -- a folder-name prompt or a project file's own story title of ".." could resolve one directory level *above* the intended export location instead of into a new subfolder. Dot-only results now fall back to a safe default name.

## v2.1.0-beta

- **Visual Theme Refresh**: Refined the dark visual system with layered charcoal/slate surfaces, restrained cyan interaction accents, cleaner borders, rounded controls, minimalist scrollbars, modern menus, and cohesive focus/selection states.
- **Waveform Presentation**: Refined waveform/ruler styling and moved the audio filename into a subtle metadata badge in the ruler margin.
- **Transcript Typography**: Added persistent transcript font-size controls with increase, decrease, and reset actions. Supports `Ctrl/Cmd + +`, `Ctrl/Cmd + -`, and `Ctrl/Cmd + 0`.
- **Transcript Readability**: Improved typography, active-selection treatment, speaker/timestamp presentation, and transcript visual hierarchy without changing the existing transcript layout.

# Changelog

## v1.9.9

- **Adjustable Custom Defaults**: Added "Save as Custom Defaults" buttons to each sub-menu in the preferences dialog, allowing users to save custom defaults that override original system defaults. Updated the reset preference option to "Restore System Defaults" to restore original factory defaults.
- **Updated Story Detection Default**: Changed the default story detection silence threshold to 3.0s.
- **Silero VAD Debug Cleanup**: Removed [STORY DEBUG] print statements from codebase.
- **Unified Application Version 1.9.9**: Synchronized version 1.9.9 across application constants, local PyInstaller/Inno Setup/Debian/macOS builders, GitHub Actions release workflows, documentation, and update verification manifests.

## v1.9.8

- **Resilient Multi-Stage Speaker Detection Progress**: Replaced brittle percentage-drop heuristics with keyword-based stage mapping across VAD, embedding extraction, and speaker clustering stages. Added monotonic percentage scaling with an upper safety ceiling (99%) to eliminate progress jumps and stalling during diarization.
- **Unified VAD Story Detection Pipeline**: Standardized story auto-detection on the Silero VAD audio pipeline with adaptive silence thresholding, 80% silence scaling margin, minimum story duration filters (5s), and music/sound token sanitization (`MUSIC_TOKEN_RE`).
- **Sequential Story Indexing**: Fixed story title generation to use contiguous sequential numbering (`Story 1`, `Story 2`, ...) even when transient sub-5-second audio blips are filtered out.
- **Unified Application Version 1.9.8**: Synchronized version 1.9.8 across the application constants, local PyInstaller/Inno Setup/Debian/macOS builders, GitHub Actions release workflows, documentation, and update verification manifests.

## v1.9.6

- **Moved WordPress settings into Preferences**: Site URL, Username, App Password, and Test Connection now live under Preferences > WordPress. The standalone "WordPress Export Settings..." menu item has been removed; the contextual "WordPress Settings..." button inside the Export dialog is unchanged and uses the same underlying settings.
- **Manage Models**: labeled the two Whisper models and the Parakeet model that are English-only ("Distil-Whisper Large v3 (English)", "Parakeet ONNX Fast TDT (English)") -- verified against each model's documentation rather than assumed.
- **Security**: sanitized update-download filenames and validated destination paths against directory traversal; restricted update downloads to official GitHub domains over HTTPS; added SHA-256 verification when a release publishes one; WordPress application passwords now use machine-derived encryption for the local-storage fallback (instead of plaintext) when no system keyring is available, with an on-screen notice when that fallback is used; project files now validate media file extensions before resolving/copying referenced media, closing a path where a malicious project file could reference and copy an arbitrary file; project file decompression is now streamed with a 200MB ceiling instead of unbounded.
- **Performance**: activity-log snapshots no longer re-serialize the full transcript/diarization/translations on every log entry -- only when a real edit occurs; first-run or upgrade installs of the local transcription/diarization environment now show a progress dialog instead of freezing the window.
- **Reliability**: the local transcription/diarization worker's stdout (JSON protocol) and stderr (diagnostic output) are no longer merged, preventing third-party library warnings from occasionally corrupting an in-flight result; WordPress export temp files now use a unique per-job directory instead of a shared fixed one; a worker-protocol-mismatch error dialog no longer shows a hardcoded, incorrect expected version number.

## v1.9.4

- **Global Multi-Stage Elapsed Time**: The progress indicator now tracks and displays elapsed time across all operations and multi-stage pipelines (including combined transcription + speaker diarization) from start to finish, rather than only during diarization.
- **Comprehensive "Restore All Settings to Defaults"**: The Restore All Defaults button in Preferences now resets all custom preferences across all areas of the application, including custom project directories, project bundling, export formats and content settings, custom export location overrides, audio output hardware and volume, AI model options, timeline preferences, detection parameters, and batch tool options.
- **New "Restore Selected Settings" Feature**: Added a dedicated "Restore Selected Settings…" dialog accessible in Preferences. Users can review customizable setting categories with checkboxes (with Select All and Deselect All convenience controls) and selectively reset only specific areas to factory defaults after a safety confirmation prompt.
- **Export Location Routing Refinement**: When using a custom export location, selected file types are saved directly to the chosen directory without creating unnecessary "Transcripts" or "Media" subfolders, keeping output clean while leaving the main project folder intact.

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
