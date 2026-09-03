"""Radio & TV Segmenter v1.1.1 — processing responsibilities.

Methods intentionally retain the MainWindow-facing API so behavior remains
maintaining the established MainWindow-facing API while responsibilities are isolated.
"""

import sys
import os
import json
from pathlib import Path
from PySide6.QtCore import QProcess, QProcessEnvironment, QThread, Qt, QTimer
from PySide6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QCheckBox,
    QPushButton,
    QMessageBox,
)

from prs_shared import (
    HELPER_PROTOCOL_VERSION,
    Story,
    SetStoriesCommand,
    SelectStoriesCommand,
    StoryAutoDetectWorker,
    format_time,
    register_process,     
    unregister_process,
)


class ProcessingMixin:
    def cancel_current_process(self):
        if self.batch_active:
            self.batch_active = False
            self.batch_queue = []
            self.batch_document_queue = []
            self.pipeline_queue = []
            self.pipeline_active = False
            if self.transcription_process is not None:
                self.cleanup_transcription_process()
            if self.diarization_process is not None:
                self.cleanup_diarization_process()
            if self.thread is not None:
                self.stop_story_detection_worker(timeout_ms=5000)
            if self.translation_thread is not None:
                self.stop_translation_worker(timeout_ms=5000)
            self.progress.hide()
            self.cancel_button.hide()
            self.set_processing_stage(None)
            self.set_tools_actions_enabled(True)
            self.log_activity("[BATCH] Batch processing canceled by user.")
            self.statusBar().showMessage("Batch processing canceled.")
            return

        if (
            self.transcription_process is not None
            or self.diarization_process is not None
            or self.thread is not None
        ):
            if self.pipeline_active:
                answer = QMessageBox.question(
                    self,
                    "Stop Processing?",
                    "Run Processing is currently active. Stopping it will keep completed stages and you can resume later.\n\nStop now?",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                )
            else:
                answer = QMessageBox.question(
                    self,
                    "Stop Processing?",
                    "Stop the current processing operation? Any completed results will be preserved.",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                )
            if answer != QMessageBox.StandardButton.Yes:
                return

        if self.transcription_process is not None:
            self.log_activity("[PROCESS] Terminating local transcription helper...")
            self.statusBar().showMessage("Canceling transcription...")
            self.cleanup_transcription_process()
            self.transcription_result_received = False
            self.pending_diarization = False
            self.pipeline_speaker_detection_requested = False
            self.pending_auto_detect_stories = False
            self.pipeline_active = False
            self.set_processing_stage(None)
            self.progress.hide()
            self.cancel_button.hide()
            self.set_tools_actions_enabled(True)
            self.log_activity("[TRANSCRIPTION] Canceled by user.")
            self.statusBar().showMessage("Transcription canceled by user.")
            return

        if self.translation_thread is not None:
            self.log_activity("[PROCESS] Canceling local translation...")
            self.stop_translation_worker()
            self.pipeline_active = False
            self.set_processing_stage(None)
            self.progress.hide()
            self.cancel_button.hide()
            self.set_tools_actions_enabled(True)
            self.log_activity("[TRANSLATION] Canceled by user.")
            return

        if self.diarization_process is not None:
            self.log_activity("[PROCESS] Terminating local Speaker Detection helper...")
            self.statusBar().showMessage("Canceling Speaker Detection...")
            self.cleanup_diarization_process()
            self.diarization_result_received = False
            self.pending_diarization = False
            self.pipeline_speaker_detection_requested = False
            self.pending_auto_detect_stories = False
            self.pipeline_active = False
            self.set_processing_stage(None)
            self.progress.hide()
            self.cancel_button.hide()
            self.set_tools_actions_enabled(True)
            self.log_activity("[SPEAKER DETECT] Canceled by user.")
            self.statusBar().showMessage("Speaker detection canceled by user.")
            return

        if self.thread is not None:
            self.log_activity("[PROCESS] Canceling local Story Detection worker...")
            self.statusBar().showMessage("Canceling Story Detection...")
            self.stop_story_detection_worker(timeout_ms=5000)
            self.pending_auto_detect_stories = False
            self.pending_diarization = False
            self.pipeline_speaker_detection_requested = False
            self.pipeline_active = False
            self.set_processing_stage(None)
            self.progress.hide()
            self.cancel_button.hide()
            self.set_tools_actions_enabled(True)
            self.log_activity("[STORY DETECT] Canceled by user.")
            self.statusBar().showMessage("Story detection canceled by user.")
            return

        self.log_activity("[PROCESS] No cancellable process is currently running.")

    def commit_story_change(self, old_stories, new_stories, description="Modify Story"):
        # Story changes are part of the same complete project-state undo
        # history as transcript/speaker edits.  Capture the state before the
        # caller's mutation and construct the after-state with the new stories.
        before_state = self._capture_project_state()
        after_state = json.loads(json.dumps(before_state, ensure_ascii=False))
        after_state["stories"] = [s.to_dict() for s in new_stories]
        self.stories = [Story.from_dict(s.to_dict()) for s in new_stories]
        self._commit_project_state_change(before_state, description)
        if not self.is_restoring_snapshot:
            self.log_activity(f"[STORY] {description} ({len(new_stories)} story/stories total)")

    def apply_story_selection_indices(self, selected_rows):
        self.is_updating_selection = True
        self.current_selected_story_indices = list(selected_rows)

        self.story_list.blockSignals(True)
        self.story_list.clearSelection()

        for idx in selected_rows:
            if 0 <= idx < self.story_list.count():
                self.story_list.item(idx).setSelected(True)

        self.story_list.blockSignals(False)

        if len(selected_rows) == 1:
            idx = selected_rows[0]
            if 0 <= idx < len(self.stories):
                story = self.stories[idx]
                self.start_input.setText(format_time(story.start))
                self.end_input.setText(format_time(story.end))
                self.title_input.setText(story.title)
                self.seek_to(story.start)
        else:
            self.start_input.clear()
            self.end_input.clear()
            self.title_input.clear()

        self.timeline.set_stories(self.stories, selected_rows)
        self.is_updating_selection = False

    def story_selection_changed(self):
        if self.is_updating_selection:
            return

        selected_rows = sorted([item.row() for item in self.story_list.selectedIndexes()])

        if selected_rows != self.current_selected_story_indices:
            old_sel = list(self.current_selected_story_indices)
            new_sel = list(selected_rows)

            desc = "Cleared Story Selection"
            if len(new_sel) == 1 and new_sel[0] < len(self.stories):
                desc = f"Selected Story #{new_sel[0] + 1}: '{self.stories[new_sel[0]].title}'"
            elif len(new_sel) > 1:
                desc = f"Selected {len(new_sel)} Stories"

            command = SelectStoriesCommand(self, old_sel, new_sel, desc)
            self.undo_stack.push(command)

            self.apply_story_selection_indices(new_sel)
            if not self.is_restoring_snapshot:
                self.log_activity(f"[STORY SELECT] {desc}")

    def handle_timeline_multi_selection(self, selected_indices):
        if self.is_updating_selection:
            return

        selected_rows = sorted(selected_indices)
        if selected_rows != self.current_selected_story_indices:
            old_sel = list(self.current_selected_story_indices)
            new_sel = list(selected_rows)

            desc = f"Box Selected {len(new_sel)} Stories" if len(new_sel) > 1 else "Timeline Selected Story"
            command = SelectStoriesCommand(self, old_sel, new_sel, desc)
            self.undo_stack.push(command)

            self.apply_story_selection_indices(new_sel)
            if not self.is_restoring_snapshot:
                self.log_activity(f"[STORY SELECT] {desc}")

    def set_tools_actions_enabled(self, enabled):
        self.mark_stale_translations()
        has_audio = bool(self.audio_file) and enabled
        self.transcribe_action.setEnabled(has_audio)
        self.diarize_action.setEnabled(has_audio)
        self.auto_detect_action.setEnabled(has_audio)
        self.transcribe_diarize_action.setEnabled(has_audio)
        self.transcribe_diarize_detect_action.setEnabled(has_audio)
        self.translate_action.setEnabled(bool(self.transcript) and enabled)
        self.translation_model_action.setEnabled(True)
        if hasattr(self, "export_translation_action"):
            self.export_translation_action.setEnabled(
                has_audio
                and self.translation_is_current(
                    self.translation_key(self.source_language_code(), self.target_language_code())
                )
            )
        if hasattr(self, "translate_button"):
            self.translate_button.setEnabled(bool(self.transcript))

    def stop_story_detection_worker(self, timeout_ms=5000):
        """Cancel Story Detection and wait for its QThread to finish."""
        thread = getattr(self, "thread", None)
        worker = getattr(self, "worker", None)
        if thread is None:
            return True
        if thread.isRunning():
            if worker is not None:
                try:
                    worker.cancel()
                except Exception:
                    pass
            thread.quit()
            if not thread.wait(timeout_ms):
                self.log_activity(
                    "[WARNING] Story Detection worker did not stop within the normal shutdown window; cancellation is still in progress.",
                    mark_dirty=False,
                )
                return False
        if not thread.isRunning():
            self.thread = None
            self.worker = None
            return True
        return False

    def stop_all_processing(self, timeout_ms=5000):
        """Stop every local processing job before changing media/projects or exiting."""
        ok = True
        if self.transcription_process is not None:
            self.cleanup_transcription_process()
        if self.diarization_process is not None:
            self.cleanup_diarization_process()
        if not self.stop_story_detection_worker(timeout_ms):
            ok = False
        if not self.stop_translation_worker(timeout_ms):
            ok = False
        self.pending_diarization = False
        self.pending_auto_detect_stories = False
        self.pipeline_speaker_detection_requested = False
        self.pipeline_active = False
        return ok

    def confirm_stop_processing_for_media_change(self):
        active = (
            self.transcription_process is not None
            or self.diarization_process is not None
            or self.thread is not None
            or self.translation_thread is not None
            or self.pipeline_active
        )
        if not active:
            return True
        answer = QMessageBox.question(
            self,
            "Processing in Progress",
            "Processing is currently running. Opening another media file or project will stop it. "
            "Completed results will be preserved.\n\nContinue?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return False
        self.log_activity(
            "[PROCESS] Stopping active processing before changing media/project.", mark_dirty=False
        )
        return self.stop_all_processing(timeout_ms=5000)

    def worker_thread_finished(self):
        self.thread = None
        self.worker = None

    def start_full_auto_pipeline(self):
        """Open a chooser for the processing stages to run, then run them in order."""
        if not self.audio_file:
            return

        dialog = QDialog(self)
        dialog.setWindowTitle("Run Processing")
        dialog.setMinimumWidth(520)
        layout = QVBoxLayout(dialog)
        layout.addWidget(
            QLabel(
                "Select the processing stages you want to run. Existing results are shown below; you can choose to rerun them when the stage starts."
            )
        )

        choices = [
            ("transcription", "Transcribe", self.transcript),
            ("diarization", "Detect Speakers", self.diarization),
            ("stories", "Detect Stories", self.stories),
            ("translation", "Translate Transcript", self.translations),
        ]
        boxes = []
        for key, label, data in choices:
            row = QHBoxLayout()
            cb = QCheckBox(label)
            cb.setChecked(bool(data) or not self.processing_status.get(key, False))
            if self.processing_status.get(key):
                state = "Complete"
            elif data:
                state = "Partial"
            else:
                state = "Not Started"
            row.addWidget(cb)
            row.addStretch()
            row.addWidget(QLabel(state))
            layout.addLayout(row)
            boxes.append((key, cb))

        layout.addSpacing(8)
        buttons = QHBoxLayout()
        select_all = QPushButton("Select All")
        clear_all = QPushButton("Clear All")
        run_btn = QPushButton("Run Selected")
        cancel_btn = QPushButton("Cancel")
        buttons.addWidget(select_all)
        buttons.addWidget(clear_all)
        buttons.addStretch()
        buttons.addWidget(run_btn)
        buttons.addWidget(cancel_btn)
        layout.addLayout(buttons)
        select_all.clicked.connect(lambda: [cb.setChecked(True) for _, cb in boxes])
        clear_all.clicked.connect(lambda: [cb.setChecked(False) for _, cb in boxes])
        cancel_btn.clicked.connect(dialog.reject)

        def run_selected():
            selected = [key for key, cb in boxes if cb.isChecked()]
            if not selected:
                QMessageBox.information(
                    dialog, "Run Processing", "Select at least one processing stage."
                )
                return
            if len(selected) > 1 and not self.ensure_project_for_processing_pipeline():
                return
            dialog.accept()
            self.pipeline_queue = list(selected)
            self.pipeline_total_stages = len(selected)
            self.pipeline_all_stages = list(selected)
            self.pipeline_current_stage_idx = 0
            self.pipeline_active = True
            self.pending_diarization = False
            self.pending_auto_detect_stories = False
            self.pipeline_speaker_detection_requested = False
            self.log_activity(
                "[AUTOMATION] Run Processing selected: " + ", ".join(selected) + "."
            )
            QTimer.singleShot(0, self._run_next_selected_processing)

        run_btn.clicked.connect(run_selected)
        dialog.exec()

    def _run_next_selected_processing(self):
        if not self.pipeline_active:
            return
        if not self.pipeline_queue:
            if self.batch_active:
                self.pipeline_active = False
                self.set_processing_stage(None)
                self.set_tools_actions_enabled(True)
                self.update_processing_stage_summary()
                self.save_project() if self.audio_file else None
                self._batch_export_current()
                QTimer.singleShot(0, self._batch_next_media)
                return
            self.pipeline_active = False
            self.set_processing_stage(None)
            self.set_tools_actions_enabled(True)
            self.update_processing_stage_summary()
            self.statusBar().showMessage("Selected processing complete.")
            self.log_activity("[AUTOMATION] Selected processing complete.")
            return

        kind = self.pipeline_queue.pop(0)
        self.pipeline_current_stage_idx = max(1, getattr(self, "pipeline_total_stages", 1) - len(self.pipeline_queue))
        if kind == "transcription":
            choice = "run" if self.batch_active else self._processing_choice("transcription")
            if choice == "cancel":
                self.pipeline_queue = []
                self.pipeline_active = False
                self.set_tools_actions_enabled(True)
                return
            if choice == "start_over":
                self.transcript = []
                self.processing_status["transcription"] = False
            self.start_transcription()
        elif kind == "diarization":
            choice = "run" if self.batch_active else self._processing_choice("diarization")
            if choice == "cancel":
                self.pipeline_queue = []
                self.pipeline_active = False
                self.set_tools_actions_enabled(True)
                return
            if choice == "start_over":
                self.diarization = {}
                self.processing_status["diarization"] = False
            self.start_diarization()
        elif kind == "stories":
            choice = "run" if self.batch_active else self._processing_choice("stories")
            if choice == "cancel":
                self.pipeline_queue = []
                self.pipeline_active = False
                self.set_tools_actions_enabled(True)
                return
            self.start_auto_detect_stories()
        elif kind == "translation":
            if not self.transcript:
                QMessageBox.warning(
                    self,
                    "Run Processing",
                    "Translation requires a transcript. Select Transcribe first or load a project containing a transcript.",
                )
                self.pipeline_queue = []
                self.pipeline_active = False
                self.set_tools_actions_enabled(True)
                return
            from_code = self.source_language_code()
            to_code = self.target_language_code()
            self.start_translation(from_code, to_code, install_if_missing=True)

    def start_transcribe_and_diarize(self):
        if not self.audio_file:
            return
        if not self.ensure_project_for_processing_pipeline():
            return
        self.pipeline_queue = ["transcription", "diarization"]
        self.pipeline_active = True
        self.log_activity("[AUTOMATION] Started Transcribe & Detect Speakers chain")
        self.start_transcription()

    def _processing_choice(self, kind):
        """Return: run, continue, start_over, or cancel based on current state."""
        status = self.processing_status.get(kind, False)
        data = {
            "transcription": self.transcript,
            "diarization": self.diarization,
            "translation": getattr(self, "translations", {}),
        }.get(kind)
        if not data:
            return "run"
        complete = bool(status)
        if complete:
            answer = QMessageBox.question(
                self,
                f"{kind.title()} Already Complete",
                f"{kind.title()} has already been completed. Run it again?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            return "run" if answer == QMessageBox.StandardButton.Yes else "cancel"
        box = QMessageBox(self)
        box.setWindowTitle(f"Incomplete {kind.title()}")
        box.setText(f"An incomplete {kind.title().lower()} exists.")
        cont = box.addButton("Continue", QMessageBox.ButtonRole.AcceptRole)
        restart = box.addButton("Start Over", QMessageBox.ButtonRole.DestructiveRole)
        cancel = box.addButton("Cancel", QMessageBox.ButtonRole.RejectRole)
        box.exec()
        clicked = box.clickedButton()
        if clicked is cont:
            return "continue"
        if clicked is restart:
            return "start_over"
        return "cancel"

    def _worker_command(self, args):
        """Return (executable, args, env_overrides) for the local AI worker.

        Source builds launch the Python worker script. Frozen/installed builds
        launch the separately packaged worker executable so they do not require
        a system Python installation. Either way, if GPU acceleration has been
        installed and enabled from Settings, that takes priority: the worker
        source runs under the separately-provisioned CUDA-enabled environment
        instead, with PRS_WHISPER_DEVICE/PRS_WHISPER_COMPUTE_TYPE set so it
        actually uses the GPU.
        """
        gpu_launch = self.gpu_worker_launch_info() if hasattr(self, "gpu_worker_launch_info") else None
        if gpu_launch is not None:
            python_exe, worker_script, env_overrides = gpu_launch
            return python_exe, [worker_script, *args], env_overrides

        if getattr(sys, "frozen", False):
            exe_name = "prs_worker.exe" if os.name == "nt" else "prs_worker"
            candidates = [
                Path(sys.executable).resolve().parent / "workers" / exe_name,
                Path(sys.executable).resolve().parent / exe_name,
            ]
            for candidate in candidates:
                if candidate.exists():
                    return str(candidate), list(args), {}
            # Re-use the main frozen executable with the lightweight worker CLI flag to avoid duplicate binaries
            return sys.executable, ["--prs-worker", *args], {}
        helper = Path(__file__).with_name("radio_tv_story_segmenter_worker.py")
        if not helper.exists():
            raise FileNotFoundError(f"Local AI worker not found: {helper}")
        feature = "diarize" if args and args[0] == "--diarize" else "transcribe"
        runtime_mgr = getattr(self, "runtime_mgr", None)
        if runtime_mgr is not None:
            ok = runtime_mgr.ensure_environment(feature)
            if not ok:
                raise RuntimeError(f"Could not initialize the {feature} runtime environment.")
            return runtime_mgr.get_executable(feature), [str(helper), *args], {}
        return sys.executable, [str(helper), *args], {}

    def _apply_worker_env_overrides(self, process, env_overrides):
        """Applies extra environment variables (e.g. GPU device selection)
        to a QProcess before starting it, on top of the normal inherited
        environment. No-op when there's nothing to override."""
        if not env_overrides:
            return
        process_env = process.processEnvironment()
        if process_env.isEmpty():
            process_env = QProcessEnvironment.systemEnvironment()
        for key, value in env_overrides.items():
            process_env.insert(key, str(value))
        process.setProcessEnvironment(process_env)

    def start_transcription(self):
        if not self.audio_file:
            self.log_activity("[TRANSCRIPTION] Aborted: no media file is loaded.")
            return

        # Stop background thumbnail and waveform workers during heavy ML tasks to free CPU/disk I/O
        self.stop_waveform_worker()
        self.stop_video_thumbnail_worker()

        choice = self._processing_choice("transcription")
        if choice == "cancel":
            self.log_activity("[TRANSCRIPTION] User canceled processing choice.")
            return
        if choice == "start_over":
            self.transcript = []
            self.processing_status["transcription"] = False
            self.log_activity("[TRANSCRIPTION] Starting over; previous transcript discarded.")
        elif choice == "continue":
            self.log_activity("[TRANSCRIPTION] Continuing from existing partial transcript.")

        if self.transcription_process is not None:
            self.log_activity("[TRANSCRIPTION] A transcription job is already running.")
            return

        self.set_tools_actions_enabled(False)
        self.progress.setValue(0)
        self.progress.show()
        self.cancel_button.show()

        model_name = self.current_whisper_model()
        self.whisper_model = model_name
        if not self.is_whisper_model_available(model_name):
            label = model_name.replace("-v3", "").title()
            answer = QMessageBox.question(
                self,
                "Model Not Installed",
                f"Whisper {label} is not yet installed locally.\n\n"
                "Would you like to download it now? Once downloaded, transcription will begin automatically.",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.Yes,
            )
            if answer != QMessageBox.StandardButton.Yes:
                self.log_activity(
                    f"[TRANSCRIPTION] Model '{model_name}' is not installed; transcription canceled by user.",
                    mark_dirty=False
                )
                self.pipeline_active = False
                self.pipeline_queue = []
                self.set_tools_actions_enabled(True)
                return

            # Modal download with progress
            progress_box = QProgressDialog(f"Downloading Whisper {label} model...", None, 0, 0, self)
            progress_box.setWindowTitle("Downloading Model")
            progress_box.setWindowModality(Qt.WindowModality.WindowModal)
            progress_box.setCancelButton(None)
            progress_box.show()
            QApplication.processEvents()

            err = self._install_whisper_model_background(model_name)
            progress_box.close()

            if err:
                QMessageBox.critical(self, "Download Failed", f"Could not download Whisper '{model_name}':\n\n{err}")
                self.pipeline_active = False
                self.pipeline_queue = []
                self.set_tools_actions_enabled(True)
                return

            self.log_activity(f"[MODELS] Whisper {label} downloaded successfully. Starting transcription...")
            if hasattr(self, "refresh_whisper_model_chooser"):
                self.refresh_whisper_model_chooser()

        if not self.pipeline_active:
            self.processing_status["transcription"] = False
        self.set_processing_stage("Transcription", f"Whisper {model_name}")
        self.transcription_output_buffer = ""
        self.transcription_helper_ready = False
        self.transcription_result_received = False
        self.log_activity(
            f"[TRANSCRIPTION] Started local Whisper transcription (Model: '{model_name}')."
        )
        self.log_activity("[TRANSCRIPTION] Starting isolated local transcription helper...")
        self.log_activity(
            "[TRANSCRIPTION] Processing backend: CPU (hardware acceleration not enabled in this version)."
        )
        self.statusBar().showMessage("Starting local transcription...")

        process = QProcess(self)
        process.setProcessChannelMode(QProcess.ProcessChannelMode.MergedChannels)
        process.readyReadStandardOutput.connect(self.on_transcription_output)
        process.finished.connect(self.on_transcription_process_finished)
        process.finished.connect(lambda: unregister_process(process))
        process.errorOccurred.connect(self.on_transcription_process_error)
        process.errorOccurred.connect(lambda: unregister_process(process))
        
        self.transcription_process = process

        try:
            worker_executable, worker_args, env_overrides = self._worker_command([
                "--transcribe",
                str(self.audio_file),
                model_name,
                getattr(self, "whisper_initial_prompt", ""),
            ])
        except FileNotFoundError as exc:
            self.cleanup_transcription_process()
            self.transcription_error(str(exc))
            return

        self._apply_worker_env_overrides(process, env_overrides)
        process.start(worker_executable, worker_args)

        if not process.waitForStarted(3000):
            error = process.errorString() or "Unknown process-start error."
            self.cleanup_transcription_process()
            self.transcription_error(
                f"Could not start the local transcription process:\n\n{error}"
            )
            return

        register_process(process)
        
        self.log_activity(
            f"[TRANSCRIPTION] Local helper process started (PID {process.processId()})."
        )

    def on_transcription_output(self):
        process = self.transcription_process
        if process is None:
            return

        data = bytes(process.readAllStandardOutput()).decode("utf-8", errors="replace")
        self.transcription_output_buffer += data

        while "\n" in self.transcription_output_buffer:
            line, self.transcription_output_buffer = self.transcription_output_buffer.split(
                "\n", 1
            )
            line = line.strip()
            if not line:
                continue

            try:
                message = json.loads(line)
            except json.JSONDecodeError:
                lowered = line.lower()
                if "warning" in lowered or "warnings.warn" in lowered:
                    level = "[WARNING]"
                elif "error" in lowered or "traceback" in lowered or "exception" in lowered:
                    level = "[ERROR]"
                else:
                    level = "[INFO]"
                self.log_activity(f"[TRANSCRIPTION] {level} Helper: {line}")
                continue

            kind = message.get("type")
            if kind == "hello":
                version = str(message.get("protocol", ""))
                capabilities = message.get("capabilities", [])
                if version != HELPER_PROTOCOL_VERSION:
                    self.transcription_error(
                        "The local processing helper is incompatible with this version of the application.\n\n"
                        f"Expected helper protocol 80.2, but found {version or 'unknown'}.\n\n"
                        "Please use the helper included with this version of Radio & TV Story Segmenter."
                    )
                    return
                if "transcribe" not in capabilities:
                    self.transcription_error(
                        "The installed local helper does not support Whisper transcription.\n\n"
                        "Please use the helper included with this version of Radio & TV Story Segmenter."
                    )
                    return
                self.transcription_helper_ready = True
                self.log_activity(
                    f"[TRANSCRIPTION] Helper protocol {version} verified; transcription capability available."
                )
            elif kind == "progress":
                percent = int(message.get("percent", 0))
                status = str(message.get("message", "Transcription in progress..."))
                self.transcription_progress(status, percent)
                self.log_activity(f"[TRANSCRIPTION] {status}")
            elif kind == "finished":
                if not self.transcription_helper_ready:
                    self.transcription_helper_ready = True

                self.transcription_result_received = True
                self.transcription_finished(message.get("result", {}))
            elif kind == "warning":
                self.log_activity(f"[WARNING] Transcription helper: {message.get('message', '')}")
            elif kind == "error":
                self.transcription_error(str(message.get("message", "Transcription failed.")))

    def on_transcription_process_finished(self, exit_code, exit_status):
        self.on_transcription_output()
        if self.transcription_process is None:
            return

        output = self.transcription_output_buffer.strip()
        was_successful = self.transcription_result_received

        self.cleanup_transcription_process()

        if was_successful:
            self.log_activity("[TRANSCRIPTION] Local helper process completed successfully.")
            return

        if exit_code != 0:
            self.cleanup_transcription_process()
            self.transcription_error(
                f"The local transcription helper exited unexpectedly (exit code {exit_code})."
                + (f"\n\nHelper output:\n{output}" if output else "")
            )
            return

        self.cleanup_transcription_process()
        self.transcription_error("Transcription ended without returning results.")

    def on_transcription_process_error(self, error):
        if self.transcription_process is None:
            return
        message = self.transcription_process.errorString()
        self.cleanup_transcription_process()
        self.transcription_error(
            f"The local transcription process reported an error:\n\n{message}"
        )

    def cleanup_transcription_process(self):
        process = self.transcription_process
        self.transcription_process = None
        self.transcription_output_buffer = ""
        self.transcription_helper_ready = False
        self.transcription_result_received = False
        if process is not None:
            unregister_process(process)
            try:
                if process.state() != QProcess.ProcessState.NotRunning:
                    process.kill()
                    process.waitForFinished(3000)
            except Exception:
                pass
            try:
                process.deleteLater()
            except Exception:
                pass

    def transcription_progress(self, message, percent):
        self.update_processing_progress(percent, message)

    def transcription_finished(self, transcript):
        if not isinstance(transcript, dict) or "segments" not in transcript:
            self.transcription_error(
                "The transcription helper returned an invalid transcript result."
            )
            return
        self.flush_pending_transcript_undo() if hasattr(self, "flush_pending_transcript_undo") else None
        before_state = self._capture_project_state() if hasattr(self, "_capture_project_state") else None
        self.progress.setValue(100)
        self.transcript = transcript
        self.processing_status["transcription"] = True
        self.progress.hide()
        self.cancel_button.hide()

        self.set_tools_actions_enabled(True)
        self.update_translation_language_selector()
        self.render_transcript()
        self.render_translation_view()

        if before_state is not None and hasattr(self, "_commit_project_state_change"):
            self._commit_project_state_change(before_state, "Transcription")
        self.log_activity("[TRANSCRIPTION] Complete. Rendered interactive transcript.")
        self.update_processing_stage_summary()
        self.statusBar().showMessage("Transcription complete.")
        self.save_project()

        if self.pipeline_active and self.pipeline_queue:
            QTimer.singleShot(0, self._run_next_selected_processing)
        elif self.batch_active and self.pipeline_active:
            self.pipeline_active = False
            self._batch_export_current()
            QTimer.singleShot(0, self._batch_next_media)

    def transcription_error(self, message):
        self.cleanup_transcription_process()
        self.pending_diarization = False
        self.pending_auto_detect_stories = False
        self.pipeline_speaker_detection_requested = False
        self.pipeline_active = False
        self.progress.hide()
        self.cancel_button.hide()
        self.set_processing_stage(None)
        self.set_tools_actions_enabled(True)

        if message == "Process canceled by user.":
            self.statusBar().showMessage("Transcription canceled by user.")
        else:
            QMessageBox.critical(self, "Transcription Error", message)

    def on_diarization_process_error(self, error):
        """Handles QProcess execution errors for the diarization process."""
        if getattr(self, "diarization_result_received", False):
            self.cleanup_diarization_process()
            return

        error_descriptions = {
            QProcess.ProcessError.FailedToStart: "The diarization helper process failed to start. Ensure Python and dependencies are correctly installed.",
            QProcess.ProcessError.Crashed: "The diarization helper process crashed unexpectedly (segmentation fault or unhandled native/Python exception).",
            QProcess.ProcessError.Timedout: "The diarization process timed out.",
            QProcess.ProcessError.WriteError: "An error occurred while writing to the diarization process.",
            QProcess.ProcessError.ReadError: "An error occurred while reading from the diarization process.",
            QProcess.ProcessError.UnknownError: "An unknown error occurred in the diarization process.",
        }
        desc = error_descriptions.get(
            error, f"Diarization process error occurred (code: {error})"
        )

        detail_msg = desc
        if self.diarization_output_buffer.strip():
            detail_msg += (
                f"\n\nCaptured Output Buffer:\n{self.diarization_output_buffer.strip()}"
            )

        if hasattr(self, "log_activity"):
            self.log_activity(f"[ERROR] {desc}")

        if hasattr(self, "set_processing_stage"):
            self.set_processing_stage(None)

        self.cleanup_diarization_process()

        if getattr(self, "batch_active", False):
            self.log_activity(
                "[BATCH WARNING] Diarization failed; proceeding with export using available transcript data."
            )
            self._batch_export_current()

            if self.pipeline_active and self.pipeline_queue:
                QTimer.singleShot(0, self._run_next_selected_processing)
            else:
                self.pipeline_active = False
                QTimer.singleShot(0, self._batch_next_media)
        else:
            QMessageBox.critical(
                self, "Diarization Error", f"Failed to run diarization process:\n\n{detail_msg}"
            )

    def start_diarization(self):
        self.log_activity("[SPEAKER DETECT] Speaker Detection startup requested.")

        if not self.audio_file:
            self.log_activity("[SPEAKER DETECT] Aborted: no audio file is loaded.")
            self.diarization_error("No audio file is loaded.")
            return

        # Stop background thumbnail and waveform workers during heavy ML tasks to free CPU/disk I/O
        self.stop_waveform_worker()
        self.stop_video_thumbnail_worker()

        if not self.batch_active:
            choice = self._processing_choice("diarization")
            if choice == "cancel":
                self.log_activity("[SPEAKER DETECT] User canceled processing choice.")
                return
            elif choice == "start_over":
                self.diarization = {}
                self.processing_status["diarization"] = False
        else:
            self.diarization = {}
            self.processing_status["diarization"] = False

        if self.diarization_process is not None:
            self.log_activity("[SPEAKER DETECT] A job is already running.")
            return

        self.set_tools_actions_enabled(False)
        self.progress.setValue(0)
        self.progress.show()
        self.cancel_button.show()
        self.set_processing_stage("Speaker Detection")
        if not self.pipeline_active:
            self.processing_status["diarization"] = False

        self.log_activity("[SPEAKER DETECT] Starting isolated local diarization helper...")
        self.log_activity(
            "[SPEAKER DETECT] Processing backend: CPU (hardware acceleration not enabled in this version)."
        )
        self.statusBar().showMessage("Starting local Speaker Detection...")

        self.diarization_output_buffer = ""
        self.diarization_helper_ready = False
        self.diarization_result_received = False

        process = QProcess(self)
        process.setProcessChannelMode(QProcess.ProcessChannelMode.MergedChannels)
        process.readyReadStandardOutput.connect(self.on_diarization_output)
        process.finished.connect(self.on_diarization_process_finished)
        process.finished.connect(lambda: unregister_process(process))
        process.errorOccurred.connect(self.on_diarization_process_error)
        process.errorOccurred.connect(lambda: unregister_process(process))

        self.diarization_process = process

        try:
            worker_executable, worker_args, env_overrides = self._worker_command([
                "--diarize", str(self.audio_file), str(self.speaker_sensitivity)
            ])
        except FileNotFoundError as exc:
            self.cleanup_diarization_process()
            self.diarization_error(str(exc))
            return

        self._apply_worker_env_overrides(process, env_overrides)
        process.start(worker_executable, worker_args)

        if not process.waitForStarted(3000):
            error = process.errorString() or "Unknown process-start error."
            self.cleanup_diarization_process()
            self.diarization_error(
                f"Could not start the local Speaker Detection process:\n\n{error}"
            )
            return

        register_process(process)
        
        self.log_activity(
            f"[SPEAKER DETECT] Local helper process started (PID {process.processId()})."
        )

    def on_diarization_output(self):
        process = self.diarization_process
        if process is None:
            return

        data = bytes(process.readAllStandardOutput()).decode("utf-8", errors="replace")
        self.diarization_output_buffer += data

        while "\n" in self.diarization_output_buffer:
            line, self.diarization_output_buffer = self.diarization_output_buffer.split(
                "\n", 1
            )
            line = line.strip()
            if not line:
                continue

            try:
                message = json.loads(line)
            except json.JSONDecodeError:
                lowered = line.lower()
                if "warning" in lowered or "warnings.warn" in lowered:
                    level = "[WARNING]"
                elif "error" in lowered or "traceback" in lowered or "exception" in lowered:
                    level = "[ERROR]"
                else:
                    level = "[INFO]"
                self.log_activity(f"[SPEAKER DETECT] {level} Helper: {line}")
                continue

            kind = message.get("type")

            if kind == "hello":
                version = str(message.get("protocol", ""))
                capabilities = message.get("capabilities", [])
                if version != HELPER_PROTOCOL_VERSION:
                    self.diarization_error(
                        "The local processing helper is incompatible with this version of the application.\n\n"
                        f"Expected helper protocol 80.2, but found {version or 'unknown'}.\n\n"
                        "Please use the helper included with this version of Radio & TV Story Segmenter."
                    )
                    return
                if "diarize" not in capabilities:
                    self.diarization_error(
                        "The installed local helper does not support Speaker Detection.\n\n"
                        "Please use the helper included with this version of Radio & TV Story Segmenter."
                    )
                    return
                self.diarization_helper_ready = True
                self.log_activity(
                    f"[SPEAKER DETECT] Helper protocol {version} verified; diarization capability available."
                )

            elif kind == "progress":
                percent = int(message.get("percent", 0))
                status = str(message.get("message", "Speaker Detection in progress..."))
                self.progress.setValue(percent)
                self.statusBar().showMessage(status)
                if hasattr(self, "processing_stage_label") and self.processing_stage_label is not None:
                    self.processing_stage_label.setText(f"Speaker Detection ({percent}%)")
                self.log_activity(f"[SPEAKER DETECT] {status}")

            elif kind == "finished":
                if not self.diarization_helper_ready:
                    self.diarization_helper_ready = True

                self.diarization_result_received = True
                result = message.get("result", {})
                self.diarization_finished(result)

            elif kind == "error":
                self.diarization_error(
                    str(message.get("message", "Speaker Detection failed."))
                )

    def on_diarization_process_finished(self, exit_code, exit_status):
        self.on_diarization_output()

        if self.diarization_process is None:
            return

        error_text = self.diarization_output_buffer.strip()
        was_successful = self.diarization_result_received

        self.cleanup_diarization_process()

        if was_successful:
            self.log_activity("[SPEAKER DETECT] Local helper process exited normally.")
            if self.pipeline_active and self.pipeline_queue:
                QTimer.singleShot(0, self._run_next_selected_processing)
            elif self.batch_active and self.pipeline_active:
                self._batch_export_current()
                self.pipeline_active = False
                QTimer.singleShot(0, self._batch_next_media)
            return

        if exit_code != 0:
            self.diarization_error(
                "The local Speaker Detection helper exited unexpectedly "
                f"(exit code {exit_code})."
                + (f"\n\nHelper output:\n{error_text}" if error_text else "")
            )
            return

        self.diarization_error("Speaker Detection ended without returning results.")

    def cleanup_diarization_process(self):
        process = self.diarization_process
        self.diarization_process = None
        self.diarization_output_buffer = ""
        self.diarization_helper_ready = False
        self.diarization_result_received = False

        if process is not None:
            
            unregister_process(process)
            
            try:
                if process.state() != QProcess.ProcessState.NotRunning:
                    process.kill()
                    process.waitForFinished(2000)
            except Exception:
                pass
            try:
                process.deleteLater()
            except Exception:
                pass

    def diarization_progress(self, message, percent):
        self.update_processing_progress(percent, message)

    def diarization_finished(self, result):
        self.progress.hide()
        self.cancel_button.hide()
        self.set_tools_actions_enabled(True)

        self.flush_pending_transcript_undo() if hasattr(self, "flush_pending_transcript_undo") else None
        before_state = self._capture_project_state() if hasattr(self, "_capture_project_state") else None
        self.diarization = result
        self.processing_status["diarization"] = True

        number = result.get("num_speakers", 0)
        self.speaker_status.setText(
            f"Speaker detection complete: {number} speaker(s) detected."
        )

        self.render_transcript()
        if before_state is not None and hasattr(self, "_commit_project_state_change"):
            self._commit_project_state_change(before_state, "Speaker Detection")
        self.save_project()

        self.log_activity(
            f"[SPEAKER DETECT] Complete: identified {number} speaker(s) locally."
        )
        self.update_processing_stage_summary()

        if self.pipeline_active and self.pipeline_queue:
            QTimer.singleShot(0, self._run_next_selected_processing)
        elif self.batch_active and self.pipeline_active:
            self.pipeline_active = False
            self._batch_export_current()
            QTimer.singleShot(0, self._batch_next_media)
        else:
            self.statusBar().showMessage(f"Speaker detection complete: {number} speaker(s) detected.")

    def diarization_error(self, message):
        self.pending_diarization = False
        self.pipeline_speaker_detection_requested = False
        self.pipeline_active = False
        self.pending_auto_detect_stories = False
        self.progress.hide()
        self.cancel_button.hide()
        self.set_processing_stage(None)
        self.set_tools_actions_enabled(True)

        if message == "Process canceled by user.":
            self.statusBar().showMessage("Speaker detection canceled by user.")
            self.log_activity("[SPEAKER DETECT] Canceled by user.")
        else:
            self.log_activity(f"[SPEAKER DETECT] Error: {message}")
            QMessageBox.critical(self, "Speaker Detection Error", message)

    def start_auto_detect_stories(self):
        if not self.audio_file:
            return

        if self.stories and not self.pipeline_active:
            answer = QMessageBox.question(
                self,
                "Detect Stories",
                "Detecting story boundaries will replace your current Stories list.\n\nDo you want to proceed?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if answer != QMessageBox.StandardButton.Yes:
                return

        self.set_tools_actions_enabled(False)
        self.set_processing_stage("Story Detection")
        if not self.pipeline_active:
            self.processing_status["stories"] = False
        self.progress.setValue(0)
        self.progress.show()
        self.cancel_button.show()
        self.log_activity(
            f"[STORY DETECT] Started story detection (Pause Threshold: {self.silence_threshold}s)"
        )

        self.story_job_token += 1
        job_token = self.story_job_token
        self.thread = QThread()
        self.worker = StoryAutoDetectWorker(
            self.audio_file,
            silence_threshold=self.silence_threshold,
            lead_in_padding=self.lead_in_padding,
            audio_duration=self.duration,
        )
        self.worker.moveToThread(self.thread)
        self.worker._job_token = job_token
        self.thread.setProperty("job_token", job_token)

        self.thread.started.connect(self.worker.run)
        self.worker.progress.connect(self.auto_detect_progress)
        self.worker.finished.connect(self.auto_detect_finished)
        self.worker.error.connect(self.auto_detect_error)

        self.worker.finished.connect(self.thread.quit, Qt.ConnectionType.DirectConnection)
        self.worker.error.connect(self.thread.quit, Qt.ConnectionType.DirectConnection)
        self.worker.finished.connect(self.worker.deleteLater)
        self.worker.error.connect(self.worker.deleteLater)
        self.thread.finished.connect(self.thread.deleteLater)
        self.thread.finished.connect(self.worker_thread_finished)

        self.thread.start()

    def auto_detect_progress(self, message, percent):
        if (
            self.sender() is not self.worker
            or getattr(self.worker, "_job_token", None) != self.story_job_token
        ):
            return
        self.update_processing_progress(percent, message)

    def auto_detect_finished(self, new_stories):
        if (
            self.sender() is not self.worker
            or getattr(self.worker, "_job_token", None) != self.story_job_token
        ):
            self.log_activity(
                "[STORY DETECT] Discarded stale results from an older processing job.",
                mark_dirty=False,
            )
            return
        self.progress.hide()
        self.cancel_button.hide()
        self.set_tools_actions_enabled(True)

        old_stories = [Story.from_dict(s.to_dict()) for s in self.stories]
        self.commit_story_change(old_stories, new_stories, "Detect Stories")

        count = len(new_stories)
        self.processing_status["stories"] = True
        self.update_processing_stage_summary()
        msg = f"Story detection complete: Created {count} story region(s)."
        self.log_activity(f"[STORY DETECT] Complete: Auto-created {count} story region(s).")
        self.statusBar().showMessage(msg)
        self.save_project()
        if self.pipeline_active and self.pipeline_queue:
            QTimer.singleShot(0, self._run_next_selected_processing)
        elif self.batch_active and self.pipeline_active:
            self.pipeline_active = False
            self._batch_export_current()
            QTimer.singleShot(0, self._batch_next_media)
        elif self.pipeline_active:
            self.pipeline_active = False
            self.set_processing_stage(None)
            self.log_activity("[AUTOMATION] Selected processing complete.")

    def auto_detect_error(self, message):
        if (
            self.sender() is not self.worker
            or getattr(self.worker, "_job_token", None) != self.story_job_token
        ):
            return
        self.progress.hide()
        self.cancel_button.hide()
        self.set_tools_actions_enabled(True)

        if message == "Process canceled by user.":
            self.statusBar().showMessage("Story detection canceled by user.")
        else:
            self.log_activity(
                "[AUTOMATION] Story Detection failed. Run All Processing can resume from completed stages after the error is addressed."
            )
            QMessageBox.critical(self, "Story Detection Error", message)

    def _diar_segments_cache_key(self):
        segments = self.diarization.get("segments") if self.diarization else None
        if not segments:
            return None
        return (id(segments), len(segments))

    def _ensure_diar_speaker_index(self):
        key = self._diar_segments_cache_key()
        if key == self._diar_index_key:
            return
        if key is None:
            self._diar_sorted_segments = []
            self._diar_sorted_orig_idx = []
            self._diar_sorted_starts = []
            self._diar_max_end_prefix = []
            self._diar_speaker_labels = set()
            self._diar_index_key = None
            return

        segments = self.diarization.get("segments", [])
        order = sorted(range(len(segments)), key=lambda i: segments[i]["start"])
        sorted_segments = [segments[i] for i in order]
        starts = [segments[i]["start"] for i in order]
        max_end_prefix = []
        running_max = float("-inf")
        for seg in sorted_segments:
            running_max = max(running_max, seg["end"])
            max_end_prefix.append(running_max)

        self._diar_sorted_segments = sorted_segments
        self._diar_sorted_orig_idx = order
        self._diar_sorted_starts = starts
        self._diar_max_end_prefix = max_end_prefix
        self._diar_speaker_labels = {
            self.display_speaker(s["speaker"]) for s in segments if s.get("speaker")
        }
        self._diar_index_key = key

    def speaker_at_time(self, start, end):
        if not self.diarization:
            return None

        self._ensure_diar_speaker_index()
        segments = self._diar_sorted_segments
        if not segments:
            return None

        from bisect import bisect_right

        hi = bisect_right(self._diar_sorted_starts, end)
        if hi == 0:
            return None
        lo = bisect_right(self._diar_max_end_prefix, start, 0, hi)

        best_speaker = None
        best_key = None
        orig_idx = self._diar_sorted_orig_idx

        for i in range(lo, hi):
            diar_segment = segments[i]
            overlap_start = max(start, diar_segment["start"])
            overlap_end = min(end, diar_segment["end"])
            overlap = overlap_end - overlap_start
            if overlap <= 0:
                continue

            key = (overlap, -orig_idx[i])
            if best_key is None or key > best_key:
                best_key = key
                best_speaker = diar_segment["speaker"]

        return best_speaker

    def get_effective_speaker_name(self, seg_idx, segment):
        raw_speaker = self.segment_speaker_overrides.get(
            seg_idx
        ) or self.speaker_for_segment(segment)
        return self.display_speaker(raw_speaker)