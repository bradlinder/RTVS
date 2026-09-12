# Changelog

## v2.9.4
- **Version Rollback & Historical Release Selector (Updater Engine)**:
  - Upgraded the "Check for Updates" dialog (`updater.py`) with an interactive historical release selector dropdown (`QComboBox`).
  - Fetches and displays all available GitHub releases with real-time release notes rendering in `QTextBrowser` upon selecting any past or current version.
  - Dynamically updates action button context and labels: "Update to v...", "Reinstall v...", or "Rollback to v...".
  - Implemented a safety warning modal confirmation dialog (`_confirm_downgrade`) when selecting an older version than currently installed to protect against configuration and project data incompatibilities.
- **Full Project Version Alignment**:
  - Synchronized `v2.9.4` across `prs_shared.py`, `updater.py`, `build_installer.py`, `RadioTVStorySegmenter.iss`, `package.json`, `metadata.json`, `index.html`, `transcript_story.py`, and plugin manifests (`wordpress`, `youtube`, `translation`).

## v2.9.3
- **CI/CD Version Tag Synchronization**:
  - Fixed workflow release packaging to dynamically extract the release version from git tags (`GITHUB_REF_NAME`) or manual workflow inputs rather than falling back to stale local files.
  - Injected `BUILD_VERSION` into all platform build jobs (`build-plugins`, `build-windows`, `build-macos`, `build-linux`) in `.github/workflows/build.yml`.
- **Dynamic Build System Overrides**:
  - Enhanced `build_installer.py` with `--version <version>` CLI parameter and `BUILD_VERSION` environment variable support.
  - Automatically updates Inno Setup compilation flags, Debian packaging names, and distributable artifact filenames to match the active build tag.
- **In-App Updater Release Asset Verification**:
  - Added real-time asset filename inspection to `updater.py` in `_on_update_available`.
  - Displays a warning notice if a remote GitHub release tag contains binary assets labeled with an mismatched version, guiding users before downloading.
- **Full Project Version Alignment**:
  - Synchronized `v2.9.3` across `prs_shared.py`, `updater.py`, `build_installer.py`, `RadioTVStorySegmenter.iss`, `package.json`, `metadata.json`, `index.html`, `transcript_story.py`, and plugin manifests (`wordpress`, `youtube`, `translation`).

## v2.9.2
- **Documentation Alignment & Post-Plugin Architecture Audit**:
  - Reconciled `STABILITY_NOTES.md` and `BUILD_INSTRUCTIONS.txt` to remove stale references claiming Hugging Face `Transformers` is tested in the core frozen binary, documenting that it lives strictly within the isolated `plugins/translation/` virtual environment.
  - Aligned core application runtime documentation with the modular post-plugin architecture.
- **WeSpeaker ONNX Embedding Engine Clarification**:
  - Confirmed and documented `wespeakerruntime` in `requirements.txt` and `radio_tv_story_segmenter_worker.py` as the dedicated, high-performance ONNX speaker voice embedding engine (`wespeaker_rt.Speaker(lang="en")`) for speaker diarization.
- **Repository Hygiene & Release Governance**:
  - Maintained `.gitignore` patterns preventing temporary build artifacts and virtual environments from being tracked.
  - Enforced release archive distribution governance via GitHub Releases.
- **Version Alignment**:
  - Bumped application version to `v2.9.2` across `prs_shared.py`, `updater.py`, `build_installer.py`, `RadioTVStorySegmenter.iss`, `package.json`, plugin manifests (`wordpress`, `youtube`, `translation`), metadata, and documentation.
- **Version-Tagged Plugin Packaging & Asset Standardization**:
  - Standardized plugin release assets to exclusively publish version-tagged `.rtvs-addon` packages (`rtvs-plugin-{id}-v{version}.rtvs-addon`) along with matching `.zip` archives.
  - Updated `build_installer.py` and `plugins/manager.py` to eliminate redundant unversioned asset duplication on GitHub Releases while ensuring robust local fallback behavior.

## v2.9.1

- **Seamless App Upgrade Plugin Synchronization**:
  - Automatically checks and upgrades installed plugins in the user directory when a newer bundled version is shipped with an application update.
  - Ensures existing users who upgrade the desktop application automatically receive all updated core plugin features without requiring manual reinstallation.
- **Independent Plugin Update Checker ("Check for Updates...")**:
  - Added a dedicated **Check for Updates...** action to the Plugin Manager (`Tools > Manage Plugins & Add-ons`), enabling users to check GitHub releases for newer versions of installed plugins and update them in-place without needing to rebuild or reinstall the core application.
  - Automatically compares installed plugin versions against the latest release assets published on GitHub (`.rtvs-addon` and `.zip` packages).
  - Displays a detailed update summary showing current vs. remote versions (e.g. `WordPress Publisher: v2.8.0 -> v2.9.1`) with one-click batch updating.
- **Enhanced In-App Plugin Browser & Update Actions**:
  - Updated the GitHub Plugins Browser dialog to detect when an installed plugin has a newer version available on GitHub, showing highlighted `Update Available (v...)` badges.
  - Added dedicated **Update to v...** action buttons for each outdated plugin, along with an **Update All Available** batch button on the toolbar.
  - Automatically reloads updated plugins dynamically and refreshes export menus immediately upon installation without requiring an app restart.
- **WordPress Publisher Plugin Custom Header / Footer Notices**:
  - Added custom header/footer text areas with placement selection (top or bottom of post).
  - Added search engine directive suppression (`data-nosnippet="true"` and `<!--googleoff: all-->...<!--googleon: all-->`) to prevent disclaimer text from overriding search engine result snippets while keeping the article fully indexable.
  - Added WordPress excerpt exclusion to keep post summaries clean in theme archives.
  - Added **Save Text & Options as Default** to persist custom notice text across all future posts.
- **Export UI Stability & Widget Proxy Fix**:
  - Fixed `AttributeError: 'ResizableTextEdit' object has no attribute 'setPlaceholderText'` by implementing complete `QTextEdit` method forwarding (`setPlaceholderText`, `placeholderText`, `clear`, `text`, `document`, and dynamic `__getattr__` delegation) on `ResizableTextEdit`.
- **Independent Modular Plugin Build & Packaging Tooling**:
  - Added `--plugin <name>` CLI option to `build_installer.py` (e.g., `python build_installer.py --plugin wordpress`) to package `.rtvs-addon` packages independently of the full installer.
  - Updated CI/CD workflow (`.github/workflows/build.yml`) to support standalone plugin builds.

## v2.8.7
- **Speaker Detection & Diarization Native Runtime Resolution**:
  - Resolved `ImportError: numpy._core.multiarray failed to import` during Speaker Detection / Diarization execution in frozen and installed Windows environments.
  - Dynamically registers all bundled C-extension dependency locations and native `.libs` directories (`numpy.libs`, `scipy.libs`, `sklearn.libs`, `wespeakerruntime`) in `_setup_windows_dll_directories()` and the PyInstaller Windows runtime hook (`torch_dll_hook.py`) via `os.add_dll_directory` and `PATH`.
  - Added explicit packaging collection flags (`--collect-all`, `--copy-metadata`, and `--hidden-import`) for `numpy`, `scipy`, `sklearn`, `wespeakerruntime`, `diarize`, and `torchaudio` across both primary GUI and standalone worker (`prs_worker`) PyInstaller builds.
  - Expanded worker `--self-test` diagnostic validation during CI/CD build staging to fully import the entire Diarization pipeline (`diarize.embeddings`, `diarize.clustering`, `diarize.vad`, `diarize.utils`, `wespeakerruntime`, and `sklearn.cluster`) before installer generation.
- **Dependency & Build Alignment**:
  - Pinned runtime and build dependencies for `scikit-learn>=1.4.0,<1.6.0`, `scipy>=1.11.0,<1.15.0`, `numpy>=1.26.0,<2.0.0`, and `wespeakerruntime>=1.0.0,<2.0.0` to guarantee binary ABI compatibility across ML modules.
- **Version Alignment**:
  - Bumped application version to `v2.8.7` across application constants (`prs_shared.py`), installer scripts (`RadioTVStorySegmenter.iss`), plugin manifests (`youtube`, `wordpress`, `translation`), metadata, and changelog viewers.

## v2.8.6
- **Real-Time Streaming OPUS-MT Model Downloads**:
  - Replaced blocking snapshot downloads with a direct chunked streaming downloader using standard Python libraries, eliminating frozen progress states and prerequisite dependencies.
  - Added live download percentage and transfer size counters (`Downloading model.safetensors (34 / 120 MB)`).
  - Integrated dynamic sibling file discovery via the Hugging Face API to ensure all required configuration, tokenizer, and weight files are acquired cleanly.
- **Persistent Progress & Stage Visualization**:
  - Decoupled the top execution panel, progress bar, and cancel button from the timeline canvas in `ui_layout.py` so processing, downloads, and translation stages stay visible when the timeline is hidden.
- **Pipeline Translation Staging & Prompting**:
  - Automatically checks for model availability when translation is included in processing workflows and prompts users for one-click download.
  - Enhanced error recovery and stage resetting on cancellation or missing prerequisites.
- **Translation Runtime & Dependency Cleanup**:
  - Added the `translate` isolated environment into the **Manage Models** dialog for disk usage tracking, manual removal, and reinstallation.
  - Prompts to remove unused translation runtime dependencies when all translation models are uninstalled.
  - Automatically purges isolated virtual environments and model caches when uninstalling the Translation plugin in the Plugin Manager.
- **Version Alignment**:
  - Bumped application version to `v2.8.6` across application constants, installer scripts, plugin manifests, and update handlers.

## v2.8.5
- **Customizable Keyboard Shortcuts**:
  - Integrated a dedicated **Keyboard Shortcuts** customization page into the Preferences dialog (`Settings > Preferences > Keyboard Shortcuts`).
  - Added a direct **Settings > Customize Keyboard Shortcuts...** menu item (`Ctrl+K` / `Cmd+K`) to jump straight to the shortcut editor.
  - Added an interactive **Key Sequence Recorder** widget allowing users to press any key or combination (with Ctrl, Alt, Shift, Meta/Cmd) or clear assignments.
  - Added real-time shortcut conflict / collision detection warning when a key sequence is already assigned to another action, with single-click reassignment.
  - Added search filtering and category dropdown filtering across File & Project, Edit, Panels & Views, AI Pipeline & Tools, Settings & Diagnostics, Help, and Playback & Navigation.
  - Added "Reset Selected" and "Reset All to Defaults" buttons, and integrated "Keyboard Shortcuts" into the "Restore System Defaults..." dialog.
  - Linked the "Customize Shortcuts..." button directly into the Quick Shortcuts Reference dialog (`F1` / `Cmd+?`).
  - Implemented dynamic live rebinding across `MainWindow` actions, `QShortcut` instances, and playback event filters without requiring application restart.
- **Documentation & Version Alignment**:
  - Updated application version to `v2.8.5` across `prs_shared.py`, `package.json`, `updater.py`, `build_installer.py`, Windows Inno Setup script (`RadioTVStorySegmenter.iss`), and `README.md`.
- **Conditional Whisper Speed / Quality Setting**:
  - Dynamically hides the **Transcription Speed / Quality** setting (`whisper_beam_size`) in Preferences whenever non-autoregressive models (such as Parakeet ONNX) are selected, displaying it exclusively for Whisper models.
- **Multi-Select & Batch Operations in Plugin Manager**:
  - Added multi-selection support with item checkboxes and batch actions in both the GitHub Plugins Browser and Local Plugin Manager.
  - Added batch toolbar actions: **Select All**, **Deselect All**, **Download & Install Selected**, **Enable Selected**, **Disable Selected**, and **Uninstall Selected**.
  - Added multi-package add-on import and batch export capabilities.
- **Translation Model Staging & Verification Resilience**:
  - Fixed snapshot download verification in `TranslationWorker` to check required file presence before checking `.complete` marker, ensuring successful Hugging Face transfers complete without unnecessary fallback retries.

## v2.8.3
- **Non-Blocking Translation Runtime Setup**:
  - Moved initial isolated translation runtime environment provisioning (`manager.ensure_environment`) off the main Qt GUI thread to a background `QThread` (`TranslationEnvSetupWorker`).
  - Added fast-path verification so up-to-date environments start immediately without setup overhead.
  - Connected real-time status and activity logging with cancellation and graceful thread cleanup support in `stop_translation_worker()`.
- **Documentation & Legal Compliance**:
  - Reconciled `README.md`, `NOTICES.txt`, and `BUILD_INSTRUCTIONS.txt` to reflect the active `diarize` (Silero VAD + WeSpeaker ONNX) diarization engine and on-demand Windows NVIDIA CUDA acceleration.
  - Added formal third-party license notices for `diarize`, `sherpa-onnx`, `WeSpeaker`, `onnxruntime`, `scipy`, `scikit-learn`, `cryptography`, and `keyring`.
- **Repository Hygiene**:
  - Added archive patterns (`*.zip`, `*.tar.gz`, `*.7z`) to `.gitignore` to prevent snapshot zips from polluting repository history.
- **Version Alignment**:
  - Updated application version, installer scripts, plugin manifests, and documentation to v2.8.3.

## v2.8.2
- **Isolated Runtime Mount Point & Link Mode Resilience**:
  - Resolved `[TRANSLATION ERROR] Failed to create Python minor version link directory (os error 448: The path cannot be traversed because it contains an untrusted mount point)` during translation runtime and OPUS-MT model installation on Windows.
  - Enforced `UV_LINK_MODE="copy"`, `UV_CACHE_DIR`, and `UV_DATA_DIR` across all `uv` environment creation (`uv venv --link-mode copy`) and package installation (`uv pip install --link-mode copy`) steps, preventing junction and symlink traversal failures on redirected or OneDrive-synced user directories.
  - Added self-healing runtime discovery (`_find_extracted_python`) in `RuntimeManager` that detects and verifies extracted Python interpreters even if post-install junction links report mount-point errors.
  - Added direct standalone CPython 3.12 download and pure archive extraction fallback (`python-build-standalone`) when junction-based package management is blocked by OS security policies.
  - Upgraded standalone `uv` toolchain version to `0.12.12`.
- **Version Alignment**:
  - Updated application version, installer scripts, and plugin manifests to v2.8.2.

## v2.8.1
- **Default Transcription Model**:
  - Set `Parakeet ONNX Fast TDT` as the out-of-the-box default transcription model across settings stores, preference dialogs, batch jobs, and project initializations.
  - Reordered model selectors across the application to prioritize Parakeet ONNX for ultra-fast, local English transcription.
- **Worker DLL Resolution in Frozen Builds**:
  - Resolved `[PYI-17568:ERROR] Failed to load Python DLL python312.dll` on Windows during transcription and diarization by prioritizing the top-level `prs_worker.exe` located directly alongside the `_internal/` dependency tree.
  - Prevented PyInstaller onedir binary placement inside `workers/` without an adjacent `_internal/` directory, and added automatic cleanup of legacy worker binaries in Windows installer upgrades.
- **Model Downloader Reliability**:
  - Implemented real-time chunked streaming downloads for Whisper and Parakeet models in `WhisperModelInstallWorker`, replacing stalled opaque downloads with live byte/MB counters and percentage tracking.
  - Resolved frozen-process `NoneType.write` crashes on clean Windows installs by introducing `NullWriter` stream guards and disabling terminal progress bars (`tqdm`, `huggingface_hub`) in GUI environments.
  - Removed deprecated `resume_download` and `local_dir_use_symlinks` parameters to eliminate modern `huggingface_hub` UserWarnings.
  - Hardened file finalization with atomic `os.replace` operations across temporary `.download` artifacts to prevent Windows file-sharing errors.
  - Added non-zero integrity checks (`stat().st_size > 1024`) in model availability verification to prevent interrupted 0-byte files from being identified as valid installations.
- **Translation Staging & Add-on Delivery**:
  - Added multi-file HTTP streaming fallback for all standard OPUS-MT assets (`config.json`, tokenizers, `source.spm`, `model.safetensors`, and `pytorch_model.bin`).
- **Tools Menu Accessibility**:
  - Added direct **Tools > Manage AI Models...** menu entry alongside existing Preferences navigation.
- **Version Alignment**:
  - Updated application, installer scripts, and plugin manifests to v2.8.1.

## v2.8.0
- Updated application and plugin versions to v2.8 across core, installers, and manifests.
- **Decoupled Translation Worker from PySide6**: Isolated translation runtime no longer requires or installs PySide6. Implemented a pure-Python `Signal` descriptor and `QObject` fallback in `worker.py` and guarded `QCoreApplication` in `runtime_entry.py`.
- **Dynamic Plugin Runtime Requirements**: `RuntimeManager` now dynamically reads `requirements-runtime.txt` from plugin directories rather than relying strictly on static configuration.
- **CPU PyTorch Wheel Configuration**: Isolated translation environment utilizes `--extra-index-url https://download.pytorch.org/whl/cpu` to avoid multi-gigabyte CUDA wheel downloads on CPU-only machines.
- **Cross-Platform `uv` Provisioning**: Added standalone `uv` binaries for Windows (x86_64, arm64), macOS (x86_64, arm64), and Linux (x86_64, aarch64) in `build_installer.py`, enabling automated managed Python provisioning across all platforms.
- **Enhanced Diagnostic Reporting**: Added detailed subprocess error capture in `RuntimeManager` and surfaced detailed error diagnostics in the translation UI.
- **Synchronized Plugin Add-on Archives**: Updated and re-packaged `.rtvs-addon` packages (`translation`, `wordpress`, `youtube`) and enhanced `PluginManager.ensure_packaged_addons()` to auto-refresh outdated archives when plugin source manifests change.

## v2.76c
- Reworked the plugin architecture around explicit core/shared versus isolated runtimes.
- Moved the OPUS-MT translation worker implementation out of the core application.
- Translation now runs through the plugin-owned isolated Python runtime.
- Removed translation-only `transformers`, `sentencepiece`, and `sacremoses` dependencies from the core Python requirements and core PyInstaller collection.
- Added `plugins/translation/requirements-runtime.txt` and isolated runtime metadata.
- Translation models are owned by the translation plugin's model registry and are hidden from Manage Models when the plugin is uninstalled.
- Uninstalling the translation plugin removes its isolated runtime but deliberately preserves downloaded translation models.
- Fixed Preferences category navigation so aliases such as `Models`, `AI Models`, `Detection`, and `Batch` select the correct page.
- WordPress and YouTube remain lightweight core-runtime plugins and use the same manifest architecture.
- Updated release version references to 2.76c.


## v2.7.1

### Disk Cache Management & "Clear Temporary Cache" Dialog
- **Temporary Cache Manager Dialog (`ClearCacheDialog`)**: Added a user-facing temporary cache inspection and cleanup dialog accessible via **Tools > Clear Temporary Cache...** and **Settings > Clear Temporary Cache...**.
- **Per-Store Disk Usage Breakdown**: Computes real-time file counts and storage size across:
  - **Video Thumbnails & Filmstrips**: Cached timeline thumbnail images in `%TEMP%/radio_tv_story_segmenter_thumbnails/`.
  - **Audio Waveform Peaks**: Precomputed waveform envelopes (`.peaks`) in `%APPDATA%/RadioTVStorySegmenter/cache/peaks/`.
  - **Temporary Audio Workfiles**: Temporary extracted audio tracks and work buffers (`prs_tmp_*.wav`, `rtvs_tmp_*.wav`).
- **Selective & Full Purging**: Users can selectively clear specific stores or click the primary **Clear All Caches** button to immediately reclaim all temporary disk space.
- **Bilingual Localization Support**: Full English and Spanish translation support for all cache dialog labels, feedback prompts, and menu actions.

### Build Pipeline Transparency & Real-Time Logging
- **Live Output Streaming**: Refactored `build_installer.py` subprocess runner to use unbuffered line-by-line live streaming via `subprocess.Popen(stdout=subprocess.PIPE, bufsize=1)`, eliminating log buffering delays in GitHub Actions CI runners.
- **Unbuffered Python Environment**: Configured `PYTHONUNBUFFERED: "1"` in `.github/workflows/build.yml` to ensure continuous stdout flushing across Windows, Linux, and macOS runners.
- **Stage Progress Banners**: Added explicit progress headers (`[1/5]` through `[5/5]`) and `--log-level INFO` verbosity to PyInstaller build steps, ensuring clear visibility into binary compilation stages.

### Ecosystem Version Alignment
- **Global v2.7.1 Synchronization**: Synchronized application, installer, and plugin versions across `prs_shared.py`, `package.json`, `RadioTVSegmenter.py`, `transcript_story.py`, `updater.py`, `build_installer.py`, `installer/Windows/RadioTVStorySegmenter.iss`, `build_windows.bat`, `build_linux.sh`, `installer/Linux/build_deb.sh`, `installer/macOS/build_app.sh`, `.github/workflows/build.yml`, and all plugin manifests (`plugins/wordpress/manifest.json`, `plugins/youtube/manifest.json`, `plugins/translation/manifest.json`).

## v2.7.0

### Video Thumbnail Caching & Instant Project Reloading
- **Persistent Disk Thumbnail Caching**: Added deterministic, media-hash-keyed thumbnail disk caching (`get_video_thumbnail_cache_dir`, `read_video_thumbnail_cache`, `invalidate_video_thumbnail_cache`) in `prs_shared.py`.
- **Instant Project Restoration**: Opening a video file or reloading an existing `.rtvs` project now instantly reads cached filmstrip thumbnails directly from disk without re-extracting frames via FFmpeg.
- **Immediate Generation Preview & Track Placeholder**: Restored immediate visual feedback during thumbnail extraction, rendering a filmstrip track placeholder along with centered "Generating video thumbnails..." preview text and status banner.
- **Cache Invalidation & Manual Refresh**: Thumbnail cache automatically validates file modification timestamps (`st_mtime`) against the source video, ensuring stale frames are evicted if media is modified. Manual regeneration (**Media > Regenerate Video Thumbnails**) clears cache and re-extracts cleanly.
- **Extended Cache Retention**: Extended default background cache retention (`cleanup_old_thumbnail_cache`) from 24 hours to 7 days (168 hours) to ensure work-in-progress desktop video projects retain cached filmstrips across sessions.

### GitHub Actions Workflow Optimizations
- **All-Build Defaults**: Updated the GitHub Actions release workflow (`.github/workflows/build.yml`) `workflow_dispatch` configuration so all build checkboxes (`build_windows`, `build_macos`, `build_linux`, `plugin_wordpress`, `plugin_youtube`, `plugin_translation`, `create_release`) default to `true` (`checked`), allowing release managers to deselect targets rather than checking each one manually.

### Ecosystem Version Alignment
- **Global v2.7.0 Synchronization**: Bumped project and plugin versions to `2.7.0` across `prs_shared.py`, `package.json`, `RadioTVSegmenter.py`, `transcript_story.py`, `updater.py`, `build_installer.py`, `installer/Windows/RadioTVStorySegmenter.iss`, `build_windows.bat`, `build_linux.sh`, `installer/Linux/build_deb.sh`, `installer/macOS/build_app.sh`, `.github/workflows/build.yml`, and all plugin manifests (`plugins/wordpress/manifest.json`, `plugins/youtube/manifest.json`, `plugins/translation/manifest.json`).

## v2.6.5

### In-Dialog Video Frame Scrubber & Thumbnail Controls
- **Interactive In-Dialog Timeline Scrubber**: Added an interactive horizontal slider, precision step buttons (`◀ -1s`, `◀ -1f`, `+1f ▶`, `+1s ▶`), live timestamp readout (`hh:mm:ss.zzz`), and a `⟳ Playhead` synchronization button directly inside both WordPress and YouTube export panels in `UnifiedExportDialog`.
- **Debounced Frame Previews**: Enabled responsive thumbnail capture with a 120ms debounce timer for smooth in-dialog scrubbing without freezing the UI.
- **Audio-Only Project Protection**: Automatically detects audio-only projects and disables "Grab frame from video" with helpful guidance tooltips, defaulting gracefully to "None", "Automatic", or custom image browse modes.

### Process Hardening & Temporary Asset Cleanup
- **FFmpeg Subprocess Timeouts**: Added 5-second timeouts and `TimeoutExpired` exception handling to all FFmpeg thumbnail extraction calls in `project_export.py`, preventing freezes on corrupted or unresponsive media.
- **Temporary Preview File Lifecycle**: Added automated tracking and purging of temporary preview files (`rtvs_wp_frame_*.jpg`, `rtvs_yt_frame_*.jpg`) on dialog cancellation or closure.

### Timeline Thumbnail Density Optimization
- **Increased Frame Extraction Density**: Increased `VideoThumbnailWorker` extraction count ceiling from 48 to 80 frames for richer visual coverage across long media files.
- **Aspect-Ratio-Preserving Density Tuning**: Optimized timeline thumbnail rendering dimensions with reduced horizontal scaling minimums and a 2.0px minimum gap, displaying more visual frames simultaneously without cropping images.

### Version Synchronization
- **Ecosystem Version Alignment**: Bumped project and plugin versions to `2.6.5` across `prs_shared.py`, `package.json`, `RadioTVSegmenter.py`, `transcript_story.py`, `updater.py`, `build_installer.py`, `installer/Windows/RadioTVStorySegmenter.iss`, `plugins/wordpress/manifest.json`, `plugins/youtube/manifest.json`, and `plugins/translation/manifest.json`.

## v2.6.0

### Modular Plugin System
- **Plugin Management Engine**: Introduced modular plugin architecture (`plugins/manager.py`) with `BasePlugin`, `PluginManifest`, and `PluginManager` supporting auto-discovery, lifecycle controls, and dynamic loading from both bundled and user-level plugin directories.
- **WordPress Publisher Plugin**: Migrated WordPress publishing capabilities into a modular add-on (`plugins/wordpress/`) with category/tag syncing, excerpt formatting, featured image uploads, and background worker threads.
- **YouTube Video Publisher Plugin**: Implemented dedicated YouTube publisher plugin (`plugins/youtube/`) featuring OAuth 2.0 PKCE authentication with local callback server, chunked resumable video uploads, metadata/tag management, video frame thumbnail capture, and privacy settings.
- **Language Translation Plugin**: Encapsulated local neural machine translation into a modular add-on (`plugins/translation/`) with MarianMT and NLLB models and bilingual split-view editing.
- **Dynamic UI Menus**: Added dynamic action populator for `File -> Publishing & Plugins` and dynamic tool entries under `Tools`, plus the `Tools -> Manage Plugins & Add-ons...` management dialog.

### Project Storage & Backward Compatibility
- **Forward & Backward Compatibility**: Enhanced `.rtvs` project serialization and `Story` models with extensible `metadata` and top-level `plugins_data` dictionaries. Projects created in v2.6.0 open seamlessly in v2.5.2 without parsing errors, and legacy projects open in v2.6.0 without data loss.

### CI/CD Workflow & Selective Build Matrix
- **Selective Plugin Packaging & Building**: Extended `build_installer.py` and GitHub Actions (`.github/workflows/build.yml`) with build target options (`Core App + Selected Plugins`, `Core App Only`, and `Plugins Only`) and individual plugin checkboxes (`plugin_wordpress`, `plugin_youtube`, `plugin_translation`).
- **Standalone Release Artifacts**: Generated standalone `.zip` packages for each plugin (`rtvs-plugin-<id>-v2.6.0.zip`) ready for direct release distribution or in-app installation.
- **Version Bump**: Bumped version to `2.6.0` across `prs_shared.py`, `RadioTVSegmenter.py`, `media_batch.py`, `playback_preferences.py`, `updater.py`, `build_installer.py`, `build_windows.bat`, `build_linux.sh`, `installer/Windows/RadioTVStorySegmenter.iss`, `installer/Linux/build_deb.sh`, `installer/macOS/build_app.sh`, `.github/workflows/build.yml`, `package.json`, and all plugin manifests.

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
