"""Radio & TV Segmenter — v2.7.1

This is the thin application composition root. UI/processing responsibilities
are implemented in focused mixins so future changes can target smaller files
without changing the MainWindow-facing API.
"""
import sys
from pathlib import Path
from bootstrap import configure_runtime_environment, ensure_sherpa_onnx_runtime, ensure_keyring_runtime

# Bootstrap writable model/cache locations and verify required runtimes before
# importing the rest of the application. Source builds can install them automatically;
# packaged builds contain them via build_installer.py.
configure_runtime_environment()
_sherpa_runtime_ready = ensure_sherpa_onnx_runtime()
_keyring_runtime_ready = ensure_keyring_runtime()

# If invoked as a background AI worker subprocess, dispatch immediately without loading the GUI.
if len(sys.argv) > 1 and sys.argv[1] in ("--prs-worker", "--worker"):
    import radio_tv_story_segmenter_worker
    raise SystemExit(radio_tv_story_segmenter_worker.main(sys.argv[2:]))

# Build-time/runtime smoke test. This runs before Qt is imported so the frozen
# executable can prove that its own native ML stack is loadable.
if len(sys.argv) > 1 and sys.argv[1] == "--self-test":
    failures = []
    checks = []
    def _check(label, fn):
        try:
            value = fn()
            checks.append(f"[SELF-TEST] {label}: PASS" + (f" ({value})" if value else ""))
        except Exception as exc:
            failures.append((label, exc))
            checks.append(f"[SELF-TEST] {label}: FAIL: {type(exc).__name__}: {exc}")
    def _torch_location_diagnostic():
        import importlib.util
        spec = importlib.util.find_spec("torch._C")
        return str(spec.origin if spec and spec.origin else "not-found")
    _check("PyTorch _C module discovery", _torch_location_diagnostic)
    _check("PyTorch", lambda: __import__("torch").__version__)
    _check("PyTorch C extension", lambda: str(__import__("torch")._C))
    _check("CTranslate2", lambda: __import__("ctranslate2").__version__)
    _check("Transformers", lambda: __import__("transformers").__version__)
    _check("Silero VAD", lambda: __import__("silero_vad").__name__)
    # Windowed PyInstaller builds may have no stdout/stderr. Persist the
    # diagnostic beside the executable so the build can inspect it.
    test_file = Path(sys.executable).resolve().parent / "ai_self_test.txt" if getattr(sys, "frozen", False) else Path("ai_self_test.txt")
    test_file.write_text("\n".join(checks) + "\n", encoding="utf-8")
    raise SystemExit(1 if failures else 0)

from prs_shared import *
from runtime_manager import RuntimeManager
from model_management import ModelManagementMixin
from media_batch import MediaBatchMixin
from playback_preferences import PlaybackPreferencesMixin
from ui_layout import UiLayoutMixin
from processing import ProcessingMixin
from translation import TranslationMixin
from transcript_story import TranscriptStoryMixin
from project_export import ProjectExportMixin
from wordpress_export import WordPressExportMixin
from gpu_acceleration import GpuAccelerationMixin
from theme_tokens import ThemeTokens
from theme_qss import TARGETED_QSS


class MainWindow(
    ModelManagementMixin,
    MediaBatchMixin,
    PlaybackPreferencesMixin,
    UiLayoutMixin,
    ProcessingMixin,
    TranslationMixin,
    TranscriptStoryMixin,
    ProjectExportMixin,
    WordPressExportMixin,
    GpuAccelerationMixin,
    QMainWindow,
):
    """Main application window for the v1.1 release.

    The constructor remains here because it defines the shared application
    state and Qt object graph. Feature methods live in focused mixins.
    """

    def __init__(self):
        super().__init__()
        
        self.tokens = ThemeTokens()

        if sys.platform == "win32":
            try:
                import pywinstyles
                pywinstyles.apply_style(self, "mica")
            except Exception as e:
                pass

        self.runtime_mgr = RuntimeManager()
        self.audio_file = None
        self.project_file = None
        self.project_dirty = False

        self.transcript = None
        self.diarization = None
        # Lazy, self-invalidating index for fast speaker_at_time() lookups.
        # self.diarization is always replaced wholesale (never mutated in
        # place) elsewhere in this file, so keying the cache on the identity
        # of the segments list is safe and needs no manual invalidation.
        self._diar_index_key = None
        self._diar_sorted_segments = []
        self._diar_sorted_orig_idx = []
        self._diar_sorted_starts = []
        self._diar_max_end_prefix = []
        self._diar_speaker_labels = set()
        self.processing_status = {"transcription": False, "diarization": False, "stories": False}
        self.pipeline_active = False
        self.pipeline_queue = []
        self.pipeline_rerun_confirmed = False
        self.speaker_names = {}
        self.segment_speaker_overrides = {}
        self.translations = {}
        self.translation_display_mode = "en"
        self.translation_thread = None
        self.translation_worker = None
        self.translation_installing = False
        self.translation_install_key = None
        self.translation_model_status_cache = {}
        self.translation_model_variant = "tiny"
        self.translation_status_threads = []
        self.current_operation = None

        self.stories = []
        self.current_selected_story_indices = []
        self.pre_drag_stories_snapshot = []

        self.duration = 0
        self.current_position = 0
        self.skip_seconds = 5
        self.whisper_model = "small"
        self.silence_threshold = 3.0
        self.lead_in_padding = 0.5
        self.expected_speakers = "auto"
        self.translation_direction = "auto"

        self.pending_diarization = False
        self.pending_auto_detect_stories = False
        self.pipeline_speaker_detection_requested = False
        self.is_updating_transcript_view = False
        self.is_updating_selection = False

        self.activity_snapshots = []
        self.is_restoring_snapshot = False

        self.undo_stack = QUndoStack(self)
        self.undo_stack.setUndoLimit(100)
        self.is_restoring_undo = False
        self._pending_transcript_edit_before = None
        self._transcript_undo_timer = QTimer(self)
        self._transcript_undo_timer.setSingleShot(True)
        self._transcript_undo_timer.setInterval(700)
        self._transcript_undo_timer.timeout.connect(self.flush_pending_transcript_undo)

        self.thread = None
        self.worker = None
        self.story_job_token = 0
        self.media_generation = 0
        self.save_in_progress = False
        self.translation_save_threads = []
        self.translation_save_lock = threading.Lock()
       # self.project_save_finished.connect(self._translation_background_save_finished)

        # Speaker detection runs in a separate local process so a stuck or
        # long-running model call can always be terminated cleanly.
        # Speaker Detection uses a dedicated helper process launched with
        # QProcess. The helper imports only the diarization backend, avoiding
        # multiprocessing/spawn re-imports of the full Qt application.
        self.diarization_process = None
        self.diarization_output_buffer = ""
        self.transcription_process = None
        self.transcription_output_buffer = ""
        self.transcription_helper_ready = False
        self.transcription_result_received = False
        self.diarization_helper_ready = False
        self.diarization_result_received = False

        self.auto_save_minutes = 5
        self.auto_save_timer = QTimer(self)
        self.auto_save_timer.timeout.connect(self.trigger_auto_save)
        self.update_auto_save_timer()

        self.scrub_timer = QTimer(self)
        self.scrub_timer.setSingleShot(True)
        self.pending_scrub_target = None
        self.scrub_timer.timeout.connect(self.execute_scrub_seek)

        self.find_dialog = None

        QApplication.instance().installEventFilter(self)

        # Initialize persistent settings before any component that reads them.
        self.settings_store = QSettings(INTERNAL_APP_ID, INTERNAL_APP_ID)
        self.default_project_directory = str(self.settings_store.value("default_project_directory", "") or "")
        self.timeline_show_waveform = str(self.settings_store.value("timeline_show_waveform", "true")).lower() in {"1", "true", "yes"}
        self.timeline_show_thumbnails = str(self.settings_store.value("timeline_show_thumbnails", "true")).lower() in {"1", "true", "yes"}
        self.timeline_thumbnail_position = str(self.settings_store.value("timeline_thumbnail_position", "below")).lower()
        if self.timeline_thumbnail_position not in ("above", "below"):
            self.timeline_thumbnail_position = "below"
        self.transcript_selection_mode = str(self.settings_store.value("transcript_selection_mode", "replace") or "replace")
        try:
            self.transcript_font_scale = max(0.80, min(1.80, float(self.settings_store.value("transcript_font_scale", 1.0))))
        except (TypeError, ValueError):
            self.transcript_font_scale = 1.0

        self.audio_output = QAudioOutput()
        self.audio_output.setVolume(1.0)

        self.player = QMediaPlayer()
        self.player.setAudioOutput(self.audio_output)
        if hasattr(self, "apply_audio_output_device"):
            self.apply_audio_output_device()
        self.player.positionChanged.connect(self.audio_position_changed)
        self.player.durationChanged.connect(self.audio_duration_changed)

        self.video_preview_dialog = None
        self.video_preview_widget = None
        self.video_preview_action = None
        self.current_media_is_video = False
        self.video_thumbnail_thread = None
        self.video_thumbnail_worker = None
        self.video_thumbnail_dir = None
        self._active_worker_threads = set()
        self.show_speaker_labels = True
        self.show_timestamps = True
        self.glossary = []
        self.language = "en"
        self.batch_active = False
        self.batch_queue = []
        self.batch_settings = {}
        self.batch_current = None
        self.batch_document_queue = []
        self.batch_document_state = None
        self._install_diagnostic_logging()

        from plugins.manager import PluginManager
        self.plugin_manager = PluginManager(self)
        self.plugins_project_data = {}

        self.build_ui()
        self.build_menus()
        self.plugin_manager.load_all_plugins()
        self.refresh_plugin_menus()
        self._check_external_dependencies()

        self.update_window_title()
        self._load_user_preferences()
        QTimer.singleShot(150, self.restore_last_opened)

        self.shortcut_find_next = QShortcut(platform_seq("Ctrl+G"), self)
        self.shortcut_find_next.activated.connect(self.trigger_find_next)

        self.log_activity("[SYSTEM] Application initialized.")
        self.statusBar().showMessage("Open a media file or create a new project to begin.")
        QTimer.singleShot(0, lambda: self.check_translation_models_async())
        QTimer.singleShot(3000, lambda: self.trigger_silent_update_check())

def main():
    if sys.platform == "win32":
        try:
            import ctypes
            app_id = f"radiotvsegmenter.radiotvstorysegmenter.app.{PROJECT_VERSION}"
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(app_id)
        except Exception:
            pass

    app = QApplication(sys.argv)
    app.setApplicationName(f"{APP_DISPLAY_NAME} v{PROJECT_VERSION}")
    app.setApplicationDisplayName(APP_DISPLAY_NAME)

    try:
        import qdarktheme
        if hasattr(qdarktheme, "setup_theme"):
            qdarktheme.setup_theme("dark", corner_shape="rounded", additional_qss=TARGETED_QSS)
        elif hasattr(qdarktheme, "load_stylesheet"):
            app.setStyleSheet(qdarktheme.load_stylesheet("dark") + "\n" + TARGETED_QSS)
        else:
            app.setStyleSheet(TARGETED_QSS)
    except ImportError:
        print("[THEME] Note: 'pyqtdarktheme' is not installed in this environment. Run 'pip install pyqtdarktheme pywinstyles' to enable modern dark theme styling.")
    except Exception as e:
        print(f"[THEME] Warning: Could not initialize qdarktheme: {e}")

    icon = get_app_icon()
    if not icon.isNull():
        app.setWindowIcon(icon)

    window = MainWindow()
    if not icon.isNull():
        window.setWindowIcon(icon)
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    raise SystemExit(main())
