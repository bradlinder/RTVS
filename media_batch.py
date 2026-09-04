"""Radio & TV Segmenter v1.1.1 — media batch responsibilities.

Methods intentionally retain the MainWindow-facing API so behavior remains
maintaining the established MainWindow-facing API while responsibilities are isolated.
"""

from prs_shared import *


class MediaBatchMixin:
    def probe_media_duration(self, path):
        """Probe duration locally so video timelines can be populated immediately."""
        try:
            result = subprocess.run(
                [ffprobe_path() or "ffprobe", "-v", "error", "-show_entries", "format=duration",
                 "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=15, check=True,
            )
            value = float(result.stdout.strip())
            return value if value > 0 else None
        except Exception:
            return None

    def stop_waveform_worker(self, timeout_ms=5000):
        """Stop the current waveform worker completely before replacing it or closing."""
        thread = getattr(self, "wf_thread", None)
        worker = getattr(self, "wf_worker", None)
        if thread is None:
            return True

        if thread.isRunning():
            if worker is not None:
                worker.cancel()
            thread.quit()
            if not thread.wait(timeout_ms):
                self.log_activity("[WARNING] Waveform worker did not stop within the normal shutdown window; leaving it tracked until Qt finishes cleanup.", mark_dirty=False)
                return False

        # Do not leave references to a QThread that has already finished.
        if not thread.isRunning():
            if hasattr(self, "timeline"):
                self.timeline.set_background_generation_active("waveform", False)
            self.wf_thread = None
            self.wf_worker = None
            return True
        return False

    def start_video_thumbnail_generation(self):
        if not self.current_media_is_video or not self.audio_file or self.duration <= 0:
            if hasattr(self, "timeline"): self.timeline.set_video_thumbnails([])
            return
        if not self.stop_video_thumbnail_worker():
            self.log_activity("[MEDIA] Thumbnail generation was not restarted because the previous worker is still stopping.", mark_dirty=False)
            return
        base=Path(tempfile.gettempdir()) / "radio_tv_story_segmenter_thumbnails"
        base.mkdir(parents=True, exist_ok=True)
        job=base / hashlib.sha1(str(self.audio_file).encode("utf-8")).hexdigest()[:16]
        if job.exists(): shutil.rmtree(job, ignore_errors=True)
        job.mkdir(parents=True, exist_ok=True)
        self.video_thumbnail_dir=job
        thread=QThread(self); worker=VideoThumbnailWorker(self.audio_file, self.duration, job)
        worker.moveToThread(thread); thread.started.connect(worker.run); worker.finished.connect(self._video_thumbnails_finished)
        worker.error.connect(lambda msg: self.log_activity(f"[MEDIA] Video thumbnail generation failed: {msg}", mark_dirty=False))
        worker.finished.connect(thread.quit); worker.error.connect(thread.quit); thread.finished.connect(worker.deleteLater); thread.finished.connect(thread.deleteLater)
        self.video_thumbnail_thread=thread; self.video_thumbnail_worker=worker
        if hasattr(self, "timeline"):
            self.timeline.set_background_generation_active("thumbnails", True)
        thread.start()

    def _video_thumbnails_finished(self, items):
        if hasattr(self, "timeline"):
            self.timeline.set_background_generation_active("thumbnails", False)
            self.timeline.set_video_thumbnails(items)
        self.video_thumbnail_worker=None
        self.video_thumbnail_thread=None

    def stop_video_thumbnail_worker(self):
        thread=self.video_thumbnail_thread; worker=self.video_thumbnail_worker
        if worker:
            try: worker.cancel()
            except Exception: pass
        if thread and thread.isRunning():
            thread.quit()
            if not thread.wait(5000):
                self.log_activity("[WARNING] Video thumbnail worker is still stopping; keeping it tracked to avoid a QThread lifetime crash.", mark_dirty=False)
                return False
        if hasattr(self, "timeline"):
            self.timeline.set_background_generation_active("thumbnails", False)
        self.video_thumbnail_thread=None; self.video_thumbnail_worker=None
        return True

    def load_waveform_async(self):
        if not self.audio_file:
            return

        # Never replace an active QThread. This is the critical lifetime rule
        # that prevents "QThread: Destroyed while thread is still running".
        if not self.stop_waveform_worker():
            self.log_activity("[ERROR] Could not safely stop the previous waveform worker; waveform generation was not restarted.")
            return

        thread = QThread(self)
        worker = WaveformWorker(self.audio_file)
        worker.moveToThread(thread)

        self.wf_thread = thread
        self.wf_worker = worker

        thread.started.connect(worker.run)
        worker.finished.connect(self._waveform_finished)
        worker.finished.connect(thread.quit, Qt.ConnectionType.DirectConnection)
        worker.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        thread.finished.connect(self._waveform_thread_finished)
        if hasattr(self, "timeline"):
            self.timeline.set_background_generation_active("waveform", True)
        thread.start()

    def _waveform_finished(self, peaks, cancelled=False):
        if hasattr(self, "timeline"):
            self.timeline.set_background_generation_active("waveform", False)
        if cancelled:
            self.log_activity("[WAVEFORM] Waveform generation canceled.")
            return
        self.timeline.set_waveform_peaks(peaks)
        if peaks:
            self.log_activity(f"[WAVEFORM] Waveform generation complete ({len(peaks):,} peaks).")
        else:
            self.log_activity("[ERROR] Waveform generation produced no audio data. The media may not contain a readable audio stream.")

    def _waveform_thread_finished(self):
        thread = self.sender()
        if thread is getattr(self, "wf_thread", None):
            self.wf_thread = None
            self.wf_worker = None

    def open_batch_processing_dialog(self):
        if self.batch_active:
            QMessageBox.information(self, "Batch Processing", "A batch job is already running.")
            return

        dialog = BatchProcessingDialog(self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return

        files = [dialog.files.item(i).text() for i in range(dialog.files.count())]
        if not files:
            QMessageBox.warning(self, "Batch Processing", "Add at least one file.")
            return

        output = dialog.output.text().strip()
        if not output:
            output = self.default_project_directory or ""
            if output:
                Path(output).mkdir(parents=True, exist_ok=True)

        if output:
            self._remember_directory(output)

        # Minimize user input: Auto-save active project before starting
        if self.project_dirty and self.audio_file:
            self.save_project(force=True)

        self.batch_active = True
        # Mute and stop media player during batch runs to prevent GPU/Audio engine contention
        if hasattr(self, "player") and self.player:
            self.player.stop()
            self.player.setSource(QUrl())
        self.batch_queue = files
        self.progress.show()
        self.cancel_button.show()
        
        scope = dialog.scope_combo.currentData()
        pipeline_mode = "custom" if dialog.pipeline_custom_radio.isChecked() else "full"
        save_project_only = dialog.save_project_only_check.isChecked()
        save_project = dialog.save_project_check.isChecked() or save_project_only

        do_transcribe = dialog.proc_transcribe.isChecked() if pipeline_mode == "custom" else True
        do_diarize = dialog.proc_diarize.isChecked() if pipeline_mode == "custom" else True
        do_stories = dialog.proc_stories.isChecked() if pipeline_mode == "custom" else True
        translate_pipeline = dialog.proc_translate.isChecked() if pipeline_mode == "custom" else dialog.translate_check.isChecked()

        self.batch_settings = {
            "output": output,
            "pipeline_mode": pipeline_mode,
            "save_project_only": save_project_only,
            "save_project": save_project,
            "do_transcribe": do_transcribe,
            "do_diarize": do_diarize,
            "do_stories": do_stories,
            "scope": scope,
            "skip_existing": dialog.skip_existing_check.isChecked() and not save_project_only,
            "full_txt": dialog.fmt_txt.isChecked() and scope in ("full", "both") and not save_project_only,
            "full_docx": dialog.fmt_docx.isChecked() and scope in ("full", "both") and not save_project_only,
            "full_srt": dialog.fmt_srt.isChecked() and scope in ("full", "both") and not save_project_only,
            "full_vtt": dialog.fmt_vtt.isChecked() and scope in ("full", "both") and not save_project_only,
            "story_txt": dialog.fmt_txt.isChecked() and scope in ("stories", "both") and not save_project_only,
            "story_docx": dialog.fmt_docx.isChecked() and scope in ("stories", "both") and not save_project_only,
            "story_srt": dialog.fmt_srt.isChecked() and scope in ("stories", "both") and not save_project_only,
            "story_vtt": dialog.fmt_vtt.isChecked() and scope in ("stories", "both") and not save_project_only,
            "include_speakers": dialog.include_speakers.isChecked(),
            "include_timestamps": dialog.include_times.isChecked(),
            "translate_es": translate_pipeline,
            "translate_stories": translate_pipeline and scope in ("stories", "both"),
            "doc_direction": dialog.doc_direction.currentData()
        }

        # Auto-route between media processing and document translation
        first_file = Path(files[0])
        if first_file.suffix.lower() in {".txt", ".docx", ".pdf", ".html", ".htm", ".md"}:
            self.batch_document_queue = list(files)
            self._batch_next_document()
        else:
            self._batch_next_media()

    def _batch_next_media(self):
        if not hasattr(self, "batch_queue") or not self.batch_queue:
            self.batch_active = False  # Reset active flag when queue is empty
            self.progress.hide()
            self.cancel_button.hide()
            self.set_processing_stage(None)
            self.log_activity("[BATCH] All media batch processing completed.")
            QMessageBox.information(self, "Batch Processing", "Batch processing completed successfully!")
            return

        # Fetch next media file
        current_file = self.batch_queue.pop(0)
        self.log_activity(f"[BATCH] Processing media file: {current_file}")

        try:
            output_dir = Path(self.batch_settings.get("output", ""))
            base_name = safe_filename(Path(current_file).stem)
            skip_existing = self.batch_settings.get("skip_existing", False)

            # Build expected output extension list based on requested formats
            required_exts = []
            if self.batch_settings.get("full_txt") or self.batch_settings.get("story_txt"):
                required_exts.append(".txt")
            if self.batch_settings.get("full_docx") or self.batch_settings.get("story_docx"):
                required_exts.append(".docx")
            if self.batch_settings.get("full_srt") or self.batch_settings.get("story_srt"):
                required_exts.append(".srt")
            if self.batch_settings.get("full_vtt") or self.batch_settings.get("story_vtt"):
                required_exts.append(".vtt")

            # Check if all target output files already exist on disk
            all_exist = False
            if skip_existing and output_dir.exists() and required_exts:
                all_exist = all((output_dir / f"{base_name}{ext}").exists() for ext in required_exts)

            # Silence auto-save prompts before switching contexts
            if self.project_dirty and self.audio_file:
                self.save_project(force=True)

            # Load the media file
            if not self.load_media_file(current_file):
                self._batch_media_error(f"Could not load file {current_file}")
                return

            # If skipping re-processing, trigger immediate export from existing data
            if all_exist:
                self.log_activity(f"[BATCH] Requested outputs exist for {base_name}. Skipping AI pipeline and generating exports directly.")
                self._batch_export_current()
                QTimer.singleShot(0, self._batch_next_media)
                return

            # Non-interactive automated pipeline setup for batch execution
            pipeline_stages = []
            pipeline_mode = self.batch_settings.get("pipeline_mode", "full")

            if pipeline_mode == "full":
                if not self.transcript or not self.processing_status.get("transcription"):
                    pipeline_stages.append("transcription")

                if self.batch_settings.get("include_speakers") and (not self.diarization or not self.processing_status.get("diarization")):
                    pipeline_stages.append("diarization")

                if self.batch_settings.get("scope") in ("stories", "both") and not self.stories:
                    pipeline_stages.append("stories")

                if self.batch_settings.get("translate_es"):
                    pipeline_stages.append("translation")
            else:
                if self.batch_settings.get("do_transcribe", True) and (not self.transcript or not self.processing_status.get("transcription")):
                    pipeline_stages.append("transcription")

                if self.batch_settings.get("do_diarize", True) and (not self.diarization or not self.processing_status.get("diarization")):
                    pipeline_stages.append("diarization")

                if self.batch_settings.get("do_stories", True) and not self.stories:
                    pipeline_stages.append("stories")

                if self.batch_settings.get("translate_es"):
                    pipeline_stages.append("translation")

            if pipeline_stages:
                self.pipeline_queue = pipeline_stages
                self.pipeline_active = True
                QTimer.singleShot(0, self._run_next_selected_processing)
            else:
                self._batch_export_current()
                QTimer.singleShot(0, self._batch_next_media)

        except Exception as e:
            self._batch_media_error(f"Failed to process {current_file}: {str(e)}")

    def _batch_next_document(self):
        if not hasattr(self, "batch_document_queue") or not self.batch_document_queue:
            self.batch_active = False
            self.progress.hide()
            self.cancel_button.hide()
            self.set_processing_stage(None)
            self.log_activity("[BATCH] All document batch processing completed.")
            QMessageBox.information(self, "Batch Processing", "Batch document translation completed successfully!")
            return

        current_doc = self.batch_document_queue.pop(0)
        self.log_activity(f"[BATCH] Translating document: {current_doc}")
        try:
            if hasattr(self, "translate_document_file"):
                self.translate_document_file(current_doc)
            else:
                self.log_activity(f"[BATCH] Processed {current_doc}")
                QTimer.singleShot(50, self._batch_next_document)
        except Exception as exc:
            self._batch_document_error(f"Error translating {current_doc}: {exc}")

    def _batch_document_error(self, msg):
        """Handles document batch translation errors safely."""
        self.log_activity(f"[BATCH] Document translation failed: {msg}")
        self.progress.hide()
        self.cancel_button.hide()
        self.batch_document_state = None

        # Reset active status so dialog reopening is not blocked
        self.batch_active = False 
        QTimer.singleShot(0, self._batch_next_document)

    def _load_user_preferences(self):
        self.language = str(self.settings_store.value("language", "en") or "en")
        self.show_speaker_labels = str(self.settings_store.value("show_speaker_labels", "true")).lower() in {"1", "true", "yes"}
        self.show_timestamps = str(self.settings_store.value("show_timestamps", "true")).lower() in {"1", "true", "yes"}
        self.default_project_directory = str(self.settings_store.value("default_project_directory", "") or "")
        self.startup_project_mode = str(self.settings_store.value("startup_project_mode", "last") or "last")
        if self.startup_project_mode not in {"new", "last", "prompt"}:
            self.startup_project_mode = "last"
        self.timeline_show_waveform = str(self.settings_store.value("timeline_show_waveform", "true")).lower() in {"1", "true", "yes"}
        self.timeline_show_thumbnails = str(self.settings_store.value("timeline_show_thumbnails", "true")).lower() in {"1", "true", "yes"}

        self.timeline_thumbnail_position = str(self.settings_store.value("timeline_thumbnail_position", "above")).lower()
        if self.timeline_thumbnail_position not in ("above", "below"):
            self.timeline_thumbnail_position = "above"

        self.transcript_selection_mode = str(self.settings_store.value("transcript_selection_mode", "replace") or "replace")
        if self.transcript_selection_mode not in ("replace", "keep"):
            self.transcript_selection_mode = "replace"
        if hasattr(self, "transcript_view") and hasattr(self.transcript_view, "set_selection_mode"):
            self.transcript_view.set_selection_mode(self.transcript_selection_mode)

        if hasattr(self, "timeline"):
            self.timeline.set_timeline_views(self.timeline_show_waveform, self.timeline_show_thumbnails)
            self.timeline.set_thumbnail_position(self.timeline_thumbnail_position)
        saved_theme = str(self.settings_store.value("theme_mode", "dark") or "dark")
        if saved_theme not in ("dark", "light", "high_contrast"):
            saved_theme = "dark"
        self.set_theme(saved_theme)
        self.apply_glossary_to_whisper_context()
        if self.language == "es":
            self.set_language("es", persist=False)

    def set_thumbnail_position(self, position):
        self.timeline_thumbnail_position = position
        self.settings_store.setValue("timeline_thumbnail_position", position)
        if hasattr(self, "timeline"):
            self.timeline.set_thumbnail_position(position)

    def _remember_saved_project(self, path):
        """Remember only projects that have actually been saved.

        Opening a project or media file must not change the startup target.
        """
        if not path:
            return
        try:
            p = Path(path).resolve()
            if p.suffix.lower() == ".json":
                resolved = str(p)
                self.settings_store.setValue("last_saved_project_path", resolved)
                raw = self.settings_store.value("recent_projects", [])
                if isinstance(raw, str):
                    try:
                        raw = json.loads(raw)
                    except Exception:
                        raw = [raw] if raw else []
                recent = [resolved]
                for item in raw if isinstance(raw, list) else []:
                    item = str(item)
                    if item and item != resolved:
                        recent.append(item)
                self.settings_store.setValue("recent_projects", json.dumps(recent[:10]))
                # Flush now rather than relying on QSettings' own timing --
                # this is the exact write "restore last project" depends on,
                # so it needs to reliably survive an app close shortly after.
                self.settings_store.sync()
                if hasattr(self, "_refresh_recent_projects_menu"):
                    self._refresh_recent_projects_menu()
        except Exception:
            pass

    def _dialog_directory(self, fallback=None):
        if self.default_project_directory:
            return self.default_project_directory
        return str(Path(fallback).parent) if fallback else ""    

    def _sync_startup_project_actions(self):
        """Synchronize the Project Settings startup radio/check actions."""
        mode = getattr(self, "startup_project_mode", "last")
        if hasattr(self, "startup_new_action"):
            self.startup_new_action.setChecked(mode == "new")
            self.startup_last_action.setChecked(mode == "last")
            self.startup_prompt_action.setChecked(mode == "prompt")

    def set_startup_project_mode(self, mode):
        """Set the startup project policy."""
        if mode not in {"new", "last", "prompt"}:
            return
        self.startup_project_mode = mode
        self.settings_store.setValue("startup_project_mode", mode)
        self._sync_startup_project_actions()

    def restore_last_opened(self):
        """Apply startup policy and offer recovery from a newer autosave snapshot."""
        mode = getattr(self, "startup_project_mode", "last")
        raw_saved = str(self.settings_store.value("last_saved_project_path", "") or "")
        if raw_saved:
            saved_path = Path(raw_saved)
            autosave = saved_path.with_suffix(saved_path.suffix + ".autosave")
            try:
                if autosave.exists() and saved_path.exists() and autosave.stat().st_mtime > saved_path.stat().st_mtime:
                    answer = QMessageBox.question(self, "Recover Auto-Saved Project", f"A newer recovery snapshot was found for {saved_path.name}. Would you like to recover it?", QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
                    if answer == QMessageBox.StandardButton.Yes:
                        if self.load_project_file(autosave, prompt=False, preserve_media=False):
                            self.project_file = saved_path
                            self.project_dirty = True
                            # The autosave is a recovery artifact, not a recent project.
                            raw_recent = self.settings_store.value("recent_projects", [])
                            try:
                                recent = json.loads(raw_recent) if isinstance(raw_recent, str) else list(raw_recent or [])
                            except Exception:
                                recent = []
                            self.settings_store.setValue("recent_projects", json.dumps([str(x) for x in recent if str(x) != str(autosave.resolve())][:10]))
                            if hasattr(self, "_refresh_recent_projects_menu"):
                                self._refresh_recent_projects_menu()
                            self.log_activity(f"[AUTOSAVE] Recovered newer snapshot for {saved_path.name}.", mark_dirty=False)
                            return
            except Exception as exc:
                self.log_activity(f"[AUTOSAVE] Recovery check failed: {exc}", mark_dirty=False)

        if mode == "new":
            self.log_activity("[STARTUP] Starting with a new, unsaved project by preference.", mark_dirty=False)
            return

        raw = str(self.settings_store.value("last_saved_project_path", "") or "")
        path = Path(raw) if raw else None
        valid_last = bool(path and path.exists() and path.is_file() and path.suffix.lower() == ".json")

        # If last_saved_project_path is missing or stale, fall back to the most recent entry from recent_projects
        if not valid_last:
            raw_recent = self.settings_store.value("recent_projects", [])
            if isinstance(raw_recent, str):
                try:
                    raw_recent = json.loads(raw_recent)
                except Exception:
                    raw_recent = []
            if isinstance(raw_recent, list):
                for candidate in raw_recent:
                    cand_path = Path(str(candidate))
                    if cand_path.exists() and cand_path.is_file() and cand_path.suffix.lower() == ".json":
                        path = cand_path
                        valid_last = True
                        self.settings_store.setValue("last_saved_project_path", str(path))
                        self.settings_store.sync()
                        break

        if mode == "prompt":
            if not valid_last:
                self.log_activity("[STARTUP] No previous project is available; starting with a new, unsaved project.", mark_dirty=False)
                return

            box = QMessageBox(self)
            box.setWindowTitle("Project Startup")
            box.setText("What would you like to open?")
            box.setInformativeText(
                "Choose whether to start with a new, unsaved project or reopen "
                "the last project you saved."
            )
            open_last_btn = box.addButton("Open Last Saved Project", QMessageBox.ButtonRole.AcceptRole)
            box.addButton("New Unsaved Project", QMessageBox.ButtonRole.DestructiveRole)
            box.exec()
            if box.clickedButton() is not open_last_btn:
                self.log_activity("[STARTUP] Starting with a new, unsaved project by user choice.", mark_dirty=False)
                return

        if not valid_last:
            self.log_activity("[STARTUP] Last project is unavailable; starting with a new, unsaved project.", mark_dirty=False)
            return

        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            media = self.resolve_project_media(path, data.get("audio_file"))
            if not data.get("audio_file") or media is not None:
                self.load_project_file(path, prompt=False, preserve_media=False)
                self.log_activity(f"[STARTUP] Restored last project: {path.name}", mark_dirty=False)
            else:
                self.log_activity(
                    "[STARTUP] Last project is available but its media file is missing; starting blank.",
                    mark_dirty=False,
                )
        except Exception as exc:
            self.log_activity(f"[STARTUP] Could not restore last project: {exc}", mark_dirty=False)

    def toggle_speaker_labels(self, checked):
        self.show_speaker_labels = bool(checked)
        self.settings_store.setValue("show_speaker_labels", self.show_speaker_labels)
        self.render_transcript()

    def toggle_timestamps(self, checked):
        self.show_timestamps = bool(checked)
        self.settings_store.setValue("show_timestamps", self.show_timestamps)
        self.render_transcript()

    def toggle_waveform_view(self, checked):
        self.timeline_show_waveform = bool(checked)
        self.settings_store.setValue("timeline_show_waveform", self.timeline_show_waveform)
        if hasattr(self, "timeline"):
            self.timeline.set_timeline_views(self.timeline_show_waveform, self.timeline_show_thumbnails)

    def toggle_thumbnail_view(self, checked):
        self.timeline_show_thumbnails = bool(checked)
        self.settings_store.setValue("timeline_show_thumbnails", self.timeline_show_thumbnails)
        if hasattr(self, "timeline"):
            self.timeline.set_timeline_views(self.timeline_show_waveform, self.timeline_show_thumbnails)

    def choose_default_project_directory(self):
        start = self.default_project_directory or str(Path.home())
        directory = QFileDialog.getExistingDirectory(
            self,
            "Choose Default Project Directory",
            start
        )
        if directory:
            self.default_project_directory = str(Path(directory).resolve())
            self.settings_store.setValue(
                "default_project_directory",
                self.default_project_directory
            )
            self.statusBar().showMessage(
                f"Default project directory: {self.default_project_directory}"
            )

    def open_document_path(self, path):
        path = Path(path).resolve()
        if not path.exists(): return False
        if not self.batch_active and (self.audio_file or self.transcript or self.project_file):
            if not self.prepare_for_new_media(): return False
        try:
            text = read_document_text(path)
        except Exception as exc:
            if not self.batch_active:
                QMessageBox.critical(self, "Open Document Error", f"Could not read document:\n\n{exc}")
            return False
        lines = text.splitlines()
        segments=[]; cursor=0.0
        for line in lines:
            value=line.strip()
            if value:
                segments.append({"text":value,"start":cursor,"end":cursor})
                cursor += 0.001
        # Clear active media player source and waveform peaks when switching to document-only mode
        if hasattr(self, "player") and self.player:
            self.player.stop()
            self.player.setSource(QUrl())
        if hasattr(self, "timeline"):
            self.timeline.set_waveform_peaks([])
            self.timeline.set_audio_filename(None)

        self.audio_file=None; self.project_file=None; self.duration=0.0
        self.transcript={"text":text,"segments":segments,"language":"en"}
        self.diarization=None; self.stories=[]; self.translations={}; self.translation_display_mode="en"
        self.project_dirty=True
        self.update_translation_language_selector(); self.render_transcript(); self.update_processing_menu_status(); self.set_tools_actions_enabled(True)
        self.statusBar().showMessage(f"Document loaded: {path.name}")
        return True

    def open_glossary_dialog(self):
        dialog=QDialog(self); dialog.setWindowTitle("Custom Vocabulary / Glossary"); dialog.resize(520,420)
        layout=QVBoxLayout(dialog); layout.addWidget(QLabel("Words and proper nouns are retained as preferred spellings for future transcription."))
        listw=QListWidget(); listw.addItems(sorted(self.glossary, key=str.casefold)); layout.addWidget(listw)
        row=QHBoxLayout(); inp=QLineEdit(); inp.setPlaceholderText("Add a word or preferred spelling…")
        add=QPushButton("Add"); remove=QPushButton("Remove Selected"); row.addWidget(inp,1); row.addWidget(add); row.addWidget(remove); layout.addLayout(row)
        buttons=QHBoxLayout(); close=QPushButton("Close"); buttons.addStretch(); buttons.addWidget(close); layout.addLayout(buttons)
        def add_word():
            word=inp.text().strip()
            if word and word.casefold() not in {x.casefold() for x in self.glossary}:
                self.glossary.append(word); listw.addItem(word); inp.clear(); self._save_glossary(); self.apply_glossary_to_whisper_context()
        def remove_word():
            for item in listw.selectedItems():
                self.glossary=[x for x in self.glossary if x != item.text()]; listw.takeItem(listw.row(item))
            self._save_glossary(); self.apply_glossary_to_whisper_context()
        add.clicked.connect(add_word); inp.returnPressed.connect(add_word); remove.clicked.connect(remove_word); close.clicked.connect(dialog.accept)
        dialog.exec()

    def _save_glossary(self):
        self.settings_store.setValue("glossary", json.dumps(self.glossary, ensure_ascii=False))

    def add_to_glossary(self, text):
        text=str(text or "").strip().strip(".,!?;:()[]{}\"'“”‘’")
        if not text: return
        if text.casefold() not in {x.casefold() for x in self.glossary}:
            self.glossary.append(text); self._save_glossary(); self.apply_glossary_to_whisper_context()
            self.statusBar().showMessage(f"Added to glossary: {text}")

    def apply_glossary_to_whisper_context(self):
        # faster-whisper does not accept a persistent custom dictionary directly;
        # retain the vocabulary here so transcription can use it as an initial prompt.
        self.whisper_initial_prompt = ", ".join(self.glossary[:200])

    def add_custom_speaker_to_glossary(self, name):
        if name and name.strip(): self.add_to_glossary(name.strip())

    def set_language(self, language, persist=True):
        self.language = "es" if language == "es" else "en"
        if persist: self.settings_store.setValue("language", self.language)
        self._apply_localization()

    def _apply_localization(self):
        mapping={
            "&File":"&Archivo","&Edit":"&Editar","&View":"&Ver","&Tools":"&Herramientas","&Settings":"&Configuración","&Help":"&Ayuda",
            "&New Project":"&Nuevo proyecto","&Load Project...":"&Cargar proyecto...","&Save Project":"&Guardar proyecto","Save &As...":"Guardar &como...","&Close Project":"&Cerrar proyecto",
            "&Open Media...":"&Abrir medio...","Open Document...":"Abrir documento...","&Export...":"&Exportar...","E&xit":"&Salir","&Undo":"&Deshacer","&Redo":"&Rehacer",
            "Find and Replace...":"Buscar y reemplazar...","Video Preview":"Vista previa de video","Timeline":"Línea de tiempo","Transcript":"Transcripción","Stories":"Historias","Activity Log":"Registro de actividad",
            "&Transcribe":"&Transcribir","&Detect Speakers":"&Detectar hablantes","&Detect Stories":"&Detectar historias","&Translate Transcript...":"&Traducir transcripción...","Manage Models...":"Administrar modelos...",
            "Run Processing…":"Ejecutar procesamiento…","Custom Vocabulary / Glossary...":"Vocabulario personalizado / glosario...","Batch Processing...":"Procesamiento por lotes...",
            "Speaker Labels":"Etiquetas de hablantes","Timestamps":"Marcas de tiempo","Language":"Idioma","English":"Inglés","Spanish":"Español",
            "Search:":"Buscar:","View:":"Vista:","Translate…":"Traducir…","Edit Transcript":"Editar transcripción","Export Transcript":"Exportar transcripción",
            "Start:":"Inicio:","End:":"Fin:","Title:":"Título:","Update Selected Story":"Actualizar historia seleccionada","Delete Selected Story":"Eliminar historia seleccionada",
            "Cancel Process":"Cancelar proceso","Export Activity Log":"Exportar registro de actividad","Clear Log":"Borrar registro","Speaker Sensitivity":"Sensibilidad de hablantes",
        }
        reverse={v:k for k,v in mapping.items()}
        active = mapping if self.language == "es" else reverse
        for action in self.findChildren(QAction):
            txt=action.text()
            if txt in active: action.setText(active[txt])
        for w in self.findChildren(QLabel):
            if w.text() in active: w.setText(active[w.text()])
        for w in self.findChildren(QPushButton):
            if w.text() in active: w.setText(active[w.text()])
        for w in self.findChildren(QGroupBox):
            if w.title() in active: w.setTitle(active[w.title()])
        if hasattr(self,"transcript_search_input"):
            self.transcript_search_input.setPlaceholderText("Buscar en la transcripción..." if self.language=="es" else "Find in transcript...")

    def open_document(self):
        filters = (
            "Supported Documents (*.txt *.docx *.pdf *.html *.htm *.md);;"
            "Text Files (*.txt *.md);;"
            "Word Documents (*.docx);;"
            "PDF Files (*.pdf);;"
            "HTML Files (*.html *.htm);;"
            "All Files (*)"
        )
        filename, _ = QFileDialog.getOpenFileName(self, "Open Document", self._dialog_directory(), filters)
        if not filename:
            return

        path = Path(filename).resolve()

        if self.audio_file or self.transcript or self.project_file:
            if not self.prepare_for_new_media():
                return

        try:
            text = read_document_text(path)
        except Exception as exc:
            self.log_activity(f"[ERROR] Failed to open document '{path.name}': {exc}")
            QMessageBox.critical(self, "Open Document Error", f"Could not read document:\n\n{exc}")
            return

        lines = text.splitlines()
        segments = []
        cursor = 0.0

        for line in lines:
            value = line.strip()
            if value:
                segments.append({"text": value, "start": cursor, "end": cursor})
                cursor += 0.001

        self.audio_file = None
        self.project_file = None
        self.duration = 0.0
        self.transcript = {"text": text, "segments": segments, "language": "en"}
        self.diarization = None
        self.stories = []
        self.translations = {}
        self.translation_display_mode = "en"
        self.project_dirty = True

        self.update_translation_language_selector()
        self.render_transcript()
        self.update_processing_menu_status()
        self.set_tools_actions_enabled(True)
        self.statusBar().showMessage(f"Document loaded: {path.name}")
        self.log_activity(f"[FILE] Imported document: {path}")

    def export_text_file(self):
        if not self.transcript: QMessageBox.warning(self,"No Text","There is no transcript/text to export."); return
        default=Path(self.project_file.stem if self.project_file else (self.audio_file.stem if self.audio_file else "transcript")).with_suffix('.txt').name
        filename,_=QFileDialog.getSaveFileName(self,"Export Text",str(Path(self._dialog_directory(default)).joinpath(default)),"Text Files (*.txt);;All Files (*)")
        if not filename: return
        path=Path(filename)
        if path.suffix.lower()!='.txt': path=path.with_suffix('.txt')
        text=self.story_text(self.transcript.get('segments',[])) if self.transcript.get('segments') else self.transcript.get('text','')
        path.write_text(text,encoding='utf-8'); self.log_activity(f"[EXPORT] Exported text to {path.name}"); QMessageBox.information(self,"Export Complete",f"Text exported to:\n{path}")

    def open_media(self):
        filename, _ = QFileDialog.getOpenFileName(
            self,
            "Open Media",
            self._dialog_directory(),
            "Media Files (*.*);;All Files (*)",
        )
        if filename:
            self.load_media_file(filename, source="file dialog")

    def prepare_for_new_media(self):
        """
        Checks for unsaved changes before loading new media.
        Bypasses interactive prompt during batch processing by auto-saving.
        """
        if self.project_dirty:
            # If running a batch process, auto-save instead of asking via dialog
            if getattr(self, "batch_active", False):
                self.save_project(force=True)
                return True

            save_answer = QMessageBox.question(
                self,
                "Save Project?",
                "The current project has unsaved changes. Would you like to save it before closing?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No | QMessageBox.StandardButton.Cancel,
                QMessageBox.StandardButton.Yes
            )
            if save_answer == QMessageBox.StandardButton.Cancel:
                return False
            if save_answer == QMessageBox.StandardButton.Yes:
                self.save_project(force=True)

        return True

    def _batch_media_error(self, message: str):
        if hasattr(self, "log_activity"):
            self.log_activity(f"[BATCH ERROR] {message}")
        self.batch_active = False  # Reset active flag on batch failure
        self.progress.hide()
        self.cancel_button.hide()
        self.set_processing_stage(None)
        self.set_tools_actions_enabled(True)

    def _batch_save_project_file(self):
        """Saves project .json to dedicated directory structure during batch processing."""
        if not self.audio_file:
            return

        base_dir = self.batch_settings.get("output") if hasattr(self, "batch_settings") else ""
        if not base_dir or not os.path.exists(base_dir):
            base_dir = self.get_default_save_directory()

        base_name = safe_filename(Path(self.audio_file).stem)

        try:
            project_dir, trans_dir, media_dir, _ = self.prepare_export_directories(
                base_dir, default_name=base_name, prompt_user=False
            )
            target_path = str(project_dir / f"{base_name}.json")
            self._write_project_file(target_path)
            self.log_activity(f"[BATCH] Auto-saved project file to {target_path}")
        except Exception as e:
            self.log_activity(f"[BATCH ERROR] Failed to save project file for {self.audio_file}: {e}")

    def _batch_export_current(self):
        """Handles automatic export or project saving during batch processing."""
        if not getattr(self, "batch_active", False) or not hasattr(self, "batch_settings"):
            return

        # 1. Save the project file (.json)
        if self.batch_settings.get("save_project", True) or self.batch_settings.get("save_project_only", False):
            self._batch_save_project_file()

        # 2. If 'Save projects only' is checked, skip generating .txt, .docx, .srt, and media files
        if self.batch_settings.get("save_project_only", False):
            base_name = safe_filename(Path(self.audio_file).stem if self.audio_file else "file")
            self.log_activity(
                f"[BATCH] Finished processing {base_name}. Project session saved (exports skipped: 'Save projects only' mode).",
                mark_dirty=False
            )
            return

        # 3. Otherwise, proceed with requested transcript, subtitle, and media exports
        base_dir = self.batch_settings.get("output") or self.get_default_save_directory()
        if not base_dir or not os.path.exists(base_dir):
            return

        base_name = safe_filename(Path(self.audio_file).stem if self.audio_file else "batch_output")
        project_dir, _, _, _ = self.prepare_export_directories(base_dir, default_name=base_name, prompt_user=False)

        formats = {
            "txt": self.batch_settings.get("full_txt", True) or self.batch_settings.get("story_txt", False),
            "docx": self.batch_settings.get("full_docx", True) or self.batch_settings.get("story_docx", False),
            "srt": self.batch_settings.get("full_srt", False) or self.batch_settings.get("story_srt", False),
            "vtt": self.batch_settings.get("full_vtt", False) or self.batch_settings.get("story_vtt", False),
            "media": False,
        }

        options = {
            "include_speakers": self.batch_settings.get("include_speakers", True),
            "include_timestamps": self.batch_settings.get("include_timestamps", False),
            "include_english": True,
            "include_spanish": self.batch_settings.get("translate_es", False),
        }

        scope = self.batch_settings.get("scope", "full")

        try:
            if scope in ("full", "both"):
                self.export_full_episode(
                    custom_formats=formats,
                    custom_base=base_name,
                    custom_options=options,
                    directory=str(project_dir),
                    show_completion=False
                )

            if scope in ("stories", "both") and self.stories:
                self.perform_stories_export(
                    target_stories=self.stories,
                    custom_formats=formats,
                    custom_base=base_name,
                    custom_options=options,
                    directory=str(project_dir),
                    show_completion=False
                )

            self.log_activity(f"[BATCH] Successfully exported files for {base_name} to {project_dir}")
        except Exception as e:
            self.log_activity(f"[BATCH ERROR] Export failed for {base_name}: {e}")

    def load_media_file(self, filename, source="media load", restore_adjacent_project=True):
        path = Path(filename).resolve()
        if not path.exists() or not path.is_file():
            QMessageBox.warning(self, "Open Media", "The selected media file could not be found.")
            return False

        try:
            # This triggers the save/discard/cancel workflow before opening new media[cite: 1]
            if not self.prepare_for_new_media():
                return False
            if not self.confirm_stop_processing_for_media_change():
                return False

            self.media_generation += 1
            self.story_job_token += 1
            self.stop_waveform_worker()

            # Immediately clear existing transcript and project state so stale text doesn't linger[cite: 1]
            self.transcript = None
            self.diarization = None
            self.stories = []
            self.translations = {}
            self.segment_speaker_overrides = {}
            self.speaker_names = {}
            if hasattr(self, "transcript_view"):
                self.transcript_view.clear()
            if hasattr(self, "story_list"):
                self.story_list.clear()

            self.audio_file = path

            probed_duration = None
            self.player.setSource(QUrl.fromLocalFile(str(path)))
            self.current_media_is_video = self.is_video_file(path)
            self.update_video_preview_state()
            if probed_duration is not None:
                self.duration = probed_duration
                self.timeline.set_duration(probed_duration)
                self.time_label.setText(f"{format_time(0)} / {format_time(self.duration)}")

            self.transcribe_action.setEnabled(True)
            self.diarize_action.setEnabled(True)
            self.auto_detect_action.setEnabled(True)
            self.transcribe_diarize_action.setEnabled(True)
            self.transcribe_diarize_detect_action.setEnabled(True)
            self.save_action.setEnabled(True)
            if hasattr(self, "quick_save_button"):
                self.quick_save_button.setEnabled(True)
            self.save_as_action.setEnabled(True)

            self.processing_status = {"transcription": False, "diarization": False, "stories": False}
            self.current_selected_story_indices = []
            self.refresh_story_list()

            self.timeline.set_audio_filename(path.name)
            self.timeline.set_waveform_peaks([])
            self.timeline.set_position(0)
            self.timeline.set_zoom(1.0)
            self.timeline.scroll_offset = 0.0
            self.current_position = 0
            self.speaker_status.setText("Speaker detection has not been run.")

            self.log_activity(f"[FILE] Opened media: {path.name} ({source})")
            if self.current_media_is_video:
                self.log_activity("[MEDIA] Video detected; extracting its audio track for waveform generation.")
            self.log_activity("[WAVEFORM] Starting local waveform generation.")
            self.statusBar().showMessage(f"Loaded: {path.name}")
            self.load_waveform_async()
            self.start_video_thumbnail_generation()

            # Look for an associated project file; if found, load it; otherwise show a blank slate[cite: 1]
            if restore_adjacent_project:
                project = self.find_adjacent_project(path)
                if project:
                    if self.load_project_file(project, prompt=False, preserve_media=True):
                        self.log_activity(f"[PROJECT] Automatically restored project: {project.name}")
                        return True
                    self.log_activity(f"[WARNING] Adjacent project could not be restored: {project.name}")

            self.project_file = None
            self.project_dirty = False
            self.update_window_title()
            return True
        except Exception as exc:
            self.log_activity(f"[ERROR] Failed to open media '{path.name}': {exc}")
            QMessageBox.critical(self, "Open Media Error", str(exc))
            return False

    def open_audio(self):
        self.open_media()

    def handle_media_drop(self, filename):
        self.load_media_file(filename, source="timeline drag-and-drop")
