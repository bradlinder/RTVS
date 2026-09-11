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
from PySide6.QtGui import QAction, QActionGroup, QIcon, QKeySequence, QTextCursor, QShortcut
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QFileDialog,
    QFormLayout,
    QFrame,
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
    ffprobe_path,
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
        # Top Controls: Playback, Time, Save, and Status
        # -----------------------------------------------------------
        self.controls_panel = QWidget(self)
        self.controls_panel.setObjectName("controls_panel")
        controls_panel_layout = QVBoxLayout(self.controls_panel)
        controls_panel_layout.setContentsMargins(0, 0, 0, 0)
        controls_panel_layout.setSpacing(4)

        controls_row = QHBoxLayout()
        controls_row.setSpacing(8)

        self.play_button = QPushButton("Play", self)
        self.play_button.setObjectName("play_button")
        self.play_button.setMinimumWidth(80)
        self.play_button.clicked.connect(self.toggle_play)
        controls_row.addWidget(self.play_button)

        self.time_label = QLabel("00:00:00 / 00:00:00", self)
        self.time_label.setObjectName("time_label")
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
        self.quick_save_button.setObjectName("quick_save_button")
        self.quick_save_button.clicked.connect(self.save_project)
        controls_row.addWidget(self.quick_save_button)

        controls_panel_layout.addLayout(controls_row)
        main_layout.addWidget(self.controls_panel)

        # -----------------------------------------------------------
        # Progress / Pipeline Execution Bar (Always visible when active,
        # independent of whether the timeline widget is shown or hidden)
        # -----------------------------------------------------------
        self.progress_panel = QWidget(self)
        self.progress_panel.setObjectName("progress_panel")
        progress_panel_layout = QVBoxLayout(self.progress_panel)
        progress_panel_layout.setContentsMargins(0, 0, 0, 0)
        progress_panel_layout.setSpacing(4)

        progress_row = QHBoxLayout()
        progress_row.setSpacing(8)

        self.processing_stage_label = QLabel("", self)
        self.processing_stage_label.setObjectName("processing_stage_label")
        self.processing_stage_label.setStyleSheet("font-weight: bold; color: #4a90e2;")
        progress_row.addWidget(self.processing_stage_label)

        self.progress_bar = QProgressBar(self)
        self.progress_bar.setObjectName("progress_bar")
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress = self.progress_bar  # Alias used in media_batch and processing
        progress_row.addWidget(self.progress_bar, 1)

        self.cancel_button = QPushButton("Cancel", self)
        self.cancel_button.setObjectName("cancel_button")
        self.cancel_button.clicked.connect(self.cancel_current_process)
        self.cancel_btn = self.cancel_button
        progress_row.addWidget(self.cancel_button)

        self.processing_stage_label.hide()
        self.progress_bar.hide()
        self.cancel_button.hide()

        progress_panel_layout.addLayout(progress_row)
        main_layout.addWidget(self.progress_panel)

        # -----------------------------------------------------------
        # Timeline and Waveform Canvas Widget
        # -----------------------------------------------------------
        self.timeline = TimelineWidget(self)
        self.timeline.setObjectName("timeline_widget")
        self.top_panel = self.timeline  # Compatibility alias
        main_layout.addWidget(self.timeline)

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
        self.transcript_search_input.setObjectName("transcript_search_input")
        self.transcript_search_input.setPlaceholderText("Search transcript...")
        self.transcript_search_input.returnPressed.connect(self.trigger_find_next)
        search_bar.addWidget(self.transcript_search_input, 1)

        self.find_next_btn = QPushButton("Find Next", self)
        self.find_next_btn.setObjectName("find_next_btn")
        self.find_next_btn.clicked.connect(self.trigger_find_next)
        search_bar.addWidget(self.find_next_btn)

        self.transcript_language_selector = QComboBox(self)
        self.transcript_language_selector.addItem("English (Original)", "en")
        self.transcript_language_selector.currentIndexChanged.connect(self.change_translation_display)
        search_bar.addWidget(self.transcript_language_selector)

        self.translate_button = QPushButton("Translate...", self)
        self.translate_button.setObjectName("translate_button")
        self.translate_button.clicked.connect(lambda: self.start_translation("en", "es"))
        search_bar.addWidget(self.translate_button)

        self.transcript_mode_toggle_btn = QPushButton("Edit Transcript", self)
        self.transcript_mode_toggle_btn.setCheckable(True)
        self.transcript_mode_toggle_btn.setChecked(False)
        self.transcript_mode_toggle_btn.setToolTip("Click to edit transcript text.")
        self.transcript_mode_toggle_btn.clicked.connect(self.toggle_transcript_editing_mode)
        search_bar.addWidget(self.transcript_mode_toggle_btn)

        # Compact transcript font controls. The font size is independent of the
        # rest of the application and is persisted between sessions.
        self.transcript_font_down_btn = QPushButton("A−", self)
        self.transcript_font_down_btn.setObjectName("transcript_font_down_btn")
        self.transcript_font_down_btn.setToolTip("Decrease transcript font size")
        self.transcript_font_down_btn.clicked.connect(lambda: self.adjust_transcript_font_size(-1))
        search_bar.addWidget(self.transcript_font_down_btn)

        self.transcript_font_reset_btn = QPushButton("A", self)
        self.transcript_font_reset_btn.setObjectName("transcript_font_reset_btn")
        self.transcript_font_reset_btn.setToolTip("Reset transcript font size")
        self.transcript_font_reset_btn.clicked.connect(self.reset_transcript_font_size)
        search_bar.addWidget(self.transcript_font_reset_btn)

        self.transcript_font_up_btn = QPushButton("A+", self)
        self.transcript_font_up_btn.setObjectName("transcript_font_up_btn")
        self.transcript_font_up_btn.setToolTip("Increase transcript font size")
        self.transcript_font_up_btn.clicked.connect(lambda: self.adjust_transcript_font_size(1))
        search_bar.addWidget(self.transcript_font_up_btn)

        left_layout.addLayout(search_bar)

        self.transcript_view = InteractiveTranscriptEdit(self)
        self.transcript_view.setObjectName("transcript_view")
        self.transcript_view.set_font_scale(getattr(self, "transcript_font_scale", 1.0))
        left_layout.addWidget(self.transcript_view, 1)

        splitter.addWidget(left_widget)

        # Right Container: Vertical Splitter dividing Stories List and Activity History
        self.right_splitter = QSplitter(Qt.Orientation.Vertical, self)
        self.right_splitter.setObjectName("right_splitter")
        self.right_splitter.setChildrenCollapsible(False)

        # Stories Box
        self.stories_panel = QWidget(self)
        self.stories_panel.setObjectName("stories_panel")
        self.stories_panel.setMinimumHeight(150)
        stories_box = self.stories_panel
        stories_box_layout = QVBoxLayout(stories_box)
        stories_box_layout.setContentsMargins(8, 8, 8, 8)
        stories_box_layout.setSpacing(6)
        self.stories_header = QLabel("Stories", stories_box)
        self.stories_header.setObjectName("stories_section_header")
        stories_box_layout.addWidget(self.stories_header)
        stories_box_layout.setContentsMargins(6, 8, 6, 6)
        stories_box_layout.setSpacing(4)

        self.story_list = StoryListWidget(self)
        self.story_list.setObjectName("story_list")
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

        # Boundary Buttons Container (Visible only when exactly one story is selected)
        self.story_boundary_container = QWidget(self)
        self.story_boundary_container.setObjectName("story_boundary_container")
        boundary_layout = QHBoxLayout(self.story_boundary_container)
        boundary_layout.setContentsMargins(0, 0, 0, 0)
        boundary_layout.setSpacing(4)

        self.set_story_start_btn = QPushButton("Set Story Start", self.story_boundary_container)
        self.set_story_start_btn.setObjectName("set_story_start_btn")
        self.set_story_start_btn.setToolTip("Set start time of selected story to current transcript or timeline position")
        self.set_story_start_btn.clicked.connect(self.set_selected_story_start)
        boundary_layout.addWidget(self.set_story_start_btn)

        self.set_story_end_btn = QPushButton("Set Story End", self.story_boundary_container)
        self.set_story_end_btn.setObjectName("set_story_end_btn")
        self.set_story_end_btn.setToolTip("Set end time of selected story to current transcript or timeline position")
        self.set_story_end_btn.clicked.connect(self.set_selected_story_end)
        boundary_layout.addWidget(self.set_story_end_btn)

        self.story_boundary_container.hide()
        stories_box_layout.addWidget(self.story_boundary_container)

        # Story action buttons
        story_btns_row = QHBoxLayout()
        story_btns_row.setSpacing(4)

        self.add_story_btn = QPushButton("Add Story", self)
        self.add_story_btn.setObjectName("add_story_btn")
        self.add_story_btn.setToolTip("Add story from active timeline selection or highlighted transcript text")
        self.add_story_btn.clicked.connect(self.add_story_from_active_selection)
        story_btns_row.addWidget(self.add_story_btn)

        self.select_all_stories_btn = QPushButton("Select All", self)
        self.select_all_stories_btn.setObjectName("select_all_stories_btn")
        self.select_all_stories_btn.setToolTip("Select all stories in the list")
        self.select_all_stories_btn.clicked.connect(self.select_all_stories)
        story_btns_row.addWidget(self.select_all_stories_btn)

        self.delete_story_btn = QPushButton("Delete", self)
        self.delete_story_btn.setObjectName("delete_story_btn")
        self.delete_story_btn.clicked.connect(self.delete_selected_story)
        story_btns_row.addWidget(self.delete_story_btn)

        self.export_stories_btn = QPushButton("Export...", self)
        self.export_stories_btn.setObjectName("export_stories_btn")
        self.export_stories_btn.setToolTip("Export full episode, selected stories, or draft to WordPress")
        self.export_stories_btn.clicked.connect(self.open_unified_export_dialog)
        story_btns_row.addWidget(self.export_stories_btn)
        
        stories_box_layout.addLayout(story_btns_row)
        self.right_splitter.addWidget(stories_box)

        # Activity / History Box
        self.activity_panel = QWidget(self)
        self.activity_panel.setObjectName("activity_panel")
        self.activity_panel.setMinimumHeight(90)
        activity_box = self.activity_panel
        activity_box_layout = QVBoxLayout(activity_box)
        activity_box_layout.setContentsMargins(8, 8, 8, 8)
        activity_box_layout.setSpacing(6)
        activity_header = QLabel("Activity History & Recovery", activity_box)
        activity_header.setObjectName("activity_section_header")
        activity_box_layout.addWidget(activity_header)
        activity_box_layout.setContentsMargins(6, 8, 6, 6)
        activity_box_layout.setSpacing(4)

        self.activity_list = QListWidget(self)
        self.activity_list.itemClicked.connect(self.handle_activity_click)
        activity_box_layout.addWidget(self.activity_list, 1)

        act_btns_row = QHBoxLayout()
        clear_act_btn = QPushButton("Clear Log", self)
        clear_act_btn.setObjectName("clear_activity_btn")
        clear_act_btn.clicked.connect(self.clear_activity_log)
        act_btns_row.addWidget(clear_act_btn)

        export_act_btn = QPushButton("Export Log...", self)
        export_act_btn.setObjectName("export_activity_btn")
        export_act_btn.clicked.connect(self.export_activity_log)
        act_btns_row.addWidget(export_act_btn)

        activity_box_layout.addLayout(act_btns_row)
        self.right_splitter.addWidget(activity_box)

        self.right_splitter.setStretchFactor(0, 3)
        self.right_splitter.setStretchFactor(1, 2)

        splitter.addWidget(self.right_splitter)
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
        self.timeline.canvas.storyClicked.connect(self.on_timeline_story_clicked)
        self.timeline.canvas.dragOperationFinished.connect(self.handle_drag_finished)
        self.timeline.mediaDropped.connect(self.load_media_file)
        
        self.timeline.selectionRangeChanged.connect(self.handle_timeline_selection_range_changed)
        self.timeline.storyCreatedFromSelection.connect(self.add_story_from_range)

        # Connect Transcript View signals
        self.transcript_view.linkClicked.connect(self.transcript_clicked)
        self.transcript_view.requestSplitAtCursor.connect(self.split_segment_at_time)
        self.transcript_view.requestInsertSpeaker.connect(self.handle_insert_speaker_request)
        self.transcript_view.requestRemoveSpeakerAtBlock.connect(self.remove_speaker_label_at_segment)
        self.transcript_view.textChanged.connect(self.on_transcript_text_changed)
        self.transcript_view.cursorPositionChanged.connect(self.on_transcript_selection_changed)
        self.transcript_view.editingModeChanged.connect(self._on_transcript_editing_mode_changed)

        # Transcript zoom shortcuts. Use platform_seq so Ctrl becomes Command on macOS.
        self.shortcut_transcript_font_up = QShortcut(platform_seq("Ctrl++"), self)
        self.shortcut_transcript_font_up.activated.connect(lambda: self.adjust_transcript_font_size(1))
        self.shortcut_transcript_font_down = QShortcut(platform_seq("Ctrl+-"), self)
        self.shortcut_transcript_font_down.activated.connect(lambda: self.adjust_transcript_font_size(-1))
        self.shortcut_transcript_font_reset = QShortcut(platform_seq("Ctrl+0"), self)
        self.shortcut_transcript_font_reset.activated.connect(self.reset_transcript_font_size)

        # Connect Story List signals
        self.story_list.itemSelectionChanged.connect(self.story_selection_changed)
        self.story_list.deleteRequested.connect(self.delete_selected_story)
        self.story_list.exportRequested.connect(self.export_selected_stories)
        self.story_list.exportStoryWordPressRequested.connect(self.open_unified_export_dialog)

        # Initialize status bar
        self.statusBar().showMessage("Ready")

        # Update terminology (Story vs. Segment) based on initial detection mode
        if hasattr(self, "update_story_segment_terminology"):
            self.update_story_segment_terminology()

    def build_menus(self):
        """Construct the main application menu bar and associated keyboard shortcuts."""
        menubar = self.menuBar()
        menubar.clear()

        # ==========================================
        # File Menu
        # NOTE FOR FUTURE MENU ADDITIONS: Every action added to any menu MUST have an explicit
        # keyboard shortcut assigned via platform_seq(...) or QKeySequence, and MUST be documented
        # in show_shortcuts_dialog() and the README.
        # ==========================================
        file_menu = menubar.addMenu("&File")

        # 1. Media Input
        open_media_act = QAction("&Open Media...", self)
        open_media_act.setShortcut(QKeySequence.Open)
        open_media_act.triggered.connect(self.open_media)
        self.open_media_action = open_media_act
        file_menu.addAction(open_media_act)

        open_doc_act = QAction("Open &Document...", self)
        open_doc_act.setShortcut(platform_seq("Ctrl+Alt+O"))
        open_doc_act.triggered.connect(self.open_document)
        self.open_doc_action = open_doc_act
        file_menu.addAction(open_doc_act)

        file_menu.addSeparator()

        # 2. Project Creation & Loading
        new_proj_act = QAction("&New Project", self)
        new_proj_act.setShortcut(QKeySequence.New)
        new_proj_act.triggered.connect(self.new_project)
        self.new_proj_action = new_proj_act
        file_menu.addAction(new_proj_act)

        open_proj_act = QAction("Open &Project...", self)
        open_proj_act.setShortcut(platform_seq("Ctrl+Shift+O"))
        open_proj_act.triggered.connect(self.open_project_dialog)
        self.open_proj_action = open_proj_act
        file_menu.addAction(open_proj_act)

        self.recent_menu = file_menu.addMenu("Recent Projects")
        self._refresh_recent_projects_menu()

        close_proj_act = QAction("&Close Project", self)
        close_proj_act.setShortcut(QKeySequence.Close)
        close_proj_act.triggered.connect(self.close_project)
        self.close_proj_action = close_proj_act
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
        self.export_action = export_act
        file_menu.addAction(export_act)

        batch_act = QAction("&Batch Processing...", self)
        batch_act.setShortcut(platform_seq("Ctrl+Shift+B"))
        batch_act.triggered.connect(self.open_batch_processing_dialog)
        self.batch_file_action = batch_act
        file_menu.addAction(batch_act)

        self.plugins_export_menu = file_menu.addMenu("Publishing & Plugins")

        file_menu.addSeparator()

        # 5. Application Exit
        exit_act = QAction("E&xit", self)
        exit_act.setShortcut(QKeySequence.Quit)
        exit_act.triggered.connect(self.close)
        self.exit_action = exit_act
        file_menu.addAction(exit_act)

        # ==========================================
        # Edit Menu
        # ==========================================
        edit_menu = menubar.addMenu("&Edit")

        self.undo_action = self.undo_stack.createUndoAction(self, "&Undo")
        self.undo_action.setShortcut(QKeySequence.Undo)
        edit_menu.addAction(self.undo_action)

        self.redo_action = self.undo_stack.createRedoAction(self, "&Redo")
        self.redo_action.setShortcuts([QKeySequence.Redo, QKeySequence("Ctrl+Y")])
        edit_menu.addAction(self.redo_action)

        edit_menu.addSeparator()

        find_act = QAction("&Find and Replace...", self)
        find_act.setShortcut(QKeySequence.Find)
        find_act.triggered.connect(self.open_find_dialog)
        self.find_action = find_act
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
        self.toggle_timeline_action.toggled.connect(lambda checked: self.timeline.setVisible(checked))
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
        self.tools_menu = tools_menu
        self.plugin_tools_actions = []

        self.transcribe_action = QAction("&Transcribe Audio...", self)
        self.transcribe_action.setShortcut(platform_seq("Ctrl+T"))
        self.transcribe_action.setEnabled(False)
        self.transcribe_action.triggered.connect(self.start_transcription)
        tools_menu.addAction(self.transcribe_action)

        self.diarize_action = QAction("&Detect Speakers...", self)
        self.diarize_action.setShortcut(platform_seq("Ctrl+D"))
        self.diarize_action.setEnabled(False)
        self.diarize_action.triggered.connect(self.start_diarization)
        tools_menu.addAction(self.diarize_action)

        self.auto_detect_action = QAction("&Detect Stories...", self)
        self.auto_detect_action.setShortcut(platform_seq("Ctrl+Shift+A"))
        self.auto_detect_action.setEnabled(False)
        self.auto_detect_action.triggered.connect(self.start_auto_detect_stories)
        tools_menu.addAction(self.auto_detect_action)

        self.translate_action = QAction("&Translate...", self)
        self.translate_action.setShortcut(platform_seq("Ctrl+Shift+L"))
        self.translate_action.setEnabled(False)
        self.translate_action.triggered.connect(lambda: self.start_translation("en", "es"))
        self.tools_translate_action = self.translate_action
        self.translate_action.setVisible(False)
        tools_menu.addAction(self.translate_action)

        tools_menu.addSeparator()

        # Retained as an instance attribute so set_tools_actions_enabled() calls do not fail
        self.transcribe_diarize_action = QAction("Transcribe && Detect &Speakers...", self)
        self.transcribe_diarize_action.setEnabled(False)
        self.transcribe_diarize_action.triggered.connect(self.start_transcribe_and_diarize)

        self.transcribe_diarize_detect_action = QAction("&Multi-Stage Processing...", self)
        self.transcribe_diarize_detect_action.setShortcut(platform_seq("Ctrl+R"))
        self.transcribe_diarize_detect_action.setEnabled(False)
        self.transcribe_diarize_detect_action.triggered.connect(self.start_full_auto_pipeline)
        tools_menu.addAction(self.transcribe_diarize_detect_action)

        tools_menu.addSeparator()

        self.batch_processing_action = QAction("&Batch Processing...", self)
        self.batch_processing_action.setShortcut(platform_seq("Ctrl+B"))
        self.batch_processing_action.triggered.connect(self.open_batch_processing_dialog)
        tools_menu.addAction(self.batch_processing_action)

        tools_menu.addSeparator()

        self.regen_waveform_action = QAction("&Regenerate Waveform", self)
        self.regen_waveform_action.setShortcut(platform_seq("Ctrl+Shift+W"))
        self.regen_waveform_action.setEnabled(False)
        self.regen_waveform_action.triggered.connect(self.regenerate_waveform)
        tools_menu.addAction(self.regen_waveform_action)

        self.regen_thumbnails_action = QAction("Regenerate Video &Thumbnails", self)
        self.regen_thumbnails_action.setShortcut(platform_seq("Ctrl+Shift+T"))
        self.regen_thumbnails_action.setEnabled(False)
        self.regen_thumbnails_action.triggered.connect(self.regenerate_video_thumbnails)
        tools_menu.addAction(self.regen_thumbnails_action)

        self.clear_cache_action = QAction("&Clear Temporary Cache...", self)
        self.clear_cache_action.setShortcut(platform_seq("Ctrl+Alt+C"))
        self.clear_cache_action.triggered.connect(self.open_clear_cache_dialog)
        tools_menu.addAction(self.clear_cache_action)

        tools_menu.addSeparator()

        self.manage_models_action = QAction("&Manage AI Models...", self)
        self.manage_models_action.setShortcut(platform_seq("Ctrl+M"))
        self.manage_models_action.triggered.connect(self.open_model_cleanup_dialog)
        self.translation_model_action = self.manage_models_action
        tools_menu.addAction(self.manage_models_action)

        self.manage_plugins_action = QAction("&Manage Plugins && Add-ons...", self)
        self.manage_plugins_action.setShortcut(platform_seq("Ctrl+Shift+X"))
        self.manage_plugins_action.triggered.connect(self.open_plugins_manager)
        tools_menu.addAction(self.manage_plugins_action)

        # ==========================================
        # Settings Menu
        # ==========================================
        settings_menu = menubar.addMenu("&Settings")

        pref_act = QAction("&Preferences...", self)
        # Ctrl+P on Windows/Linux, Cmd+P on macOS (platform_seq automatically adapts Meta/Ctrl)
        pref_act.setShortcut(platform_seq("Ctrl+P"))
        pref_act.triggered.connect(self.open_preferences_dialog)
        self.pref_action = pref_act
        settings_menu.addAction(pref_act)

        shortcuts_pref_act = QAction("Customize &Keyboard Shortcuts...", self)
        shortcuts_pref_act.setShortcut(platform_seq("Ctrl+K"))
        shortcuts_pref_act.triggered.connect(lambda: self.open_preferences_dialog(initial_category="Keyboard Shortcuts"))
        self.shortcuts_pref_action = shortcuts_pref_act
        settings_menu.addAction(shortcuts_pref_act)

        clear_cache_settings_act = QAction("Clear &Temporary Cache...", self)
        clear_cache_settings_act.setShortcut(platform_seq("Ctrl+Alt+C"))
        clear_cache_settings_act.triggered.connect(self.open_clear_cache_dialog)
        settings_menu.addAction(clear_cache_settings_act)

        settings_menu.addAction(self.manage_models_action)

        gpu_act = QAction("&GPU Acceleration Settings...", self)
        gpu_act.setShortcut(platform_seq("Ctrl+Alt+G"))
        gpu_act.triggered.connect(self.open_gpu_acceleration_settings)
        self.gpu_action = gpu_act
        settings_menu.addAction(gpu_act)

        glossary_act = QAction("&Glossary & Custom Vocabulary...", self)
        glossary_act.setShortcut(platform_seq("Ctrl+Shift+G"))
        glossary_act.triggered.connect(self.open_glossary_dialog)
        self.glossary_action = glossary_act
        settings_menu.addAction(glossary_act)

        # Language submenu in Settings menu
        self.language_menu = settings_menu.addMenu("&Language / Idioma")
        self.lang_action_group = QActionGroup(self)
        self.lang_action_group.setExclusive(True)

        self.lang_en_action = QAction("English", self, checkable=True)
        self.lang_en_action.setChecked(getattr(self, "language", "en") != "es")
        self.lang_en_action.triggered.connect(lambda: self.set_language("en"))
        self.lang_action_group.addAction(self.lang_en_action)
        self.language_menu.addAction(self.lang_en_action)

        self.lang_es_action = QAction("Español (Spanish)", self, checkable=True)
        self.lang_es_action.setChecked(getattr(self, "language", "en") == "es")
        self.lang_es_action.triggered.connect(lambda: self.set_language("es"))
        self.lang_action_group.addAction(self.lang_es_action)
        self.language_menu.addAction(self.lang_es_action)

        settings_menu.addSeparator()

        update_act = QAction("Check for &Updates...", self)
        update_act.setShortcut(platform_seq("Ctrl+U"))
        update_act.triggered.connect(self.check_for_updates)
        self.update_action = update_act
        settings_menu.addAction(update_act)

        # ==========================================
        # Help Menu
        # ==========================================
        help_menu = menubar.addMenu("&Help")

        shortcuts_act = QAction("&Keyboard Shortcuts", self)
        # HelpContents maps to F1 on Windows/Linux, and Cmd+? on macOS (avoiding brightness key conflict)
        shortcuts_act.setShortcut(QKeySequence.HelpContents)
        shortcuts_act.triggered.connect(self.show_shortcuts_dialog)
        self.shortcuts_help_action = shortcuts_act
        help_menu.addAction(shortcuts_act)

        help_menu.addSeparator()

        about_act = QAction("&About Radio & TV Story Segmenter", self)
        about_act.setShortcut(platform_seq("Shift+F1"))
        about_act.triggered.connect(self.show_about_dialog)
        self.about_action = about_act
        help_menu.addAction(about_act)

        log_act = QAction("Open &Diagnostic Log Folder", self)
        log_act.setShortcut(platform_seq("Ctrl+Shift+K"))
        log_act.triggered.connect(self.open_diagnostic_log_folder)
        self.log_action = log_act
        help_menu.addAction(log_act)

        licenses_act = QAction("&Third-Party Licenses", self)
        licenses_act.setShortcut(platform_seq("Ctrl+Shift+F1"))
        licenses_act.triggered.connect(self.show_licenses_dialog)
        self.licenses_action = licenses_act
        help_menu.addAction(licenses_act)

        # Apply any saved user custom keyboard shortcut mappings
        self.apply_user_shortcuts()

    def apply_user_shortcuts(self):
        """Rebind all menu actions and application shortcuts according to user preferences."""
        if not hasattr(self, "shortcuts_manager") or not self.shortcuts_manager:
            from shortcuts_manager import ShortcutsManager
            self.shortcuts_manager = ShortcutsManager(getattr(self, "settings_store", None))
        self.shortcuts_manager.apply_to_window(self)

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
            self.transcribe_action.setText("Transcribe Audio (Complete)" if has_transcription else "Transcribe Audio...")
        if hasattr(self, "diarize_action"):
            self.diarize_action.setText("Detect Speakers (Complete)" if has_diarization else "Detect Speakers...")
        if hasattr(self, "auto_detect_action"):
            is_music = (getattr(self, "story_detection_mode", "voice") == "music")
            is_es = (getattr(self, "language", "en") == "es")
            if is_music:
                if is_es:
                    self.auto_detect_action.setText("&Detectar canciones (Completado)" if has_stories else "&Detectar canciones...")
                else:
                    self.auto_detect_action.setText("Detect Songs (Complete)" if has_stories else "&Detect Songs...")
            else:
                if is_es:
                    self.auto_detect_action.setText("&Detectar historias (Completado)" if has_stories else "&Detectar historias...")
                else:
                    self.auto_detect_action.setText("Detect Stories (Complete)" if has_stories else "&Detect Stories...")

    def open_project_dialog(self):
        """Prompt user to open a project file (*.rtvs)."""
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Open Project",
            self._dialog_directory(),
            "RadioTV Story Segmenter Projects (*.rtvs);;Legacy Projects (*.json);;All Files (*.*)",
        )
        if file_path:
            try:
                directory = str(Path(file_path).resolve().parent)
                self.settings_store.setValue("last_open_directory", directory)
                self.settings_store.sync()
            except Exception:
                pass
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
        if getattr(self, "translation_display_mode", "en") != "en":
            if hasattr(self, "statusBar"):
                self.statusBar().showMessage("Editing is only available in English (Original) view.")
            return
        new_mode = not getattr(self.transcript_view, "is_editing_mode", False)
        self.transcript_view.set_editing_mode(new_mode)

    def _on_transcript_editing_mode_changed(self, is_editing: bool):
        """Respond to changes in transcript edit vs view mode."""
        if hasattr(self, "transcript_mode_toggle_btn"):
            self.transcript_mode_toggle_btn.setChecked(is_editing)
            if is_editing:
                self.transcript_mode_toggle_btn.setText("View Transcript")
                self.transcript_mode_toggle_btn.setToolTip("Click to exit editing mode and return to interactive viewing.")
                self.transcript_mode_toggle_btn.setStyleSheet("font-weight: bold; background-color: #2b5278; color: white;")
            else:
                self.transcript_mode_toggle_btn.setText("Edit Transcript")
                self.transcript_mode_toggle_btn.setToolTip("Click to edit transcript text.")
                self.transcript_mode_toggle_btn.setStyleSheet("")
        if not is_editing and hasattr(self, "render_transcript"):
            # Re-render so word-level clickable anchors and highlights are freshly constructed
            self.render_transcript()

    def _apply_transcript_font_scale(self, scale, persist=True):
        """Apply a transcript-only font scale and optionally persist it."""
        scale = max(0.80, min(1.80, float(scale)))
        # Snap to 5% increments for predictable keyboard/button behavior.
        scale = round(scale / 0.05) * 0.05
        self.transcript_font_scale = scale
        if hasattr(self, "transcript_view"):
            self.transcript_view.set_font_scale(scale)
        if persist and hasattr(self, "settings_store"):
            self.settings_store.setValue("transcript_font_scale", scale)
            self.settings_store.sync()
        if hasattr(self, "statusBar"):
            self.statusBar().showMessage(f"Transcript font size: {round(scale * 100)}%", 1500)

    def adjust_transcript_font_size(self, direction):
        """Increase or decrease transcript font size by one 5% step."""
        self._apply_transcript_font_scale(self.transcript_font_scale + (0.05 * (1 if direction > 0 else -1)))

    def reset_transcript_font_size(self):
        """Restore the default transcript font size."""
        self._apply_transcript_font_scale(1.0)

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

        def get_sc(action_id: str, fallback: str = "") -> str:
            if hasattr(self, "shortcuts_manager") and self.shortcuts_manager:
                sc = self.shortcuts_manager.get_current_shortcut(action_id)
                if sc and sc != "None":
                    from shortcuts_manager import format_sequence_display
                    return format_sequence_display(sc)
                if sc == "None":
                    return "Unassigned"
            return fallback

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
            <tr><td><b>Play / Pause</b></td><td><kbd>{get_sc("play_pause", "Space")}</kbd> or <kbd>Media Play/Pause</kbd></td></tr>
            <tr><td><b>Skip Backward / Forward</b></td><td><kbd>{get_sc("seek_backward", "Left")}</kbd> / <kbd>{get_sc("seek_forward", "Right")}</kbd></td></tr>
            <tr><td><b>Seek to Start / End</b></td><td><kbd>{get_sc("seek_start", "Home")}</kbd> / <kbd>{get_sc("seek_end", "End")}</kbd></td></tr>
            <tr><td><b>Zoom In / Out on Timeline</b></td><td><kbd>{get_sc("zoom_in", "+")}</kbd> / <kbd>{get_sc("zoom_out", "-")}</kbd> or <kbd>Mouse Wheel</kbd></td></tr>
            <tr><td><b>Pan Timeline View</b></td><td><kbd>Shift + Wheel</kbd> or <kbd>Middle-Click Drag</kbd></td></tr>
            <tr><td><b>Increase / Decrease Transcript Text</b></td><td><kbd>{get_sc("transcript_font_up", f"{cmd}++")}</kbd> / <kbd>{get_sc("transcript_font_down", f"{cmd}+-")}</kbd></td></tr>
            <tr><td><b>Reset Transcript Text Size</b></td><td><kbd>{get_sc("transcript_font_reset", f"{cmd}+0")}</kbd></td></tr>
        </table>

        <h3>File & Project</h3>
        <table>
            <tr><td><b>New Project</b></td><td><kbd>{get_sc("new_project", f"{cmd}+N")}</kbd></td></tr>
            <tr><td><b>Open Media File</b></td><td><kbd>{get_sc("open_media", f"{cmd}+O")}</kbd></td></tr>
            <tr><td><b>Open Document</b></td><td><kbd>{get_sc("open_document", f"{cmd}+{opt}+O")}</kbd></td></tr>
            <tr><td><b>Open Project Session</b></td><td><kbd>{get_sc("open_project", f"{cmd}+Shift+O")}</kbd></td></tr>
            <tr><td><b>Close Project Session</b></td><td><kbd>{get_sc("close_project", f"{cmd}+W")}</kbd></td></tr>
            <tr><td><b>Save Project</b></td><td><kbd>{get_sc("save_project", f"{cmd}+S")}</kbd></td></tr>
            <tr><td><b>Save Project As...</b></td><td><kbd>{get_sc("save_project_as", f"{cmd}+Shift+S")}</kbd></td></tr>
            <tr><td><b>Export Dialog</b></td><td><kbd>{get_sc("export", f"{cmd}+E")}</kbd></td></tr>
            <tr><td><b>Batch Processing</b></td><td><kbd>{get_sc("batch_processing", f"{cmd}+Shift+B")}</kbd></td></tr>
            <tr><td><b>Preferences</b></td><td><kbd>{get_sc("preferences", f"{cmd}+P")}</kbd></td></tr>
            <tr><td><b>Customize Keyboard Shortcuts</b></td><td><kbd>{get_sc("customize_shortcuts", f"{cmd}+K")}</kbd></td></tr>
            <tr><td><b>Exit Application</b></td><td><kbd>{get_sc("exit_app", f"{cmd}+Q")}</kbd></td></tr>
        </table>

        <h3>Panels & Views</h3>
        <table>
            <tr><td><b>Toggle Timeline Panel</b></td><td><kbd>{get_sc("toggle_timeline", f"{panel_mod}+1")}</kbd></td></tr>
            <tr><td><b>Toggle Transcript Panel</b></td><td><kbd>{get_sc("toggle_transcript", f"{panel_mod}+2")}</kbd></td></tr>
            <tr><td><b>Toggle Stories Panel</b></td><td><kbd>{get_sc("toggle_stories", f"{panel_mod}+3")}</kbd></td></tr>
            <tr><td><b>Toggle Activity History Panel</b></td><td><kbd>{get_sc("toggle_activity", f"{panel_mod}+4")}</kbd></td></tr>
            <tr><td><b>Toggle Waveform Display</b></td><td><kbd>{get_sc("toggle_waveform", f"{cmd}+{opt}+W")}</kbd></td></tr>
            <tr><td><b>Toggle Video Thumbnails</b></td><td><kbd>{get_sc("toggle_thumbnails", f"{cmd}+{opt}+T")}</kbd></td></tr>
            <tr><td><b>Toggle Video Preview Window</b></td><td><kbd>{get_sc("toggle_video_preview", f"{cmd}+Shift+M")}</kbd></td></tr>
            <tr><td><b>Toggle Speaker Labels</b></td><td><kbd>{get_sc("toggle_speaker_labels", f"{cmd}+{opt}+S")}</kbd></td></tr>
            <tr><td><b>Toggle Timestamps</b></td><td><kbd>{get_sc("toggle_timestamps", f"{cmd}+{opt}+I")}</kbd></td></tr>
        </table>

        <h3>Editing & Transcript</h3>
        <table>
            <tr><td><b>Undo / Redo</b></td><td><kbd>{get_sc("undo", f"{cmd}+Z")}</kbd> / <kbd>{get_sc("redo", f"{cmd}+Y")}</kbd></td></tr>
            <tr><td><b>Find and Replace</b></td><td><kbd>{get_sc("find_replace", f"{cmd}+F")}</kbd></td></tr>
            <tr><td><b>Find Next Match</b></td><td><kbd>{get_sc("find_next", f"{cmd}+G")}</kbd></td></tr>
            <tr><td><b>Insert Speaker Break (Edit Mode)</b></td><td><kbd>Shift+Enter</kbd></td></tr>
            <tr><td><b>Insert Timestamp Line (Edit Mode)</b></td><td><kbd>Enter</kbd></td></tr>
            <tr><td><b>Exit Editing Mode</b></td><td><kbd>Esc</kbd></td></tr>
        </table>

        <h3>AI Pipeline & Tools</h3>
        <table>
            <tr><td><b>Transcribe Audio</b></td><td><kbd>{get_sc("transcribe", f"{cmd}+T")}</kbd></td></tr>
            <tr><td><b>Detect Speakers (Diarization)</b></td><td><kbd>{get_sc("detect_speakers", f"{cmd}+D")}</kbd></td></tr>
            <tr><td><b>Detect Stories</b></td><td><kbd>{get_sc("detect_stories", f"{cmd}+Shift+A")}</kbd></td></tr>
            <tr><td><b>Translate Transcript</b></td><td><kbd>{get_sc("translate", f"{cmd}+Shift+L")}</kbd></td></tr>
            <tr><td><b>Multi-Stage Processing Pipeline</b></td><td><kbd>{get_sc("run_pipeline", f"{cmd}+R")}</kbd></td></tr>
            <tr><td><b>Regenerate Waveform</b></td><td><kbd>{get_sc("regen_waveform", f"{cmd}+Shift+W")}</kbd></td></tr>
            <tr><td><b>Regenerate Video Thumbnails</b></td><td><kbd>{get_sc("regen_thumbnails", f"{cmd}+Shift+T")}</kbd></td></tr>
            <tr><td><b>Clear Temporary Cache</b></td><td><kbd>{get_sc("clear_cache", f"{cmd}+{opt}+C")}</kbd></td></tr>
            <tr><td><b>Manage AI Models</b></td><td><kbd>{get_sc("manage_models", f"{cmd}+M")}</kbd></td></tr>
            <tr><td><b>Manage Plugins & Add-ons</b></td><td><kbd>{get_sc("manage_plugins", f"{cmd}+Shift+X")}</kbd></td></tr>
        </table>

        <h3>Settings & Diagnostics</h3>
        <table>
            <tr><td><b>Preferences</b></td><td><kbd>{get_sc("preferences", f"{cmd}+P")}</kbd></td></tr>
            <tr><td><b>Customize Keyboard Shortcuts</b></td><td><kbd>{get_sc("customize_shortcuts", f"{cmd}+K")}</kbd></td></tr>
            <tr><td><b>GPU Acceleration Settings</b></td><td><kbd>{get_sc("gpu_settings", f"{cmd}+{opt}+G")}</kbd></td></tr>
            <tr><td><b>Glossary & Custom Vocabulary</b></td><td><kbd>{get_sc("glossary", f"{cmd}+Shift+G")}</kbd></td></tr>
            <tr><td><b>Check for Updates</b></td><td><kbd>{get_sc("check_updates", f"{cmd}+U")}</kbd></td></tr>
            <tr><td><b>Keyboard Shortcuts Reference</b></td><td><kbd>{get_sc("help_shortcuts", "F1" if not is_mac else "Cmd+?")}</kbd></td></tr>
            <tr><td><b>About Radio & TV Story Segmenter</b></td><td><kbd>{get_sc("about", "Shift+F1")}</kbd></td></tr>
            <tr><td><b>Open Diagnostic Log Folder</b></td><td><kbd>{get_sc("diagnostic_log", f"{cmd}+Shift+K")}</kbd></td></tr>
            <tr><td><b>Third-Party Licenses</b></td><td><kbd>{get_sc("licenses", f"{cmd}+Shift+F1")}</kbd></td></tr>
        </table>
        """

        browser.setHtml(html_content)
        layout.addWidget(browser)

        button_box = QDialogButtonBox(dialog)
        customize_btn = button_box.addButton("Customize Shortcuts...", QDialogButtonBox.ButtonRole.ActionRole)
        close_btn = button_box.addButton(QDialogButtonBox.StandardButton.Close)

        def _open_customize():
            dialog.accept()
            self.open_preferences_dialog(initial_category="Keyboard Shortcuts")

        customize_btn.clicked.connect(_open_customize)
        close_btn.clicked.connect(dialog.accept)
        layout.addWidget(button_box)

        dialog.exec()

    def show_about_dialog(self):
        """Display dialog with application version, description, and attribution."""
        from PySide6.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton
        from PySide6.QtCore import Qt

        dialog = QDialog(self)
        dialog.setWindowTitle("About Radio & TV Segmenter")
        dialog.setFixedWidth(520)

        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(14)

        # Main content (header, version, description, open-source attribution)
        content_label = QLabel(
            f"<h2 style='margin: 0 0 6px 0;'>{APP_DISPLAY_NAME}</h2>"
            f"<p style='margin: 0 0 10px 0;'><b>Version {PROJECT_VERSION}</b></p>"
            "<p style='margin: 0 0 14px 0; color: #b0b0b0;'>"
            "An automated broadcast audio segmentation, transcription, and speaker detection platform built for radio production."
            "</p>"
            "<hr style='border: 0; border-top: 1px solid #444; margin-bottom: 12px;'/>"
            "<p style='margin: 0 0 8px 0;'><b>Open-Source Licensing &amp; Attribution:</b></p>"
            "<ul style='margin: 0 0 12px 18px; padding: 0; color: #8c8c8c; line-height: 1.5;'>"
            "<li><b>Application Icon:</b> 'Electronic Media' by Fatam Organa from "
            "<a href='https://thenounproject.com' style='color: #ff8c42;'>Noun Project</a> (licensed under CC BY 3.0).</li>"
            "<li><b>PySide6 / Qt 6:</b> The Qt Company (LGPLv3). Dynamically linked.</li>"
            "<li><b>FFmpeg:</b> FFmpeg developers (LGPLv2.1+ / GPLv2+). Invoked as separate binary.</li>"
            "<li><b>AI &amp; Speech:</b> OpenAI Whisper (MIT), faster-whisper &amp; CTranslate2 (MIT), PyTorch (BSD-3), Hugging Face Transformers &amp; Hub (Apache 2.0).</li>"
            "</ul>"
            "<p style='margin: 0; color: #888; font-size: 11px;'>"
            "Click 'View Licenses' to review full license texts, compliance disclosures, and copyright notices."
            "</p>",
            dialog,
        )
        content_label.setTextFormat(Qt.TextFormat.RichText)
        content_label.setOpenExternalLinks(True)
        content_label.setWordWrap(True)
        layout.addWidget(content_label)

        # Standard button row
        btn_layout = QHBoxLayout()
        btn_layout.setContentsMargins(0, 8, 0, 0)
        btn_layout.setSpacing(10)
        btn_layout.addStretch()

        ok_btn = QPushButton("OK", dialog)
        ok_btn.setMinimumWidth(70)
        ok_btn.clicked.connect(dialog.accept)
        btn_layout.addWidget(ok_btn)

        updates_btn = QPushButton("Check for Updates...", dialog)
        updates_btn.clicked.connect(lambda: (dialog.accept(), self.check_for_updates()))
        btn_layout.addWidget(updates_btn)

        licenses_btn = QPushButton("View Licenses", dialog)
        licenses_btn.clicked.connect(lambda: (dialog.accept(), self.show_licenses_dialog()))
        btn_layout.addWidget(licenses_btn)

        layout.addLayout(btn_layout)

        dialog.exec()

    def show_licenses_dialog(self):
        """Display bundled third-party open source notices and licenses."""
        from PySide6.QtWidgets import QDialog, QVBoxLayout, QTextBrowser, QDialogButtonBox

        dialog = QDialog(self)
        dialog.setWindowTitle("Third-Party Licenses & Notices")
        dialog.resize(720, 560)

        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        browser = QTextBrowser(dialog)
        browser.setOpenExternalLinks(True)

        notices_candidates = [
            Path(__file__).resolve().parent / "NOTICES.txt",
            Path(getattr(sys, "_MEIPASS", "")) / "NOTICES.txt",
            Path.cwd() / "NOTICES.txt",
        ]

        notices_text = "Third-party notices file (NOTICES.txt) was not found."
        for p in notices_candidates:
            if p.is_file():
                try:
                    notices_text = p.read_text(encoding="utf-8", errors="replace")
                    break
                except Exception:
                    continue

        browser.setPlainText(notices_text)
        layout.addWidget(browser)

        button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Close, dialog)
        button_box.rejected.connect(dialog.accept)
        layout.addWidget(button_box)

        dialog.exec()

    def open_plugins_manager(self):
        """Open the Plugin Manager dialog to enable, disable, or inspect plugins."""
        if not hasattr(self, "plugin_manager"):
            return
        from plugins.manager import PluginManagerDialog
        dlg = PluginManagerDialog(self.plugin_manager, self)
        dlg.exec()
        self.refresh_plugin_menus()

    def refresh_plugin_menus(self):
        """Dynamically populate plugin export actions, tools menu actions, and core UI controls."""
        if not hasattr(self, "plugin_manager"):
            return

        # 1. Refresh Export & Publishing menu
        if hasattr(self, "plugins_export_menu"):
            self.plugins_export_menu.clear()
            has_export_actions = False
            for p in self.plugin_manager.plugins.values():
                is_p_enabled = getattr(p, "is_enabled", True)
                if callable(is_p_enabled):
                    is_p_enabled = is_p_enabled()
                if is_p_enabled and self.plugin_manager.is_plugin_enabled(p.id):
                    for label, callback in p.get_export_actions():
                        act = self.plugins_export_menu.addAction(label)
                        act.triggered.connect(callback)
                        has_export_actions = True
            self.plugins_export_menu.menuAction().setVisible(has_export_actions)

        # 2. Refresh Tools menu dynamic actions
        if hasattr(self, "plugin_tools_actions") and hasattr(self, "tools_menu"):
            for act in self.plugin_tools_actions:
                self.tools_menu.removeAction(act)
            self.plugin_tools_actions.clear()

            for p in self.plugin_manager.plugins.values():
                is_p_enabled = getattr(p, "is_enabled", True)
                if callable(is_p_enabled):
                    is_p_enabled = is_p_enabled()
                if is_p_enabled and self.plugin_manager.is_plugin_enabled(p.id):
                    for label, callback in p.get_tools_actions():
                        act = QAction(label, self)
                        act.triggered.connect(callback)
                        self.tools_menu.addAction(act)
                        self.plugin_tools_actions.append(act)

        # 3. Synchronize core UI elements according to plugin enabled state
        is_translation_enabled = self.plugin_manager.is_plugin_enabled("translation")
        if hasattr(self, "translate_button"):
            self.translate_button.setVisible(is_translation_enabled)
        if hasattr(self, "transcript_language_selector"):
            self.transcript_language_selector.setVisible(is_translation_enabled)
        if hasattr(self, "translate_action"):
            self.translate_action.setVisible(is_translation_enabled)
        if hasattr(self, "tools_translate_action"):
            self.tools_translate_action.setVisible(is_translation_enabled)

    def open_youtube_publish_dialog(self, story=None):
        """Open the YouTube video publishing dialog or export view from the YouTube plugin."""
        if hasattr(self, "plugin_manager") and self.plugin_manager.is_plugin_enabled("youtube"):
            if hasattr(self, "open_unified_export_dialog"):
                initial_scope = "selected_stories" if story is not None else None
                self.open_unified_export_dialog(initial_scope=initial_scope, initial_dest="youtube")
                return
            plugin = self.plugin_manager.plugins.get("youtube")
            if plugin:
                from plugins.youtube.plugin import YouTubePublishDialog
                # If no story was explicitly passed, check selected story in UI
                if story is None and hasattr(self, "stories") and hasattr(self, "current_selected_story_indices"):
                    sel = getattr(self, "current_selected_story_indices", [])
                    if sel and 0 <= sel[0] < len(self.stories):
                        story = self.stories[sel[0]]
                dlg = YouTubePublishDialog(plugin, parent=self, story=story)
                dlg.exec()
                return
        QMessageBox.information(
            self,
            "YouTube Plugin Required",
            "The YouTube Video Publisher plugin is not enabled or not loaded.\n"
            "You can enable it under Settings > Manage Plugins & Add-ons.",
        )

    def open_wordpress_publish_dialog(self, story=None):
        """Open the WordPress direct publish dialog from the WordPress plugin."""
        if hasattr(self, "plugin_manager") and self.plugin_manager.is_plugin_enabled("wordpress"):
            plugin = self.plugin_manager.plugins.get("wordpress")
            if plugin:
                from plugins.wordpress.plugin import WordPressPublishDialog
                if story is None and hasattr(self, "stories") and hasattr(self, "current_selected_story_indices"):
                    sel = getattr(self, "current_selected_story_indices", [])
                    if sel and 0 <= sel[0] < len(self.stories):
                        story = self.stories[sel[0]]
                dlg = WordPressPublishDialog(plugin, parent=self, story=story)
                dlg.exec()
                return
        QMessageBox.information(
            self,
            "WordPress Plugin Required",
            "The WordPress Publisher plugin is not enabled or not loaded.\n"
            "You can enable it under Settings > Manage Plugins & Add-ons.",
        )



