"""Radio & TV Segmenter v1.1.1 — optional GPU acceleration responsibilities.

The base install (and installer) is CPU-only by design to keep download size
small. This module lets a user with an NVIDIA GPU download a CUDA-enabled
Whisper/diarization environment on demand from Settings, instead of it being
bundled into every install. It reuses the same isolated-environment machinery
(runtime_manager.RuntimeManager) already used for the source-build feature
environments, just for one more feature: "gpu_transcribe".
"""

from prs_shared import *
from runtime_manager import RuntimeManager, detect_nvidia_gpu


class GpuAccelerationInstallWorker(QObject):
    progress = Signal(str)
    finished = Signal(object)  # error message (str) or None on success

    def __init__(self, force_rebuild=False):
        super().__init__()
        self.force_rebuild = force_rebuild

    def run(self):
        error = None
        try:
            runtime_mgr = RuntimeManager()
            ok = runtime_mgr.ensure_environment(
                "gpu_transcribe",
                force_rebuild=self.force_rebuild,
                progress_cb=lambda msg: self.progress.emit(msg),
            )
            if not ok:
                error = "The GPU acceleration environment could not be created. See the diagnostic log for details."
        except Exception as exc:
            error = f"{type(exc).__name__}: {exc}"
        self.finished.emit(error)


class GpuAccelerationMixin:
    def gpu_acceleration_settings_key(self):
        return "gpu_acceleration_enabled"

    def is_gpu_acceleration_enabled(self):
        store = getattr(self, "settings_store", None)
        if store is None:
            return False
        return str(store.value(self.gpu_acceleration_settings_key(), "false")).lower() in {"1", "true", "yes"}

    def is_gpu_acceleration_installed(self):
        try:
            return RuntimeManager().is_env_up_to_date("gpu_transcribe")
        except Exception:
            return False

    def gpu_worker_launch_info(self):
        """If GPU acceleration is installed and enabled, returns
        (python_executable, worker_script_path, env_overrides) to launch the
        AI worker with; otherwise returns None, meaning the caller should
        fall back to its normal (CPU) worker launch path unchanged."""
        if sys.platform != "win32" or not (self.is_gpu_acceleration_enabled() and self.is_gpu_acceleration_installed()):
            return None
        try:
            runtime_mgr = RuntimeManager()
            python_exe = runtime_mgr.get_executable("gpu_transcribe")
        except Exception:
            return None

        if getattr(sys, "frozen", False):
            worker_script = Path(sys.executable).resolve().parent / "workers" / "radio_tv_story_segmenter_worker.py"
        else:
            worker_script = Path(__file__).with_name("radio_tv_story_segmenter_worker.py")

        if not worker_script.exists() or python_exe == sys.executable:
            # python_exe falling back to the host interpreter means the GPU
            # env isn't actually ready despite is_env_up_to_date() -- don't
            # silently run the CPU-only host interpreter and call it GPU mode.
            return None

        env_overrides = {
            "PRS_WHISPER_DEVICE": "cuda",
            "PRS_WHISPER_COMPUTE_TYPE": "float16",
        }
        return python_exe, str(worker_script), env_overrides

    def open_gpu_acceleration_settings(self):
        if sys.platform != "win32":
            QMessageBox.information(
                self, "GPU Acceleration",
                "Optional NVIDIA CUDA acceleration is currently supported on Windows only. "
                "This application remains CPU-first on macOS."
            )
            return
        dialog = QDialog(self)
        dialog.setWindowTitle("GPU Acceleration (NVIDIA CUDA)")
        dialog.setMinimumSize(480, 300)
        layout = QVBoxLayout(dialog)

        intro = QLabel(
            "Transcription and speaker detection run on the CPU by default, which keeps "
            "the install small and works on any machine. If this computer has a supported "
            "NVIDIA GPU, you can download an additional CUDA-enabled environment to speed "
            "those steps up. This is a separate download (a few gigabytes) and is optional."
        )
        intro.setWordWrap(True)
        layout.addWidget(intro)

        gpu_detected = detect_nvidia_gpu()
        detect_label = QLabel(
            "NVIDIA GPU detected on this machine." if gpu_detected
            else "No NVIDIA GPU was detected on this machine. The optional CUDA runtime will "
                 "not be installed unless a compatible NVIDIA GPU and driver are available."
        )
        detect_label.setWordWrap(True)
        layout.addWidget(detect_label)

        installed = self.is_gpu_acceleration_installed()
        status_label = QLabel(f"Status: {'Installed' if installed else 'Not installed'}")
        layout.addWidget(status_label)

        enable_checkbox = QCheckBox("Use GPU acceleration when available")
        enable_checkbox.setChecked(self.is_gpu_acceleration_enabled())
        enable_checkbox.setEnabled(installed)
        layout.addWidget(enable_checkbox)

        button_row = QHBoxLayout()
        install_btn = QPushButton("Update / Reinstall" if installed else "Download and Install")
        install_btn.setEnabled(gpu_detected)
        uninstall_btn = QPushButton("Uninstall")
        uninstall_btn.setEnabled(installed)
        close_btn = QPushButton("Close")
        button_row.addWidget(install_btn)
        button_row.addWidget(uninstall_btn)
        button_row.addStretch(1)
        button_row.addWidget(close_btn)
        layout.addLayout(button_row)

        def on_enable_toggled(checked):
            self.settings_store.setValue(self.gpu_acceleration_settings_key(), "true" if checked else "false")

        enable_checkbox.toggled.connect(on_enable_toggled)

        def on_uninstall():
            confirm = QMessageBox.question(
                dialog, "Uninstall GPU Acceleration",
                "Remove the downloaded GPU acceleration environment? Transcription and "
                "speaker detection will fall back to CPU.",
            )
            if confirm != QMessageBox.StandardButton.Yes:
                return
            try:
                runtime_mgr = RuntimeManager()
                shutil.rmtree(runtime_mgr.get_env_dir("gpu_transcribe"), ignore_errors=True)
            except Exception as exc:
                QMessageBox.critical(dialog, "Uninstall Failed", str(exc))
                return
            self.settings_store.setValue(self.gpu_acceleration_settings_key(), "false")
            self.log_activity("[GPU] GPU acceleration environment removed.", mark_dirty=False)
            dialog.accept()
            self.open_gpu_acceleration_settings()

        uninstall_btn.clicked.connect(on_uninstall)
        close_btn.clicked.connect(dialog.accept)
        install_btn.clicked.connect(lambda: self._start_gpu_acceleration_install(dialog))

        dialog.exec()

    def _start_gpu_acceleration_install(self, parent_dialog=None):
        if getattr(self, "_gpu_install_thread", None) is not None:
            return

        if parent_dialog is not None:
            parent_dialog.accept()

        self.set_processing_stage("GPU Acceleration", "Downloading and installing...")
        self.progress.setValue(5)
        self.progress.show()
        self.log_activity("[GPU] Starting GPU acceleration environment install...")

        self._gpu_install_qthread = QThread(self)
        self._gpu_install_worker = GpuAccelerationInstallWorker(force_rebuild=True)
        self._gpu_install_worker.moveToThread(self._gpu_install_qthread)
        self._gpu_install_qthread.started.connect(self._gpu_install_worker.run)
        self._gpu_install_worker.progress.connect(self._on_gpu_install_progress)
        self._gpu_install_worker.finished.connect(self._on_gpu_install_finished)
        self._gpu_install_worker.finished.connect(self._gpu_install_qthread.quit)
        self._gpu_install_qthread.finished.connect(self._gpu_install_worker.deleteLater)
        self._gpu_install_qthread.finished.connect(self._gpu_install_thread_cleanup)
        self._gpu_install_thread = self._gpu_install_qthread
        self._gpu_install_qthread.start()

    def _on_gpu_install_progress(self, message):
        self.log_activity(f"[GPU] {message}", mark_dirty=False)
        self.set_processing_stage("GPU Acceleration", message)

    def _on_gpu_install_finished(self, error):
        self._gpu_install_error = error

    def _gpu_install_thread_cleanup(self):
        thread = getattr(self, "_gpu_install_thread", None)
        error = getattr(self, "_gpu_install_error", None)
        if thread is not None:
            thread.deleteLater()
        self._gpu_install_thread = None
        self._gpu_install_qthread = None
        self._gpu_install_worker = None

        self.progress.setValue(100)
        self.progress.hide()
        self.set_processing_stage(None)

        if error:
            self.log_activity(f"[GPU] Install failed: {error}", mark_dirty=False)
            QMessageBox.critical(self, "GPU Acceleration", f"Could not install GPU acceleration:\n\n{error}")
        else:
            self.settings_store.setValue(self.gpu_acceleration_settings_key(), "true")
            self.log_activity("[GPU] GPU acceleration installed and enabled.", mark_dirty=False)
            QMessageBox.information(
                self, "GPU Acceleration",
                "GPU acceleration was installed and enabled. It will be used for the next "
                "transcription or diarization run."
            )
