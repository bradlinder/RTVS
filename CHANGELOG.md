# Changelog

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
