"""Radio & TV Segmenter v1.6 — playback preferences responsibilities.

Methods intentionally retain the MainWindow-facing API so behavior remains
maintaining the established MainWindow-facing API while responsibilities are isolated.
"""

from prs_shared import *


class PlaybackPreferencesMixin:
    def _install_diagnostic_logging(self):
        """Install startup-safe diagnostics that never depend on the GUI widgets."""
        self._original_showwarning = warnings.showwarning
        self._original_excepthook = sys.excepthook
        self.log_dir = get_app_data_dir() / "logs"
        try:
            self.log_dir.mkdir(parents=True, exist_ok=True)
        except Exception:
            self.log_dir = Path.cwd() / "logs"
            try:
                self.log_dir.mkdir(parents=True, exist_ok=True)
            except Exception:
                pass
        self.crash_log_file = self.log_dir / f"prs_{datetime.now().strftime('%Y-%m-%d')}.log"

        def write_diag(kind, message):
            try:
                operation = getattr(self, "current_operation", None) or "idle"
                with self.crash_log_file.open("a", encoding="utf-8") as f:
                    f.write(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] [{kind}] {INTERNAL_APP_ID}_v{PROJECT_VERSION} operation={operation}\n")
                    f.write(str(message))
                    f.write("\n\n")
            except Exception:
                pass

        self._write_diag = write_diag
        try:
            self._faulthandler_file = self.crash_log_file.open("a", encoding="utf-8")
            import faulthandler
            faulthandler.enable(file=self._faulthandler_file, all_threads=True)
            self._faulthandler_enabled = True
        except Exception as exc:
            self._faulthandler_file = None
            self._faulthandler_enabled = False
            write_diag("WARNING", f"Could not enable faulthandler: {exc}")
        write_diag("SYSTEM", "Diagnostic logging initialized.")
        try:
            write_diag("SYSTEM", f"Python={sys.version.split()[0]} | executable={sys.executable}")
            write_diag("SYSTEM", f"Model root={TranslationWorker.model_root()}")
            for _f, _t in (("en", "es"), ("es", "en")):
                write_diag("SYSTEM", f"Model {_f}->{_t} installed={TranslationWorker.model_is_installed(_f, _t)} path={TranslationWorker.model_dir(_f, _t)}")
        except Exception as exc:
            write_diag("WARNING", f"Startup model diagnostic failed: {exc}")

        def showwarning(message, category, filename, lineno, file=None, line=None):
            text = f"{category.__name__}: {message} ({Path(filename).name}:{lineno})"
            write_diag("WARNING", text)
            # Only mirror the warning into the GUI once the widget exists.
            if getattr(self, "activity_list", None) is not None:
                try:
                    self.log_activity(f"[WARNING] {text}", mark_dirty=False)
                except Exception:
                    pass
            try:
                return self._original_showwarning(message, category, filename, lineno, file, line)
            except Exception:
                return None

        def excepthook(exc_type, exc_value, exc_tb):
            text = "".join(traceback.format_exception(exc_type, exc_value, exc_tb))
            write_diag("CRASH/EXCEPTION", text)
            # Never let the crash reporter throw a second exception.
            if getattr(self, "activity_list", None) is not None:
                try:
                    self.log_activity(f"[ERROR] {exc_type.__name__}: {exc_value}", mark_dirty=False)
                except Exception:
                    pass
            try:
                self._original_excepthook(exc_type, exc_value, exc_tb)
            except Exception:
                pass

        def thread_excepthook(args):
            try:
                thread_name = getattr(args.thread, "name", "unknown")
                text = "".join(traceback.format_exception(args.exc_type, args.exc_value, args.exc_traceback))
                write_diag("THREAD-CRASH", f"thread={thread_name}\n{text}")
            except Exception:
                pass

        warnings.showwarning = showwarning
        sys.excepthook = excepthook
        threading.excepthook = thread_excepthook

    def export_activity_log(self):
        if self.activity_list.count() == 0:
            QMessageBox.information(self, "Activity Log", "There are no activity log entries to export.")
            return

        filename, _ = QFileDialog.getSaveFileName(
            self, "Export Activity Log", "activity_log.txt", "Text Files (*.txt);;All Files (*)"
        )
        if not filename:
            return
        try:
            lines = [self.activity_list.item(i).text() for i in range(self.activity_list.count())]
            Path(filename).write_text("\n".join(lines) + "\n", encoding="utf-8")
            self.log_activity(f"[EXPORT] Exported activity log to {Path(filename).name}")
            self.statusBar().showMessage(f"Activity log exported: {Path(filename).name}")
        except Exception as exc:
            self.log_activity(f"[ERROR] Activity log export failed: {exc}")
            QMessageBox.critical(self, "Activity Log Export Error", str(exc))

    def is_video_file(self, path):
        return Path(path).suffix.lower() in {
            ".mp4", ".mov", ".m4v", ".mkv", ".avi", ".webm", ".wmv",
            ".mpeg", ".mpg", ".m2v", ".mts", ".m2ts", ".ts", ".flv", ".3gp",
            ".ogv", ".vob", ".asf", ".rm", ".rmvb"
        }

    def update_video_preview_state(self):
        if self.video_preview_action is not None:
            self.video_preview_action.setEnabled(bool(self.current_media_is_video))
        if not self.current_media_is_video and self.video_preview_dialog is not None:
            self.video_preview_dialog.hide()

    def toggle_video_preview(self, checked=None):
        if not self.current_media_is_video:
            return
        if self.video_preview_dialog is None:
            self.video_preview_dialog = QDialog(self)
            self.video_preview_dialog.setWindowTitle("Video Preview — Radio & TV Story Segmenter")
            self.video_preview_dialog.resize(720, 405)
            layout = QVBoxLayout(self.video_preview_dialog)
            self.video_preview_widget = QVideoWidget(self.video_preview_dialog)
            layout.addWidget(self.video_preview_widget)
            self.player.setVideoOutput(self.video_preview_widget)
        visible = self.video_preview_dialog.isVisible()
        if checked is None:
            checked = not visible
        if checked:
            self.video_preview_dialog.show()
            self.video_preview_dialog.raise_()
            self.video_preview_dialog.activateWindow()
        else:
            self.video_preview_dialog.hide()
        if self.video_preview_action is not None:
            self.video_preview_action.setChecked(bool(checked))

    def handle_scrub_position(self, seconds):
        self.pending_scrub_target = seconds
        if not self.scrub_timer.isActive():
            self.scrub_timer.start(35)

    def execute_scrub_seek(self):
        if self.pending_scrub_target is not None:
            seconds = self.pending_scrub_target
            self.pending_scrub_target = None

            self.player.setPosition(int(seconds * 1000))
            self.timeline.ensure_position_visible(seconds)
            self.transcript_view.highlight_word_at_time(seconds, self.transcript)

    def log_activity(self, action_text, mark_dirty=True):
        if mark_dirty and not self.is_restoring_snapshot and not action_text.startswith("[SYSTEM]"):
            self.project_dirty = True
            self.update_window_title()
        now_str = datetime.now().strftime("%I:%M:%S %p")
        log_entry_str = f"[{now_str}] {action_text}"

        # Keep recovery snapshots bounded: each one contains full transcript
        # data and otherwise grows memory use with every log entry.
        snapshot_index = None
        # Lower memory footprint by capping history limit to 15 entries
        MAX_ACTIVITY_SNAPSHOTS = 15
        if len(self.activity_snapshots) >= MAX_ACTIVITY_SNAPSHOTS:
            self.activity_snapshots.pop(0)

        snapshot = {
            "log_text": log_entry_str,
            "stories": [Story.from_dict(s.to_dict()) for s in self.stories],
            "transcript": json.loads(json.dumps(self.transcript)) if self.transcript else None,
            "diarization": json.loads(json.dumps(self.diarization)) if self.diarization else None,
            "speaker_names": dict(self.speaker_names),
            "segment_speaker_overrides": dict(self.segment_speaker_overrides),
            "translations": json.loads(json.dumps(self.translations)),
            "translation_display_mode": self.translation_display_mode,
            "selected_indices": list(self.current_selected_story_indices),
        }
        self.activity_snapshots.append(snapshot)
        snapshot_index = len(self.activity_snapshots) - 1

        self.activity_list.blockSignals(True)
        item = QListWidgetItem(log_entry_str)
        item.setData(Qt.ItemDataRole.UserRole, snapshot_index)
        self.activity_list.addItem(item)
        self.activity_list.setCurrentItem(item)
        self.activity_list.scrollToItem(item)
        self.activity_list.blockSignals(False)

    def handle_activity_click(self, item):
        snap_idx = item.data(Qt.ItemDataRole.UserRole)
        if isinstance(snap_idx, int) and 0 <= snap_idx < len(self.activity_snapshots):
            self.restore_snapshot(snap_idx)

    def restore_snapshot(self, index):
        if not (0 <= index < len(self.activity_snapshots)):
            return

        self.is_restoring_snapshot = True
        snapshot = self.activity_snapshots[index]

        self.stories = [Story.from_dict(s.to_dict()) for s in snapshot["stories"]]
        self.transcript = json.loads(json.dumps(snapshot["transcript"])) if snapshot["transcript"] else None
        self.diarization = json.loads(json.dumps(snapshot["diarization"])) if snapshot["diarization"] else None
        self.speaker_names = dict(snapshot["speaker_names"])
        self.segment_speaker_overrides = dict(snapshot["segment_speaker_overrides"])
        self.translations = json.loads(json.dumps(snapshot.get("translations", {})))
        self.translation_display_mode = snapshot.get("translation_display_mode", "en")
        if hasattr(self, "transcript_language_selector"):
            idx = self.transcript_language_selector.findData(self.translation_display_mode)
            if idx >= 0:
                self.transcript_language_selector.setCurrentIndex(idx)

        if self.diarization:
            num = self.diarization.get("num_speakers", 0)
            self.speaker_status.setText(f"Speaker detection: {num} speaker(s) detected.")
        else:
            self.speaker_status.setText("Speaker detection has not been run.")

        self.render_transcript()
        self.render_translation_view()
        self.change_translation_display()
        self.refresh_story_list()
        self.apply_story_selection_indices(snapshot.get("selected_indices", []))
        self.is_restoring_snapshot = False

        self.statusBar().showMessage(f"Reverted project state to: {snapshot['log_text']}")

    def clear_activity_log(self):
        self.activity_snapshots.clear()
        self.activity_list.clear()
        self.log_activity("[SYSTEM] Activity log cleared.")

    def trigger_find_next(self):
        target = self.transcript_search_input.text().strip()
        if target:
            self.filter_transcript_search(target)
        elif self.find_dialog and self.find_dialog.isVisible():
            self.find_dialog.find_next()

    def _format_time_remaining(self, seconds: float) -> str:
        if seconds < 0 or seconds != seconds:
            return "calculating..."
        seconds = int(round(seconds))
        if seconds < 3:
            return "a few seconds"
        if seconds < 60:
            return f"~{seconds}s"
        mins = seconds // 60
        secs = seconds % 60
        if mins < 60:
            if secs > 0:
                return f"~{mins}m {secs}s"
            return f"~{mins}m"
        hours = mins // 60
        rem_mins = mins % 60
        return f"~{hours}h {rem_mins}m"

    def _get_stage_estimated_duration(self, stage_key: str) -> float:
        media_dur = getattr(self, "duration", 0) or 180.0
        if stage_key == "transcription":
            return max(8.0, media_dur * 0.12)
        elif stage_key == "diarization":
            return max(8.0, media_dur * 0.15)
        elif stage_key == "stories":
            return 4.0
        elif stage_key == "translation":
            num_segs = len(getattr(self, "transcript", {}).get("segments", [])) if getattr(self, "transcript", None) else 50
            return max(5.0, num_segs * 0.08)
        return 15.0

    def calculate_processing_eta(self, percent: float) -> tuple[float, float, str]:
        """Calculate ETA for active process and remaining stages in pipeline."""
        import time
        stage_key = getattr(self, "current_processing_stage_key", "transcription") or "transcription"
        stage_start = getattr(self, "stage_start_monotonic", None) or time.monotonic()
        elapsed = max(0.1, time.monotonic() - stage_start)

        stage_base_est = self._get_stage_estimated_duration(stage_key)
        
        if percent >= 2.0:
            stage_total_est = elapsed / (percent / 100.0)
            if percent < 10.0:
                weight = percent / 10.0
                stage_total_est = (1.0 - weight) * stage_base_est + weight * stage_total_est
            stage_remaining = max(0.0, stage_total_est - elapsed)
        else:
            stage_remaining = max(1.0, stage_base_est - elapsed)

        is_pipeline = getattr(self, "pipeline_active", False) and getattr(self, "pipeline_total_stages", 0) > 1
        
        if is_pipeline:
            future_rem = 0.0
            for future_stage in getattr(self, "pipeline_queue", []):
                future_rem += self._get_stage_estimated_duration(future_stage)
            total_remaining = stage_remaining + future_rem
            formatted = self._format_time_remaining(total_remaining)
            return stage_remaining, total_remaining, formatted
        else:
            formatted = self._format_time_remaining(stage_remaining)
            return stage_remaining, stage_remaining, formatted

    def set_processing_stage(self, stage, detail=""):
        import time
        if not hasattr(self, "processing_stage_label"):
            return
        if stage:
            stage_lower = stage.lower()
            if "transcri" in stage_lower:
                stage_key = "transcription"
            elif "speaker" in stage_lower or "diari" in stage_lower:
                stage_key = "diarization"
            elif "stor" in stage_lower:
                stage_key = "stories"
            elif "translat" in stage_lower:
                stage_key = "translation"
            else:
                stage_key = stage_lower

            self.current_processing_stage_key = stage_key
            self.current_processing_stage_name = stage
            self.current_processing_stage_detail = detail
            self.stage_start_monotonic = time.monotonic()
            self.last_reported_stage_percent = 0

            if not getattr(self, "pipeline_active", False):
                self.pipeline_total_stages = 1
                self.pipeline_current_stage_idx = 1
                self.pipeline_all_stages = [stage_key]
            else:
                total = getattr(self, "pipeline_total_stages", 1)
                queue_len = len(getattr(self, "pipeline_queue", []))
                self.pipeline_current_stage_idx = max(1, total - queue_len)

            self.update_processing_progress(0, "")
        else:
            self.current_processing_stage_key = None
            self.current_processing_stage_name = ""
            self.current_processing_stage_detail = ""
            self.stage_start_monotonic = None
            self.last_reported_stage_percent = 0
            self.processing_stage_label.clear()
            self.processing_stage_label.hide()
            if hasattr(self, "progress"):
                self.progress.hide()
                self.progress.setFormat("%p%")

    def update_processing_progress(self, percent: float, message: str = ""):
        percent = max(0, min(100, int(percent)))
        self.last_reported_stage_percent = percent
        
        stage_rem, total_rem, eta_str = self.calculate_processing_eta(percent)
        
        is_pipeline = getattr(self, "pipeline_active", False) and getattr(self, "pipeline_total_stages", 0) > 1
        stage_name = getattr(self, "current_processing_stage_name", "Processing")
        stage_detail = getattr(self, "current_processing_stage_detail", "")
        
        stage_desc = f"{stage_name}"
        if stage_detail:
            stage_desc += f" ({stage_detail})"
            
        if is_pipeline:
            current_idx = getattr(self, "pipeline_current_stage_idx", 1)
            total_stages = getattr(self, "pipeline_total_stages", 1)
            label_text = f"Stage {current_idx} of {total_stages}: {stage_desc} — {eta_str} remaining"
            prog_format = f"%p% (Stage {current_idx}/{total_stages}) — {eta_str} remaining"
        else:
            label_text = f"{stage_desc} — {eta_str} remaining"
            prog_format = f"%p% — {eta_str} remaining"
            
        if hasattr(self, "processing_stage_label"):
            self.processing_stage_label.setText(label_text)
            self.processing_stage_label.show()
        if hasattr(self, "progress"):
            self.progress.setValue(percent)
            self.progress.setFormat(prog_format)
            self.progress.show()
        if message and hasattr(self, "statusBar"):
            self.statusBar().showMessage(message)

    def update_processing_stage_summary(self):
        if not hasattr(self, "processing_stage_label"):
            return
        done = []
        if self.processing_status.get("transcription"):
            done.append("Transcription")
        if self.processing_status.get("diarization"):
            done.append("Speaker Detection")
        if self.processing_status.get("stories"):
            done.append("Story Detection")
        if done:
            self.processing_stage_label.setToolTip("Completed: " + ", ".join(done))
        else:
            self.processing_stage_label.setToolTip("")

    def _capture_project_state(self):
        """Capture all editable project data for the application undo stack.

        transcript/diarization/translations are deep-copied with
        copy.deepcopy() rather than a json.dumps/json.loads round-trip --
        same isolation guarantee for the plain dict/list/str/number data
        this app actually stores here, without paying for two full text
        serializations on every edit.
        """
        return {
            "stories": [s.to_dict() for s in self.stories],
            "transcript": copy.deepcopy(self.transcript) if self.transcript is not None else None,
            "diarization": copy.deepcopy(self.diarization) if self.diarization is not None else None,
            "speaker_names": dict(self.speaker_names),
            "segment_speaker_overrides": {str(k): v for k, v in self.segment_speaker_overrides.items()},
            "translations": copy.deepcopy(self.translations),
            "translation_display_mode": getattr(self, "translation_display_mode", "en"),
            "selected_indices": list(getattr(self, "current_selected_story_indices", [])),
        }

    def _restore_project_state_for_undo(self, state):
        """Restore a complete editable project state without creating another undo entry."""
        if getattr(self, "is_restoring_undo", False):
            return
        self.is_restoring_undo = True
        try:
            self.stories = [Story.from_dict(item) for item in state.get("stories", [])]
            self.transcript = copy.deepcopy(state.get("transcript")) if state.get("transcript") is not None else None
            self.diarization = copy.deepcopy(state.get("diarization")) if state.get("diarization") is not None else None
            self.speaker_names = {str(k): str(v) for k, v in state.get("speaker_names", {}).items()}
            self.segment_speaker_overrides = {int(k): str(v) for k, v in state.get("segment_speaker_overrides", {}).items()}
            self.translations = copy.deepcopy(state.get("translations", {}))
            self.translation_display_mode = state.get("translation_display_mode", "en")
            self.current_selected_story_indices = list(state.get("selected_indices", []))

            if hasattr(self, "transcript_language_selector"):
                idx = self.transcript_language_selector.findData(self.translation_display_mode)
                if idx >= 0:
                    self.transcript_language_selector.blockSignals(True)
                    self.transcript_language_selector.setCurrentIndex(idx)
                    self.transcript_language_selector.blockSignals(False)

            if self.transcript:
                self.render_transcript()
            else:
                self.transcript_view.clear()
                self.transcript_view.set_char_timestamp_map([])
            self.refresh_story_list()
            self.apply_story_selection_indices(self.current_selected_story_indices)
            self.project_dirty = True
            self.update_window_title()
            self.save_project()
        finally:
            self.is_restoring_undo = False

    def _commit_project_state_change(self, before_state, description="Modify Project"):
        """Push a complete project-state undo command after a mutation."""
        if getattr(self, "is_restoring_undo", False) or not before_state:
            return
        after_state = self._capture_project_state()
        # Plain dict/list equality is equivalent to the previous
        # sort_keys-JSON-string comparison for this data (order-independent
        # for dict keys, exact for lists/scalars) and skips two full-project
        # text serializations on every single edit.
        if before_state == after_state:
            return
        self.undo_stack.push(ProjectStateCommand(self, before_state, after_state, description))

    def flush_pending_transcript_undo(self):
        """Commit a pending grouped text edit before another project action or Ctrl+Z."""
        timer = getattr(self, "_transcript_undo_timer", None)
        if timer is not None and timer.isActive():
            timer.stop()
        if getattr(self, "_pending_transcript_edit_before", None) is not None:
            before = self._pending_transcript_edit_before
            self._pending_transcript_edit_before = None
            self._commit_project_state_change(before, "Edit Transcript")

    def mark_project_dirty(self, reason=None):
        """Mark the current project as needing a save and refresh the UI state."""
        if self.is_restoring_snapshot:
            return
        self.project_dirty = True
        self.update_window_title()
        if reason:
            self.log_activity(f"[PROJECT] {reason}", mark_dirty=False)

    def update_window_title(self):
        proj_name = self.project_file.name if self.project_file else "Unsaved"
        dirty_marker = " *" if self.project_dirty else ""
        self.setWindowTitle(f"{APP_DISPLAY_NAME} v{PROJECT_VERSION} — Project: {proj_name}{dirty_marker}")
        if hasattr(self, "save_state_label"):
            if self.project_dirty:
                self.save_state_label.setText("● Unsaved changes")
            elif self.project_file:
                self.save_state_label.setText("✓ Saved")
            else:
                self.save_state_label.setText("Not saved")

    def open_diagnostic_log_folder(self):
        folder = getattr(self, "log_dir", get_app_data_dir() / "logs")
        try:
            folder.mkdir(parents=True, exist_ok=True)
            if sys.platform.startswith("win"):
                try:
                    os.startfile(str(folder))
                except Exception:
                    subprocess.Popen(['explorer', str(folder)])
            elif sys.platform == "darwin":
                subprocess.Popen(["open", str(folder)])
            else:
                subprocess.Popen(["xdg-open", str(folder)])
        except Exception as exc:
            QMessageBox.critical(self, "Diagnostics", f"Could not open the diagnostic log folder.\n\n{exc}")

    def show_about_dialog(self):
        about_text = (
            f"<h2>{APP_DISPLAY_NAME}</h2>"
            f"<p><b>Version {PROJECT_VERSION}</b></p>"
            f"<p>An automated broadcast audio segmentation, transcription, "
            f"and speaker detection platform built for radio production.</p>"
            f"<hr>"
            f"<p><b>Open-Source Licensing &amp; Attribution:</b></p>"
            f"<p style='font-size:12px; color:#444; line-height:1.4;'>"
            f"• <b>Application Icon:</b> <i>'Electronic Media'</i> by Fatam Organa from "
            f"<a href='https://thenounproject.com/icon/electronic-media-5929933/'>Noun Project</a> "
            f"(licensed under CC BY 3.0).<br>"
            f"• <b>PySide6 / Qt 6:</b> The Qt Company (LGPLv3). Dynamically linked.<br>"
            f"• <b>FFmpeg:</b> FFmpeg developers (LGPLv2.1+ / GPLv2+). Invoked as separate binary.<br>"
            f"• <b>AI &amp; Speech:</b> OpenAI Whisper (MIT), faster-whisper &amp; CTranslate2 (MIT), "
            f"PyTorch (BSD-3), Hugging Face Transformers &amp; Hub (Apache 2.0).<br>"
            f"</p>"
            f"<p style='font-size:11px; color:#666;'>"
            f"Click 'View Licenses' to review full license texts, compliance disclosures, and copyright notices."
            f"</p>"
        )
        msg_box = QMessageBox(self)
        msg_box.setWindowTitle(f"About {APP_DISPLAY_NAME}")
        msg_box.setText(about_text)
        msg_box.setTextFormat(Qt.TextFormat.RichText)
        icon = get_app_icon()
        if not icon.isNull():
            msg_box.setIconPixmap(icon.pixmap(64, 64))

        check_updates_btn = msg_box.addButton("Check for Updates…", QMessageBox.ButtonRole.ActionRole)
        view_licenses_btn = msg_box.addButton("View Licenses", QMessageBox.ButtonRole.ActionRole)
        msg_box.addButton(QMessageBox.StandardButton.Ok)

        msg_box.exec()

        if msg_box.clickedButton() == check_updates_btn:
            self.check_for_updates(interactive=True)
        elif msg_box.clickedButton() == view_licenses_btn:
            self.show_licenses_dialog()

    def check_for_updates(self, interactive: bool = True):
        """Open the Check for Updates dialog to query GitHub releases and install updates."""
        try:
            from updater import CheckUpdateDialog
            dialog = CheckUpdateDialog(self, auto_start=True)
            if interactive:
                dialog.exec()
            else:
                dialog.show()
        except Exception as exc:
            if interactive:
                QMessageBox.warning(self, "Update Error", f"Unable to launch update checker:\n{exc}")

    def trigger_silent_update_check(self):
        """Perform a background update check without showing UI unless an update is found."""
        try:
            from updater import CheckUpdateWorker
            settings = QSettings(INTERNAL_APP_ID, INTERNAL_APP_ID)
            auto_check = str(settings.value("auto_check_updates", "true")).lower() in {"1", "true", "yes"}
            if not auto_check:
                return

            repo = get_github_repo()
            worker = CheckUpdateWorker(repo, self)

            def on_update(release_info, asset_info, is_newer):
                if is_newer:
                    tag = release_info.get("tag_name", "")
                    self.log_activity(f"[UPDATE] New version {tag} available on GitHub.", mark_dirty=False)
                    if hasattr(self, "statusBar"):
                        self.statusBar().showMessage(f"★ Update Available: {tag} — Check About dialog to install.", 15000)

            worker.update_available.connect(on_update)
            worker.start()
            self._background_update_worker = worker
        except Exception:
            pass

    def open_preferences_dialog(self, initial_category="General"):
        """Open the multi-category Preferences dialog."""
        if not isinstance(initial_category, str):
            initial_category = "General"

        from PySide6.QtWidgets import (
            QDialog, QHBoxLayout, QVBoxLayout, QListWidget, QListWidgetItem,
            QStackedWidget, QWidget, QFormLayout, QGroupBox, QCheckBox,
            QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox, QPushButton,
            QDialogButtonBox, QLabel, QFileDialog, QSlider
        )
        from PySide6.QtCore import Qt
        dialog = QDialog(self)
        dialog.setWindowTitle(f"Preferences — {APP_DISPLAY_NAME}")
        dialog.resize(700, 500)

        main_layout = QVBoxLayout(dialog)
        main_layout.setContentsMargins(14, 14, 14, 14)
        main_layout.setSpacing(10)

        content_layout = QHBoxLayout()
        content_layout.setSpacing(12)

        # Left category tree / list
        cat_list = QListWidget(dialog)
        cat_list.setFixedWidth(160)
        categories = ["General", "Audio Hardware", "Updates & GitHub", "AI Models", "Playback & Timeline", "Detection"]
        for cat in categories:
            cat_list.addItem(QListWidgetItem(cat))
        content_layout.addWidget(cat_list)

        # Right stacked pages
        stack = QStackedWidget(dialog)

        # 1. General Page
        page_general = QWidget()
        gen_layout = QVBoxLayout(page_general)
        gen_form = QFormLayout()

        theme_combo = QComboBox()
        theme_combo.addItems(["dark", "light", "high_contrast"])
        curr_theme = str(self.settings_store.value("theme_mode", "dark") or "dark")
        idx = theme_combo.findText(curr_theme)
        if idx >= 0:
            theme_combo.setCurrentIndex(idx)
        gen_form.addRow("Theme Mode:", theme_combo)

        startup_combo = QComboBox()
        startup_combo.addItem("Open last project", "last")
        startup_combo.addItem("Start new project", "new")
        startup_combo.addItem("Ask me", "prompt")

        curr_startup = getattr(
            self,
            "startup_project_mode",
            str(self.settings_store.value("startup_project_mode", "last") or "last")
        )
        idx = startup_combo.findData(curr_startup)
        if idx >= 0:
            startup_combo.setCurrentIndex(idx)
        else:
            startup_combo.setCurrentIndex(0)
        gen_form.addRow("Startup Project:", startup_combo)

        # --- Project Directory & Organization Settings ---
        proj_dir_edit = QLineEdit(str(self.settings_store.value("default_project_directory", "") or ""))
        proj_dir_btn = QPushButton("Browse…")
        def _browse_proj_dir():
            chosen = QFileDialog.getExistingDirectory(dialog, "Select Default Projects Directory", proj_dir_edit.text() or str(Path.home()))
            if chosen:
                proj_dir_edit.setText(chosen)
        proj_dir_btn.clicked.connect(_browse_proj_dir)

        p_dir_layout = QHBoxLayout()
        p_dir_layout.addWidget(proj_dir_edit)
        p_dir_layout.addWidget(proj_dir_btn)
        gen_form.addRow("Default Projects Folder:", p_dir_layout)

        save_with_media_chk = QCheckBox("Save projects in the same folder as original media file")
        save_with_media_chk.setChecked(str(self.settings_store.value("save_project_with_media", "false")).lower() in {"1", "true", "yes"})
        gen_form.addRow("", save_with_media_chk)

        bundle_folder_chk = QCheckBox("Create dedicated project folder with subfolders for exports")
        bundle_folder_chk.setToolTip("Creates [ProjectName]/ containing project.json, with /Transcripts and /Media subfolders.")
        bundle_folder_chk.setChecked(str(self.settings_store.value("create_project_subfolders", "true")).lower() in {"1", "true", "yes"})
        gen_form.addRow("", bundle_folder_chk)

        autosave_spin = QSpinBox()
        autosave_spin.setRange(0, 120)
        autosave_spin.setValue(self.auto_save_minutes)
        autosave_spin.setSuffix(" min (0 = off)")
        gen_form.addRow("Auto-save Interval:", autosave_spin)

        batch_reset_btn = QPushButton("Reset Batch Add Files Location")
        batch_reset_btn.setToolTip("Forget the last directory used by Batch Processing > Add Files and return to the normal default location.")
        def _reset_batch_add_location():
            self.settings_store.remove("batch_add_files_directory")
            QMessageBox.information(dialog, "Batch Add Files Location", "The Batch Processing Add Files location has been reset to the default.")
        batch_reset_btn.clicked.connect(_reset_batch_add_location)
        gen_form.addRow("Batch Add Files Location:", batch_reset_btn)

        gen_layout.addLayout(gen_form)
        gen_layout.addStretch()
        stack.addWidget(page_general)

        # 2. Audio Hardware Page
        page_audio = QWidget()
        audio_layout = QVBoxLayout(page_audio)
        audio_form = QFormLayout()

        audio_dev_combo = QComboBox()
        audio_dev_combo.addItem("System Default")
        try:
            from PySide6.QtMultimedia import QMediaDevices
            for dev in QMediaDevices.audioOutputs():
                d_name = dev.description()
                if d_name and audio_dev_combo.findText(d_name) < 0:
                    audio_dev_combo.addItem(d_name)
        except Exception as dev_err:
            logger.warning(f"Could not enumerate audio devices: {dev_err}")

        saved_dev = str(self.settings_store.value("audio_output_device", "System Default") or "System Default")
        found_dev_idx = audio_dev_combo.findText(saved_dev)
        if found_dev_idx >= 0:
            audio_dev_combo.setCurrentIndex(found_dev_idx)
        else:
            audio_dev_combo.setCurrentIndex(0)
        audio_form.addRow("Audio Output Device:", audio_dev_combo)

        vol_layout = QHBoxLayout()
        vol_slider = QSlider(Qt.Orientation.Horizontal)
        vol_slider.setRange(0, 100)
        curr_vol = int(float(self.settings_store.value("audio_output_volume", 100) or 100))
        vol_slider.setValue(curr_vol)
        vol_label = QLabel(f"{curr_vol}%")
        vol_slider.valueChanged.connect(lambda v: vol_label.setText(f"{v}%"))
        vol_layout.addWidget(vol_slider, 1)
        vol_layout.addWidget(vol_label)
        audio_form.addRow("Default Output Volume:", vol_layout)

        def _test_audio_device():
            try:
                from PySide6.QtCore import QUrl
                import winsound
                winsound.MessageBeep(winsound.MB_ICONASTERISK)
            except Exception:
                try:
                    from PySide6.QtWidgets import QApplication
                    QApplication.beep()
                except Exception:
                    pass

        test_btn = QPushButton("Test Audio Output")
        test_btn.clicked.connect(_test_audio_device)
        audio_form.addRow("Device Test:", test_btn)

        audio_layout.addLayout(audio_form)
        audio_layout.addStretch()
        stack.addWidget(page_audio)

        # 2. Updates & GitHub Page
        page_updates = QWidget()
        up_layout = QVBoxLayout(page_updates)
        up_form = QFormLayout()

        auto_update_chk = QCheckBox("Automatically check for new releases on startup")
        curr_auto = str(self.settings_store.value("auto_check_updates", "true")).lower() in {"1", "true", "yes"}
        auto_update_chk.setChecked(curr_auto)
        up_form.addRow("Auto-Check:", auto_update_chk)

        repo_edit = QLineEdit(get_github_repo())
        repo_edit.setPlaceholderText("owner/repository")
        up_form.addRow("GitHub Repository:", repo_edit)

        up_layout.addLayout(up_form)

        check_now_btn = QPushButton("Check for Updates Now…")
        check_now_btn.setStyleSheet("QPushButton { font-weight: bold; padding: 6px 14px; }")
        check_now_btn.clicked.connect(lambda: self.check_for_updates(interactive=True))
        up_layout.addWidget(check_now_btn)

        up_info = QLabel(
            f"Current application version: <b>v{PROJECT_VERSION}</b><br>"
            "Releases are published automatically via GitHub Actions CI/CD workflows."
        )
        up_info.setStyleSheet("color: #666; font-size: 12px; margin-top: 10px;")
        up_layout.addWidget(up_info)
        up_layout.addStretch()
        stack.addWidget(page_updates)

        # 3. AI Models Page
        page_models = QWidget()
        mod_layout = QVBoxLayout(page_models)
        mod_form = QFormLayout()

        # Storage directory picker
        curr_model_dir = str(get_models_storage_dir())
        model_dir_edit = QLineEdit(curr_model_dir)
        model_dir_btn = QPushButton("Browse…")
        def _browse_model_dir():
            chosen = QFileDialog.getExistingDirectory(dialog, "Select AI Models Storage Directory", model_dir_edit.text())
            if chosen:
                model_dir_edit.setText(chosen)
        model_dir_btn.clicked.connect(_browse_model_dir)

        m_dir_layout = QHBoxLayout()
        m_dir_layout.addWidget(model_dir_edit)
        m_dir_layout.addWidget(model_dir_btn)
        mod_form.addRow("Model Storage Directory:", m_dir_layout)

        # Transcription Model (Whisper) selector
        pref_whisper_combo = QComboBox()
        whisper_models = [
            ("tiny", "Tiny"),
            ("base", "Base"),
            ("small", "Small"),
            ("medium", "Medium"),
            ("large-v3", "Large (v3)")
        ]
        for m_id, label in whisper_models:
            installed = self.is_whisper_model_available(m_id)
            display = f"{label} ✓" if installed else label
            pref_whisper_combo.addItem(display, m_id)

        curr_whisper = getattr(self, "whisper_model", "small")
        w_idx = pref_whisper_combo.findData(curr_whisper)
        if w_idx >= 0:
            pref_whisper_combo.setCurrentIndex(w_idx)
        mod_form.addRow("Default Transcription Model:", pref_whisper_combo)

        # Translation Model (OPUS-MT) selector
        pref_trans_combo = QComboBox()
        trans_variants = [
            ("tiny", "OPUS-MT-tiny"),
            ("standard", "OPUS-MT (Standard)")
        ]
        for v_id, label in trans_variants:
            installed_en_es = TranslationWorker.model_is_installed("en", "es", v_id)
            installed_es_en = TranslationWorker.model_is_installed("es", "en", v_id)
            installed = installed_en_es and installed_es_en
            display = f"{label} ✓" if installed else label
            pref_trans_combo.addItem(display, v_id)

        curr_trans = getattr(self, "translation_model_variant", "tiny")
        t_idx = pref_trans_combo.findData(curr_trans)
        if t_idx >= 0:
            pref_trans_combo.setCurrentIndex(t_idx)
        mod_form.addRow("Default Translation Model:", pref_trans_combo)

        mod_layout.addLayout(mod_form)

        manage_models_btn = QPushButton("Open Full Model Manager (Download / Remove Models)…")
        manage_models_btn.setToolTip("View exact disk sizes, pre-download, or delete local models.")
        def _open_mgr():
            dialog.accept()
            if hasattr(self, "open_model_cleanup_dialog"):
                self.open_model_cleanup_dialog()
        manage_models_btn.clicked.connect(_open_mgr)
        mod_layout.addWidget(manage_models_btn)

        mod_layout.addStretch()
        stack.addWidget(page_models)

        # 4. Playback & Timeline Page
        page_play = QWidget()
        play_layout = QVBoxLayout(page_play)
        play_form = QFormLayout()

        skip_spin = QSpinBox()
        skip_spin.setRange(1, 300)
        skip_spin.setValue(self.skip_seconds)
        skip_spin.setSuffix(" sec")
        play_form.addRow("Arrow Key Skip Length:", skip_spin)

        wave_chk = QCheckBox("Show audio waveform on timeline")
        wave_chk.setChecked(self.timeline_show_waveform)
        play_form.addRow("Timeline Waveform:", wave_chk)

        thumb_chk = QCheckBox("Show video thumbnails on timeline")
        thumb_chk.setChecked(self.timeline_show_thumbnails)
        play_form.addRow("Timeline Thumbnails:", thumb_chk)

        play_layout.addLayout(play_form)
        play_layout.addStretch()
        stack.addWidget(page_play)

        # 5. Detection Page
        page_detect = QWidget()
        det_layout = QVBoxLayout(page_detect)
        det_form = QFormLayout()

        gap_spin = QDoubleSpinBox()
        gap_spin.setRange(0.5, 30.0)
        gap_spin.setSingleStep(0.5)
        gap_spin.setValue(self.silence_threshold)
        gap_spin.setSuffix(" sec")
        det_form.addRow("Silence Gap Threshold:", gap_spin)

        pad_spin = QDoubleSpinBox()
        pad_spin.setRange(0.0, 5.0)
        pad_spin.setSingleStep(0.1)
        pad_spin.setValue(self.lead_in_padding)
        pad_spin.setSuffix(" sec")
        det_form.addRow("Lead-In Padding:", pad_spin)

        sens_slider = QSlider(Qt.Orientation.Horizontal)
        sens_slider.setRange(1, 10)
        sens_slider.setSingleStep(1)
        sens_slider.setPageStep(1)
        sens_slider.setValue(self.speaker_sensitivity)
        sens_value = QLabel(str(self.speaker_sensitivity))
        sens_value.setMinimumWidth(28)
        sens_value.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        sens_slider.valueChanged.connect(lambda v: sens_value.setText(str(v)))
        sens_layout = QHBoxLayout()
        sens_layout.addWidget(sens_slider, 1)
        sens_layout.addWidget(sens_value)
        det_form.addRow("Speaker Detection Sensitivity:", sens_layout)
        sens_slider.setToolTip("1 = more conservative speaker separation; 10 = more sensitive speaker separation.")

        det_layout.addLayout(det_form)
        det_layout.addStretch()
        stack.addWidget(page_detect)

        content_layout.addWidget(stack, 1)
        main_layout.addLayout(content_layout)

        # Switch page on category selection
        cat_list.currentRowChanged.connect(stack.setCurrentIndex)
        cat_search = str(initial_category).strip().lower()[:4] if initial_category else "gene"
        for i, c in enumerate(categories):
            if c.lower().startswith(cat_search):
                cat_list.setCurrentRow(i)
                break
        else:
            cat_list.setCurrentRow(0)

        # Dialog buttons
        btn_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel, dialog)
        main_layout.addWidget(btn_box)

        def _save_preferences():
            # Save General
            new_theme = theme_combo.currentText()
            self.settings_store.setValue("theme_mode", new_theme)
            self.set_theme(new_theme)

            new_startup = startup_combo.currentData()
            if hasattr(self, "set_startup_project_mode"):
                self.set_startup_project_mode(new_startup)
            else:
                self.startup_project_mode = new_startup
                self.settings_store.setValue("startup_project_mode", new_startup)

            self.default_project_directory = proj_dir_edit.text().strip()
            self.settings_store.setValue("default_project_directory", self.default_project_directory)
            self.settings_store.setValue("save_project_with_media", "true" if save_with_media_chk.isChecked() else "false")
            self.settings_store.setValue("create_project_subfolders", "true" if bundle_folder_chk.isChecked() else "false")

            self.auto_save_minutes = autosave_spin.value()
            self.settings_store.setValue("auto_save_minutes", self.auto_save_minutes)
            self.update_auto_save_timer()

            # Save Audio Hardware
            new_dev = audio_dev_combo.currentText()
            self.settings_store.setValue("audio_output_device", new_dev)
            new_vol = vol_slider.value()
            self.settings_store.setValue("audio_output_volume", new_vol)
            if hasattr(self, "apply_audio_output_device"):
                self.apply_audio_output_device(new_dev, new_vol / 100.0)

            # Save Updates
            self.settings_store.setValue("auto_check_updates", str(auto_update_chk.isChecked()).lower())
            new_repo = repo_edit.text().strip()
            if new_repo:
                self.settings_store.setValue("github_repo", new_repo)

            # Save Models dir & selections
            new_model_dir = model_dir_edit.text().strip()
            if new_model_dir:
                set_models_storage_dir(new_model_dir)

            new_whisper = pref_whisper_combo.currentData()
            if new_whisper:
                self.whisper_model = str(new_whisper)
                self.settings_store.setValue("whisper_model", self.whisper_model)
                if hasattr(self, "refresh_whisper_model_chooser"):
                    self.refresh_whisper_model_chooser()

            new_trans = pref_trans_combo.currentData()
            if new_trans:
                self.translation_model_variant = str(new_trans)
                self.settings_store.setValue("translation_model_variant", self.translation_model_variant)
                if hasattr(self, "refresh_translation_model_chooser"):
                    self.refresh_translation_model_chooser()

            # Save Playback
            self.skip_seconds = skip_spin.value()
            self.settings_store.setValue("skip_seconds", self.skip_seconds)
            if hasattr(self, "timeline"):
                self.timeline.set_skip_seconds(self.skip_seconds)

            self.timeline_show_waveform = wave_chk.isChecked()
            self.settings_store.setValue("timeline_show_waveform", str(self.timeline_show_waveform).lower())

            self.timeline_show_thumbnails = thumb_chk.isChecked()
            self.settings_store.setValue("timeline_show_thumbnails", str(self.timeline_show_thumbnails).lower())

            if hasattr(self, "timeline"):
                self.timeline.set_timeline_views(self.timeline_show_waveform, self.timeline_show_thumbnails)

            # Save Detection
            self.silence_threshold = gap_spin.value()
            self.lead_in_padding = pad_spin.value()
            self.speaker_sensitivity = sens_slider.value()
            self.settings_store.setValue("silence_threshold", self.silence_threshold)
            self.settings_store.setValue("lead_in_padding", self.lead_in_padding)
            self.settings_store.setValue("speaker_sensitivity", self.speaker_sensitivity)

            # Force these writes to disk now rather than relying on
            # QSettings' own flush timing, so a Preferences change is
            # durable even if the app is closed or killed shortly after.
            try:
                self.settings_store.sync()
            except Exception:
                pass

            self.log_activity("[SETTINGS] Preferences updated.")
            dialog.accept()

        btn_box.accepted.connect(_save_preferences)
        btn_box.rejected.connect(dialog.reject)

        dialog.exec()

    def apply_audio_output_device(self, device_name=None, volume=None):
        """Apply selected audio output device and volume to the active player."""
        if not hasattr(self, "audio_output") or not self.audio_output:
            return
        if device_name is None:
            device_name = str(self.settings_store.value("audio_output_device", "System Default") or "System Default")
        if volume is None:
            try:
                volume = float(self.settings_store.value("audio_output_volume", 100) or 100) / 100.0
            except Exception:
                volume = 1.0

        try:
            from PySide6.QtMultimedia import QMediaDevices
            if not device_name or device_name in ("System Default", "default"):
                default_dev = QMediaDevices.defaultAudioOutput()
                self.audio_output.setDevice(default_dev)
            else:
                for dev in QMediaDevices.audioOutputs():
                    if dev.description() == device_name:
                        self.audio_output.setDevice(dev)
                        break
            self.audio_output.setVolume(max(0.0, min(1.0, float(volume))))
        except Exception as e:
            logger.warning(f"Could not set audio output device '{device_name}': {e}")

    def show_licenses_dialog(self):
        from PySide6.QtWidgets import QDialog, QVBoxLayout, QTextEdit, QDialogButtonBox
        dialog = QDialog(self)
        dialog.setWindowTitle(f"{APP_DISPLAY_NAME} — Open-Source Licenses & Attributions")
        dialog.resize(750, 520)

        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        text_edit = QTextEdit(dialog)
        text_edit.setReadOnly(True)
        text_edit.setFontFamily("monospace")

        notices_path = get_license_file_path("NOTICES.txt")
        content = ""
        if notices_path and notices_path.is_file():
            try:
                content = notices_path.read_text(encoding="utf-8")
            except Exception as e:
                content = f"Error reading NOTICES.txt: {e}"
        else:
            content = "NOTICES.txt not found."

        text_edit.setPlainText(content)
        layout.addWidget(text_edit)

        button_box = QDialogButtonBox(dialog)
        open_file_btn = button_box.addButton("Open File", QDialogButtonBox.ButtonRole.ActionRole)
        close_btn = button_box.addButton(QDialogButtonBox.StandardButton.Close)

        def _open_file():
            if notices_path and notices_path.is_file():
                QDesktopServices.openUrl(QUrl.fromLocalFile(str(notices_path)))

        open_file_btn.clicked.connect(_open_file)
        close_btn.clicked.connect(dialog.accept)

        layout.addWidget(button_box)
        dialog.exec()

    def eventFilter(self, watched, event):
        if event.type() == QEvent.Type.KeyPress:
            key = event.key()

            media_keys = {
                Qt.Key.Key_MediaPlay, Qt.Key.Key_MediaPause, Qt.Key.Key_MediaTogglePlayPause,
                Qt.Key.Key_MediaStop, Qt.Key.Key_MediaNext, Qt.Key.Key_MediaPrevious,
            }
            if key in media_keys:
                if key in (Qt.Key.Key_MediaPlay, Qt.Key.Key_MediaTogglePlayPause):
                    self.toggle_play()
                elif key == Qt.Key.Key_MediaPause:
                    self.player.pause()
                    self.timeline.set_playing_state(False)
                    self.play_button.setText("▶ Play")
                elif key == Qt.Key.Key_MediaStop:
                    self.stop_audio()
                elif key == Qt.Key.Key_MediaNext:
                    self.seek_to(min(self.duration, self.current_position + self.skip_seconds))
                elif key == Qt.Key.Key_MediaPrevious:
                    self.seek_to(max(0, self.current_position - self.skip_seconds))
                event.accept()
                return True

            if key == Qt.Key.Key_Space:
                focused_widget = QApplication.focusWidget()
                if focused_widget and isinstance(focused_widget, QLineEdit):
                    return super().eventFilter(watched, event)
                if focused_widget and isinstance(focused_widget, InteractiveTranscriptEdit) and focused_widget.is_editing_mode:
                    return super().eventFilter(watched, event)
                self.toggle_play()
                return True

        return super().eventFilter(watched, event)

    def set_skip_seconds_from_ui(self, value):
        self.skip_seconds = max(1, int(value))
        if hasattr(self, "timeline"):
            self.timeline.set_skip_seconds(self.skip_seconds)
        if hasattr(self, "skip_display") and self.skip_display.value() != self.skip_seconds:
            self.skip_display.setValue(self.skip_seconds)
        self.project_dirty = True
        self.update_window_title()

    def toggle_play(self):
        if self.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self.player.pause()
            self.timeline.set_playing_state(False)
            self.play_button.setText("▶ Play")
        else:
            self.player.play()
            self.timeline.set_playing_state(True)
            self.play_button.setText("❚❚ Pause")

    def stop_audio(self):
        self.player.stop()
        self.timeline.set_playing_state(False)
        self.play_button.setText("▶ Play")

    def seek_to(self, seconds):
        self.player.setPosition(int(seconds * 1000))
        self.timeline.ensure_position_visible(seconds)
        self.transcript_view.highlight_word_at_time(seconds, self.transcript)

    def audio_position_changed(self, position):
        self.current_position = position / 1000
        self.timeline.set_position(self.current_position)
        self.time_label.setText(
            f"{format_time(self.current_position)} / {format_time(self.duration)}"
        )
        self.transcript_view.highlight_word_at_time(self.current_position, self.transcript)

    def audio_duration_changed(self, duration):
        self.duration = duration / 1000
        self.timeline.set_duration(self.duration)
        if self.current_media_is_video:
            QTimer.singleShot(0, self.start_video_thumbnail_generation)

    def set_theme(self, mode):
        app = QApplication.instance()
        if mode not in ("light", "dark", "high_contrast"):
            mode = "dark"
        self.settings_store.setValue("theme_mode", mode)
        self.transcript_view.apply_theme_style(mode)
        translation_style = transcript_text_view_stylesheet(mode)
        for view_name in ("translation_view", "bilingual_english_view", "bilingual_spanish_view"):
            view = getattr(self, view_name, None)
            if view is not None:
                view.setStyleSheet(translation_style)

        if mode == "dark":
            dark_palette = QPalette()
            dark_palette.setColor(QPalette.Window, QColor("#121418"))
            dark_palette.setColor(QPalette.WindowText, QColor("#f0f0f0"))
            dark_palette.setColor(QPalette.Base, QColor("#1e222b"))
            dark_palette.setColor(QPalette.AlternateBase, QColor("#2a2e39"))
            dark_palette.setColor(QPalette.ToolTipBase, QColor("#2a2e39"))
            dark_palette.setColor(QPalette.ToolTipText, QColor("#ffffff"))
            dark_palette.setColor(QPalette.Text, QColor("#ffffff"))
            dark_palette.setColor(QPalette.Button, QColor("#2a2e39"))
            dark_palette.setColor(QPalette.ButtonText, QColor("#ffffff"))
            dark_palette.setColor(QPalette.BrightText, QColor("#ff4d4d"))
            dark_palette.setColor(QPalette.Highlight, QColor("#315c85"))
            dark_palette.setColor(QPalette.HighlightedText, QColor("#ffffff"))
            app.setPalette(dark_palette)
            app.setStyleSheet("""
                QMainWindow { background-color: #121418; color: #f0f0f0; }
                #app_surface { background-color: #121418; }
                #app_brand { font-size: 16px; font-weight: 700; color: #f0f0f0; }
                QWidget { color: #f0f0f0; }
                QLabel { color: #f0f0f0; }
                QPushButton { background-color: #2a2e39; color: #ffffff; border: 1px solid #3a3f4d; border-radius: 5px; padding: 5px 10px; font-weight: 500; }
                QPushButton:hover { border-color: #58a6ff; background-color: #343a46; }
                QPushButton:pressed { background-color: #20242c; }
                QPushButton:disabled { color: #707580; background-color: #1a1d24; border-color: #2a2e39; }
                QGroupBox { font-weight: 600; border: 1px solid #30363d; border-radius: 6px; margin-top: 8px; padding-top: 10px; color: #f0f0f0; }
                QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 4px; color: #f0f0f0; }
                QMenuBar { background-color: #121418; color: #f0f0f0; }
                QMenuBar::item:selected { background-color: #2a2e39; }
                QMenu { background-color: #1e222b; color: #f0f0f0; border: 1px solid #3a3f4d; }
                QMenu::item:selected { background-color: #315c85; color: #ffffff; }
                QListWidget, QListView, QTreeView, QTableView, QLineEdit, QSpinBox, QComboBox { background-color: #1e222b; color: #ffffff; border: 1px solid #3a3f4d; border-radius: 4px; padding: 4px; }
                QLineEdit:focus, QSpinBox:focus, QComboBox:focus { border-color: #58a6ff; }
                QListWidget::item, QListView::item, QTreeView::item, QTableView::item { padding: 4px 6px; border-radius: 3px; }
                QListWidget::item:hover, QListView::item:hover, QTreeView::item:hover, QTableView::item:hover { background-color: #262c37; color: #ffffff; }
                QListWidget::item:selected, QListView::item:selected, QTreeView::item:selected, QTableView::item:selected { background-color: #315c85; color: #ffffff; }
                QListWidget::item:selected:!active, QListView::item:selected:!active, QTreeView::item:selected:!active, QTableView::item:selected:!active { background-color: #2b5278; color: #ffffff; }
                QComboBox QAbstractItemView { background-color: #1e222b; color: #ffffff; selection-background-color: #315c85; selection-color: #ffffff; border: 1px solid #3a3f4d; }
                QSlider { background: transparent; height: 22px; }
                QSlider::groove:horizontal {
                    border: 1px solid #3a3f4d;
                    height: 6px;
                    background: #1e222b;
                    border-radius: 3px;
                }
                QSlider::sub-page:horizontal {
                    background: #1f6feb;
                    border: 1px solid #388bfd;
                    height: 6px;
                    border-radius: 3px;
                }
                QSlider::add-page:horizontal {
                    background: #161920;
                    border: 1px solid #3a3f4d;
                    height: 6px;
                    border-radius: 3px;
                }
                QSlider::handle:horizontal {
                    background: #f0f0f0;
                    border: 2px solid #58a6ff;
                    width: 14px;
                    margin-top: -5px;
                    margin-bottom: -5px;
                    border-radius: 8px;
                }
                QSlider::handle:horizontal:hover {
                    background: #ffffff;
                    border-color: #79b8ff;
                }
                QSlider::handle:horizontal:pressed {
                    background: #58a6ff;
                    border-color: #ffffff;
                }
                QProgressBar {
                    border: 1px solid #3a3f4d;
                    border-radius: 4px;
                    text-align: center;
                    background-color: #1e222b;
                    color: #ffffff;
                    font-weight: 500;
                }
                QProgressBar::chunk {
                    background-color: #1f6feb;
                    border-radius: 3px;
                }
                QScrollBar:vertical {
                    border: none;
                    background: #121418;
                    width: 10px;
                    margin: 0px;
                }
                QScrollBar::handle:vertical {
                    background: #30363d;
                    min-height: 20px;
                    border-radius: 5px;
                }
                QScrollBar::handle:vertical:hover {
                    background: #58a6ff;
                }
                QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
                    height: 0px;
                }
                QScrollBar:horizontal {
                    border: none;
                    background: #121418;
                    height: 10px;
                    margin: 0px;
                }
                QScrollBar::handle:horizontal {
                    background: #30363d;
                    min-width: 20px;
                    border-radius: 5px;
                }
                QScrollBar::handle:horizontal:hover {
                    background: #58a6ff;
                }
                QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {
                    width: 0px;
                }
                QToolTip { color: #ffffff; background-color: #1f242d; border: 1px solid #4a5162; padding: 4px 8px; border-radius: 4px; font-size: 13px; }
                QCheckBox { color: #f0f0f0; spacing: 8px; font-size: 13px; }
                QCheckBox::indicator, QListWidget::indicator, QListView::indicator, QTreeView::indicator, QTableView::indicator, QAbstractItemView::indicator {
                    width: 16px;
                    height: 16px;
                    border: 1.5px solid #6b7280;
                    border-radius: 3px;
                    background-color: #1e222b;
                }
                QCheckBox::indicator:hover, QListWidget::indicator:hover, QListView::indicator:hover, QTreeView::indicator:hover, QTableView::indicator:hover, QAbstractItemView::indicator:hover {
                    border-color: #58a6ff;
                }
                QCheckBox::indicator:checked, QListWidget::indicator:checked, QListView::indicator:checked, QTreeView::indicator:checked, QAbstractItemView::indicator:checked {
                    border-color: #58a6ff;
                    background-color: #1f6feb;
                    image: url("data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' width='12' height='12' viewBox='0 0 12 12'><path fill='none' stroke='%23ffffff' stroke-width='2' stroke-linecap='round' stroke-linejoin='round' d='M2.5 6.5l2.5 2.5 4.5-5.5'/></svg>");
                }
                QCheckBox::indicator:disabled, QListWidget::indicator:disabled, QListView::indicator:disabled, QTreeView::indicator:disabled, QAbstractItemView::indicator:disabled {
                    border-color: #374151;
                    background-color: #16181d;
                }
                QCheckBox::indicator:checked:disabled, QListWidget::indicator:checked:disabled, QListView::indicator:checked:disabled, QTreeView::indicator:checked:disabled, QAbstractItemView::indicator:checked:disabled {
                    background-color: #4b5563;
                    border-color: #4b5563;
                    image: url("data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' width='12' height='12' viewBox='0 0 12 12'><path fill='none' stroke='%239ca3af' stroke-width='2' stroke-linecap='round' stroke-linejoin='round' d='M2.5 6.5l2.5 2.5 4.5-5.5'/></svg>");
                }
                QRadioButton { color: #f0f0f0; spacing: 8px; font-size: 13px; }
                QRadioButton::indicator { width: 16px; height: 16px; border: 1.5px solid #6b7280; border-radius: 8px; background-color: #1e222b; }
                QRadioButton::indicator:hover { border-color: #58a6ff; }
                QRadioButton::indicator:checked {
                    border-color: #58a6ff;
                    background-color: #1e222b;
                    image: url("data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' width='16' height='16' viewBox='0 0 16 16'><circle cx='8' cy='8' r='4' fill='%2358a6ff'/></svg>");
                }
                QRadioButton::indicator:disabled { border-color: #374151; background-color: #16181d; }
                QSplitter::handle { background-color: #30363d; height: 8px; }
                QSplitter::handle:hover { background-color: #58a6ff; }
                QScrollArea { border: 1px solid #30363d; background-color: transparent; }
                QTabWidget::pane { border: 1px solid #30363d; }
                QTabBar::tab { background-color: #1e222b; color: #f0f0f0; padding: 6px 12px; border: 1px solid #30363d; border-bottom: none; border-top-left-radius: 4px; border-top-right-radius: 4px; }
                QTabBar::tab:selected { background-color: #2a2e39; color: #ffffff; font-weight: bold; }
                #timeline_border_frame {
                    border: 2px solid #58a6ff;
                    border-radius: 4px;
                    background-color: #181b20;
                }
                #resizable_text_grip {
                    background-color: #3e4451;
                    border: 1px solid #555d6e;
                    border-radius: 3px;
                    margin: 2px 25%;
                }
                #resizable_text_grip:hover {
                    background-color: #58a6ff;
                }
            """)
        elif mode == "light":
            light_palette = QPalette()
            light_palette.setColor(QPalette.Window, QColor("#f4f5f7"))
            light_palette.setColor(QPalette.WindowText, QColor("#111111"))
            light_palette.setColor(QPalette.Base, QColor("#ffffff"))
            light_palette.setColor(QPalette.AlternateBase, QColor("#e9eaee"))
            light_palette.setColor(QPalette.ToolTipBase, QColor("#1f242d"))
            light_palette.setColor(QPalette.ToolTipText, QColor("#ffffff"))
            light_palette.setColor(QPalette.Text, QColor("#111111"))
            light_palette.setColor(QPalette.Button, QColor("#f0f1f4"))
            light_palette.setColor(QPalette.ButtonText, QColor("#111111"))
            light_palette.setColor(QPalette.Highlight, QColor("#1971c2"))
            light_palette.setColor(QPalette.HighlightedText, QColor("#ffffff"))
            app.setPalette(light_palette)
            app.setStyleSheet("""
                QMainWindow { background-color: #f4f5f7; color: #111111; }
                #app_surface { background-color: #f4f5f7; }
                #app_brand { font-size: 16px; font-weight: 700; color: #111111; }
                QWidget { color: #111111; }
                QLabel { color: #111111; }
                QPushButton { background-color: #ffffff; color: #111111; border: 1px solid #b0b4ba; border-radius: 5px; padding: 5px 10px; font-weight: 500; }
                QPushButton:hover { border-color: #1971c2; background-color: #edf2ff; }
                QPushButton:pressed { background-color: #dbe4ff; }
                QPushButton:disabled { color: #9ca3af; background-color: #f3f4f6; border-color: #d1d5db; }
                QGroupBox { font-weight: 600; border: 1px solid #c5c9d0; border-radius: 6px; margin-top: 8px; padding-top: 10px; color: #111111; }
                QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 4px; color: #111111; }
                QMenuBar { background-color: #e5e7eb; color: #111111; border-bottom: 1px solid #d1d5db; }
                QMenuBar::item:selected { background-color: #d1d5db; }
                QMenu { background-color: #ffffff; color: #111111; border: 1px solid #b0b4ba; }
                QMenu::item:selected { background-color: #1971c2; color: #ffffff; }
                QListWidget, QListView, QTreeView, QTableView, QLineEdit, QSpinBox, QComboBox, QTextEdit, QPlainTextEdit { background-color: #ffffff; color: #111111; border: 1px solid #b0b4ba; border-radius: 4px; padding: 4px; }
                QLineEdit:focus, QSpinBox:focus, QComboBox:focus, QTextEdit:focus, QPlainTextEdit:focus { border-color: #1971c2; }
                QListWidget::item, QListView::item, QTreeView::item, QTableView::item { padding: 4px 6px; border-radius: 3px; }
                QListWidget::item:hover, QListView::item:hover, QTreeView::item:hover, QTableView::item:hover { background-color: #edf2ff; color: #111111; }
                QListWidget::item:selected, QListView::item:selected, QTreeView::item:selected, QTableView::item:selected { background-color: #1971c2; color: #ffffff; }
                QListWidget::item:selected:!active, QListView::item:selected:!active, QTreeView::item:selected:!active, QTableView::item:selected:!active { background-color: #459dea; color: #ffffff; }
                QComboBox QAbstractItemView { background-color: #ffffff; color: #111111; selection-background-color: #1971c2; selection-color: #ffffff; border: 1px solid #b0b4ba; }
                QSlider { background: transparent; height: 22px; }
                QSlider::groove:horizontal {
                    border: 1px solid #b0b4ba;
                    height: 6px;
                    background: #d1d5db;
                    border-radius: 3px;
                }
                QSlider::sub-page:horizontal {
                    background: #1971c2;
                    border: 1px solid #1864ab;
                    height: 6px;
                    border-radius: 3px;
                }
                QSlider::add-page:horizontal {
                    background: #e9eaee;
                    border: 1px solid #b0b4ba;
                    height: 6px;
                    border-radius: 3px;
                }
                QSlider::handle:horizontal {
                    background: #ffffff;
                    border: 2px solid #1971c2;
                    width: 14px;
                    margin-top: -5px;
                    margin-bottom: -5px;
                    border-radius: 8px;
                }
                QSlider::handle:horizontal:hover {
                    background: #1971c2;
                    border-color: #1864ab;
                }
                QSlider::handle:horizontal:pressed {
                    background: #1864ab;
                    border-color: #0c4a6e;
                }
                QProgressBar {
                    border: 1px solid #b0b4ba;
                    border-radius: 4px;
                    text-align: center;
                    background-color: #e5e7eb;
                    color: #111111;
                    font-weight: 500;
                }
                QProgressBar::chunk {
                    background-color: #1971c2;
                    border-radius: 3px;
                }
                QScrollBar:vertical {
                    border: none;
                    background: #f4f5f7;
                    width: 10px;
                    margin: 0px;
                }
                QScrollBar::handle:vertical {
                    background: #c5c9d0;
                    min-height: 20px;
                    border-radius: 5px;
                }
                QScrollBar::handle:vertical:hover {
                    background: #9ca3af;
                }
                QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
                    height: 0px;
                }
                QScrollBar:horizontal {
                    border: none;
                    background: #f4f5f7;
                    height: 10px;
                    margin: 0px;
                }
                QScrollBar::handle:horizontal {
                    background: #c5c9d0;
                    min-width: 20px;
                    border-radius: 5px;
                }
                QScrollBar::handle:horizontal:hover {
                    background: #9ca3af;
                }
                QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {
                    width: 0px;
                }
                QToolTip { color: #ffffff; background-color: #1f242d; border: 1px solid #374151; padding: 4px 8px; border-radius: 4px; font-size: 13px; }
                QCheckBox { color: #111111; spacing: 8px; font-size: 13px; }
                QCheckBox::indicator, QListWidget::indicator, QListView::indicator, QTreeView::indicator, QTableView::indicator, QAbstractItemView::indicator {
                    width: 16px;
                    height: 16px;
                    border: 1.5px solid #6b7280;
                    border-radius: 3px;
                    background-color: #ffffff;
                }
                QCheckBox::indicator:hover, QListWidget::indicator:hover, QListView::indicator:hover, QTreeView::indicator:hover, QTableView::indicator:hover, QAbstractItemView::indicator:hover {
                    border-color: #1971c2;
                }
                QCheckBox::indicator:checked, QListWidget::indicator:checked, QListView::indicator:checked, QTreeView::indicator:checked, QAbstractItemView::indicator:checked {
                    border-color: #1971c2;
                    background-color: #1971c2;
                    image: url("data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' width='12' height='12' viewBox='0 0 12 12'><path fill='none' stroke='%23ffffff' stroke-width='2' stroke-linecap='round' stroke-linejoin='round' d='M2.5 6.5l2.5 2.5 4.5-5.5'/></svg>");
                }
                QCheckBox::indicator:disabled, QListWidget::indicator:disabled, QListView::indicator:disabled, QTreeView::indicator:disabled, QAbstractItemView::indicator:disabled {
                    border-color: #d1d5db;
                    background-color: #f3f4f6;
                }
                QCheckBox::indicator:checked:disabled, QListWidget::indicator:checked:disabled, QListView::indicator:checked:disabled, QTreeView::indicator:checked:disabled, QAbstractItemView::indicator:checked:disabled {
                    background-color: #9ca3af;
                    border-color: #9ca3af;
                    image: url("data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' width='12' height='12' viewBox='0 0 12 12'><path fill='none' stroke='%23f3f4f6' stroke-width='2' stroke-linecap='round' stroke-linejoin='round' d='M2.5 6.5l2.5 2.5 4.5-5.5'/></svg>");
                }
                QRadioButton { color: #111111; spacing: 8px; font-size: 13px; }
                QRadioButton::indicator { width: 16px; height: 16px; border: 1.5px solid #6b7280; border-radius: 8px; background-color: #ffffff; }
                QRadioButton::indicator:hover { border-color: #1971c2; }
                QRadioButton::indicator:checked {
                    border-color: #1971c2;
                    background-color: #ffffff;
                    image: url("data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' width='16' height='16' viewBox='0 0 16 16'><circle cx='8' cy='8' r='4' fill='%231971c2'/></svg>");
                }
                QRadioButton::indicator:disabled { border-color: #d1d5db; background-color: #f3f4f6; }
                QSplitter::handle { background-color: #c5c9d0; height: 8px; }
                QSplitter::handle:hover { background-color: #1971c2; }
                QScrollArea { border: 1px solid #c5c9d0; background-color: transparent; }
                QTabWidget::pane { border: 1px solid #c5c9d0; }
                QTabBar::tab { background-color: #e5e7eb; color: #111111; padding: 6px 12px; border: 1px solid #c5c9d0; border-bottom: none; border-top-left-radius: 4px; border-top-right-radius: 4px; }
                QTabBar::tab:selected { background-color: #ffffff; color: #111111; font-weight: bold; }
                #timeline_border_frame {
                    border: 2px solid #1971c2;
                    border-radius: 4px;
                    background-color: #e9eaee;
                }
                #resizable_text_grip {
                    background-color: #d1d5db;
                    border: 1px solid #9ca3af;
                    border-radius: 3px;
                    margin: 2px 25%;
                }
                #resizable_text_grip:hover {
                    background-color: #1971c2;
                }
            """)
        elif mode == "high_contrast":
            hc_palette = QPalette()
            hc_palette.setColor(QPalette.Window, QColor("#000000"))
            hc_palette.setColor(QPalette.WindowText, QColor("#ffffff"))
            hc_palette.setColor(QPalette.Base, QColor("#000000"))
            hc_palette.setColor(QPalette.AlternateBase, QColor("#1a1a1a"))
            hc_palette.setColor(QPalette.ToolTipBase, QColor("#ffff00"))
            hc_palette.setColor(QPalette.ToolTipText, QColor("#000000"))
            hc_palette.setColor(QPalette.Text, QColor("#ffffff"))
            hc_palette.setColor(QPalette.Button, QColor("#000000"))
            hc_palette.setColor(QPalette.ButtonText, QColor("#ffff00"))
            hc_palette.setColor(QPalette.BrightText, QColor("#00ffff"))
            hc_palette.setColor(QPalette.Highlight, QColor("#ffff00"))
            hc_palette.setColor(QPalette.HighlightedText, QColor("#000000"))
            app.setPalette(hc_palette)
            app.setStyleSheet("""
                QMainWindow { background-color: #000000; color: #ffffff; }
                #app_surface { background-color: #000000; }
                #app_brand { font-size: 16px; font-weight: 700; color: #ffff00; }
                QWidget { color: #ffffff; font-weight: 500; }
                QLabel { color: #ffffff; }
                QPushButton { background-color: #000000; color: #ffff00; border: 2px solid #ffff00; border-radius: 4px; padding: 6px 12px; font-weight: bold; }
                QPushButton:hover { background-color: #ffff00; color: #000000; border-color: #ffffff; }
                QPushButton:pressed { background-color: #cccc00; color: #000000; }
                QPushButton:disabled { color: #666666; background-color: #000000; border-color: #666666; }
                QGroupBox { font-weight: bold; border: 2px solid #ffff00; border-radius: 4px; margin-top: 10px; padding-top: 12px; color: #ffff00; }
                QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 4px; color: #ffff00; }
                QMenuBar { background-color: #000000; color: #ffffff; border-bottom: 2px solid #ffff00; }
                QMenuBar::item:selected { background-color: #ffff00; color: #000000; }
                QMenu { background-color: #000000; color: #ffffff; border: 2px solid #ffff00; }
                QMenu::item:selected { background-color: #ffff00; color: #000000; }
                QListWidget, QListView, QTreeView, QTableView, QLineEdit, QSpinBox, QComboBox, QTextEdit, QPlainTextEdit { background-color: #000000; color: #ffffff; border: 2px solid #ffffff; }
                QLineEdit:focus, QSpinBox:focus, QComboBox:focus, QTextEdit:focus, QPlainTextEdit:focus { border-color: #ffff00; }
                QListWidget::item, QListView::item, QTreeView::item, QTableView::item { padding: 4px 6px; }
                QListWidget::item:hover, QListView::item:hover, QTreeView::item:hover, QTableView::item:hover { background-color: #1a1a1a; color: #ffff00; }
                QListWidget::item:selected, QListView::item:selected, QTreeView::item:selected, QTableView::item:selected { background-color: #ffff00; color: #000000; font-weight: bold; }
                QListWidget::item:selected:!active, QListView::item:selected:!active, QTreeView::item:selected:!active, QTableView::item:selected:!active { background-color: #cccc00; color: #000000; font-weight: bold; }
                QComboBox QAbstractItemView { background-color: #000000; color: #ffffff; selection-background-color: #ffff00; selection-color: #000000; border: 2px solid #ffffff; }
                QSlider { background: transparent; height: 22px; }
                QSlider::groove:horizontal {
                    border: 2px solid #ffffff;
                    height: 6px;
                    background: #000000;
                    border-radius: 3px;
                }
                QSlider::sub-page:horizontal {
                    background: #ffff00;
                    border: 2px solid #ffff00;
                    height: 6px;
                    border-radius: 3px;
                }
                QSlider::add-page:horizontal {
                    background: #000000;
                    border: 2px solid #ffffff;
                    height: 6px;
                    border-radius: 3px;
                }
                QSlider::handle:horizontal {
                    background: #ffff00;
                    border: 2px solid #ffffff;
                    width: 16px;
                    margin-top: -6px;
                    margin-bottom: -6px;
                    border-radius: 9px;
                }
                QSlider::handle:horizontal:hover {
                    background: #ffffff;
                    border-color: #ffff00;
                }
                QSlider::handle:horizontal:pressed {
                    background: #00ffff;
                    border-color: #ffffff;
                }
                QProgressBar {
                    border: 2px solid #ffffff;
                    border-radius: 4px;
                    text-align: center;
                    background-color: #000000;
                    color: #ffff00;
                    font-weight: bold;
                }
                QProgressBar::chunk {
                    background-color: #ffff00;
                }
                QScrollBar:vertical {
                    border: 1px solid #ffff00;
                    background: #000000;
                    width: 12px;
                    margin: 0px;
                }
                QScrollBar::handle:vertical {
                    background: #ffff00;
                    min-height: 20px;
                }
                QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
                    height: 0px;
                }
                QScrollBar:horizontal {
                    border: 1px solid #ffff00;
                    background: #000000;
                    height: 12px;
                    margin: 0px;
                }
                QScrollBar::handle:horizontal {
                    background: #ffff00;
                    min-width: 20px;
                }
                QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {
                    width: 0px;
                }
                QToolTip { color: #000000; background-color: #ffff00; border: 2px solid #ffffff; padding: 4px 8px; font-size: 13px; font-weight: bold; }
                QCheckBox { color: #ffffff; spacing: 8px; font-weight: bold; font-size: 13px; }
                QCheckBox::indicator, QListWidget::indicator, QListView::indicator, QTreeView::indicator, QTableView::indicator, QAbstractItemView::indicator {
                    width: 18px;
                    height: 18px;
                    border: 2px solid #ffffff;
                    border-radius: 3px;
                    background-color: #000000;
                }
                QCheckBox::indicator:hover, QListWidget::indicator:hover, QListView::indicator:hover, QTreeView::indicator:hover, QTableView::indicator:hover, QAbstractItemView::indicator:hover {
                    border-color: #ffff00;
                }
                QCheckBox::indicator:checked, QListWidget::indicator:checked, QListView::indicator:checked, QTreeView::indicator:checked, QAbstractItemView::indicator:checked {
                    border-color: #ffff00;
                    background-color: #ffff00;
                    image: url("data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' width='12' height='12' viewBox='0 0 12 12'><path fill='none' stroke='%23000000' stroke-width='2.5' stroke-linecap='round' stroke-linejoin='round' d='M2.5 6.5l2.5 2.5 4.5-5.5'/></svg>");
                }
                QCheckBox::indicator:disabled, QListWidget::indicator:disabled, QListView::indicator:disabled, QTreeView::indicator:disabled, QAbstractItemView::indicator:disabled {
                    background-color: #222222;
                    border-color: #666666;
                }
                QRadioButton { color: #ffffff; spacing: 8px; font-weight: bold; font-size: 13px; }
                QRadioButton::indicator { width: 18px; height: 18px; border: 2px solid #ffffff; border-radius: 9px; background-color: #000000; }
                QRadioButton::indicator:hover { border-color: #ffff00; }
                QRadioButton::indicator:checked {
                    border-color: #ffff00;
                    background-color: #000000;
                    image: url("data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' width='18' height='18' viewBox='0 0 18 18'><circle cx='9' cy='9' r='5' fill='%23ffff00'/></svg>");
                }
                QRadioButton::indicator:disabled { border-color: #666666; background-color: #222222; }
                QSplitter::handle { background-color: #ffff00; height: 8px; }
                QSplitter::handle:hover { background-color: #00ffff; }
                QScrollArea { border: 2px solid #ffff00; background-color: transparent; }
                QTabWidget::pane { border: 2px solid #ffff00; }
                QTabBar::tab { background-color: #000000; color: #ffffff; padding: 6px 14px; border: 2px solid #ffff00; border-bottom: none; border-top-left-radius: 4px; border-top-right-radius: 4px; }
                QTabBar::tab:selected { background-color: #ffff00; color: #000000; font-weight: bold; }
                #timeline_border_frame {
                    border: 3px solid #ffff00;
                    border-radius: 4px;
                    background-color: #000000;
                }
                #resizable_text_grip {
                    background-color: #ffff00;
                    border: 1px solid #ffffff;
                    border-radius: 3px;
                    margin: 2px 25%;
                }
            """)

        # Re-render active views so all inline HTML tags refresh with the new theme colors
        if hasattr(self, "render_transcript") and getattr(self, "transcript", None):
            try:
                self.render_transcript()
            except Exception:
                pass

        if hasattr(self, "render_translation_view"):
            try:
                self.render_translation_view()
            except Exception:
                pass

        if hasattr(self, "timeline") and hasattr(self.timeline, "canvas"):
            self.timeline.canvas.pixmap_dirty = True
            self.timeline.canvas.update()

    def update_sensitivity_tooltip(self, val):
        pct = int((val / 10.0) * 100)
        if val <= 3:
            desc = "More conservative separation; merges more short isolated speaker fragments."
        elif val <= 7:
            desc = "Balanced speaker separation."
        else:
            desc = "More sensitive separation; preserves shorter speaker changes."

        tooltip_msg = f"Speaker Detection sensitivity: {pct}%\\n({desc})\\nAdjusts short-fragment cleanup after detection."
        if hasattr(self, "sensitivity_slider"):
            self.sensitivity_slider.setToolTip(tooltip_msg)

    def on_sensitivity_changed(self, val):
        new_value = int(val)
        changed = new_value != self.speaker_sensitivity
        self.speaker_sensitivity = new_value
        self.update_sensitivity_tooltip(val)
        if changed and self.diarization is not None:
            self.processing_status["diarization"] = False
            self.log_activity("[PROCESSING] Speaker Detection sensitivity changed; existing speaker detection is marked for reprocessing.", mark_dirty=False)
        self.mark_project_dirty()
        self.log_activity(f"[SETTINGS] Speaker cleanup sensitivity set to {int(val) * 10}%.")
        self.statusBar().showMessage(f"Speaker Detection sensitivity: {int(val) * 10}%.")

    def update_auto_save_timer(self):
        if self.auto_save_minutes > 0:
            self.auto_save_timer.start(self.auto_save_minutes * 60 * 1000)
        else:
            self.auto_save_timer.stop()

    def prompt_set_whisper_model(self):
        if hasattr(self, "model_input"):
            self.model_input.setFocus()
            self.model_input.showPopup()

    def prompt_set_skip_seconds(self):
        val, accepted = QInputDialog.getInt(
            self,
            "Set Arrow Key Skip Length",
            "Enter skip duration in seconds for Left/Right arrow keys:",
            self.skip_seconds,
            1,
            300,
            1,
        )
        if accepted:
            self.skip_seconds = val
            self.timeline.set_skip_seconds(val)
            self.log_activity(f"[SETTINGS] Skip length set to {val}s.")
            self.statusBar().showMessage(f"Arrow key skip length set to {val} second(s).")

    def prompt_set_auto_detect_thresholds(self):
        dialog = QDialog(self)
        dialog.setWindowTitle("Story Detection Threshold")
        dialog.setFixedWidth(360)

        layout = QVBoxLayout(dialog)
        form = QFormLayout()

        thresh_box = QDoubleSpinBox()
        thresh_box.setRange(0.5, 30.0)
        thresh_box.setSingleStep(0.5)
        thresh_box.setValue(self.silence_threshold)
        thresh_box.setSuffix(" sec")

        pad_box = QDoubleSpinBox()
        pad_box.setRange(0.0, 5.0)
        pad_box.setSingleStep(0.1)
        pad_box.setValue(self.lead_in_padding)
        pad_box.setSuffix(" sec")

        form.addRow("Silence Gap Threshold:", thresh_box)
        form.addRow("Lead-In Padding:", pad_box)

        layout.addLayout(form)

        btn_box = QHBoxLayout()
        ok_btn = QPushButton("Save")
        cancel_btn = QPushButton("Cancel")
        btn_box.addWidget(ok_btn)
        btn_box.addWidget(cancel_btn)
        layout.addLayout(btn_box)

        ok_btn.clicked.connect(dialog.accept)
        cancel_btn.clicked.connect(dialog.reject)

        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.silence_threshold = thresh_box.value()
            self.lead_in_padding = pad_box.value()
            self.log_activity(f"[SETTINGS] Thresholds set: Gap={self.silence_threshold}s, Padding={self.lead_in_padding}s.")
            self.statusBar().showMessage(f"Thresholds updated: {self.silence_threshold}s silence gap, {self.lead_in_padding}s padding.")

    def prompt_set_auto_save(self):
        val, accepted = QInputDialog.getInt(
            self,
            "Auto-Save Interval",
            "Enter auto-save frequency in minutes (0 to disable):",
            self.auto_save_minutes,
            0,
            120,
            1,
        )
        if accepted:
            self.auto_save_minutes = val
            self.update_auto_save_timer()
            if val > 0:
                self.log_activity(f"[SETTINGS] Auto-save set to {val} min.")
                self.statusBar().showMessage(f"Auto-save configured for every {val} minute(s).")
            else:
                self.log_activity("[SETTINGS] Auto-save disabled.")
                self.statusBar().showMessage("Auto-save disabled.")

    def trigger_auto_save(self):
        if not (self.audio_file and self.project_file and self.project_dirty):
            return
        try:
            autosave = self.project_file.with_suffix(self.project_file.suffix + ".autosave")
            data = self.project_data()
            # Waveform peaks are derived data and can be regenerated; omitting
            # them keeps recovery snapshots small for long recordings.
            data["waveform_peaks"] = []
            data["_autosave"] = {"created_at": datetime.now().isoformat(timespec="seconds"), "source_project": str(self.project_file)}
            tmp = autosave.with_name(autosave.name + ".tmp")
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
                f.flush(); os.fsync(f.fileno())
            os.replace(tmp, autosave)
            current_time = QTime.currentTime().toString("hh:mm A")
            self.log_activity(f"[AUTOSAVE] Recovery snapshot written ({current_time}).", mark_dirty=False)
            self.statusBar().showMessage(f"Recovery snapshot saved at {current_time}")
            if hasattr(self, "save_state_label"):
                self.save_state_label.setText(f"✓ Recovery snapshot {current_time}")
        except Exception as exc:
            self.log_activity(f"[AUTOSAVE] Recovery snapshot failed: {exc}", mark_dirty=False)
