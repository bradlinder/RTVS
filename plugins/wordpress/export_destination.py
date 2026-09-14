"""WordPress Export Destination for UnifiedExportDialog."""
from __future__ import annotations

import html
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from PySide6.QtCore import Qt, QTimer, QSettings
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFormLayout,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QRadioButton,
    QScrollArea,
    QSlider,
    QVBoxLayout,
    QWidget,
)

from prs_shared import (
    INTERNAL_APP_ID,
    CollapsibleSection,
    ResizableTextEdit,
    ffmpeg_path,
    format_time,
    safe_filename,
)
from plugins.base import ExportDestination
from wordpress_export import WordPressClient, generate_wp_excerpt, WordPressSettingsDialog


def capture_video_frame(video_path: str, timestamp: float, output_path: str) -> bool:
    ff = ffmpeg_path() or "ffmpeg"
    cmd = [
        ff, "-hide_banner", "-loglevel", "error", "-y",
        "-ss", f"{max(0.0, timestamp):.3f}",
        "-i", str(video_path),
        "-frames:v", "1",
        "-q:v", "2",
        str(output_path),
    ]
    flags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
    res = subprocess.run(cmd, capture_output=True, creationflags=flags)
    return res.returncode == 0 and Path(output_path).exists() and Path(output_path).stat().st_size > 0


class WordPressExportTabWidget(QWidget):
    """Configuration and preview panel for WordPress Draft Posts."""

    def __init__(self, parent: QWidget, main_window: Any):
        super().__init__(parent)
        self.main_window = main_window
        self.settings = QSettings(INTERNAL_APP_ID, INTERNAL_APP_ID)
        self._is_video_project = bool(getattr(self.main_window, "current_media_is_video", False))
        self._temp_preview_files = set()

        self._wp_scrub_timer = QTimer(self)
        self._wp_scrub_timer.setSingleShot(True)
        self._wp_scrub_timer.setInterval(120)
        self._wp_scrub_timer.timeout.connect(self._on_wp_scrub_timer_timeout)

        self.wp_cached_authors_data: List[Dict[str, Any]] = []
        self.wp_cached_categories_data: List[Dict[str, Any]] = []
        self.wp_post_items: List[Dict[str, Any]] = []
        self._current_post_index = 0
        self._syncing_post_editor = False

        self._setup_ui()

    def _setup_ui(self):
        wp_page_layout = QVBoxLayout(self)
        wp_page_layout.setContentsMargins(0, 0, 0, 0)

        wp_scroll = QScrollArea()
        wp_scroll.setWidgetResizable(True)
        wp_scroll.setFrameShape(QFrame.Shape.NoFrame)
        wp_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        wp_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)

        wp_scroll_content = QWidget()
        wp_layout = QVBoxLayout(wp_scroll_content)
        wp_layout.setContentsMargins(2, 2, 2, 2)
        wp_layout.setSpacing(10)

        self.wp_info_section = CollapsibleSection("WordPress Post Configuration", self, is_expanded=True, subtitle="Title, Excerpt, Authors, Categories")
        wp_notice = QLabel(
            "Extracts audio as <b>128 kbps MP3</b>, uploads to your WordPress Media Library, "
            "and creates a <b>Draft Post</b> with Gutenberg audio player and formatted transcript."
        )
        wp_notice.setWordWrap(True)
        self.wp_info_section.add_widget(wp_notice)

        # Master-Detail Container for Posts
        self.wp_posts_container = QHBoxLayout()
        self.wp_posts_container.setSpacing(12)

        # Left Nav: Post selector
        self.wp_post_nav_widget = QWidget()
        nav_layout = QVBoxLayout(self.wp_post_nav_widget)
        nav_layout.setContentsMargins(0, 0, 0, 0)
        nav_layout.setSpacing(6)
        nav_label = QLabel("<b>Posts to Export:</b>")
        self.wp_posts_list = QListWidget()
        self.wp_posts_list.setMinimumWidth(160)
        self.wp_posts_list.setMaximumWidth(220)
        self.wp_autofill_all_excerpts_btn = QPushButton("Auto-fill All Excerpts")
        self.wp_autofill_all_excerpts_btn.setToolTip("Auto-generate snippet (≤55 words) from transcript for every post")
        self.wp_autofill_all_excerpts_btn.clicked.connect(self._autofill_all_excerpts)

        nav_layout.addWidget(nav_label)
        nav_layout.addWidget(self.wp_posts_list, 1)
        nav_layout.addWidget(self.wp_autofill_all_excerpts_btn)
        self.wp_posts_container.addWidget(self.wp_post_nav_widget)

        # Right Pane: Detailed post editor
        self.wp_post_editor_widget = QWidget()
        editor_layout = QVBoxLayout(self.wp_post_editor_widget)
        editor_layout.setContentsMargins(0, 0, 0, 0)
        editor_layout.setSpacing(8)

        self.wp_current_post_header = QLabel("<b>Post Settings</b>")
        self.wp_current_post_header.setStyleSheet("color: #38bdf8; font-size: 12px;")
        editor_layout.addWidget(self.wp_current_post_header)

        # Title Field
        post_title_row = QHBoxLayout()
        post_title_row.addWidget(QLabel("Post Title:"))
        self.wp_title_edit = QLineEdit()
        self.wp_title_edit.textEdited.connect(self._on_title_edited)
        post_title_row.addWidget(self.wp_title_edit, 1)
        editor_layout.addLayout(post_title_row)

        # Excerpt Field
        excerpt_box = QVBoxLayout()
        excerpt_box.setSpacing(3)
        exc_hdr = QHBoxLayout()
        exc_hdr.addWidget(QLabel("Excerpt / Description (≤55 words):"))
        exc_hdr.addStretch()
        self.wp_auto_excerpt_btn = QPushButton("Generate from Story")
        self.wp_auto_excerpt_btn.setToolTip("Auto-generate excerpt from the current story's transcript")
        self.wp_auto_excerpt_btn.clicked.connect(self._auto_generate_current_excerpt)
        exc_hdr.addWidget(self.wp_auto_excerpt_btn)
        excerpt_box.addLayout(exc_hdr)

        self.wp_excerpt_edit = ResizableTextEdit()
        self.wp_excerpt_edit.setMaximumHeight(55)
        self.wp_excerpt_edit.textChanged.connect(self._on_excerpt_edited)
        excerpt_box.addWidget(self.wp_excerpt_edit)
        editor_layout.addLayout(excerpt_box)

        # Dual Column: Authors and Categories Checklist
        tax_container = QHBoxLayout()
        tax_container.setSpacing(10)

        # Author selection column
        author_col = QVBoxLayout()
        author_col.setSpacing(3)
        auth_hdr = QHBoxLayout()
        auth_hdr.addWidget(QLabel("Authors:"))
        auth_hdr.addStretch()
        self.wp_clear_authors_btn = QPushButton("Clear")
        self.wp_clear_authors_btn.setStyleSheet("padding: 1px 6px; font-size: 10px;")
        self.wp_clear_authors_btn.clicked.connect(self._clear_current_authors)
        auth_hdr.addWidget(self.wp_clear_authors_btn)
        author_col.addLayout(auth_hdr)

        self.wp_author_filter_edit = QLineEdit()
        self.wp_author_filter_edit.setPlaceholderText("Filter authors...")
        self.wp_author_filter_edit.textChanged.connect(self._filter_authors_list)
        author_col.addWidget(self.wp_author_filter_edit)

        self.wp_author_list = QListWidget()
        self.wp_author_list.setMaximumHeight(95)
        self.wp_author_list.itemChanged.connect(self._on_author_item_changed)
        author_col.addWidget(self.wp_author_list)
        tax_container.addLayout(author_col)

        # Category selection column
        cat_col = QVBoxLayout()
        cat_col.setSpacing(3)
        cat_hdr = QHBoxLayout()
        cat_hdr.addWidget(QLabel("Categories:"))
        cat_hdr.addStretch()
        self.wp_clear_cats_btn = QPushButton("Clear")
        self.wp_clear_cats_btn.setStyleSheet("padding: 1px 6px; font-size: 10px;")
        self.wp_clear_cats_btn.clicked.connect(self._clear_current_categories)
        cat_hdr.addWidget(self.wp_clear_cats_btn)
        cat_col.addLayout(cat_hdr)

        self.wp_category_filter_edit = QLineEdit()
        self.wp_category_filter_edit.setPlaceholderText("Filter categories...")
        self.wp_category_filter_edit.textChanged.connect(self._filter_categories_list)
        cat_col.addWidget(self.wp_category_filter_edit)

        self.wp_category_list = QListWidget()
        self.wp_category_list.setMaximumHeight(95)
        self.wp_category_list.itemChanged.connect(self._on_category_item_changed)
        cat_col.addWidget(self.wp_category_list)
        tax_container.addLayout(cat_col)

        editor_layout.addLayout(tax_container)

        # Featured Image Section
        self.wp_thumb_section = CollapsibleSection("Featured Image (Thumbnail)", self, is_expanded=True)
        wp_thumb_layout = QHBoxLayout()
        wp_thumb_layout.setSpacing(10)

        wp_thumb_controls = QVBoxLayout()
        wp_thumb_controls.setSpacing(6)

        self.wp_rad_thumb_none = QRadioButton("None")
        self.wp_rad_thumb_grab = QRadioButton("Grab frame from video")
        self.wp_rad_thumb_file = QRadioButton("Select custom image file...")
        self.wp_rad_thumb_none.setChecked(True)

        if not self._is_video_project:
            self.wp_rad_thumb_grab.setEnabled(False)
            self.wp_rad_thumb_grab.setText("Grab frame from video (Audio-only project)")
            self.wp_rad_thumb_grab.setToolTip("Video frame capture requires video media (audio-only file loaded)")

        wp_thumb_controls.addWidget(self.wp_rad_thumb_none)
        wp_thumb_controls.addWidget(self.wp_rad_thumb_grab)

        # In-dialog Frame Scrubber & Stepper for WordPress
        self.wp_scrub_widget = QWidget()
        wp_scrub_vbox = QVBoxLayout(self.wp_scrub_widget)
        wp_scrub_vbox.setContentsMargins(16, 2, 4, 4)
        wp_scrub_vbox.setSpacing(4)

        self.wp_scrub_slider = QSlider(Qt.Orientation.Horizontal)
        self.wp_scrub_slider.setRange(0, 10000)
        self.wp_scrub_slider.valueChanged.connect(self._on_wp_slider_value_changed)
        wp_scrub_vbox.addWidget(self.wp_scrub_slider)

        wp_stepper_row = QHBoxLayout()
        wp_stepper_row.setSpacing(4)
        self.wp_step_back_sec_btn = QPushButton("◀ -1s")
        self.wp_step_back_sec_btn.setToolTip("Step backward 1 second")
        self.wp_step_back_sec_btn.clicked.connect(lambda: self._on_wp_step(-1.0))
        self.wp_step_back_frame_btn = QPushButton("◀ -1f")
        self.wp_step_back_frame_btn.setToolTip("Step backward 1 frame (~33ms)")
        self.wp_step_back_frame_btn.clicked.connect(lambda: self._on_wp_step(-0.0333))

        self.wp_scrub_time_label = QLabel("00:00:00.000")
        self.wp_scrub_time_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.wp_scrub_time_label.setStyleSheet("padding: 2px 6px; background-color: #0f172a; border: 1px solid #334155; border-radius: 4px; font-family: monospace; font-size: 11px; font-weight: bold; color: #e2e8f0;")

        self.wp_step_fwd_frame_btn = QPushButton("+1f ▶")
        self.wp_step_fwd_frame_btn.setToolTip("Step forward 1 frame (~33ms)")
        self.wp_step_fwd_frame_btn.clicked.connect(lambda: self._on_wp_step(0.0333))
        self.wp_step_fwd_sec_btn = QPushButton("+1s ▶")
        self.wp_step_fwd_sec_btn.setToolTip("Step forward 1 second")
        self.wp_step_fwd_sec_btn.clicked.connect(lambda: self._on_wp_step(1.0))
        self.wp_sync_playhead_btn = QPushButton("⟳ Playhead")
        self.wp_sync_playhead_btn.setToolTip("Sync thumbnail position to the main timeline playhead")
        self.wp_sync_playhead_btn.clicked.connect(self._on_wp_sync_playhead)

        wp_stepper_row.addWidget(self.wp_step_back_sec_btn)
        wp_stepper_row.addWidget(self.wp_step_back_frame_btn)
        wp_stepper_row.addWidget(self.wp_scrub_time_label)
        wp_stepper_row.addWidget(self.wp_step_fwd_frame_btn)
        wp_stepper_row.addWidget(self.wp_step_fwd_sec_btn)
        wp_stepper_row.addWidget(self.wp_sync_playhead_btn)
        wp_stepper_row.addStretch()
        wp_scrub_vbox.addLayout(wp_stepper_row)
        self.wp_scrub_widget.setVisible(False)
        wp_thumb_controls.addWidget(self.wp_scrub_widget)

        wp_thumb_controls.addWidget(self.wp_rad_thumb_file)

        # Custom Browse Button row
        self.wp_browse_widget = QWidget()
        wp_browse_box = QHBoxLayout(self.wp_browse_widget)
        wp_browse_box.setContentsMargins(16, 2, 4, 4)
        wp_browse_box.setSpacing(6)
        self.wp_browse_thumb_btn = QPushButton("Browse Image...")
        self.wp_browse_thumb_btn.clicked.connect(self._on_wp_browse_thumb)
        wp_browse_box.addWidget(self.wp_browse_thumb_btn)
        wp_browse_box.addStretch()
        self.wp_browse_widget.setVisible(False)
        wp_thumb_controls.addWidget(self.wp_browse_widget)

        self.wp_thumb_path_label = QLabel("No image selected")
        self.wp_thumb_path_label.setStyleSheet("color: #64748b; font-size: 11px;")
        wp_thumb_controls.addWidget(self.wp_thumb_path_label)

        wp_thumb_layout.addLayout(wp_thumb_controls, stretch=2)

        self.wp_thumb_preview_label = QLabel("No Thumbnail")
        self.wp_thumb_preview_label.setFixedSize(160, 90)
        self.wp_thumb_preview_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.wp_thumb_preview_label.setStyleSheet("border: 1px dashed #475569; border-radius: 4px; background-color: #0f172a; color: #64748b; font-size: 10px;")
        wp_thumb_layout.addWidget(self.wp_thumb_preview_label, stretch=1)

        self.wp_thumb_section.add_layout(wp_thumb_layout)
        editor_layout.addWidget(self.wp_thumb_section)

        self.wp_rad_thumb_none.toggled.connect(self._on_wp_thumb_mode_changed)
        self.wp_rad_thumb_grab.toggled.connect(self._on_wp_thumb_mode_changed)
        self.wp_rad_thumb_file.toggled.connect(self._on_wp_thumb_mode_changed)

        # Bulk Actions Row
        self.wp_bulk_box = QWidget()
        bulk_layout = QHBoxLayout(self.wp_bulk_box)
        bulk_layout.setContentsMargins(0, 0, 0, 0)
        self.wp_apply_authors_all_btn = QPushButton("Apply Authors to All Posts")
        self.wp_apply_authors_all_btn.setToolTip("Copy this post's author selection to all other posts in the queue")
        self.wp_apply_authors_all_btn.clicked.connect(self._apply_authors_to_all_posts)
        self.wp_apply_cats_all_btn = QPushButton("Apply Categories to All Posts")
        self.wp_apply_cats_all_btn.setToolTip("Copy this post's category selection to all other posts in the queue")
        self.wp_apply_cats_all_btn.clicked.connect(self._apply_categories_to_all_posts)
        self.wp_apply_thumb_all_btn = QPushButton("Apply Thumbnail to All Posts")
        self.wp_apply_thumb_all_btn.setToolTip("Copy this post's thumbnail selection to all other posts in the queue")
        self.wp_apply_thumb_all_btn.clicked.connect(self._apply_thumbnails_to_all_posts)
        bulk_layout.addWidget(self.wp_apply_authors_all_btn)
        bulk_layout.addWidget(self.wp_apply_cats_all_btn)
        bulk_layout.addWidget(self.wp_apply_thumb_all_btn)
        bulk_layout.addStretch()
        editor_layout.addWidget(self.wp_bulk_box)

        self.wp_posts_container.addWidget(self.wp_post_editor_widget)
        self.wp_info_section.add_layout(self.wp_posts_container)

        self.wp_posts_list.currentRowChanged.connect(self._on_wp_post_selection_changed)

        # Load cached metadata
        self._populate_wp_export_metadata(force_refresh=False)
        self.rebuild_post_items()

        # Metadata Refresh Button Row
        meta_btn_row = QHBoxLayout()
        self.wp_refresh_meta_btn = QPushButton("Refresh WordPress Metadata")
        self.wp_refresh_meta_btn.setToolTip("Fetch fresh Author and Category lists from WordPress site")
        self.wp_refresh_meta_btn.clicked.connect(self._refresh_wp_metadata)
        meta_btn_row.addStretch()
        meta_btn_row.addWidget(self.wp_refresh_meta_btn)
        self.wp_info_section.add_layout(meta_btn_row)
        wp_layout.addWidget(self.wp_info_section)

        # Languages & Presentation
        self.wp_lang_section = CollapsibleSection("Transcript Languages & Presentation", self, is_expanded=True)
        wp_lang_checks = QHBoxLayout()
        self.wp_cb_en = QCheckBox("English")
        self.wp_cb_en.setChecked(True)
        has_es = bool(getattr(self.main_window, "spanish_transcript", None))
        self.wp_cb_es = QCheckBox("Spanish (Translated)")
        self.wp_cb_es.setChecked(has_es)
        self.wp_cb_es.setEnabled(has_es)
        if not has_es:
            self.wp_cb_es.setToolTip("Spanish translation is not available for this project. Generate a translation first to enable.")
        wp_lang_checks.addWidget(self.wp_cb_en)
        wp_lang_checks.addWidget(self.wp_cb_es)
        wp_lang_checks.addStretch()
        self.wp_lang_section.add_layout(wp_lang_checks)

        # Dual language options
        self.wp_pres_container = QWidget()
        pres_layout = QVBoxLayout(self.wp_pres_container)
        pres_layout.setContentsMargins(0, 4, 0, 0)
        pres_layout.setSpacing(6)

        prim_row = QHBoxLayout()
        prim_label = QLabel("Primary Language:")
        self.wp_primary_lang_combo = QComboBox()
        self.wp_primary_lang_combo.addItem("English", "en")
        self.wp_primary_lang_combo.addItem("Spanish", "es")
        prim_row.addWidget(prim_label)
        prim_row.addWidget(self.wp_primary_lang_combo)
        prim_row.addStretch()
        pres_layout.addLayout(prim_row)

        pres_row = QHBoxLayout()
        pres_label = QLabel("Placement:")
        self.wp_pres_combo = QComboBox()
        self.wp_pres_combo.addItem("Interactive language toggle (Accordion)", "accordion")
        self.wp_pres_combo.addItem("English first, Spanish below", "en_first")
        self.wp_pres_combo.addItem("Spanish first, English below", "es_first")
        pres_row.addWidget(pres_label)
        pres_row.addWidget(self.wp_pres_combo)
        pres_row.addStretch()
        pres_layout.addLayout(pres_row)

        self.wp_lang_section.add_widget(self.wp_pres_container)

        def update_wp_pres_visibility():
            both = self.wp_cb_en.isChecked() and self.wp_cb_es.isChecked()
            self.wp_pres_container.setVisible(both)

        self.wp_cb_en.toggled.connect(update_wp_pres_visibility)
        self.wp_cb_es.toggled.connect(update_wp_pres_visibility)
        update_wp_pres_visibility()
        wp_layout.addWidget(self.wp_lang_section)

        # Custom Notice Section
        self.wp_custom_section = CollapsibleSection("Custom Header / Footer Notice (Optional)", self, is_expanded=False)
        self.wp_custom_text_edit = ResizableTextEdit("")
        self.wp_custom_text_edit.setPlaceholderText(
            "e.g. Note: The following transcript was machine-generated and may contain some spelling errors or other inaccuracies."
        )
        self.wp_custom_text_edit.setMaximumHeight(65)
        self.wp_custom_section.add_widget(self.wp_custom_text_edit)

        wp_pos_row = QHBoxLayout()
        self.wp_pos_button_group = QButtonGroup(self)
        self.wp_rad_pos_top = QRadioButton("Place at top of post")
        self.wp_rad_pos_bottom = QRadioButton("Place at bottom of post")
        self.wp_pos_button_group.addButton(self.wp_rad_pos_top)
        self.wp_pos_button_group.addButton(self.wp_rad_pos_bottom)
        self.wp_rad_pos_top.setChecked(True)
        wp_pos_row.addWidget(self.wp_rad_pos_top)
        wp_pos_row.addWidget(self.wp_rad_pos_bottom)
        wp_pos_row.addStretch()
        self.wp_custom_section.add_layout(wp_pos_row)
        wp_layout.addWidget(self.wp_custom_section)

        # Connection status footer
        wp_conn_layout = QHBoxLayout()
        self.wp_conn_status = QLabel("WordPress: Checking connection...")
        self.wp_conn_status.setStyleSheet("color: #94a3b8; font-size: 11px;")
        self.wp_settings_btn = QPushButton("WordPress Settings...")
        self.wp_settings_btn.clicked.connect(self._open_wp_settings)
        wp_conn_layout.addWidget(self.wp_conn_status)
        wp_conn_layout.addStretch()
        wp_conn_layout.addWidget(self.wp_settings_btn)
        wp_layout.addLayout(wp_conn_layout)

        self._update_wp_conn_status()
        wp_layout.addStretch()

        wp_scroll.setWidget(wp_scroll_content)
        wp_page_layout.addWidget(wp_scroll)

    def _update_wp_conn_status(self):
        url = str(self.settings.value("wp_site_url", "") or "").rstrip("/")
        user = str(self.settings.value("wp_username", "") or "")
        if url and user:
            self.wp_conn_status.setText(f"Connected to: <b>{url}</b> (as {user})")
            self.wp_conn_status.setStyleSheet("color: #4ade80; font-size: 11px;")
        else:
            self.wp_conn_status.setText("WordPress credentials not configured.")
            self.wp_conn_status.setStyleSheet("color: #f87171; font-size: 11px;")

    def _open_wp_settings(self):
        dlg = WordPressSettingsDialog(parent=self)
        if dlg.exec():
            self._update_wp_conn_status()
            self._populate_wp_export_metadata(force_refresh=True)

    def _filter_authors_list(self, text: str):
        query = text.strip().lower()
        for i in range(self.wp_author_list.count()):
            item = self.wp_author_list.item(i)
            item.setHidden(query != "" and query not in item.text().lower())

    def _filter_categories_list(self, text: str):
        query = text.strip().lower()
        for i in range(self.wp_category_list.count()):
            item = self.wp_category_list.item(i)
            item.setHidden(query != "" and query not in item.text().lower())

    def _on_title_edited(self, text: str):
        if self._syncing_post_editor or not (0 <= self._current_post_index < len(self.wp_post_items)):
            return
        self.wp_post_items[self._current_post_index]["title"] = text.strip()
        self._update_post_list_item_label(self._current_post_index)

    def _on_excerpt_edited(self):
        if self._syncing_post_editor or not (0 <= self._current_post_index < len(self.wp_post_items)):
            return
        self.wp_post_items[self._current_post_index]["excerpt"] = self.wp_excerpt_edit.toPlainText().strip()

    def _auto_generate_current_excerpt(self):
        if not (0 <= self._current_post_index < len(self.wp_post_items)):
            return
        post = self.wp_post_items[self._current_post_index]
        raw_text = self.main_window._get_transcript_text_slice(post.get("start"), post.get("end")) if hasattr(self.main_window, "_get_transcript_text_slice") else ""
        excerpt = generate_wp_excerpt(raw_text, 55)
        self.wp_excerpt_edit.setPlainText(excerpt)
        post["excerpt"] = excerpt

    def _autofill_all_excerpts(self):
        for post in self.wp_post_items:
            raw_text = self.main_window._get_transcript_text_slice(post.get("start"), post.get("end")) if hasattr(self.main_window, "_get_transcript_text_slice") else ""
            post["excerpt"] = generate_wp_excerpt(raw_text, 55)
        if 0 <= self._current_post_index < len(self.wp_post_items):
            self.wp_excerpt_edit.setPlainText(self.wp_post_items[self._current_post_index].get("excerpt", ""))
        QMessageBox.information(self, "Auto-fill Excerpts", f"Generated transcript excerpts for all {len(self.wp_post_items)} posts.")

    def _on_author_item_changed(self, item):
        if self._syncing_post_editor or not (0 <= self._current_post_index < len(self.wp_post_items)):
            return
        auth_ids, term_ids = self._get_editor_checked_authors()
        post = self.wp_post_items[self._current_post_index]
        post["author_ids"] = auth_ids
        post["author_term_ids"] = term_ids
        self._update_post_list_item_label(self._current_post_index)

    def _on_category_item_changed(self, item):
        if self._syncing_post_editor or not (0 <= self._current_post_index < len(self.wp_post_items)):
            return
        cat_ids = self._get_editor_checked_categories()
        post = self.wp_post_items[self._current_post_index]
        post["category_ids"] = cat_ids
        self._update_post_list_item_label(self._current_post_index)

    def _clear_current_authors(self):
        self._set_editor_checked_authors([], [])
        if 0 <= self._current_post_index < len(self.wp_post_items):
            self.wp_post_items[self._current_post_index]["author_ids"] = []
            self.wp_post_items[self._current_post_index]["author_term_ids"] = []
            self._update_post_list_item_label(self._current_post_index)

    def _clear_current_categories(self):
        self._set_editor_checked_categories([])
        if 0 <= self._current_post_index < len(self.wp_post_items):
            self.wp_post_items[self._current_post_index]["category_ids"] = []
            self._update_post_list_item_label(self._current_post_index)

    def _apply_authors_to_all_posts(self):
        if not (0 <= self._current_post_index < len(self.wp_post_items)):
            return
        current_auth_ids = list(self.wp_post_items[self._current_post_index].get("author_ids", []))
        current_term_ids = list(self.wp_post_items[self._current_post_index].get("author_term_ids", []))
        for post in self.wp_post_items:
            post["author_ids"] = list(current_auth_ids)
            post["author_term_ids"] = list(current_term_ids)
        for idx in range(len(self.wp_post_items)):
            self._update_post_list_item_label(idx)
        QMessageBox.information(self, "Applied Authors", f"Assigned author selection to all {len(self.wp_post_items)} posts.")

    def _apply_categories_to_all_posts(self):
        if not (0 <= self._current_post_index < len(self.wp_post_items)):
            return
        current_cat_ids = list(self.wp_post_items[self._current_post_index].get("category_ids", []))
        for post in self.wp_post_items:
            post["category_ids"] = list(current_cat_ids)
        for idx in range(len(self.wp_post_items)):
            self._update_post_list_item_label(idx)
        QMessageBox.information(self, "Applied Categories", f"Assigned category selection to all {len(self.wp_post_items)} posts.")

    def _apply_thumbnails_to_all_posts(self):
        if not (0 <= self._current_post_index < len(self.wp_post_items)):
            return
        current_img = self.wp_post_items[self._current_post_index].get("featured_image")
        current_mode = self.wp_post_items[self._current_post_index].get("featured_image_mode", "none")
        for post in self.wp_post_items:
            post["featured_image"] = current_img
            post["featured_image_mode"] = current_mode
        QMessageBox.information(self, "Applied Thumbnails", f"Applied thumbnail settings to all {len(self.wp_post_items)} posts.")

    def _update_post_list_item_label(self, idx: int):
        if not (0 <= idx < len(self.wp_post_items)) or not hasattr(self, "wp_posts_list") or idx >= self.wp_posts_list.count():
            return
        post = self.wp_post_items[idx]
        title = post.get("title") or post.get("task_label", f"Post {idx + 1}")
        n_auths = len(post.get("author_ids", [])) + len(post.get("author_term_ids", []))
        n_cats = len(post.get("category_ids", []))
        meta_sub = []
        if n_auths:
            meta_sub.append(f"{n_auths} author" + ("s" if n_auths > 1 else ""))
        if n_cats:
            meta_sub.append(f"{n_cats} cat" + ("s" if n_cats > 1 else ""))
        meta_str = f" ({', '.join(meta_sub)})" if meta_sub else ""
        self.wp_posts_list.item(idx).setText(f"{post.get('task_label', 'Post')}: {title}{meta_str}")

    def _on_wp_post_selection_changed(self, row: int):
        if row < 0 or row >= len(self.wp_post_items):
            return
        self._load_post_editor_state(row)

    def _get_editor_checked_authors(self) -> Tuple[List[int], List[int]]:
        author_ids = []
        author_term_ids = []
        for i in range(self.wp_author_list.count()):
            item = self.wp_author_list.item(i)
            if item.checkState() == Qt.CheckState.Checked:
                data = item.data(Qt.ItemDataRole.UserRole)
                if isinstance(data, dict):
                    if data.get("is_guest"):
                        tid = data.get("term_id") or data.get("id")
                        if tid:
                            author_term_ids.append(int(tid))
                    else:
                        uid = data.get("user_id") or data.get("id")
                        if uid:
                            author_ids.append(int(uid))
        return author_ids, author_term_ids

    def _set_editor_checked_authors(self, author_ids: List[int], author_term_ids: List[int]):
        self._syncing_post_editor = True
        auth_set = set(int(x) for x in (author_ids or []))
        term_set = set(int(x) for x in (author_term_ids or []))
        for i in range(self.wp_author_list.count()):
            item = self.wp_author_list.item(i)
            data = item.data(Qt.ItemDataRole.UserRole)
            checked = False
            if isinstance(data, dict):
                if data.get("is_guest"):
                    tid = data.get("term_id") or data.get("id")
                    if tid and int(tid) in term_set:
                        checked = True
                else:
                    uid = data.get("user_id") or data.get("id")
                    if uid and int(uid) in auth_set:
                        checked = True
            item.setCheckState(Qt.CheckState.Checked if checked else Qt.CheckState.Unchecked)
        self._syncing_post_editor = False

    def _get_editor_checked_categories(self) -> List[int]:
        cat_ids = []
        for i in range(self.wp_category_list.count()):
            item = self.wp_category_list.item(i)
            if item.checkState() == Qt.CheckState.Checked:
                cid = item.data(Qt.ItemDataRole.UserRole)
                if cid is not None:
                    cat_ids.append(int(cid))
        return cat_ids

    def _set_editor_checked_categories(self, cat_ids: List[int]):
        self._syncing_post_editor = True
        cid_set = set(int(x) for x in (cat_ids or []))
        for i in range(self.wp_category_list.count()):
            item = self.wp_category_list.item(i)
            cid = item.data(Qt.ItemDataRole.UserRole)
            checked = (cid is not None and int(cid) in cid_set)
            item.setCheckState(Qt.CheckState.Checked if checked else Qt.CheckState.Unchecked)
        self._syncing_post_editor = False

    def _get_wp_post_bounds(self, post_index=None) -> Tuple[float, float]:
        idx = self._current_post_index if post_index is None else post_index
        if 0 <= idx < len(self.wp_post_items):
            p = self.wp_post_items[idx]
            if p.get("start") is not None and p.get("end") is not None:
                t_start = float(p["start"])
                t_end = float(p["end"])
                return t_start, max(t_start + 0.1, t_end)
        dur = max(0.1, float(getattr(self.main_window, "duration", 0.0) or 0.0))
        return 0.0, dur

    def _sync_wp_slider_to_pos(self, pos: float):
        t_min, t_max = self._get_wp_post_bounds()
        clamped = max(t_min, min(t_max, float(pos)))
        if 0 <= self._current_post_index < len(self.wp_post_items):
            self.wp_post_items[self._current_post_index]["frame_pos"] = clamped
        span = max(0.001, t_max - t_min)
        val = int(round(((clamped - t_min) / span) * 10000))
        self.wp_scrub_slider.blockSignals(True)
        self.wp_scrub_slider.setValue(max(0, min(10000, val)))
        self.wp_scrub_slider.blockSignals(False)
        self.wp_scrub_time_label.setText(format_time(clamped, include_millis=True))

    def _on_wp_slider_value_changed(self, val: int):
        if self._syncing_post_editor or not (0 <= self._current_post_index < len(self.wp_post_items)):
            return
        t_min, t_max = self._get_wp_post_bounds()
        pos = t_min + (val / 10000.0) * (t_max - t_min)
        post = self.wp_post_items[self._current_post_index]
        post["frame_pos"] = pos
        self.wp_scrub_time_label.setText(format_time(pos, include_millis=True))
        self._wp_scrub_timer.start(120)

    def _on_wp_scrub_timer_timeout(self):
        if 0 <= self._current_post_index < len(self.wp_post_items):
            post = self.wp_post_items[self._current_post_index]
            pos = post.get("frame_pos")
            self._capture_wp_frame(pos=pos)

    def _on_wp_step(self, delta_secs: float):
        if not (0 <= self._current_post_index < len(self.wp_post_items)):
            return
        post = self.wp_post_items[self._current_post_index]
        t_min, t_max = self._get_wp_post_bounds()
        cur_pos = post.get("frame_pos", t_min)
        new_pos = max(t_min, min(t_max, cur_pos + delta_secs))
        self._sync_wp_slider_to_pos(new_pos)
        self._capture_wp_frame(pos=new_pos)

    def _on_wp_sync_playhead(self):
        if not (0 <= self._current_post_index < len(self.wp_post_items)):
            return
        t_min, t_max = self._get_wp_post_bounds()
        playhead_pos = float(getattr(self.main_window, "current_position", 0.0) or 0.0)
        new_pos = max(t_min, min(t_max, playhead_pos))
        self._sync_wp_slider_to_pos(new_pos)
        self._capture_wp_frame(pos=new_pos)

    def _load_post_editor_state(self, index: int):
        if not (0 <= index < len(self.wp_post_items)):
            return
        self._current_post_index = index
        post = self.wp_post_items[index]

        self._syncing_post_editor = True
        self.wp_current_post_header.setText(f"<b>Post Settings: {html.escape(post.get('task_label', 'Post'))}</b>")
        self.wp_title_edit.setText(post.get("title", ""))
        self.wp_excerpt_edit.setPlainText(post.get("excerpt", ""))

        mode = post.get("featured_image_mode", "none")
        img = post.get("featured_image")
        frame_pos = post.get("frame_pos")
        if frame_pos is None:
            t_min, _ = self._get_wp_post_bounds(index)
            frame_pos = t_min
            post["frame_pos"] = frame_pos

        if mode == "grab" and self._is_video_project:
            self.wp_rad_thumb_grab.setChecked(True)
            self.wp_scrub_widget.setVisible(True)
            self.wp_browse_widget.setVisible(False)
            self._sync_wp_slider_to_pos(frame_pos)
            if img and Path(img).exists():
                self.wp_thumb_path_label.setText(f"Video frame captured at {format_time(frame_pos, include_millis=True)}")
                pix = QPixmap(str(img)).scaled(160, 90, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
                self.wp_thumb_preview_label.setPixmap(pix)
            else:
                self.wp_thumb_path_label.setText("Frame will be captured from video")
                self.wp_thumb_preview_label.clear()
                self.wp_thumb_preview_label.setText("Video Frame")
        elif mode == "file" and img:
            self.wp_rad_thumb_file.setChecked(True)
            self.wp_scrub_widget.setVisible(False)
            self.wp_browse_widget.setVisible(True)
            self.wp_thumb_path_label.setText(Path(img).name)
            if Path(img).exists():
                pix = QPixmap(str(img)).scaled(160, 90, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
                self.wp_thumb_preview_label.setPixmap(pix)
            else:
                self.wp_thumb_preview_label.clear()
                self.wp_thumb_preview_label.setText("Image not found")
        else:
            self.wp_rad_thumb_none.setChecked(True)
            self.wp_scrub_widget.setVisible(False)
            self.wp_browse_widget.setVisible(False)
            self.wp_thumb_path_label.setText("No image selected")
            self.wp_thumb_preview_label.clear()
            self.wp_thumb_preview_label.setText("No Thumbnail")

        self._syncing_post_editor = False

        self._set_editor_checked_authors(post.get("author_ids", []), post.get("author_term_ids", []))
        self._set_editor_checked_categories(post.get("category_ids", []))

    def _on_wp_thumb_mode_changed(self):
        if self._syncing_post_editor or not (0 <= self._current_post_index < len(self.wp_post_items)):
            return
        post = self.wp_post_items[self._current_post_index]
        if self.wp_rad_thumb_none.isChecked():
            self.wp_scrub_widget.setVisible(False)
            self.wp_browse_widget.setVisible(False)
            self.wp_thumb_path_label.setText("No image selected")
            self.wp_thumb_preview_label.clear()
            self.wp_thumb_preview_label.setText("No Thumbnail")
            post["featured_image"] = None
            post["featured_image_mode"] = "none"
        elif self.wp_rad_thumb_grab.isChecked():
            self.wp_browse_widget.setVisible(False)
            self.wp_scrub_widget.setVisible(True)
            if post.get("frame_pos") is None:
                t_min, _ = self._get_wp_post_bounds()
                post["frame_pos"] = t_min
            self._sync_wp_slider_to_pos(post["frame_pos"])
            self._capture_wp_frame(pos=post.get("frame_pos"))
        elif self.wp_rad_thumb_file.isChecked():
            self.wp_scrub_widget.setVisible(False)
            self.wp_browse_widget.setVisible(True)
            custom_path = post.get("featured_image")
            if custom_path and Path(custom_path).exists() and post.get("featured_image_mode") == "file":
                self.wp_thumb_path_label.setText(Path(custom_path).name)
                pix = QPixmap(str(custom_path)).scaled(160, 90, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
                self.wp_thumb_preview_label.setPixmap(pix)
            else:
                self.wp_thumb_path_label.setText("Click Browse to select image file")
                self.wp_thumb_preview_label.clear()
                self.wp_thumb_preview_label.setText("No Image\nSelected")

    def _capture_wp_frame(self, pos=None):
        if not (0 <= self._current_post_index < len(self.wp_post_items)):
            return None
        if not self._is_video_project:
            self.wp_thumb_preview_label.setText("Audio-only media\n(No video frames)")
            return None
        post = self.wp_post_items[self._current_post_index]
        media_file = getattr(self.main_window, "audio_file", None)
        if not media_file or not Path(media_file).exists():
            self.wp_thumb_preview_label.setText("No media\nloaded")
            return None

        if pos is None:
            if post.get("frame_pos") is not None:
                pos = float(post["frame_pos"])
            elif post.get("start") is not None:
                pos = float(post["start"])
            else:
                pos = float(getattr(self.main_window, "current_position", 0.0) or 0.0)

        post["frame_pos"] = float(pos)
        out_dir = Path(tempfile.gettempdir())
        out_path = out_dir / f"rtvs_wp_frame_{self._current_post_index}_{os.getpid()}.jpg"
        ff = ffmpeg_path() or "ffmpeg"
        cmd = [
            ff, "-hide_banner", "-loglevel", "error", "-y",
            "-ss", f"{max(0.0, float(pos)):.3f}",
            "-i", str(media_file),
            "-frames:v", "1",
            "-q:v", "2",
            str(out_path),
        ]
        flags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
        try:
            res = subprocess.run(cmd, capture_output=True, timeout=5, creationflags=flags)
            if res.returncode == 0 and out_path.exists() and out_path.stat().st_size > 0:
                post["featured_image"] = str(out_path)
                post["featured_image_mode"] = "grab"
                self._temp_preview_files.add(str(out_path))
                self.wp_thumb_path_label.setText(f"Video frame captured at {format_time(pos, include_millis=True)}")
                pix = QPixmap(str(out_path)).scaled(160, 90, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
                self.wp_thumb_preview_label.setPixmap(pix)
                return str(out_path)
        except subprocess.TimeoutExpired:
            print(f"[WORDPRESS EXPORT] Frame capture timed out after 5 seconds at {pos}s")
            self.wp_thumb_preview_label.setText("Frame capture\ntimed out")
            return None
        except Exception as exc:
            print(f"[WORDPRESS EXPORT] Frame capture failed: {exc}")
        self.wp_thumb_preview_label.setText("Frame capture\nfailed")
        return None

    def _on_wp_browse_thumb(self):
        if not (0 <= self._current_post_index < len(self.wp_post_items)):
            return
        fn, _ = QFileDialog.getOpenFileName(
            self,
            "Select WordPress Featured Image",
            "",
            "Image Files (*.jpg *.jpeg *.png *.webp);;All Files (*.*)",
        )
        if fn:
            post = self.wp_post_items[self._current_post_index]
            post["featured_image"] = fn
            post["featured_image_mode"] = "file"
            self.wp_rad_thumb_file.setChecked(True)
            self.wp_thumb_path_label.setText(Path(fn).name)
            pix = QPixmap(fn).scaled(160, 90, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
            self.wp_thumb_preview_label.setPixmap(pix)

    def rebuild_post_items(self):
        scope = "full"
        if hasattr(self.parent(), "scope_combo"):
            scope = self.parent().scope_combo.currentData()
        audio_file = getattr(self.main_window, "audio_file", None)
        base_name = Path(audio_file).stem if audio_file else "Draft Story"
        stories = getattr(self.main_window, "stories", []) or []

        new_items = []

        if scope == "full":
            raw_text = self.main_window._get_transcript_text_slice(0.0, None) if hasattr(self.main_window, "_get_transcript_text_slice") else ""
            excerpt = generate_wp_excerpt(raw_text, 55)
            new_items.append({
                "task_label": "Full Episode",
                "title": base_name,
                "excerpt": excerpt,
                "start": None,
                "end": None,
                "frame_pos": float(getattr(self.main_window, "current_position", 0.0) or 0.0),
                "author_ids": [],
                "author_term_ids": [],
                "category_ids": [],
                "featured_image": None,
                "featured_image_mode": "none",
            })
        elif scope == "selected_stories":
            indices = getattr(self.main_window, "current_selected_story_indices", []) or []
            if not indices and stories:
                indices = [0]
            for idx in indices:
                if 0 <= idx < len(stories):
                    st = stories[idx]
                    st_title = st.title if st.title else f"{base_name} - Story {idx + 1}"
                    raw_text = self.main_window._get_transcript_text_slice(st.start, st.end) if hasattr(self.main_window, "_get_transcript_text_slice") else ""
                    excerpt = generate_wp_excerpt(raw_text, 55)
                    new_items.append({
                        "task_label": f"Story {idx + 1}" + (f": {st.title}" if st.title else ""),
                        "title": st_title,
                        "excerpt": excerpt,
                        "start": st.start,
                        "end": st.end,
                        "frame_pos": float(st.start if st.start is not None else (getattr(self.main_window, "current_position", 0.0) or 0.0)),
                        "author_ids": [],
                        "author_term_ids": [],
                        "category_ids": [],
                        "featured_image": None,
                        "featured_image_mode": "none",
                    })
        elif scope == "all_stories":
            for idx, st in enumerate(stories):
                st_title = st.title if st.title else f"{base_name} - Story {idx + 1}"
                raw_text = self.main_window._get_transcript_text_slice(st.start, st.end) if hasattr(self.main_window, "_get_transcript_text_slice") else ""
                excerpt = generate_wp_excerpt(raw_text, 55)
                new_items.append({
                    "task_label": f"Story {idx + 1}" + (f": {st.title}" if st.title else ""),
                    "title": st_title,
                    "excerpt": excerpt,
                    "start": st.start,
                    "end": st.end,
                    "frame_pos": float(st.start if st.start is not None else (getattr(self.main_window, "current_position", 0.0) or 0.0)),
                    "author_ids": [],
                    "author_term_ids": [],
                    "category_ids": [],
                    "featured_image": None,
                    "featured_image_mode": "none",
                })
        elif scope == "full_and_all_stories":
            raw_text = self.main_window._get_transcript_text_slice(0.0, None) if hasattr(self.main_window, "_get_transcript_text_slice") else ""
            excerpt = generate_wp_excerpt(raw_text, 55)
            new_items.append({
                "task_label": "Full Episode",
                "title": base_name,
                "excerpt": excerpt,
                "start": None,
                "end": None,
                "frame_pos": float(getattr(self.main_window, "current_position", 0.0) or 0.0),
                "author_ids": [],
                "author_term_ids": [],
                "category_ids": [],
                "featured_image": None,
                "featured_image_mode": "none",
            })
            for idx, st in enumerate(stories):
                st_title = st.title if st.title else f"{base_name} - Story {idx + 1}"
                raw_text = self.main_window._get_transcript_text_slice(st.start, st.end) if hasattr(self.main_window, "_get_transcript_text_slice") else ""
                st_excerpt = generate_wp_excerpt(raw_text, 55)
                new_items.append({
                    "task_label": f"Story {idx + 1}" + (f": {st.title}" if st.title else ""),
                    "title": st_title,
                    "excerpt": st_excerpt,
                    "start": st.start,
                    "end": st.end,
                    "frame_pos": float(st.start if st.start is not None else (getattr(self.main_window, "current_position", 0.0) or 0.0)),
                    "author_ids": [],
                    "author_term_ids": [],
                    "category_ids": [],
                    "featured_image": None,
                    "featured_image_mode": "none",
                })

        if not new_items:
            new_items.append({
                "task_label": "Draft Story",
                "title": base_name,
                "excerpt": "",
                "start": None,
                "end": None,
                "frame_pos": float(getattr(self.main_window, "current_position", 0.0) or 0.0),
                "author_ids": [],
                "author_term_ids": [],
                "category_ids": [],
                "featured_image": None,
                "featured_image_mode": "none",
            })

        self.wp_post_items = new_items
        self._current_post_index = 0

        self.wp_posts_list.blockSignals(True)
        self.wp_posts_list.clear()
        for idx in range(len(self.wp_post_items)):
            self.wp_posts_list.addItem("")
            self._update_post_list_item_label(idx)
        self.wp_posts_list.blockSignals(False)

        has_multi = len(self.wp_post_items) > 1
        self.wp_post_nav_widget.setVisible(has_multi)
        self.wp_bulk_box.setVisible(has_multi)

        if self.wp_posts_list.count() > 0:
            self.wp_posts_list.setCurrentRow(0)
        self._load_post_editor_state(0)

    def _populate_wp_export_metadata(self, force_refresh: bool = False):
        categories = []
        authors = []

        if not force_refresh:
            cached_cats = self.settings.value("wp_cached_categories", "")
            cached_auths = self.settings.value("wp_cached_authors", "")
            if cached_cats and cached_auths:
                try:
                    categories = json.loads(cached_cats)
                    authors = json.loads(cached_auths)
                except Exception:
                    pass

        if not categories or not authors or force_refresh:
            client = getattr(self.main_window, "_get_wp_client", lambda: None)()
            if client:
                try:
                    categories = client.get_categories() if hasattr(client, "get_categories") else []
                    authors = client.get_authors() if hasattr(client, "get_authors") else []
                    self.settings.setValue("wp_cached_categories", json.dumps(categories))
                    self.settings.setValue("wp_cached_authors", json.dumps(authors))
                except Exception as exc:
                    print(f"[WORDPRESS EXPORT UI] Failed to fetch metadata: {exc}")

        self.wp_cached_authors_data = authors or []
        self.wp_cached_categories_data = categories or []

        self.wp_author_list.blockSignals(True)
        self.wp_author_list.clear()
        for author in self.wp_cached_authors_data:
            if isinstance(author, dict):
                name = author.get("name", "Unknown Author")
                slug = author.get("slug", "")
                slug_str = f" (@{slug})" if slug else ""
                auth_type = author.get("type", "Guest Author" if author.get("is_guest") else "WP User")
                item = QListWidgetItem(f"{name}{slug_str} [{auth_type}]")
                item.setData(Qt.ItemDataRole.UserRole, author)
                item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                item.setCheckState(Qt.CheckState.Unchecked)
                self.wp_author_list.addItem(item)
        self.wp_author_list.blockSignals(False)

        self.wp_category_list.blockSignals(True)
        self.wp_category_list.clear()
        for cat in self.wp_cached_categories_data:
            if isinstance(cat, dict):
                item = QListWidgetItem(cat.get("name", "Unnamed Category"))
                item.setData(Qt.ItemDataRole.UserRole, cat.get("id"))
                item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                item.setCheckState(Qt.CheckState.Unchecked)
                self.wp_category_list.addItem(item)
        self.wp_category_list.blockSignals(False)

    def _refresh_wp_metadata(self):
        self._populate_wp_export_metadata(force_refresh=True)
        if 0 <= self._current_post_index < len(self.wp_post_items):
            self._load_post_editor_state(self._current_post_index)
        QMessageBox.information(self, "WordPress Metadata", "Author and Category lists refreshed successfully.")


class WordPressExportDestination(ExportDestination):
    """Export destination handler for WordPress REST API Draft Posts."""

    def __init__(self, plugin: Any = None):
        super().__init__(
            id="wordpress",
            title="WordPress Draft Post",
            description="Extracts audio and publishes formatted draft posts directly to your WordPress site.",
            icon="wordpress",
        )
        self.plugin = plugin
        self.tab_widget: Optional[WordPressExportTabWidget] = None

    def create_widget(self, parent: Any, main_window: Any) -> Any:
        self.tab_widget = WordPressExportTabWidget(parent, main_window)
        return self.tab_widget

    def on_scope_changed(self, scope: str, stories: list) -> None:
        if self.tab_widget:
            self.tab_widget.rebuild_post_items()

    def validate(self) -> Tuple[bool, str]:
        if not self.tab_widget:
            return False, "WordPress tab not initialized."
        w = self.tab_widget
        if not w.wp_cb_en.isChecked() and not w.wp_cb_es.isChecked():
            return False, "Please select at least one language for WordPress export (English or Spanish)."
        if not w.wp_post_items:
            return False, "No posts configured for WordPress export."
        return True, ""

    def get_export_data(self) -> Dict[str, Any]:
        if not self.tab_widget:
            return {}
        w = self.tab_widget
        return {
            "wp_posts": list(w.wp_post_items),
            "include_english": w.wp_cb_en.isChecked(),
            "include_spanish": w.wp_cb_es.isChecked(),
            "spanish_presentation": w.wp_pres_combo.currentData(),
            "primary_language": w.wp_primary_lang_combo.currentData(),
            "custom_notice": w.wp_custom_text_edit.toPlainText().strip(),
            "notice_placement": "top" if w.wp_rad_pos_top.isChecked() else "bottom",
        }

    def execute_export(self, main_window: Any, export_data: Dict[str, Any], progress_dialog: Any = None) -> bool:
        if hasattr(main_window, "_handle_wordpress_export_result"):
            main_window._handle_wordpress_export_result(export_data)
            return True
        return False
