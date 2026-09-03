"""Radio & TV Segmenter v1.1.1 — model management responsibilities.

Methods intentionally retain the MainWindow-facing API so behavior remains
maintaining the established MainWindow-facing API while responsibilities are isolated.
"""

from prs_shared import *


class WhisperModelInstallWorker(QObject):
    finished = Signal(object)

    def __init__(self, model_name):
        super().__init__()
        self.model_name = str(model_name)

    def run(self):
        error = None
        try:
            WhisperModel(self.model_name, device="cpu", compute_type="int8")
        except Exception as exc:
            error = f"{type(exc).__name__}: {exc}"
        self.finished.emit(error)


class ModelManagementMixin:
    def model_cache_path(self, model_name):
        models_dir = get_models_storage_dir()
        cache_root = models_dir / "huggingface" / "hub"
        candidates = [
            cache_root / f"models--Systran--faster-whisper-{model_name}",
            get_app_data_dir() / "models" / "huggingface" / "hub" / f"models--Systran--faster-whisper-{model_name}",
            Path(__file__).resolve().parent / "models" / f"faster-whisper-{model_name}",
        ]
        return next((p for p in candidates if p.exists()), candidates[0])

    def is_whisper_model_available(self, model_name):
        path = self.model_cache_path(model_name)
        if not path.exists():
            return False
        if path.is_dir() and any(path.rglob("model.bin")):
            return True
        if path.is_dir() and any(path.rglob("*.bin")):
            return True
        return False

    def refresh_whisper_model_chooser(self):
        if not hasattr(self, "model_input"):
            return
        current = self.whisper_model
        self.model_input.blockSignals(True)
        self.model_input.clear()
        models = [("tiny", "Tiny"), ("base", "Base"), ("small", "Small"), ("medium", "Medium"), ("large-v3", "Large")]
        for model_id, label in models:
            available = self.is_whisper_model_available(model_id)
            display = f"{label} ✓" if available else f"{label} — download when used"
            self.model_input.addItem(display, model_id)
            self.model_input.setItemData(self.model_input.count()-1, model_id, Qt.ItemDataRole.UserRole)
        idx = max(0, self.model_input.findData(current))
        self.model_input.setCurrentIndex(idx)
        self.model_input.blockSignals(False)
        self.update_whisper_model_tooltip()

    def current_whisper_model(self):
        if hasattr(self, "model_input"):
            value = self.model_input.currentData(Qt.ItemDataRole.UserRole)
            if value:
                return str(value)
        return self.whisper_model

    def update_whisper_model_tooltip(self):
        model = self.current_whisper_model()
        available = self.is_whisper_model_available(model)
        label = model.replace("-v3", "").title()
        state = "installed locally" if available else "not downloaded; it will download locally on first use"
        if hasattr(self, "model_input"):
            self.model_input.setToolTip(f"Whisper {label}: {state}. No cloud service is used for processing.")

    def set_whisper_model_from_ui(self, index):
        model = self.model_input.itemData(index, Qt.ItemDataRole.UserRole)
        if not model:
            return
        new_model = str(model)
        changed = new_model != self.whisper_model
        self.whisper_model = new_model
        self.update_whisper_model_tooltip()
        if changed and self.transcript is not None:
            self.processing_status["transcription"] = False
            self.log_activity("[PROCESSING] Whisper model changed; existing transcription is marked for reprocessing.", mark_dirty=False)
        self.mark_project_dirty()
        available = self.is_whisper_model_available(self.whisper_model)
        self.log_activity(f"[SETTINGS] Whisper model set to {self.whisper_model} ({'installed' if available else 'will download locally on first use'}).")
        self.statusBar().showMessage(f"Whisper model: {self.whisper_model}")

    def translation_model_display_name(self, variant=None):
        variant = variant or self.translation_model_variant
        return "OPUS-MT-tiny" if variant == "tiny" else "OPUS-MT"

    def translation_model_root(self, variant=None):
        return TranslationWorker.model_root(variant or self.translation_model_variant)

    def refresh_translation_model_chooser(self):
        if not hasattr(self, "translation_model_input"): return
        self.translation_model_input.blockSignals(True)
        self.translation_model_input.clear()
        for vid, label in (("tiny", "OPUS-MT-tiny"), ("standard", "OPUS-MT")):
            self.translation_model_input.addItem(label, vid)
        idx = self.translation_model_input.findData(self.translation_model_variant)
        self.translation_model_input.setCurrentIndex(max(0, idx))
        self.translation_model_input.blockSignals(False)
        if hasattr(self, "translation_model_input"):
            self.translation_model_input.setToolTip(f"Preferred local translation model: {self.translation_model_display_name()} . Models download only when needed and remain available offline.")

    def set_translation_model_from_ui(self, index):
        value = self.translation_model_input.itemData(index, Qt.ItemDataRole.UserRole)
        if not value: return
        value = str(value)
        if value == self.translation_model_variant: return
        self.translation_model_variant = value
        self.mark_project_dirty()
        self.log_activity(f"[SETTINGS] Translation model set to {self.translation_model_display_name()}.")
        self.statusBar().showMessage(f"Translation model: {self.translation_model_display_name()}")
        self.refresh_translation_model_chooser()

    def prompt_translation_model(self):
        items = ["OPUS-MT-tiny", "OPUS-MT"]
        current = 0 if self.translation_model_variant == "tiny" else 1
        choice, ok = QInputDialog.getItem(self, "Translation Model", "Preferred translation model:", items, current, False)
        if ok:
            self.translation_model_variant = "tiny" if choice == "OPUS-MT-tiny" else "standard"
            self.refresh_translation_model_chooser()
            self.mark_project_dirty()
            self.log_activity(f"[SETTINGS] Translation model set to {choice}.")

    def open_model_cleanup_dialog(self):
        """Unified local model manager for Whisper and OPUS-MT models."""
        dialog = QDialog(self)
        dialog.setWindowTitle("Manage Models")
        dialog.setMinimumWidth(820)
        layout = QVBoxLayout(dialog)
        layout.addWidget(QLabel(
            "Download, install, inspect, or remove local transcription and translation models. "
            "Models are never removed automatically."
        ))

        # Storage directory banner with link to Preferences
        storage_box = QFrame()
        storage_box.setFrameShape(QFrame.Shape.StyledPanel)
        storage_layout = QHBoxLayout(storage_box)
        storage_layout.setContentsMargins(8, 6, 8, 6)
        curr_dir_str = str(get_models_storage_dir())
        loc_label = QLabel(f"<b>Model Storage Folder:</b> {curr_dir_str}")
        loc_label.setToolTip(curr_dir_str)
        pref_link_btn = QPushButton("Change Storage Folder in Preferences…")
        pref_link_btn.setToolTip("Open Preferences to change the download/storage directory for models")
        def _go_to_prefs():
            dialog.accept()
            if hasattr(self, "open_preferences_dialog"):
                self.open_preferences_dialog(initial_category="Models")
        pref_link_btn.clicked.connect(_go_to_prefs)
        storage_layout.addWidget(loc_label, 1)
        storage_layout.addWidget(pref_link_btn)
        layout.addWidget(storage_box)

        rows = []

        def size_text(path):
            try:
                total = sum(f.stat().st_size for f in Path(path).rglob('*') if f.is_file())
                return f"{total / (1024 * 1024):.1f} MB"
            except Exception:
                return "size unavailable"

        def add_row(kind, model_id, label, path, installed, install_fn):
            row = QHBoxLayout()
            name = QLabel(label)
            name.setMinimumWidth(250)
            status = QLabel("✓ Installed" if installed else "Not installed")
            status.setMinimumWidth(145)
            size = QLabel(size_text(path) if installed else "—")
            size.setMinimumWidth(85)
            install_btn = QPushButton("Repair / Reinstall" if installed else "Download / Install")
            install_btn.clicked.connect(install_fn)  # Fixed: Connected button click signal
            remove_cb = QCheckBox("Remove")
            remove_cb.setEnabled(installed)
            row.addWidget(name)
            row.addWidget(status)
            row.addWidget(size)
            row.addWidget(install_btn)
            row.addWidget(remove_cb)
            layout.addLayout(row)
            rows.append({
                "kind": kind, "model_id": model_id, "label": label, "path": Path(path),
                "status": status, "size": size, "button": install_btn, "remove": remove_cb,
                "install_fn": install_fn,
            })
            return row

        layout.addWidget(QLabel("<b>Transcription models</b>"))
        whisper_models = [
            ("tiny", "Whisper Tiny"), ("base", "Whisper Base"),
            ("small", "Whisper Small"), ("medium", "Whisper Medium"),
            ("large-v3", "Whisper Large"),
        ]
        for model_id, label in whisper_models:
            path = self.model_cache_path(model_id)
            installed = self.is_whisper_model_available(model_id)
            add_row("whisper", model_id, label, path, installed,
                    lambda _, m=model_id: self.install_whisper_model_for_manager(m, dialog))  # Added '_' here

        layout.addSpacing(8)
        layout.addWidget(QLabel("<b>Translation models</b>"))
        for variant, variant_label in (("tiny", "OPUS-MT-tiny"), ("standard", "OPUS-MT")):
            for pair, pair_label in ((("en", "es"), "English → Spanish"), (("es", "en"), "Spanish → English")):
                from_code, to_code = pair
                path = TranslationWorker.model_dir(from_code, to_code, variant)
                installed = TranslationWorker.model_is_installed(from_code, to_code, variant)
                label = f"{variant_label} — {pair_label}"
                add_row("translation", f"{variant}:{from_code}-{to_code}", label, path, installed,
                        lambda _, f=from_code, t=to_code, d=variant: self.install_translation_models_for_manager(f, t, d, dialog))  # Added '_' here

        layout.addSpacing(8)
        layout.addWidget(QLabel("Select <b>Remove</b> beside any installed model you no longer need, then click Remove Selected."))
        buttons = QHBoxLayout()
        remove_btn = QPushButton("Remove Selected")
        close_btn = QPushButton("Close")
        buttons.addStretch(); buttons.addWidget(remove_btn); buttons.addWidget(close_btn)
        layout.addLayout(buttons)
        close_btn.clicked.connect(dialog.reject)

        def refresh_rows():
            busy = self.translation_thread is not None or getattr(self, "_model_install_thread", None) is not None
            for item in rows:
                if item["kind"] == "whisper":
                    installed_now = self.is_whisper_model_available(item["model_id"])
                else:
                    variant, pair = item["model_id"].split(":", 1)
                    f, t = pair.split("-", 1)
                    installed_now = TranslationWorker.model_is_installed(f, t, variant)
                item["status"].setText("✓ Installed" if installed_now else "Not installed")
                item["size"].setText(size_text(item["path"]) if installed_now else "—")
                item["button"].setText("Repair / Reinstall" if installed_now else "Download / Install")
                item["button"].setEnabled(not busy)
                item["remove"].setEnabled(installed_now and not busy)
                if not installed_now:
                    item["remove"].setChecked(False)

        def remove_selected():
            selected = [item for item in rows if item["remove"].isChecked()]
            if not selected:
                QMessageBox.information(dialog, "Remove Models", "Select at least one installed model to remove.")
                return
            labels = "\n".join(f"• {item['label']}" for item in selected)
            answer = QMessageBox.question(
                dialog, "Remove Models",
                f"Remove these model(s)? This cannot be undone.\n\n{labels}",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if answer != QMessageBox.StandardButton.Yes:
                return
            for item in selected:
                try:
                    if item["path"].exists():
                        shutil.rmtree(item["path"])
                    item["remove"].setChecked(False)
                    self.log_activity(f"[MODELS] Removed {item['label']}", mark_dirty=False)
                except Exception as exc:
                    self.log_activity(f"[MODELS] Could not remove {item['label']}: {exc}", mark_dirty=False)
                    QMessageBox.warning(dialog, "Remove Model", f"Could not remove {item['label']}:\n\n{exc}")
            self.refresh_whisper_model_chooser()
            self.refresh_translation_model_chooser()
            refresh_rows()

        remove_btn.clicked.connect(remove_selected)
        dialog.refresh_models = refresh_rows
        refresh_rows()
        dialog.exec()

    def open_translation_model_manager(self):
        # Compatibility alias: translation model management is now consolidated.
        self.open_model_cleanup_dialog()

    def install_whisper_model_for_manager(self, model_name, dialog):
        if getattr(self, "_model_install_thread", None) is not None:
            return

        self._model_install_dialog = dialog
        self._model_install_model = model_name
        self._model_install_kind = "whisper"
        self._model_install_error = None

        # Show main window progress indicator
        self.set_processing_stage("Model Download", f"Whisper {model_name}")
        self.progress.setValue(10)
        self.progress.show()

        self.log_activity(f"[MODELS] Starting download/install for Whisper '{model_name}'...")

        self._model_install_qthread = QThread(self)
        self._model_install_worker = WhisperModelInstallWorker(model_name)
        self._model_install_worker.moveToThread(self._model_install_qthread)
        self._model_install_qthread.started.connect(self._model_install_worker.run)
        self._model_install_worker.finished.connect(self._model_install_finished)
        self._model_install_worker.finished.connect(self._model_install_qthread.quit)
        self._model_install_qthread.finished.connect(self._model_install_worker.deleteLater)
        self._model_install_qthread.finished.connect(self._model_install_thread_finished)
        self._model_install_thread = self._model_install_qthread
        self._model_install_qthread.start()
        dialog.refresh_models()

    def _install_whisper_model_background(self, model_name):
        # Retained as a compatibility method for callers; the actual work now
        # runs in WhisperModelInstallWorker on a QThread.
        error = None
        try:
            WhisperModel(model_name, device="cpu", compute_type="int8")
        except Exception as exc:
            error = str(exc)
        return error

    def _model_install_finished(self, error):
        self._model_install_error = error

    def _model_install_thread_finished(self):
        dialog = getattr(self, "_model_install_dialog", None)
        model_name = getattr(self, "_model_install_model", "")
        error = getattr(self, "_model_install_error", None)
        thread = getattr(self, "_model_install_thread", None)
        if thread is not None:
            thread.deleteLater()
        self._model_install_thread = None
        self._model_install_qthread = None
        self._model_install_worker = None

        self.progress.setValue(100)
        self.progress.hide()
        self.set_processing_stage(None)
        self._model_install_dialog = None
        self._model_install_model = None
        self._model_install_kind = None

        if error:
            self.log_activity(f"[MODELS] {model_name} installation failed: {error}", mark_dirty=False)
            if dialog is not None:
                QMessageBox.critical(dialog, "Model Installation Error", f"Could not install {model_name}:\n\n{error}")
        else:
            self.log_activity(f"[MODELS] {model_name} installed and verified.", mark_dirty=False)
            self.refresh_whisper_model_chooser()
            if dialog is not None:
                QMessageBox.information(dialog, "Model Ready", f"Whisper '{model_name}' is installed and ready for offline use.")

        if dialog is not None:
            dialog.refresh_models()

    def _poll_model_install(self, dialog):
        # Compatibility no-op; model installation completion is signal-driven.
        return

    def install_translation_models_for_manager(self, from_code, to_code, variant, dialog):
        """Install the selected OPUS-MT direction with main window progress reporting safely."""
        if getattr(self, "_model_install_thread", None) is not None or self.translation_thread is not None:
            return

        # Parameter guards to catch any stray Qt boolean signals:
        if isinstance(from_code, bool):
            from_code = "en"
        if isinstance(to_code, bool):
            to_code = "es"

        from_code = str(from_code)
        to_code = str(to_code)
        variant = str(variant)

        self._model_install_dialog = dialog
        model_label = f"OPUS-MT-{variant} ({from_code.upper()} → {to_code.upper()})"
        self._model_install_model = model_label
        self._model_install_kind = "translation"

        # Show main window progress indicator
        self.set_processing_stage("Model Download", model_label)
        self.progress.setValue(0)
        self.progress.show()

        self.log_activity(f"[MODELS] Starting download/install for {model_label}...")

        self.translation_thread = QThread(self)
        self.translation_worker = TranslationWorker(
            [], from_code, to_code,
            install_if_missing=True,
            installation_only=True,
            model_variant=variant
        )

        self.translation_worker.moveToThread(self.translation_thread)

        self.translation_thread.started.connect(self.translation_worker.run)

        # Thread-safe GUI updates via explicit QueuedConnection slots
        def _safe_update_progress(pct, msg):
            self.progress.setValue(pct)
            self.set_processing_stage("Model Download", msg)

        self.translation_worker.progress.connect(_safe_update_progress, Qt.ConnectionType.QueuedConnection)

        self.translation_worker.finished.connect(
            lambda res, key: self._translation_manager_install_finished(from_code, to_code, variant, dialog),
            Qt.ConnectionType.QueuedConnection
        )
        self.translation_worker.error.connect(
            lambda msg: self._translation_manager_install_error(msg, dialog),
            Qt.ConnectionType.QueuedConnection
        )

        self.translation_worker.finished.connect(self.translation_thread.quit)
        self.translation_worker.error.connect(self.translation_thread.quit)
        self.translation_thread.finished.connect(self.translation_worker.deleteLater)
        self.translation_thread.finished.connect(self._translation_thread_finished)

        self.translation_thread.start()

        # Defer model manager UI refresh until next event loop tick
        QTimer.singleShot(0, dialog.refresh_models)

    def _translation_manager_install_finished(self, from_code, to_code, variant, dialog):
        self.progress.setValue(100)
        self.progress.hide()
        self.set_processing_stage(None)

        model_label = f"OPUS-MT-{variant} ({from_code.upper()} → {to_code.upper()})"
        self.log_activity(f"[MODELS] {model_label} installed and verified.", mark_dirty=False)
        self.refresh_translation_model_chooser()

        QMessageBox.information(dialog, "Model Ready", f"{model_label} is installed and ready for offline use.")

        # Post the dialog refresh back onto the main event loop
        if hasattr(dialog, "refresh_models"):
            QTimer.singleShot(0, dialog.refresh_models)

    def _translation_manager_install_error(self, message, dialog):
        self.progress.hide()
        self.set_processing_stage(None)

        self.log_activity(f"[MODELS] Translation model installation failed: {message}", mark_dirty=False)
        QMessageBox.critical(dialog, "Model Installation Error", f"Could not install translation model:\n\n{message}")

        if hasattr(dialog, "refresh_models"):
            QTimer.singleShot(0, dialog.refresh_models)
