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
- **Recovery / Error Response**:
  If the web preview breaks, fails linting, or reports build errors, the agent MUST fix the build configuration/types within `/src/App.tsx` to restore the changelog viewer. The agent MUST NOT "re-imagine" or regenerate a new UI from scratch.
- **Changelog Synchronization**:
  Whenever `CHANGELOG.md` or version information is updated in the desktop application codebase, ensure the changes are reflected in the changelog viewer in `/src/App.tsx`.

## 2. Standardized Version Bump Checklist
When bumping or updating the application version number, you MUST update **ALL** of the following locations synchronously:
1. `prs_shared.py` (`PROJECT_VERSION`)
2. `updater.py` (`PROJECT_VERSION` fallback)
3. `build_installer.py` (`PROJECT_VERSION` fallback)
4. `installer/Windows/RadioTVStorySegmenter.iss` (`#define MyAppVersion`)
5. `plugins/*/manifest.json` (`version` across `wordpress`, `youtube`, `translation`)
6. `transcript_story.py` (docstring version header)
7. `package.json`, `metadata.json`, and `index.html` (title & meta tags)
8. `CHANGELOG.md` & `/src/App.tsx` (version notes and expanded accordion defaults)

## 3. Pre-Completion Verification
Before completing code modifications:
- Run Python syntax compilation checks: `python -m py_compile RadioTVSegmenter.py prs_shared.py processing.py runtime_manager.py radio_tv_story_segmenter_worker.py updater.py build_installer.py plugins/manager.py`
- Run the web preview linter and build tools (`lint_applet` & `compile_applet`) to ensure zero regressions.

## 4. Architectural Invariants Reference
Always adhere strictly to the invariants defined in `ARCHITECTURE.md`:
- Core modules must NEVER import from `plugins/`.
- Heavy translation runtimes must remain isolated inside `plugins/translation/`.
- Speaker diarization uses `wespeakerruntime` as the primary ONNX embedding engine.
