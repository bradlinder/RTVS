"""Radio & TV Segmenter — Local Translation Mixin.

Provides offline neural machine translation via TranslationWorker (CTranslate2 / Opus-MT),
translation state management, UI language toggling, and asynchronous model verification.
"""

from __future__ import annotations

import copy
import json
import os
import threading
import json
import tempfile
from pathlib import Path
from typing import Any

from prs_shared import format_time


def _translation_worker_class():
    """Load the translation worker only when the translation plugin is installed."""
    from plugins.translation.worker import TranslationWorker
    return TranslationWorker

from PySide6.QtCore import QObject, Qt, QThread, QTimer, QProcess, QProcessEnvironment, Signal
from PySide6.QtWidgets import (
    QApplication,
    QMessageBox,
    QProgressDialog,
)


class TranslationEnvSetupWorker(QObject):
    """Background worker that sets up the isolated translation runtime environment."""
    progress = Signal(str)
    finished = Signal(object)  # None on success, error message (str) on failure

    def __init__(self, plugin_dir: Path | None = None):
        super().__init__()
        self.plugin_dir = plugin_dir
        self._cancelled = False

    def cancel(self):
        self._cancelled = True

    def run(self):
        error = None
        try:
            manager = _translation_runtime_manager()

            def _on_progress(msg: str):
                if not self._cancelled:
                    self.progress.emit(msg)

            ok = manager.ensure_environment(
                "translate",
                progress_cb=_on_progress,
                plugin_dir=self.plugin_dir,
            )
            if not ok:
                err_detail = manager.get_last_error()
                error = "The isolated translation runtime could not be installed or updated."
                if err_detail:
                    error = f"{error}\n\nDetails:\n{err_detail}"
            elif self._cancelled:
                error = "Translation environment preparation was cancelled."
        except Exception as exc:
            error = f"{type(exc).__name__}: {exc}"
        self.finished.emit(error)


def _translation_runtime_entry_path(app=None) -> Path:
    manager = getattr(app, "plugin_manager", None) if app is not None else None
    if manager is not None:
        folder = manager.plugin_paths.get("translation")
        if folder:
            folder = Path(folder)
            if folder.is_dir():
                candidate = folder / "runtime_entry.py"
                if candidate.exists():
                    return candidate

    try:
        from plugins.manager import PluginManager
        candidates = [
            Path(__file__).resolve().parent / "plugins" / "translation" / "runtime_entry.py",
            PluginManager.get_user_plugins_dir() / "translation" / "runtime_entry.py",
            PluginManager.get_bundled_plugins_dir() / "translation" / "runtime_entry.py",
        ]
        for c in candidates:
            if c.is_file():
                return c
    except Exception:
        fallback = Path(__file__).resolve().parent / "plugins" / "translation" / "runtime_entry.py"
        if fallback.is_file():
            return fallback

    return Path()

def _translation_runtime_manager():
    from runtime_manager import RuntimeManager
    return RuntimeManager()

class TranslationMixin:
    """Mixin class managing transcript translation, language toggling, and worker lifecycle."""

    def source_language_code(self) -> str:
        """Return the source language code for translation.

        Honors an explicit direction chosen via the batch dialog's
        Translation control ("en-es" or "es-en"); for "auto" (the default),
        flips based on the transcript's Whisper-detected language so a
        Spanish-language recording translates to English and vice versa.
        """
        direction = str(getattr(self, "translation_direction", "auto") or "auto")
        if direction == "es-en":
            return "es"
        if direction == "en-es":
            return "en"
        detected = str((self.transcript or {}).get("language", "en") or "en").lower()
        return "es" if detected.startswith("es") else "en"

    def target_language_code(self) -> str:
        """Return the target language code for translation (see source_language_code)."""
        direction = str(getattr(self, "translation_direction", "auto") or "auto")
        if direction == "es-en":
            return "en"
        if direction == "en-es":
            return "es"
        detected = str((self.transcript or {}).get("language", "en") or "en").lower()
        return "en" if detected.startswith("es") else "es"

    def translation_key(self, from_code: str = "en", to_code: str = "es") -> str:
        """Generate standardized dictionary key for language translation pair."""
        return f"{from_code}-{to_code}"

    def get_translation_item(self, from_code: str, to_code: str) -> dict | None:
        """Return a current translation for an explicit language pair."""
        if not isinstance(getattr(self, "translations", None), dict):
            return None
        data = self.translations.get(self.translation_key(from_code, to_code))
        if data is None:
            data = self.translations.get(f"{from_code}_{to_code}")
        if not isinstance(data, dict) or data.get("status") == "stale":
            return None
        return data if data.get("segments") else None

    def translation_export_spec(self, options: dict | None = None):
        """Return (source, target, suffix) for batch translation exports.

        Normal interactive exports remain English + optional Spanish. Batch
        exports may explicitly request either direction, so the exported
        translated document uses the actual requested target language.
        """
        options = options or {}
        direction = str(options.get("translation_direction", "en-es") or "en-es")
        if direction not in {"en-es", "es-en"}:
            direction = "es-en" if self.source_language_code() == "es" else "en-es"
        source, target = direction.split("-")
        suffix = f"_{target}"
        return source, target, suffix

    def translation_is_current(self, key: str | None = None) -> bool:
        """Check if translation for the given key exists, has content, and is not stale."""
        key = key or self.translation_key()
        if not hasattr(self, "translations") or not isinstance(self.translations, dict):
            return False
        data = self.translations.get(key)
        if not data or not isinstance(data, dict):
            alt_key = key.replace("-", "_")
            data = self.translations.get(alt_key)
        if not data or not isinstance(data, dict):
            return False
        if data.get("status") == "stale":
            return False
        segments = data.get("segments", [])
        return bool(segments)

    def has_spanish_translation(self) -> bool:
        """Check if an English-to-Spanish translation is available."""
        item = self.get_spanish_translation_item()
        if not item or not isinstance(item, dict):
            return False
        segments = item.get("segments", [])
        return bool(segments)

    def get_spanish_translation_item(self) -> dict | None:
        """Return the translation dictionary for en-es if present."""
        if not hasattr(self, "translations") or not isinstance(self.translations, dict):
            return None
        return (
            self.translations.get("en-es")
            or self.translations.get("en_es")
            or None
        )

    def mark_stale_translations(self):
        """Mark all existing translations as stale when transcript text changes."""
        if hasattr(self, "translations") and isinstance(self.translations, dict):
            for key, val in self.translations.items():
                if isinstance(val, dict):
                    val["status"] = "stale"
        if hasattr(self, "update_translation_language_selector"):
            self.update_translation_language_selector()

    def update_translation_language_selector(self):
        """Update translation UI selector states (tabs / combobox / actions)."""
        has_es = self.has_spanish_translation()
        if hasattr(self, "transcript_language_selector") and self.transcript_language_selector is not None:
            self.transcript_language_selector.blockSignals(True)
            self.transcript_language_selector.clear()
            self.transcript_language_selector.addItem("English (Original)", "en")
            if has_es:
                es_item = self.get_spanish_translation_item()
                is_stale = isinstance(es_item, dict) and es_item.get("status") == "stale"
                es_label = "Español (Translation - Outdated)" if is_stale else "Español (Translation)"
                self.transcript_language_selector.addItem(es_label, "es")
                self.transcript_language_selector.addItem("Bilingual (Split)", "split")
            target_mode = getattr(self, "translation_display_mode", "en")
            if target_mode == "bilingual":
                target_mode = "split"
            cur_idx = self.transcript_language_selector.findData(target_mode)
            if cur_idx < 0:
                cur_idx = 0
                self.translation_display_mode = "en"
            self.transcript_language_selector.setCurrentIndex(cur_idx)
            self.transcript_language_selector.blockSignals(False)

        if hasattr(self, "export_translation_action") and self.export_translation_action is not None:
            self.export_translation_action.setEnabled(has_es)

    def change_translation_display(self, mode: str | int | None = None):
        """Change the active translation display mode ('en', 'es', or 'split')."""
        if isinstance(mode, int):
            if hasattr(self, "transcript_language_selector") and self.transcript_language_selector is not None:
                mode = self.transcript_language_selector.itemData(mode)
            else:
                mode = "en"
        elif mode is None:
            if hasattr(self, "transcript_language_selector") and self.transcript_language_selector is not None:
                mode = self.transcript_language_selector.currentData()
            else:
                mode = "en"
        mode_str = str(mode or "en")
        if mode_str == "bilingual":
            mode_str = "split"
        self.translation_display_mode = mode_str
        self.render_transcript()

    def render_translation_view(self):
        """Re-render transcript or translation view based on current display settings."""
        self.render_transcript()

    def check_translation_models_async(self):
        """Asynchronously verify if required translation models are installed."""
        def _check():
            variant = getattr(self, "translation_model_variant", "tiny")
            try:
                if hasattr(self, "plugin_manager") and not self.plugin_manager.is_plugin_installed("translation"):
                    return
                is_installed = _translation_worker_class().model_is_installed("en", "es", variant)
            except Exception:
                return
            cache_key = f"{variant}:en-es"
            if hasattr(self, "translation_model_status_cache"):
                self.translation_model_status_cache[cache_key] = is_installed

        t = threading.Thread(target=_check, daemon=True)
        t.start()

    def _cleanup_translation_env_thread(self):
        thread = getattr(self, "_translation_env_qthread", None)
        if thread is not None:
            try:
                thread.quit()
                thread.wait(1000)
            except Exception:
                pass
        self._translation_env_thread = None
        self._translation_env_qthread = None
        self._translation_env_worker = None

    def _on_translation_env_progress(self, message: str):
        self.log_activity(f"[TRANSLATION] {message}", mark_dirty=False)
        self.set_processing_stage("Translation Runtime", message)

    def stop_translation_worker(self, timeout_ms: int = 5000) -> bool:
        if getattr(self, "_translation_env_worker", None) is not None:
            try:
                self._translation_env_worker.cancel()
            except Exception:
                pass
        self._cleanup_translation_env_thread()

        proc = getattr(self, "translation_process", None)
        if proc is not None:
            try:
                proc.terminate()
                if not proc.waitForFinished(timeout_ms):
                    proc.kill()
                    proc.waitForFinished(1000)
            except Exception:
                pass
        self.translation_process = None
        self.translation_thread = None
        self.translation_worker = None
        if hasattr(self, "cancel_button") and self.cancel_button is not None:
            self.cancel_button.hide()
        return True

    def _start_translation_runtime_request(self, request: dict, on_finished=None) -> bool:
        """Run translation code in the plugin-owned isolated Python environment."""
        if (
            getattr(self, "translation_process", None) is not None
            or getattr(self, "_translation_env_thread", None) is not None
        ):
            return False
        entry = _translation_runtime_entry_path(self)
        if not entry.exists():
            self._on_translation_error("The translation plugin runtime entry point is missing.")
            return False

        manager = _translation_runtime_manager()
        plugin_dir = entry.parent if entry and entry.exists() else None

        # Fast path: check if environment is already up-to-date on disk
        is_ready = False
        try:
            raw_exe = manager._get_raw_executable("translate")
            is_ready = bool(raw_exe.exists() and manager.is_env_up_to_date("translate"))
        except Exception:
            is_ready = False

        if is_ready:
            python_exe = manager.get_executable("translate")
            if python_exe and Path(python_exe).exists():
                return self._launch_translation_process(request, on_finished, python_exe, entry)

        # First-run or update: provision environment asynchronously to keep UI completely responsive
        self.set_processing_stage("Translation Runtime", "Preparing isolated translation environment (first run)…")
        self.log_activity("[TRANSLATION] Preparing isolated translation environment in background...")
        if hasattr(self, "cancel_button") and self.cancel_button is not None:
            self.cancel_button.show()
            self.cancel_button.setEnabled(True)

        self._translation_env_qthread = QThread(self)
        self._translation_env_worker = TranslationEnvSetupWorker(plugin_dir=plugin_dir)
        self._translation_env_worker.moveToThread(self._translation_env_qthread)
        if hasattr(self, "_track_worker_thread"):
            self._track_worker_thread(self._translation_env_qthread)

        self._translation_env_qthread.started.connect(self._translation_env_worker.run)
        self._translation_env_worker.progress.connect(self._on_translation_env_progress)

        def _on_setup_finished(error):
            self._cleanup_translation_env_thread()
            if error:
                self.log_activity(f"[TRANSLATION] Environment setup error: {error}", mark_dirty=False)
                self._on_translation_error(error)
                if on_finished:
                    try:
                        on_finished(-1, error, "")
                    except Exception:
                        pass
                return

            py_exe = manager.get_executable("translate")
            if not py_exe or not Path(py_exe).exists():
                err = "The isolated translation Python runtime is unavailable."
                self._on_translation_error(err)
                if on_finished:
                    try:
                        on_finished(-1, err, "")
                    except Exception:
                        pass
                return

            self._launch_translation_process(request, on_finished, py_exe, entry)

        self._translation_env_worker.finished.connect(_on_setup_finished)
        self._translation_env_thread = self._translation_env_qthread
        self._translation_env_qthread.start()
        return True

    def _launch_translation_process(self, request: dict, on_finished, python_exe: str, entry: Path) -> bool:
        fd, request_path = tempfile.mkstemp(prefix="rtvs_translate_", suffix=".json")
        os.close(fd)
        request_file = Path(request_path)
        request_file.write_text(json.dumps(request, ensure_ascii=False), encoding="utf-8")

        proc = QProcess(self)
        proc_env = QProcessEnvironment.systemEnvironment()
        proc_env.insert("KMP_DUPLICATE_LIB_OK", "TRUE")
        proc_env.insert("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")
        proc_env.insert("TOKENIZERS_PARALLELISM", "false")
        proc.setProcessEnvironment(proc_env)
        proc.setProgram(python_exe)
        proc.setArguments([str(entry), str(request_file)])
        proc.setProcessChannelMode(QProcess.ProcessChannelMode.SeparateChannels)
        proc._rtvs_request_file = request_file
        proc._rtvs_output = ""
        proc._rtvs_line_buffer = ""
        proc._rtvs_callback = on_finished
        self.translation_process = proc
        # Keep compatibility with existing busy checks.
        self.translation_thread = proc

        def read_output():
            data = bytes(proc.readAllStandardOutput()).decode("utf-8", errors="replace")
            proc._rtvs_output += data
            proc._rtvs_line_buffer += data
            lines = proc._rtvs_line_buffer.split("\n")
            proc._rtvs_line_buffer = lines.pop() if lines else ""
            for line in lines:
                line = line.strip()
                if not line:
                    continue
                try:
                    msg = json.loads(line)
                except Exception:
                    continue
                kind = msg.get("type")
                if kind == "progress":
                    self._on_translation_progress(msg.get("percent", 0), msg.get("message", ""))
                elif kind == "finished":
                    if not request.get("installation_only"):
                        self._on_translation_finished(msg.get("result", []), msg.get("key", ""))
                elif kind == "cancelled":
                    self._on_translation_cancelled(msg.get("result", []), msg.get("key", ""))

        def finished(exit_code, exit_status):
            stderr = bytes(proc.readAllStandardError()).decode("utf-8", errors="replace").strip()
            if proc._rtvs_callback:
                try:
                    proc._rtvs_callback(exit_code, stderr, proc._rtvs_output)
                except Exception as exc:
                    self.log_activity(f"[TRANSLATION] Runtime callback error: {exc}", mark_dirty=False)
            if exit_code != 0 and stderr:
                self._on_translation_error(stderr[-4000:])
            try:
                proc._rtvs_request_file.unlink(missing_ok=True)
            except Exception:
                pass
            self.translation_process = None
            self.translation_thread = None
            self.translation_worker = None
            proc.deleteLater()

        proc.readyReadStandardOutput.connect(read_output)
        proc.finished.connect(finished)
        proc.start()
        if not proc.waitForStarted(10000):
            try:
                request_file.unlink(missing_ok=True)
            except Exception:
                pass
            self.translation_process = None
            self.translation_thread = None
            self._on_translation_error("Could not start the isolated translation runtime.")
            proc.deleteLater()
            return False
        return True

    def start_translation(self, from_code: str = "en", to_code: str = "es", install_if_missing: bool = True):
        """Start local translation in the translation plugin's isolated runtime."""
        if hasattr(self, "plugin_manager") and not self.plugin_manager.is_plugin_enabled("translation"):
            QMessageBox.warning(self, "Plugin Disabled", "The Language Translation plugin is currently disabled.\nYou can enable it in Settings > Manage Plugins & Add-ons.")
            return
        if getattr(self, "translation_process", None) is not None:
            QMessageBox.information(self, "Translation Busy", "A translation task is already running.")
            return

        raw_segments = self.transcript.get("segments", []) if isinstance(self.transcript, dict) else (self.transcript if isinstance(self.transcript, list) else [])
        if not raw_segments:
            QMessageBox.warning(self, "No Transcript", "A transcript is required before running translation.")
            return

        variant = getattr(self, "translation_model_variant", "tiny")
        if not _translation_worker_class().model_is_installed(from_code, to_code, variant) and not install_if_missing:
            QMessageBox.warning(self, "Translation Model Missing", f"The {variant} translation model ({from_code}->{to_code}) is not installed.\nPlease install it via Settings > Manage Models.")
            return

        self.set_processing_stage("Translating transcript", f"{from_code} → {to_code}")
        if hasattr(self, "cancel_button") and self.cancel_button is not None:
            self.cancel_button.show(); self.cancel_button.setEnabled(True)
        self.set_tools_actions_enabled(False)

        request = {
            "segments": copy.deepcopy(raw_segments),
            "from_code": from_code, "to_code": to_code,
            "install_if_missing": install_if_missing,
            "model_variant": variant, "variant": variant,
            "transcript": copy.deepcopy(self.transcript),
            "device": getattr(self, "translation_device", "cpu"),
        }
        self.log_activity(f"[TRANSLATION] Starting isolated {from_code}->{to_code} translation ({variant}).")
        if not self._start_translation_runtime_request(request):
            self.set_tools_actions_enabled(True)
            if hasattr(self, "cancel_button") and self.cancel_button is not None: self.cancel_button.hide()

    def _on_translation_progress(self, percent: float, message: str):
        """Handle progress updates from _translation_worker_class()."""
        self.update_processing_progress(percent, message)

    def _on_translation_finished(self, translated_transcript: Any, translation_key: str):
        """Handle successful translation results."""
        if not hasattr(self, "translations") or not isinstance(self.translations, dict):
            self.translations = {}

        if isinstance(translated_transcript, list):
            translated_dict = copy.deepcopy(self.transcript) if isinstance(self.transcript, dict) else {}
            translated_dict["segments"] = translated_transcript
        elif isinstance(translated_transcript, dict):
            translated_dict = translated_transcript
        else:
            translated_dict = {"segments": []}

        translated_dict["status"] = "current"
        self.translations[translation_key] = translated_dict
        if hasattr(self, "processing_status") and isinstance(self.processing_status, dict):
            self.processing_status["translation"] = True
        if hasattr(self, "update_processing_stage_summary"):
            self.update_processing_stage_summary()

        self.log_activity(f"[TRANSLATION] Completed translation ({translation_key}).")
        self.mark_project_dirty("Translation completed")
        self.update_translation_language_selector()
        self.set_processing_stage("", "")
        self.set_tools_actions_enabled(True)
        if hasattr(self, "cancel_button") and self.cancel_button is not None:
            self.cancel_button.hide()

        # Maintain the current language view until the user selects a different view
        self.render_transcript()

        if getattr(self, "pipeline_active", False) and getattr(self, "pipeline_queue", []):
            QTimer.singleShot(0, self._run_next_selected_processing)
        elif getattr(self, "batch_active", False) and getattr(self, "pipeline_active", False):
            self.pipeline_active = False
            self.pipeline_rerun_confirmed = False
            self._batch_export_current()
            QTimer.singleShot(0, self._batch_next_media)
        elif getattr(self, "pipeline_active", False):
            self.pipeline_active = False
            self.pipeline_rerun_confirmed = False
            self.set_processing_stage(None)
            self.log_activity("[AUTOMATION] Selected processing complete.")

    def _on_translation_cancelled(self, results: Any, translation_key: str):
        """Handle translation worker cancellation."""
        self.log_activity(f"[TRANSLATION] Canceled by user ({translation_key}).")
        if getattr(self, "pipeline_active", False):
            self.pipeline_active = False
            self.pipeline_queue = []
            self.pipeline_rerun_confirmed = False
        self.set_processing_stage("", "")
        self.set_tools_actions_enabled(True)
        if hasattr(self, "cancel_button") and self.cancel_button is not None:
            self.cancel_button.hide()

    def _on_translation_error(self, error_message: str):
        """Handle translation worker failures."""
        self.log_activity(f"[TRANSLATION ERROR] {error_message}")
        if getattr(self, "pipeline_active", False):
            self.pipeline_active = False
            self.pipeline_queue = []
            self.pipeline_rerun_confirmed = False
        self.set_processing_stage("", "")
        self.set_tools_actions_enabled(True)
        if hasattr(self, "cancel_button") and self.cancel_button is not None:
            self.cancel_button.hide()
        QMessageBox.critical(self, "Translation Error", f"Translation failed:\n\n{error_message}")

    def _on_translation_thread_finished(self):
        """Clean up thread reference."""
        self.translation_thread = None
        self.translation_worker = None

    def _translation_thread_finished(self):
        """Alias for _on_translation_thread_finished."""
        self._on_translation_thread_finished()
