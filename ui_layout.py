"""Radio & TV Segmenter — UI Layout & Menu Construction Mixin.

Builds the main window visual hierarchy, menu bar, status bar, timeline canvas,
interactive transcript editor, story segmentation panel, and search bar.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from PySide6.QtCore import Qt, QUrl, QTimer, QSize
from PySide6.QtGui import QAction, QIcon, QKeySequence, QTextCursor
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QFileDialog,
    QFormLayout,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QMenu,
    QMenuBar,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QSplitter,
    QStatusBar,
    QVBoxLayout,
    QWidget,
)

from prs_shared import (
    FindReplaceDialog,
    InteractiveTranscriptEdit,
    StoryListWidget,
    TimelineWidget,
    ffmpeg_path,
    format_time,
    platform_seq,
    safe_filename,
)


class UiLayoutMixin:
    """Mixin class providing UI construction, menu assembly, and UI event binding."""

    def build_ui(self):
        """Build and assemble all central widgets, layouts, and panels."""
        central_widget = QWidget(self)
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(8, 8, 8, 8)
        main_layout.setSpacing(6)

        # -----------------------------------------------------------
        # Top Panel: Playback, Time, Save, Status, and Progress Bar
        # -----------------------------------------------------------
        self.top_panel = QWidget(self)
        top_panel = self.top_panel
        top_layout = QVBoxLayout(top_panel)
        top_layout.setContentsMargins(0, 0, 0, 0)
        top_layout.setSpacing(4)

        controls_row = QHBoxLayout()
        controls_row.setSpacing(8)

        self.play_button = QPushButton("Play", self)
        self.play_button.setMinimumWidth(80)
        self.play_button.clicked.connect(self.toggle_play)
        controls_row.addWidget(self.play_button)

        self.time_label = QLabel("00:00:00 / 00:00:00", self)
        self.time_label.setMinimumWidth(160)
        controls_row.addWidget(self.time_label)

        self.speaker_status = QLabel("Speaker detection has not been run.", self)
        self.speaker_status.setStyleSheet("color: #888888; font-size: 11px;")
        controls_row.addWidget(self.speaker_status)

        controls_row.addStretch()

        self.save_state_label = QLabel("", self)
        self.save_state_label.setStyleSheet("color: #888888; font-size: 11px;")
        controls_row.addWidget(self.save_state_label)

        self.quick_save_button = QPushButton("Save Project", self)
        self.quick_save_button.clicked.connect(self.save_project)
        controls_row.addWidget(self.quick_save_button)

        top_layout.addLayout(controls_row)

        # Progress / Pipeline Execution Bar (hidden by default)
        progress_row = QHBoxLayout()
        progress_row.setSpacing(8)

        self.processing_stage_label = QLabel("", self)
        self.processing_stage_label.setStyleSheet("font-weight: bold; color: #4a90e2;")
        progress_row.addWidget(self.processing_stage_label)

        self.progress_bar = QProgressBar(self)
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress = self.progress_bar  # Alias used in media_batch and processing
        progress_row.addWidget(self.progress_bar, 1)

        self.cancel_button = QPushButton("Cancel", self)
        self.cancel_button.clicked.connect(self.cancel_current_process)
        self.cancel_btn = self.cancel_button
        progress_row.addWidget(self.cancel_button)

        self.processing_stage_label.hide()
        self.progress_bar.hide()
        self.cancel_button.hide()

        top_layout.addLayout(progress_row)

        # Timeline and Waveform Canvas Widget
        self.timeline = TimelineWidget(self)
        self.timeline.setMinimumHeight(140)
        top_layout.addWidget(self.timeline)

        main_layout.addWidget(top_panel)

        # -----------------------------------------------------------
        # Center Panel: Splitter with Transcript View and Story Manager
        # -----------------------------------------------------------
        splitter = QSplitter(Qt.Orientation.Horizontal, self)
        splitter.setChildrenCollapsible(False)

        # Left Container: Search Header + Interactive Transcript
        self.transcript_panel = QWidget(self)
        left_widget = self.transcript_panel
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(6)

        search_bar = QHBoxLayout()
        search_bar.setSpacing(6)

        self.transcript_search_input = QLineEdit(self)
        self.transcript_search_input.setPlaceholderText("Search transcript...")
        self.transcript_search_input.returnPressed.connect(self.trigger_find_next)
        search_bar.addWidget(self.transcript_search_input, 1)

        self.find_next_btn = QPushButton("Find Next", self)
        self.find_next_btn.clicked.connect(self.trigger_find_next)
        search_bar.addWidget(self.find_next_btn)

        self.transcript_language_selector = QComboBox(self)
        self.transcript_language_selector.addItem("English (Original)", "en")
        self.transcript_language_selector.currentIndexChanged.connect(self.change_translation_display)
        search_bar.addWidget(self.transcript_language_selector)

        self.translate_button = QPushButton("Translate...", self)
        self.translate_button.clicked.connect(lambda: self.start_translation("en", "es"))
        search_bar.addWidget(self.translate_button)

        self.transcript_mode_toggle_btn = QPushButton("Viewing Mode", self)
        self.transcript_mode_toggle_btn.setCheckable(True)
        self.transcript_mode_toggle_btn.setChecked(False)
        self.transcript_mode_toggle_btn.setToolTip("Toggle between Viewing Mode (click to play/seek audio) and Editing Mode (type/edit transcript text).")
        self.transcript_mode_toggle_btn.clicked.connect(self.toggle_transcript_editing_mode)
        search_bar.addWidget(self.transcript_mode_toggle_btn)

        left_layout.addLayout(search_bar)

        self.transcript_view = InteractiveTranscriptEdit(self)
        left_layout.addWidget(self.transcript_view, 1)

        splitter.addWidget(left_widget)

        # Right Container: Stories List, Story Detail Inputs, and Activity History
        right_widget = QWidget(self)
        right_layout = QVBoxLayout(right_widget)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(6)

        # Stories Box
        self.stories_panel = QGroupBox("Stories & Segments", self)
        stories_box = self.stories_panel
        stories_box_layout = QVBoxLayout(stories_box)
        stories_box_layout.setContentsMargins(6, 8, 6, 6)
        stories_box_layout.setSpacing(4)

        self.story_list = StoryListWidget(self)
        self.story_list.setSelectionMode(StoryListWidget.SelectionMode.ExtendedSelection)
        stories_box_layout.addWidget(self.story_list, 1)

        # Story Edit Inputs
        form_layout = QFormLayout()
        form_layout.setContentsMargins(0, 4, 0, 4)
        form_layout.setSpacing(4)

        self.title_input = QLineEdit(self)
        self.title_input.setPlaceholderText("Story headline / title")
        self.title_input.editingFinished.connect(self.update_selected_story)
        form_layout.addRow("Title:", self.title_input)

        times_layout = QHBoxLayout()
        self.start_input = QLineEdit(self)
        self.start_input.setPlaceholderText("00:00:00")
        self.start_input.editingFinished.connect(self.update_selected_story)
        times_layout.addWidget(self.start_input)

        times_layout.addWidget(QLabel("to"))

        self.end_input = QLineEdit(self)
        self.end_input.setPlaceholderText("00:00:00")
        self.end_input.editingFinished.connect(self.update_selected_story)
        times_layout.addWidget(self.end_input)

        form_layout.addRow("Range:", times_layout)
        stories_box_layout.addLayout(form_layout)

        # Story action buttons
        story_btns_row = QHBoxLayout()
        story_btns_row.setSpacing(4)

        self.set_start_btn = QPushButton("Set Start", self)
        self.set_start_btn.setToolTip("Set start boundary to current playhead")
        self.set_start_btn.clicked.connect(self.set_story_start)
        story_btns_row.addWidget(self.set_start_btn)

        self.set_end_btn = QPushButton("Set End", self)
        self.set_end_btn.setToolTip("Set end boundary to current playhead")
        self.set_end_btn.clicked.connect(self.set_story_end)
        story_btns_row.addWidget(self.set_end_btn)

        self.add_story_btn = QPushButton("Add Story", self)
        self.add_story_btn.clicked.connect(self.add_story)
        story_btns_row.addWidget(self.add_story_btn)

        self.delete_story_btn = QPushButton("Delete", self)
        self.delete_story_btn.clicked.connect(self.delete_selected_story)
        story_btns_row.addWidget(self.delete_story_btn)

        stories_box_layout.addLayout(story_btns_row)
        right_layout.addWidget(stories_box, 2)

        # Activity / History Box
        self.activity_panel = QGroupBox("Activity History & Recovery", self)
        activity_box = self.activity_panel
        activity_box_layout = QVBoxLayout(activity_box)
        activity_box_layout.setContentsMargins(6, 8, 6, 6)
        activity_box_layout.setSpacing(4)

        self.activity_list = QListWidget(self)
        self.activity_list.itemClicked.connect(self.handle_activity_click)
        activity_box_layout.addWidget(self.activity_list, 1)

        act_btns_row = QHBoxLayout()
        clear_act_btn = QPushButton("Clear Log", self)
        clear_act_btn.clicked.connect(self.clear_activity_log)
        act_btns_row.addWidget(clear_act_btn)

        export_act_btn = QPushButton("Export Log...", self)
        export_act_btn.clicked.connect(self.export_activity_log)
        act_btns_row.addWidget(export_act_btn)

        activity_box_layout.addLayout(act_btns_row)
        right_layout.addWidget(activity_box, 1)

        splitter.addWidget(right_widget)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 2)

        main_layout.addWidget(splitter, 1)

        # Connect Timeline signals
        self.timeline.canvas.positionClicked.connect(self.seek_to)
        self.timeline.canvas.scrubPositionChanged.connect(self.handle_scrub_position)
        self.timeline.canvas.storyRegionUpdated.connect(self.handle_drag_story_region)
        self.timeline.canvas.newRegionStarted.connect(self.handle_new_story_started)
        self.timeline.canvas.newRegionUpdated.connect(self.handle_new_story_updated)
        self.timeline.canvas.multiSelectionChanged.connect(self.handle_timeline_multi_selection)
        self.timeline.canvas.dragOperationFinished.connect(self.handle_drag_finished)
        self.timeline.mediaDropped.connect(self.load_media_file)

        # Connect Transcript View signals
        self.transcript_view.linkClicked.connect(self.transcript_clicked)
        self.transcript_view.requestSplitAtCursor.connect(self.split_segment_at_time)
        self.transcript_view.requestInsertSpeaker.connect(self.handle_insert_speaker_request)
        self.transcript_view.requestRemoveSpeakerAtBlock.connect(self.remove_speaker_label_at_segment)
        self.transcript_view.textChanged.connect(self.on_transcript_text_changed)
        self.transcript_view.cursorPositionChanged.connect(self.on_transcript_selection_changed)
        self.transcript_view.editingModeChanged.connect(self._on_transcript_editing_mode_changed)

        # Connect Story List signals
        self.story_list.itemSelectionChanged.connect(self.story_selection_changed)
        self.story_list.deleteRequested.connect(self.delete_selected_story)
        self.story_list.exportRequested.connect(self.export_selected_stories)
        self.story_list.exportStoryWordPressRequested.connect(self.open_unified_export_dialog)

        # Initialize status bar
        self.statusBar().showMessage("Ready")

    def build_menus(self):
        """Construct the main application menu bar and associated keyboard shortcuts."""
        menubar = self.menuBar()
        menubar.clear()

        # ==========================================
        # File Menu
        # ==========================================
        file_menu = menubar.addMenu("&File")

        # 1. Media Input
        open_media_act = QAction("&Open Media...", self)
        open_media_act.setShortcut(QKeySequence.Open)
        open_media_act.triggered.connect(self.open_media)
        file_menu.addAction(open_media_act)

        open_doc_act = QAction("Open &Document...", self)
        open_doc_act.triggered.connect(self.open_document)
        file_menu.addAction(open_doc_act)

        file_menu.addSeparator()

        # 2. Project Creation & Loading
        new_proj_act = QAction("&New Project", self)
        new_proj_act.setShortcut(QKeySequence.New)
        new_proj_act.triggered.connect(self.new_project)
        file_menu.addAction(new_proj_act)

        open_proj_act = QAction("Open &Project...", self)
        open_proj_act.setShortcut(platform_seq("Ctrl+Shift+O"))
        open_proj_act.triggered.connect(self.open_project_dialog)
        file_menu.addAction(open_proj_act)

        self.recent_menu = file_menu.addMenu("Recent Projects")
        self._refresh_recent_projects_menu()

        close_proj_act = QAction("&Close Project", self)
        close_proj_act.setShortcut(QKeySequence.Close)
        close_proj_act.triggered.connect(self.close_project)
        file_menu.addAction(close_proj_act)

        file_menu.addSeparator()

        # 3. Project Persistence
        self.save_action = QAction("&Save Project", self)
        self.save_action.setShortcut(QKeySequence.Save)
        self.save_action.triggered.connect(self.save_project)
        file_menu.addAction(self.save_action)

        self.save_as_action = QAction("Save Project &As...", self)
        self.save_as_action.setShortcut(QKeySequence.SaveAs)
        self.save_as_action.triggered.connect(self.save_project_as)
        file_menu.addAction(self.save_as_action)

        file_menu.addSeparator()

        # 4. Export & Batch Processing
        export_act = QAction("&Export...", self)
        export_act.setShortcut(platform_seq("Ctrl+E"))
        export_act.triggered.connect(self.open_unified_export_dialog)
        file_menu.addAction(export_act)

        batch_act = QAction("&Batch Processing...", self)
        batch_act.setShortcut(platform_seq("Ctrl+Shift+B"))
        batch_act.triggered.connect(self.open_batch_processing_dialog)
        file_menu.addAction(batch_act)

        file_menu.addSeparator()

        # 5. Application Exit
        exit_act = QAction("E&xit", self)
        exit_act.setShortcut(QKeySequence.Quit)
        exit_act.triggered.connect(self.close)
        file_menu.addAction(exit_act)

        # ==========================================
        # Edit Menu
        # ==========================================
        edit_menu = menubar.addMenu("&Edit")

        self.undo_action = self.undo_stack.createUndoAction(self, "&Undo")
        self.undo_action.setShortcut(QKeySequence.Undo)
        edit_menu.addAction(self.undo_action)

        self.redo_action = self.undo_stack.createRedoAction(self, "&Redo")
        self.redo_action.setShortcut(QKeySequence.Redo)
        edit_menu.addAction(self.redo_action)

        edit_menu.addSeparator()

        find_act = QAction("&Find and Replace...", self)
        find_act.setShortcut(QKeySequence.Find)
        find_act.triggered.connect(self.open_find_dialog)
        edit_menu.addAction(find_act)

        # ==========================================
        # View Menu
        # ==========================================
        view_menu = menubar.addMenu("&View")

        # Main Panel Visibility Toggles (Alt+1-4 on Win/Linux, Ctrl+Alt+1-4 on Mac)
        panel_mod = "Ctrl+Alt" if sys.platform == "darwin" else "Alt"

        self.toggle_timeline_action = QAction("&Timeline Panel", self, checkable=True)
        self.toggle_timeline_action.setShortcut(QKeySequence(f"{panel_mod}+1"))
        self.toggle_timeline_action.setChecked(True)
        self.toggle_timeline_action.toggled.connect(lambda checked: self.top_panel.setVisible(checked))
        view_menu.addAction(self.toggle_timeline_action)

        self.toggle_transcript_action = QAction("&Transcript Panel", self, checkable=True)
        self.toggle_transcript_action.setShortcut(QKeySequence(f"{panel_mod}+2"))
        self.toggle_transcript_action.setChecked(True)
        self.toggle_transcript_action.toggled.connect(lambda checked: self.transcript_panel.setVisible(checked))
        view_menu.addAction(self.toggle_transcript_action)

        self.toggle_stories_action = QAction("&Stories Panel", self, checkable=True)
        self.toggle_stories_action.setShortcut(QKeySequence(f"{panel_mod}+3"))
        self.toggle_stories_action.setChecked(True)
        self.toggle_stories_action.toggled.connect(lambda checked: self.stories_panel.setVisible(checked))
        view_menu.addAction(self.toggle_stories_action)

        self.toggle_activity_action = QAction("&Activity History Panel", self, checkable=True)
        self.toggle_activity_action.setShortcut(QKeySequence(f"{panel_mod}+4"))
        self.toggle_activity_action.setChecked(True)
        self.toggle_activity_action.toggled.connect(lambda checked: self.activity_panel.setVisible(checked))
        view_menu.addAction(self.toggle_activity_action)

        view_menu.addSeparator()

        # 1. Timeline Submenu
        timeline_menu = view_menu.addMenu("&Timeline")

        self.show_waveform_action = QAction("Show &Waveform", self, checkable=True)
        self.show_waveform_action.setShortcut(platform_seq("Ctrl+Alt+W"))
        self.show_waveform_action.setChecked(getattr(self, "timeline_show_waveform", True))
        self.show_waveform_action.toggled.connect(self.toggle_waveform_view)
        timeline_menu.addAction(self.show_waveform_action)

        self.show_thumbnails_action = QAction("Show Video &Thumbnails", self, checkable=True)
        self.show_thumbnails_action.setShortcut(platform_seq("Ctrl+Alt+T"))
        self.show_thumbnails_action.setChecked(getattr(self, "timeline_show_thumbnails", True))
        self.show_thumbnails_action.toggled.connect(self.toggle_thumbnail_view)
        timeline_menu.addAction(self.show_thumbnails_action)

        timeline_menu.addSeparator()

        self.video_preview_action = QAction("&Video Preview Window", self, checkable=True)
        self.video_preview_action.setShortcut(platform_seq("Ctrl+Shift+M"))
        self.video_preview_action.setEnabled(False)
        self.video_preview_action.toggled.connect(self.toggle_video_preview)
        timeline_menu.addAction(self.video_preview_action)

        # 2. Transcript Submenu
        transcript_menu = view_menu.addMenu("T&ranscript")

        self.show_speaker_labels_action = QAction("Show &Speaker Labels", self, checkable=True)
        self.show_speaker_labels_action.setShortcut(platform_seq("Ctrl+Alt+S"))
        self.show_speaker_labels_action.setChecked(getattr(self, "show_speaker_labels", True))
        self.show_speaker_labels_action.toggled.connect(self.toggle_speaker_labels)
        transcript_menu.addAction(self.show_speaker_labels_action)

        self.show_timestamps_action = QAction("Show T&imestamps", self, checkable=True)
        self.show_timestamps_action.setShortcut(platform_seq("Ctrl+Alt+I"))
        self.show_timestamps_action.setChecked(getattr(self, "show_timestamps", True))
        self.show_timestamps_action.toggled.connect(self.toggle_timestamps)
        transcript_menu.addAction(self.show_timestamps_action)

        view_menu.addSeparator()

        theme_menu = view_menu.addMenu("&Theme")
        dark_theme_act = QAction("&Dark", self)
        dark_theme_act.triggered.connect(lambda: self.set_theme("dark"))
        theme_menu.addAction(dark_theme_act)

        light_theme_act = QAction("&Light", self)
        light_theme_act.triggered.connect(lambda: self.set_theme("light"))
        theme_menu.addAction(light_theme_act)

        hc_theme_act = QAction("&High Contrast", self)
        hc_theme_act.triggered.connect(lambda: self.set_theme("high_contrast"))
        theme_menu.addAction(hc_theme_act)

        # ==========================================
        # Tools Menu (AI Pipeline)
        # ==========================================
        tools_menu = menubar.addMenu("&Tools")

        self.transcribe_action = QAction("&Transcribe Audio (Whisper)...", self)
        self.transcribe_action.setEnabled(False)
        self.transcribe_action.triggered.connect(self.start_transcription)
        tools_menu.addAction(self.transcribe_action)

        self.diarize_action = QAction("Speaker &Diarization...", self)
        self.diarize_action.setEnabled(False)
        self.diarize_action.triggered.connect(self.start_diarization)
        tools_menu.addAction(self.diarize_action)

        self.auto_detect_action = QAction("&Auto-Detect Stories...", self)
        self.auto_detect_action.setEnabled(False)
        self.auto_detect_action.triggered.connect(self.start_auto_detect_stories)
        tools_menu.addAction(self.auto_detect_action)

        tools_menu.addSeparator()

        self.transcribe_diarize_action = QAction("Transcribe + Diari&ze...", self)
        self.transcribe_diarize_action.setEnabled(False)
        self.transcribe_diarize_action.triggered.connect(self.start_transcribe_and_diarize)
        tools_menu.addAction(self.transcribe_diarize_action)

        self.transcribe_diarize_detect_action = QAction("&Run Processing...", self)
        self.transcribe_diarize_detect_action.setEnabled(False)
        self.transcribe_diarize_detect_action.triggered.connect(self.start_full_auto_pipeline)
        tools_menu.addAction(self.transcribe_diarize_detect_action)

        tools_menu.addSeparator()

        self.translate_action = QAction("Translate &Transcript (OPUS-MT)...", self)
        self.translate_action.setEnabled(False)
        self.translate_action.triggered.connect(lambda: self.start_translation("en", "es"))
        tools_menu.addAction(self.translate_action)

        tools_menu.addSeparator()

        self.batch_processing_action = QAction("&Batch Processing...", self)
        self.batch_processing_action.triggered.connect(self.open_batch_processing_dialog)
        tools_menu.addAction(self.batch_processing_action)

       # ==========================================
        # Settings Menu
        # ==========================================
        settings_menu = menubar.addMenu("&Settings")

        pref_act = QAction("&Preferences...", self)
        # QKeySequence.Preferences maps automatically to Cmd+, on macOS and Ctrl+, on Windows/Linux
        pref_act.setShortcut(QKeySequence.Preferences)
        pref_act.triggered.connect(self.open_preferences_dialog)
        settings_menu.addAction(pref_act)

        wp_settings_act = QAction("&WordPress Export Settings...", self)
        wp_settings_act.triggered.connect(self._open_wp_settings)
        settings_menu.addAction(wp_settings_act)

        self.translation_model_action = QAction("&Manage AI Models...", self)
        self.translation_model_action.triggered.connect(self.open_translation_model_manager)
        settings_menu.addAction(self.translation_model_action)

        gpu_act = QAction("&GPU Acceleration Settings...", self)
        gpu_act.triggered.connect(self.open_gpu_acceleration_settings)
        settings_menu.addAction(gpu_act)

        glossary_act = QAction("&Glossary & Custom Vocabulary...", self)
        glossary_act.triggered.connect(self.open_glossary_dialog)
        settings_menu.addAction(glossary_act)

        settings_menu.addSeparator()

        update_act = QAction("Check for &Updates...", self)
        update_act.triggered.connect(self.check_for_updates)
        settings_menu.addAction(update_act)

        # ==========================================
        # Help Menu
        # ==========================================
        help_menu = menubar.addMenu("&Help")

        shortcuts_act = QAction("&Keyboard Shortcuts", self)
        # HelpContents maps to F1 on Windows/Linux, and Cmd+? on macOS (avoiding brightness key conflict)
        shortcuts_act.setShortcut(QKeySequence.HelpContents)
        shortcuts_act.triggered.connect(self.show_shortcuts_dialog)
        help_menu.addAction(shortcuts_act)

        help_menu.addSeparator()

        about_act = QAction("&About Radio & TV Story Segmenter", self)
        about_act.triggered.connect(self.show_about_dialog)
        help_menu.addAction(about_act)

        log_act = QAction("Open &Diagnostic Log Folder", self)
        log_act.triggered.connect(self.open_diagnostic_log_folder)
        help_menu.addAction(log_act)

        licenses_act = QAction("&Third-Party Licenses", self)
        licenses_act.triggered.connect(self.show_licenses_dialog)
        help_menu.addAction(licenses_act)

    def _refresh_recent_projects_menu(self):
        """Update recent projects submenu items based on user settings store."""
        if not hasattr(self, "recent_menu") or self.recent_menu is None:
            return
        self.recent_menu.clear()
        recent_paths = self.settings_store.value("recent_projects", [])
        if isinstance(recent_paths, str):
            try:
                recent_paths = json.loads(recent_paths)
            except Exception:
                recent_paths = []

        if not isinstance(recent_paths, list) or not recent_paths:
            empty_act = QAction("No Recent Projects", self)
            empty_act.setEnabled(False)
            self.recent_menu.addAction(empty_act)
            return

        for p_str in recent_paths:
            path = Path(p_str)
            label = path.name if path.name else str(path)
            act = QAction(label, self)
            act.setData(str(path))
            act.triggered.connect(
                lambda checked=False, target=str(path): self.load_project_file(
                    target, prompt=True, preserve_media=False
                )
            )
            self.recent_menu.addAction(act)

    def _check_external_dependencies(self):
        """Verify presence of FFmpeg and log guidance if missing."""
        ff = ffmpeg_path()
        if not ff:
            self.log_activity(
                "[WARNING] FFmpeg binary was not found. Please install FFmpeg for full audio and waveform support.",
                mark_dirty=False,
            )

    def _sync_undo_redo_actions(self):
        """Synchronize undo/redo action states with QUndoStack."""
        if hasattr(self, "undo_action") and hasattr(self, "undo_stack"):
            self.undo_action.setEnabled(self.undo_stack.canUndo())
            desc = self.undo_stack.undoText()
            self.undo_action.setText(f"&Undo {desc}".strip() if self.undo_stack.canUndo() else "&Undo")
        if hasattr(self, "redo_action") and hasattr(self, "undo_stack"):
            self.redo_action.setEnabled(self.undo_stack.canRedo())
            desc = self.undo_stack.redoText()
            self.redo_action.setText(f"&Redo {desc}".strip() if self.undo_stack.canRedo() else "&Redo")

    def _remember_directory(self, path):
        """Persist directory of chosen file to improve user file dialog experience."""
        if not path:
            return
        try:
            p = Path(path)
            folder = p if p.is_dir() else p.parent
            if folder.exists():
                self.settings_store.setValue("last_directory", str(folder))
        except Exception:
            pass

    def filter_transcript_search(self, target: str):
        """Highlight and focus next occurrence of search term in transcript text view."""
        if not target or not hasattr(self, "transcript_view"):
            return

        cursor = self.transcript_view.textCursor()
        document = self.transcript_view.document()
        found = document.find(target, cursor)
        if found.isNull():
            # Wrap around to document beginning
            cursor.setPosition(0)
            found = document.find(target, cursor)

        if not found.isNull():
            self.transcript_view.setTextCursor(found)
            self.transcript_view.ensureCursorVisible()
        else:
            self.statusBar().showMessage(f"No occurrences of '{target}' found.", 3000)

    def update_processing_menu_status(self):
        """Update label annotations on Tools actions reflecting pipeline stage completion."""
        status = getattr(self, "processing_status", {})
        has_transcription = bool(status.get("transcription"))
        has_diarization = bool(status.get("diarization"))
        has_stories = bool(status.get("stories"))

        if hasattr(self, "transcribe_action"):
            self.transcribe_action.setText("Transcribe Audio (Complete)" if has_transcription else "Transcribe Audio (Whisper)...")
        if hasattr(self, "diarize_action"):
            self.diarize_action.setText("Speaker Diarization (Complete)" if has_diarization else "Speaker Diarization...")
        if hasattr(self, "auto_detect_action"):
            self.auto_detect_action.setText("Auto-Detect Stories (Complete)" if has_stories else "Auto-Detect Stories...")

    def open_project_dialog(self):
        """Prompt user to open a project file (*.json)."""
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Open Project",
            self._dialog_directory(),
            "Project Files (*.json);;All Files (*.*)",
        )
        if file_path:
            self.load_project_file(file_path, prompt=True, preserve_media=False)

    def open_find_dialog(self):
        """Display the Find and Replace dialog window."""
        if not getattr(self, "find_dialog", None):
            self.find_dialog = FindReplaceDialog(self.transcript_view, self)
        self.find_dialog.show()
        self.find_dialog.raise_()
        self.find_dialog.activateWindow()

    def toggle_transcript_editing_mode(self):
        """Toggle between Viewing Mode (navigation/click-to-seek) and Editing Mode (text editing)."""
        if not hasattr(self, "transcript_view"):
            return
        new_mode = not getattr(self.transcript_view, "is_editing_mode", False)
        self.transcript_view.set_editing_mode(new_mode)

    def _on_transcript_editing_mode_changed(self, is_editing: bool):
        """Respond to changes in transcript edit vs view mode."""
        if hasattr(self, "transcript_mode_toggle_btn"):
            self.transcript_mode_toggle_btn.setChecked(is_editing)
            if is_editing:
                self.transcript_mode_toggle_btn.setText("Editing Mode")
                self.transcript_mode_toggle_btn.setStyleSheet("font-weight: bold; background-color: #2b5278; color: white;")
            else:
                self.transcript_mode_toggle_btn.setText("Viewing Mode")
                self.transcript_mode_toggle_btn.setStyleSheet("")

    def show_shortcuts_dialog(self):
        """Display a searchable or structured reference table of all active shortcuts."""
        from PySide6.QtWidgets import QDialog, QVBoxLayout, QTextBrowser, QDialogButtonBox

        dialog = QDialog(self)
        dialog.setWindowTitle("Keyboard Shortcuts")
        dialog.resize(620, 540)

        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(10)

        browser = QTextBrowser(dialog)
        browser.setOpenExternalLinks(False)
        browser.setStyleSheet("""
            QTextBrowser {
                font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Arial, sans-serif;
                font-size: 13px;
                padding: 10px;
            }
        """)

        is_mac = sys.platform == "darwin"
        cmd = "Cmd" if is_mac else "Ctrl"
        opt = "Option" if is_mac else "Alt"
        panel_mod = "Ctrl+Option" if is_mac else "Alt"
        help_key = "Cmd+?" if is_mac else "F1"
        pref_key = "Cmd+," if is_mac else "Ctrl+,"

        html_content = f"""
        <style>
            table {{ width: 100%; border-collapse: collapse; margin-bottom: 16px; }}
            th {{ text-align: left; padding: 6px 8px; border-bottom: 2px solid #555; }}
            td {{ padding: 5px 8px; border-bottom: 1px solid #333; }}
            kbd {{
                background-color: #2b303c;
                border: 1px solid #4f5666;
                border-radius: 4px;
                padding: 2px 6px;
                font-family: monospace;
                font-size: 12px;
                color: #e6edf3;
            }}
            h3 {{ margin-top: 14px; margin-bottom: 6px; color: #58a6ff; }}
        </style>

        <h3>Playback & Navigation</h3>
        <table>
            <tr><td><b>Play / Pause</b></td><td><kbd>Space</kbd> or <kbd>Media Play/Pause</kbd></td></tr>
            <tr><td><b>Skip Backward / Forward</b></td><td><kbd>Left</kbd> / <kbd>Right</kbd></td></tr>
            <tr><td><b>Seek to Start / End</b></td><td><kbd>Home</kbd> / <kbd>End</kbd></td></tr>
            <tr><td><b>Zoom In / Out on Timeline</b></td><td><kbd>+</kbd> / <kbd>-</kbd> or <kbd>Mouse Wheel</kbd></td></tr>
            <tr><td><b>Pan Timeline View</b></td><td><kbd>Shift + Wheel</kbd> or <kbd>Middle-Click Drag</kbd></td></tr>
        </table>

        <h3>File & Project</h3>
        <table>
            <tr><td><b>New Project</b></td><td><kbd>{cmd}+N</kbd></td></tr>
            <tr><td><b>Open Media File</b></td><td><kbd>{cmd}+O</kbd></td></tr>
            <tr><td><b>Open Project Session</b></td><td><kbd>{cmd}+Shift+O</kbd></td></tr>
            <tr><td><b>Close Project Session</b></td><td><kbd>{cmd}+W</kbd></td></tr>
            <tr><td><b>Save Project</b></td><td><kbd>{cmd}+S</kbd></td></tr>
            <tr><td><b>Save Project As...</b></td><td><kbd>{cmd}+Shift+S</kbd></td></tr>
            <tr><td><b>Export Dialog</b></td><td><kbd>{cmd}+E</kbd></td></tr>
            <tr><td><b>Batch Processing</b></td><td><kbd>{cmd}+Shift+B</kbd></td></tr>
            <tr><td><b>Preferences</b></td><td><kbd>{pref_key}</kbd></td></tr>
            <tr><td><b>Exit Application</b></td><td><kbd>{cmd}+Q</kbd></td></tr>
        </table>

        <h3>Panels & Views</h3>
        <table>
            <tr><td><b>Toggle Timeline Panel</b></td><td><kbd>{panel_mod}+1</kbd></td></tr>
            <tr><td><b>Toggle Transcript Panel</b></td><td><kbd>{panel_mod}+2</kbd></td></tr>
            <tr><td><b>Toggle Stories Panel</b></td><td><kbd>{panel_mod}+3</kbd></td></tr>
            <tr><td><b>Toggle Activity History Panel</b></td><td><kbd>{panel_mod}+4</kbd></td></tr>
            <tr><td><b>Toggle Waveform Display</b></td><td><kbd>{cmd}+{opt}+W</kbd></td></tr>
            <tr><td><b>Toggle Video Thumbnails</b></td><td><kbd>{cmd}+{opt}+T</kbd></td></tr>
            <tr><td><b>Toggle Video Preview Window</b></td><td><kbd>{cmd}+Shift+M</kbd></td></tr>
            <tr><td><b>Toggle Speaker Labels</b></td><td><kbd>{cmd}+{opt}+S</kbd></td></tr>
            <tr><td><b>Toggle Timestamps</b></td><td><kbd>{cmd}+{opt}+I</kbd></td></tr>
        </table>

        <h3>Editing & Transcript</h3>
        <table>
            <tr><td><b>Undo / Redo</b></td><td><kbd>{cmd}+Z</kbd> / <kbd>{cmd}+Y</kbd></td></tr>
            <tr><td><b>Find and Replace</b></td><td><kbd>{cmd}+F</kbd></td></tr>
            <tr><td><b>Find Next Match</b></td><td><kbd>{cmd}+G</kbd></td></tr>
            <tr><td><b>Insert Speaker Break (Edit Mode)</b></td><td><kbd>Shift+Enter</kbd></td></tr>
            <tr><td><b>Insert Timestamp Line (Edit Mode)</b></td><td><kbd>Enter</kbd></td></tr>
            <tr><td><b>Exit Editing Mode</b></td><td><kbd>Esc</kbd></td></tr>
            <tr><td><b>Keyboard Shortcuts Reference</b></td><td><kbd>{help_key}</kbd></td></tr>
        </table>
        """

        browser.setHtml(html_content)
        layout.addWidget(browser)

        button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Close, dialog)
        button_box.rejected.connect(dialog.accept)
        layout.addWidget(button_box)

        dialog.exec()