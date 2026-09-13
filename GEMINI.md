# AI Studio Project Instructions

## 1. App Purpose & Web Preview Directive (CRITICAL RECOVERY DIRECTIVE)
- **What the AI Studio Preview MUST Display**: 
  The AI Studio web preview for this project MUST always display the **interactive changelog and release history viewer** powered by `/src/App.tsx` and synchronized with `CHANGELOG.md`.
- **STRICT PROHIBITION (Never Replace)**:
  Under NO circumstances should an agent rewrite, scaffold over, or replace `/src/App.tsx` or `/index.html` with:
  - Dummy/mock audio waveform players or simulated transcription editors
  - Promotional SaaS landing pages, "Hero" headers, or feature pitch marketing cards
  - Standalone single-purpose demo widgets or test audio uploaders
- **Why this exists**:
  The actual application is a native Python/PySide6 (Qt) desktop software suite. The Node/Vite web container in AI Studio exists exclusively to serve the live interactive changelog, release documentation, and version inspector on port 3000.
- **Recovery / Error Response & Zero-Token Restoration**:
  If the web preview breaks, fails linting, reports build errors, or if preview files are missing after a git update/pull (since web preview files are ignored in `.gitignore` to keep the desktop repository focused on the Python app):
  - **NEVER** rewrite, scaffold over, or regenerate the UI from scratch (which wastes tokens and risks hallucination).
  - Run `python preview_manager.py` (or `python preview_manager.py --restore`) to immediately restore all preview files in < 0.1s.
- **Changelog Synchronization**:
  `/src/App.tsx` imports `CHANGELOG.md` directly (`import CHANGELOG_MARKDOWN from '../CHANGELOG.md?raw'`). Whenever `CHANGELOG.md` is updated, the changes are automatically reflected in the web preview without needing to duplicate markdown strings in React code. Use `python preview_manager.py --sync` to align version numbers across preview files.

## 2. Standardized Version Bump Checklist
- **Incremental Point Release Policy**:
  - Incrementally update the version number with a point release (e.g., `v2.9.5` -> `v2.9.6`, `v2.9.7`, `v2.10.1`) whenever you make an update, bug fix, or feature enhancement to the core app, unless the user explicitly specifies a different version number to apply.
  - Always format version strings strictly as standard semantic numbers with single period delimiters (e.g. `2.9.6`, `2.9.7`, `2.10.1`). Never introduce double dots (e.g. `2.9..6`).
  - Execute the full version bump checklist below synchronously with every update.

When bumping or updating the application version number, you MUST update **ALL** of the following locations synchronously:
1. `prs_shared.py` (`PROJECT_VERSION`)
2. `updater.py` (`PROJECT_VERSION` fallback)
3. `build_installer.py` (`PROJECT_VERSION` fallback)
4. `installer/Windows/RadioTVStorySegmenter.iss` (`#define MyAppVersion`)
5. `plugins/*/manifest.json` (`version` across `wordpress`, `youtube`, `translation`)
6. `transcript_story.py` (docstring version header)
7. `package.json`, `metadata.json`, and `index.html` (title & meta tags)
8. `CHANGELOG.md` & `/src/App.tsx` (version notes and expanded accordion defaults)
9. `roadmap.txt & CHANGELOG.md (N-1 Sliding-Window & Real-Time Sync Policy)`:
   - Whenever any code change, bug fix, packaging adjustment, or feature refinement is made during a release cycle, it MUST be recorded immediately in the current release section of `roadmap.txt` and `CHANGELOG.md` (even if it occurs after the initial version number bump).
   - Retain only the active release ($N$) and its immediate predecessor ($N-1$); prune any versions older than $N-1$ from `roadmap.txt`.
10. `Roadmap Item Status Tracking Policy (Social Digest Progress Indicator Style)`:
   - `roadmap.txt` milestones and feature items MUST be annotated with explicit progress checkboxes and status notations:
     * `[x]` for completed items / releases (e.g. `[x] 1.1 Feature Title` or `(Completed in vX.X)`)
     * `[-]` for in-progress items (e.g. `[-] 3.1 Feature Title`)
     * `[ ]` for planned / not started items (e.g. `[ ] 3.2 Feature Title` or `[NOT STARTED]`)
   - When work starts on an item in the roadmap, mark it immediately as in-progress (`[-]`).
   - Mark an item as completed (`[x]`) when implementation is finalized, or ask the user if it's time to mark an item as completed, or infer based on whether development has moved on to another part of the roadmap.

## 3. Pre-Completion Verification
Before completing code modifications:
- Run Python syntax compilation checks: `python -m py_compile RadioTVSegmenter.py prs_shared.py processing.py runtime_manager.py radio_tv_story_segmenter_worker.py updater.py build_installer.py plugins/manager.py`
- Run the web preview linter and build tools (`lint_applet` & `compile_applet`) to ensure zero regressions.

## 4. Architectural Invariants Reference
Always adhere strictly to the invariants defined in `ARCHITECTURE.md`:
- Core modules must NEVER import from `plugins/`.
- Heavy translation runtimes must remain isolated inside `plugins/translation/`.
- Speaker diarization uses `wespeakerruntime` as the primary ONNX embedding engine.

## 5. Release Snapshots & Rollback Directive
- **Snapshot Manager (`snapshot_manager.py`)**:
  - The project maintains an automated snapshot and rollback manager in `snapshot_manager.py`.
  - Snapshots are preserved as standalone archives in `.snapshots/<name>.tar.gz` and cataloged in `.snapshots/manifest.json`.
  - A local Git repository with tags (e.g. `v2.9.6-stable`, `latest-stable`) and branch `stable` provides dual redundancy.
- **How to Revert to Stable Release**:
  - If the user asks to revert to the latest stable release (or a specific stable snapshot):
    Run `python snapshot_manager.py --restore stable` (or `python snapshot_manager.py --restore v2.9.6-stable`).
    Then run `python preview_manager.py --sync` and verify with `lint_applet` & `compile_applet`.
  - To create a new stable snapshot: `python snapshot_manager.py --create <name> --stable`.

