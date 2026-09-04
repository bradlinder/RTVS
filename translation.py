"""Radio & TV Segmenter — Local Translation Mixin.

Provides offline neural machine translation via TranslationWorker (CTranslate2 / Opus-MT),
translation state management, UI language toggling, and asynchronous model verification.
"""

from __future__ import annotations

import copy
import json
import os
import threading
from typing import Any

from prs_shared import (
    TranslationWorker,
    format_time,
)

from PySide6.QtCore import QObject, Qt, QThread, QTimer
from PySide6.QtWidgets import (
    QApplication,
    QMessageBox,
    QProgressDialog,
)


class TranslationMixin:
    """Mixin class managing transcript translation, language toggling, and worker lifecycle."""

    def source_language_code(self) -> str:
        """Return the source language code (defaults to 'en')."""
        return "en"

    def target_language_code(self) -> str:
        """Return the target language code (defaults to 'es')."""
        return "es"

    def translation_key(self, from_code: str = "en", to_code: str = "es") -> str:
        """Generate standardized dictionary key for language translation pair."""
        return f"{from_code}-{to_code}"

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
            is_installed = TranslationWorker.model_is_installed("en", "es", variant)
            cache_key = f"{variant}:en-es"
            if hasattr(self, "translation_model_status_cache"):
                self.translation_model_status_cache[cache_key] = is_installed

        t = threading.Thread(target=_check, daemon=True)
        t.start()

    def stop_translation_worker(self, timeout_ms: int = 5000) -> bool:
        """Gracefully stop any running translation worker and wait for thread exit."""
        if getattr(self, "translation_worker", None) is not None:
            try:
                self.translation_worker.cancel()
            except Exception:
                pass
        if getattr(self, "translation_thread", None) is not None:
            try:
                self.translation_thread.quit()
                if not self.translation_thread.wait(timeout_ms):
                    self.translation_thread.terminate()
                    self.translation_thread.wait(1000)
            except Exception:
                pass
            finally:
                self.translation_thread = None
                self.translation_worker = None
        if hasattr(self, "cancel_button") and self.cancel_button is not None:
            self.cancel_button.hide()
        return True

    def start_translation(self, from_code: str = "en", to_code: str = "es", install_if_missing: bool = True):
        """Start local translation worker in a background QThread."""
        if getattr(self, "translation_thread", None) is not None:
            QMessageBox.information(self, "Translation Busy", "A translation task is already running.")
            return

        raw_segments = []
        if isinstance(self.transcript, dict):
            raw_segments = self.transcript.get("segments", [])
        elif isinstance(self.transcript, list):
            raw_segments = self.transcript

        if not raw_segments:
            QMessageBox.warning(self, "No Transcript", "A transcript is required before running translation.")
            if getattr(self, "pipeline_active", False):
                self.pipeline_active = False
                self.pipeline_queue = []
                self.pipeline_rerun_confirmed = False
            return

        variant = getattr(self, "translation_model_variant", "tiny")
        if not TranslationWorker.model_is_installed(from_code, to_code, variant):
            if not install_if_missing:
                QMessageBox.warning(
                    self,
                    "Translation Model Missing",
                    f"The {variant} translation model ({from_code}->{to_code}) is not installed.\n"
                    "Please install it via Settings > Manage Models."
                )
                if getattr(self, "pipeline_active", False):
                    self.pipeline_active = False
                    self.pipeline_queue = []
                    self.pipeline_rerun_confirmed = False
                return

        self.set_processing_stage("Translating transcript", f"{from_code} → {to_code}")
        if hasattr(self, "cancel_button") and self.cancel_button is not None:
            self.cancel_button.show()
            self.cancel_button.setEnabled(True)
        self.set_tools_actions_enabled(False)

        device = getattr(self, "translation_device", "cpu")
        segments = raw_segments

        worker = TranslationWorker(
            segments=copy.deepcopy(segments),
            from_code=from_code,
            to_code=to_code,
            install_if_missing=install_if_missing,
            model_variant=variant,
            transcript=copy.deepcopy(self.transcript),
            variant=variant,
            device=device,
        )
        thread = QThread(self)
        worker.moveToThread(thread)

        self.translation_worker = worker
        self.translation_thread = thread

        thread.started.connect(worker.run)
        worker.progress.connect(self._on_translation_progress)
        worker.finished.connect(self._on_translation_finished)
        worker.cancelled.connect(self._on_translation_cancelled)
        worker.error.connect(self._on_translation_error)

        worker.finished.connect(thread.quit)
        worker.cancelled.connect(thread.quit)
        worker.error.connect(thread.quit)
        thread.finished.connect(worker.deleteLater)
        thread.finished.connect(self._on_translation_thread_finished)

        thread.start()
        self.log_activity(f"[TRANSLATION] Started {from_code}->{to_code} local translation ({variant}).")

    def _on_translation_progress(self, percent: float, message: str):
        """Handle progress updates from TranslationWorker."""
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

        # Switch view to Spanish to show the result
        self.translation_display_mode = "es"
        if hasattr(self, "transcript_language_selector") and self.transcript_language_selector is not None:
            idx = self.transcript_language_selector.findData("es")
            if idx >= 0:
                self.transcript_language_selector.blockSignals(True)
                self.transcript_language_selector.setCurrentIndex(idx)
                self.transcript_language_selector.blockSignals(False)
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
