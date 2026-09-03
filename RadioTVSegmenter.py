"""Radio & TV Segmenter — v1.6

This is the thin application composition root. UI/processing responsibilities
are implemented in focused mixins so future changes can target smaller files
without changing the MainWindow-facing API.
"""
import sys
from bootstrap import configure_runtime_environment

# Bootstrap lightweight core UI dependencies before importing third-party modules.
configure_runtime_environment()

# If invoked as a background AI worker subprocess, dispatch immediately without loading the GUI.
if len(sys.argv) > 1 and sys.argv[1] in ("--prs-worker", "--worker"):
    import radio_tv_story_segmenter_worker
    raise SystemExit(radio_tv_story_segmenter_worker.main(sys.argv[2:]))

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
        self.speaker_sensitivity = 8

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
        self.timeline_thumbnail_position = "above"

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

        self.build_ui()
        self.build_menus()
        self._check_external_dependencies()

        self.update_window_title()
        self._load_user_preferences()
        QTimer.singleShot(150, self.restore_last_opened)

        self.shortcut_find_next = QShortcut(QKeySequence("Ctrl+G"), self)
        self.shortcut_find_next.activated.connect(self.trigger_find_next)

        self.log_activity("[SYSTEM] Application initialized.")
        self.statusBar().showMessage("Open a media file or create a new project to begin.")
        QTimer.singleShot(0, lambda: self.check_translation_models_async())
        QTimer.singleShot(3000, lambda: self.trigger_silent_update_check())

    def _check_external_dependencies(self):
        """Check bundled media tools and record actionable diagnostics."""
        missing = []
        if ffmpeg_path() is None:
            missing.append("ffmpeg")
        if ffprobe_path() is None:
            missing.append("ffprobe")
        if missing:
            self.log_activity(
                "[DEPENDENCIES] Missing bundled media tool(s): " + ", ".join(missing) +
                ". Install media runtime components or place them in the application's runtime/bin folder.",
                mark_dirty=False,
            )
        else:
            self.log_activity("[DEPENDENCIES] FFmpeg and ffprobe detected.", mark_dirty=False)

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
