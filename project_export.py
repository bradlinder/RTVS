"""Radio & TV Segmenter v1.1.1 — project export responsibilities.

Methods intentionally retain the MainWindow-facing API so behavior remains
maintaining the established MainWindow-facing API while responsibilities are isolated.
"""

from prs_shared import *
from wordpress_export import generate_wp_excerpt, WordPressSettingsDialog, _get_wp_password


class UnifiedExportDialog(QDialog):
    """Unified Export Center supporting Local Files and WordPress Draft Posts."""

    def __init__(self, main_window, initial_scope="full", parent=None):
        super().__init__(parent or main_window)
        self.main_window = main_window
        self.setWindowTitle("Export")
        self.setMinimumWidth(820)
        self.setMinimumHeight(640)
        self.resize(880, 720)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)

        # Target Selection: Local vs WordPress
        dest_group = QGroupBox("Export Destination")
        dest_layout = QHBoxLayout(dest_group)
        self.radio_local = QRadioButton("Local Files (Media && Transcripts)")
        self.radio_wp = QRadioButton("WordPress Draft Post")
        self.radio_local.setChecked(True)
        dest_layout.addWidget(self.radio_local)
        dest_layout.addWidget(self.radio_wp)
        layout.addWidget(dest_group)

        # Scope Selection
        scope_group = QGroupBox("Export Scope")
        scope_layout = QVBoxLayout(scope_group)
        self.scope_combo = QComboBox()
        self.scope_combo.addItem("Selected Stories", "selected_stories")
        self.scope_combo.addItem("All Stories", "all_stories")
        self.scope_combo.addItem("Full Episode", "full")
        self.scope_combo.addItem("Full Episode & All Stories", "full_and_all_stories")
        
        # Set default selection
        idx = self.scope_combo.findData(initial_scope)
        if idx >= 0:
            self.scope_combo.setCurrentIndex(idx)
        else:
            # If stories exist and one is selected, default to selected stories
            selected_rows = getattr(self.main_window, "current_selected_story_indices", [])
            if selected_rows:
                self.scope_combo.setCurrentIndex(0)
            elif getattr(self.main_window, "stories", []):
                self.scope_combo.setCurrentIndex(1)
            else:
                self.scope_combo.setCurrentIndex(2)

        scope_layout.addWidget(self.scope_combo)
        layout.addWidget(scope_group)

        # Stacked options area for Destination
        self.stacked_widget = QStackedWidget()

        # Page 0: Local Options
        local_page = QWidget()
        local_page_layout = QVBoxLayout(local_page)
        local_page_layout.setContentsMargins(0, 0, 0, 0)

        local_scroll = QScrollArea()
        local_scroll.setWidgetResizable(True)
        local_scroll.setFrameShape(QFrame.Shape.NoFrame)
        local_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        local_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)

        local_scroll_content = QWidget()
        local_layout = QVBoxLayout(local_scroll_content)
        local_layout.setContentsMargins(2, 2, 2, 2)
        local_layout.setSpacing(10)

        formats_group = QGroupBox("Local Formats")
        formats_layout = QVBoxLayout(formats_group)
        self.cb_txt = QCheckBox("Text transcript (.txt)")
        self.cb_docx = QCheckBox("Word document (.docx)")
        self.cb_srt = QCheckBox("SubRip subtitles (.srt)")
        self.cb_vtt = QCheckBox("WebVTT subtitles (.vtt)")
        
        audio_file = getattr(self.main_window, "audio_file", None)
        media_ext = audio_file.suffix.lower() if audio_file else "media"
        self.cb_media = QCheckBox(f"Media clip ({media_ext})")
        
        self.cb_txt.setChecked(True)
        self.cb_docx.setChecked(True)
        self.cb_media.setChecked(audio_file is not None)
        self.cb_media.setEnabled(audio_file is not None)

        formats_layout.addWidget(self.cb_txt)
        formats_layout.addWidget(self.cb_docx)
        formats_layout.addWidget(self.cb_srt)
        formats_layout.addWidget(self.cb_vtt)
        formats_layout.addWidget(self.cb_media)
        local_layout.addWidget(formats_group)

        # Local Content & Language options
        content_group = QGroupBox("Content & Language Options")
        content_layout = QVBoxLayout(content_group)
        self.cb_speakers = QCheckBox("Include Speaker Labels")
        self.cb_speakers.setChecked(True)
        self.cb_timestamps = QCheckBox("Include Timestamps")
        self.cb_timestamps.setChecked(False)
        content_layout.addWidget(self.cb_speakers)
        content_layout.addWidget(self.cb_timestamps)

        lang_layout = QHBoxLayout()
        self.cb_en = QCheckBox("English")
        self.cb_en.setChecked(True)
        self.cb_es = QCheckBox("Spanish (Translated)")
        
        has_es = self.main_window.has_spanish_translation() if hasattr(self.main_window, "has_spanish_translation") else (
            self.main_window.translation_is_current(self.main_window.translation_key("en", "es")) if hasattr(self.main_window, "translation_is_current") else False
        )
        self.cb_es.setChecked(has_es)
        self.cb_es.setEnabled(has_es)
        if not has_es:
            self.cb_es.setToolTip("Spanish translation is not available for this project. Generate a translation first to enable.")
        lang_layout.addWidget(self.cb_en)
        lang_layout.addWidget(self.cb_es)
        lang_layout.addStretch()
        content_layout.addLayout(lang_layout)
        local_layout.addWidget(content_group)

        # Base Filename
        name_form = QFormLayout()
        default_name = safe_filename(
            self.main_window.project_file.stem
            if getattr(self.main_window, "project_file", None)
            else (self.main_window.audio_file.stem if getattr(self.main_window, "audio_file", None) else "export")
        )
        self.filename_edit = QLineEdit(default_name)
        name_form.addRow("Base filename:", self.filename_edit)
        local_layout.addLayout(name_form)
        local_layout.addStretch()

        local_scroll.setWidget(local_scroll_content)
        local_page_layout.addWidget(local_scroll)

        self.stacked_widget.addWidget(local_page)

        # Page 1: WordPress Options
        wp_page = QWidget()
        wp_page_layout = QVBoxLayout(wp_page)
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

        wp_info_group = QGroupBox("WordPress Draft Settings")
        wp_info_layout = QVBoxLayout(wp_info_group)
        wp_info_layout.setSpacing(10)

        wp_notice = QLabel(
            "Extracts audio as <b>128 kbps MP3</b>, uploads to your WordPress Media Library, "
            "and creates a <b>Draft Post</b> with Gutenberg audio player and formatted transcript."
        )
        wp_notice.setWordWrap(True)
        wp_info_layout.addWidget(wp_notice)

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
        nav_layout.addWidget(self.wp_posts_list)
        nav_layout.addWidget(self.wp_autofill_all_excerpts_btn)
        self.wp_posts_container.addWidget(self.wp_post_nav_widget)

        # Right Editor: Active Post configuration
        self.wp_post_editor_widget = QWidget()
        editor_layout = QVBoxLayout(self.wp_post_editor_widget)
        editor_layout.setContentsMargins(0, 0, 0, 0)
        editor_layout.setSpacing(8)

        self.wp_current_post_header = QLabel("<b>Post Settings</b>")
        editor_layout.addWidget(self.wp_current_post_header)

        # Title & Excerpt Form
        form_layout = QFormLayout()
        form_layout.setLabelAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignRight)
        form_layout.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        form_layout.setRowWrapPolicy(QFormLayout.RowWrapPolicy.DontWrapRows)
        form_layout.setVerticalSpacing(8)
        self.wp_title_edit = QLineEdit(default_name)
        self.wp_title_edit.textEdited.connect(self._on_title_edited)
        form_layout.addRow("Post Title:", self.wp_title_edit)

        excerpt_container = QWidget()
        excerpt_row = QHBoxLayout(excerpt_container)
        excerpt_row.setContentsMargins(0, 0, 0, 0)
        excerpt_row.setSpacing(6)
        self.wp_excerpt_edit = ResizableTextEdit("")
        self.wp_excerpt_edit.setToolTip("Transcript snippet (≤55 words). Drag bottom handle to resize.")
        self.wp_excerpt_edit.textChanged.connect(self._on_excerpt_edited)
        self.wp_auto_excerpt_btn = QPushButton("Auto")
        self.wp_auto_excerpt_btn.setToolTip("Generate excerpt from transcript snippet")
        self.wp_auto_excerpt_btn.clicked.connect(self._auto_generate_current_excerpt)
        excerpt_row.addWidget(self.wp_excerpt_edit)
        excerpt_row.addWidget(self.wp_auto_excerpt_btn)
        form_layout.addRow("Excerpt (≤55 words):", excerpt_container)
        editor_layout.addLayout(form_layout)

        # Authors & Categories columns
        tax_columns = QHBoxLayout()
        tax_columns.setSpacing(10)

        # Authors Column
        authors_box = QVBoxLayout()
        authors_box.setSpacing(4)
        auth_hdr = QLabel("<b>Authors (supports multiple):</b>")
        auth_hdr.setWordWrap(True)
        self.wp_author_filter = QLineEdit()
        self.wp_author_filter.setPlaceholderText("Filter authors...")
        self.wp_author_filter.textChanged.connect(self._filter_authors_list)
        self.wp_author_list = QListWidget()
        self.wp_author_list.setMinimumHeight(100)
        self.wp_author_list.setMaximumHeight(180)
        self.wp_author_list.itemChanged.connect(self._on_author_item_changed)

        auth_btn_row = QHBoxLayout()
        self.wp_clear_auths_btn = QPushButton("Clear")
        self.wp_clear_auths_btn.clicked.connect(self._clear_current_authors)
        auth_btn_row.addStretch()
        auth_btn_row.addWidget(self.wp_clear_auths_btn)

        authors_box.addWidget(auth_hdr)
        authors_box.addWidget(self.wp_author_filter)
        authors_box.addWidget(self.wp_author_list)
        authors_box.addLayout(auth_btn_row)
        tax_columns.addLayout(authors_box)

        # Categories Column
        cats_box = QVBoxLayout()
        cats_box.setSpacing(4)
        cat_hdr = QLabel("<b>Categories:</b>")
        cat_hdr.setWordWrap(True)
        self.wp_category_filter = QLineEdit()
        self.wp_category_filter.setPlaceholderText("Filter categories...")
        self.wp_category_filter.textChanged.connect(self._filter_categories_list)
        self.wp_category_list = QListWidget()
        self.wp_category_list.setMinimumHeight(100)
        self.wp_category_list.setMaximumHeight(180)
        self.wp_category_list.itemChanged.connect(self._on_category_item_changed)

        cat_btn_row = QHBoxLayout()
        self.wp_clear_cats_btn = QPushButton("Clear")
        self.wp_clear_cats_btn.clicked.connect(self._clear_current_categories)
        cat_btn_row.addStretch()
        cat_btn_row.addWidget(self.wp_clear_cats_btn)

        cats_box.addWidget(cat_hdr)
        cats_box.addWidget(self.wp_category_filter)
        cats_box.addWidget(self.wp_category_list)
        cats_box.addLayout(cat_btn_row)
        tax_columns.addLayout(cats_box)

        editor_layout.addLayout(tax_columns)

        # Bulk Actions Row (When multi-post scope is active)
        self.wp_bulk_box = QWidget()
        bulk_layout = QHBoxLayout(self.wp_bulk_box)
        bulk_layout.setContentsMargins(0, 0, 0, 0)
        self.wp_apply_authors_all_btn = QPushButton("Apply Authors to All Posts")
        self.wp_apply_authors_all_btn.setToolTip("Copy this post's author selection to all other posts in the queue")
        self.wp_apply_authors_all_btn.clicked.connect(self._apply_authors_to_all_posts)
        self.wp_apply_cats_all_btn = QPushButton("Apply Categories to All Posts")
        self.wp_apply_cats_all_btn.setToolTip("Copy this post's category selection to all other posts in the queue")
        self.wp_apply_cats_all_btn.clicked.connect(self._apply_categories_to_all_posts)
        bulk_layout.addWidget(self.wp_apply_authors_all_btn)
        bulk_layout.addWidget(self.wp_apply_cats_all_btn)
        bulk_layout.addStretch()
        editor_layout.addWidget(self.wp_bulk_box)

        self.wp_posts_container.addWidget(self.wp_post_editor_widget)
        wp_info_layout.addLayout(self.wp_posts_container)

        # Post list selection change hook
        self.wp_posts_list.currentRowChanged.connect(self._on_wp_post_selection_changed)

        # Cached raw metadata
        self.wp_cached_authors_data = []
        self.wp_cached_categories_data = []
        self.wp_post_items = []
        self._current_post_index = 0
        self._syncing_post_editor = False

        # Load cached metadata into UI immediately
        self._populate_wp_export_metadata(force_refresh=False)

        # Build post list based on initial scope
        self._rebuild_wp_post_items()

        # Metadata Refresh Button Row
        meta_btn_row = QHBoxLayout()
        self.wp_refresh_meta_btn = QPushButton("Refresh WordPress Metadata")
        self.wp_refresh_meta_btn.setToolTip("Fetch fresh Author and Category lists from WordPress site")
        self.wp_refresh_meta_btn.clicked.connect(self._refresh_wp_metadata)
        meta_btn_row.addStretch()
        meta_btn_row.addWidget(self.wp_refresh_meta_btn)
        wp_info_layout.addLayout(meta_btn_row)

        # WordPress Language Options
        wp_lang_group = QGroupBox("Transcript Languages")
        wp_lang_layout = QVBoxLayout(wp_lang_group)

        wp_lang_checks = QHBoxLayout()
        self.wp_cb_en = QCheckBox("English")
        self.wp_cb_en.setChecked(True)
        self.wp_cb_es = QCheckBox("Spanish (Translated)")
        self.wp_cb_es.setChecked(has_es)
        self.wp_cb_es.setEnabled(has_es)
        if not has_es:
            self.wp_cb_es.setToolTip("Spanish translation is not available for this project. Generate a translation first to enable.")
        wp_lang_checks.addWidget(self.wp_cb_en)
        wp_lang_checks.addWidget(self.wp_cb_es)
        wp_lang_checks.addStretch()
        wp_lang_layout.addLayout(wp_lang_checks)

        # Dual-language options container (Primary Language + Placement)
        self.wp_pres_container = QWidget()
        pres_layout = QVBoxLayout(self.wp_pres_container)
        pres_layout.setContentsMargins(0, 4, 0, 0)
        pres_layout.setSpacing(6)

        # Primary Language Selector
        prim_row = QHBoxLayout()
        prim_label = QLabel("Primary Language:")
        self.wp_primary_lang_combo = QComboBox()
        self.wp_primary_lang_combo.addItem("English", "en")
        self.wp_primary_lang_combo.addItem("Spanish", "es")
        prim_row.addWidget(prim_label)
        prim_row.addWidget(self.wp_primary_lang_combo)
        prim_row.addStretch()
        pres_layout.addLayout(prim_row)

        # Placement / Presentation Selector
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

        wp_lang_layout.addWidget(self.wp_pres_container)

        def update_wp_pres_visibility():
            both = self.wp_cb_en.isChecked() and self.wp_cb_es.isChecked()
            self.wp_pres_container.setVisible(both)

        self.wp_cb_en.toggled.connect(update_wp_pres_visibility)
        self.wp_cb_es.toggled.connect(update_wp_pres_visibility)
        update_wp_pres_visibility()

        wp_info_layout.addWidget(wp_lang_group)

        # Connection status & Settings button
        wp_conn_layout = QHBoxLayout()
        self.wp_conn_status = QLabel("")
        self.wp_settings_btn = QPushButton("WordPress Settings...")
        self.wp_settings_btn.clicked.connect(self._open_wp_settings)
        wp_conn_layout.addWidget(self.wp_conn_status)
        wp_conn_layout.addStretch()
        wp_conn_layout.addWidget(self.wp_settings_btn)
        wp_info_layout.addLayout(wp_conn_layout)

        self._update_wp_conn_status()

        wp_layout.addWidget(wp_info_group)
        wp_layout.addStretch()

        wp_scroll.setWidget(wp_scroll_content)
        wp_page_layout.addWidget(wp_scroll)

        self.stacked_widget.addWidget(wp_page)

        layout.addWidget(self.stacked_widget)

        # Connect radio buttons
        self.radio_local.toggled.connect(self._on_dest_changed)
        self.scope_combo.currentIndexChanged.connect(self._on_scope_changed)

        # Dialog Buttons
        btns = QHBoxLayout()
        btns.addStretch()
        self.export_btn = QPushButton("Export")
        self.export_btn.setDefault(True)
        self.cancel_btn = QPushButton("Cancel")
        btns.addWidget(self.export_btn)
        btns.addWidget(self.cancel_btn)
        layout.addLayout(btns)

        self.cancel_btn.clicked.connect(self.reject)
        self.export_btn.clicked.connect(self._handle_accept)

        self._on_dest_changed()

    def _open_wp_settings(self):
        dialog = WordPressSettingsDialog(self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self._update_wp_conn_status()
            self._populate_wp_export_metadata(force_refresh=True)

    def _update_wp_conn_status(self):
        settings = QSettings("RadioTVStorySegmenter", "RadioTVStorySegmenter")
        url = str(settings.value("wp_site_url", "") or "").strip()
        user = str(settings.value("wp_username", "") or "").strip()
        pwd = _get_wp_password(user) if user else ""
        if url and user and pwd:
            try:
                import urllib.parse
                domain = urllib.parse.urlparse(url).netloc or url
            except Exception:
                domain = url
            self.wp_conn_status.setText(f"Connected to: <b>{html.escape(domain)}</b> ({html.escape(user)})")
            self.wp_conn_status.setStyleSheet("color: #2ea44f;")
        else:
            self.wp_conn_status.setText("<i>WordPress credentials not configured</i>")
            self.wp_conn_status.setStyleSheet("color: #e06c75;")

    def _get_initial_transcript_text(self) -> str:
        if hasattr(self.main_window, "_get_transcript_text_slice"):
            return self.main_window._get_transcript_text_slice(0.0, None)
        if getattr(self.main_window, "transcript", None):
            segs = self.main_window.transcript.get("segments", [])
            return " ".join(s.get("text", "") for s in segs)
        return ""

    def _on_dest_changed(self):
        if self.radio_local.isChecked():
            self.stacked_widget.setCurrentIndex(0)
            self.export_btn.setText("Export Files...")
        else:
            self.stacked_widget.setCurrentIndex(1)
            self.export_btn.setText("Publish Draft to WordPress")
            self._rebuild_wp_post_items()

    def _on_scope_changed(self):
        if not self.radio_local.isChecked():
            self._rebuild_wp_post_items()

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
        excerpt = generate_wp_excerpt(raw_text, 55) if 'generate_wp_excerpt' in globals() else raw_text
        self.wp_excerpt_edit.setPlainText(excerpt)
        post["excerpt"] = excerpt

    def _autofill_all_excerpts(self):
        for post in self.wp_post_items:
            raw_text = self.main_window._get_transcript_text_slice(post.get("start"), post.get("end")) if hasattr(self.main_window, "_get_transcript_text_slice") else ""
            post["excerpt"] = generate_wp_excerpt(raw_text, 55) if 'generate_wp_excerpt' in globals() else raw_text
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

    def _get_editor_checked_authors(self) -> tuple[list[int], list[int]]:
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

    def _set_editor_checked_authors(self, author_ids: list[int], author_term_ids: list[int]):
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

    def _get_editor_checked_categories(self) -> list[int]:
        cat_ids = []
        for i in range(self.wp_category_list.count()):
            item = self.wp_category_list.item(i)
            if item.checkState() == Qt.CheckState.Checked:
                cid = item.data(Qt.ItemDataRole.UserRole)
                if cid is not None:
                    cat_ids.append(int(cid))
        return cat_ids

    def _set_editor_checked_categories(self, cat_ids: list[int]):
        self._syncing_post_editor = True
        cid_set = set(int(x) for x in (cat_ids or []))
        for i in range(self.wp_category_list.count()):
            item = self.wp_category_list.item(i)
            cid = item.data(Qt.ItemDataRole.UserRole)
            checked = (cid is not None and int(cid) in cid_set)
            item.setCheckState(Qt.CheckState.Checked if checked else Qt.CheckState.Unchecked)
        self._syncing_post_editor = False

    def _load_post_editor_state(self, index: int):
        if not (0 <= index < len(self.wp_post_items)):
            return
        self._current_post_index = index
        post = self.wp_post_items[index]

        self._syncing_post_editor = True
        self.wp_current_post_header.setText(f"<b>Post Settings: {html.escape(post.get('task_label', 'Post'))}</b>")
        self.wp_title_edit.setText(post.get("title", ""))
        self.wp_excerpt_edit.setPlainText(post.get("excerpt", ""))
        self._syncing_post_editor = False

        self._set_editor_checked_authors(post.get("author_ids", []), post.get("author_term_ids", []))
        self._set_editor_checked_categories(post.get("category_ids", []))

    def _rebuild_wp_post_items(self):
        scope = self.scope_combo.currentData()
        audio_file = getattr(self.main_window, "audio_file", None)
        base_name = Path(audio_file).stem if audio_file else "Draft Story"
        stories = getattr(self.main_window, "stories", []) or []

        new_items = []

        if scope == "full":
            raw_text = self.main_window._get_transcript_text_slice(0.0, None) if hasattr(self.main_window, "_get_transcript_text_slice") else ""
            excerpt = generate_wp_excerpt(raw_text, 55) if 'generate_wp_excerpt' in globals() else raw_text[:55]
            new_items.append({
                "task_label": "Full Episode",
                "title": base_name,
                "excerpt": excerpt,
                "start": None,
                "end": None,
                "author_ids": [],
                "author_term_ids": [],
                "category_ids": [],
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
                    excerpt = generate_wp_excerpt(raw_text, 55) if 'generate_wp_excerpt' in globals() else raw_text[:55]
                    new_items.append({
                        "task_label": f"Story {idx + 1}" + (f": {st.title}" if st.title else ""),
                        "title": st_title,
                        "excerpt": excerpt,
                        "start": st.start,
                        "end": st.end,
                        "author_ids": [],
                        "author_term_ids": [],
                        "category_ids": [],
                    })
        elif scope == "all_stories":
            for idx, st in enumerate(stories):
                st_title = st.title if st.title else f"{base_name} - Story {idx + 1}"
                raw_text = self.main_window._get_transcript_text_slice(st.start, st.end) if hasattr(self.main_window, "_get_transcript_text_slice") else ""
                excerpt = generate_wp_excerpt(raw_text, 55) if 'generate_wp_excerpt' in globals() else raw_text[:55]
                new_items.append({
                    "task_label": f"Story {idx + 1}" + (f": {st.title}" if st.title else ""),
                    "title": st_title,
                    "excerpt": excerpt,
                    "start": st.start,
                    "end": st.end,
                    "author_ids": [],
                    "author_term_ids": [],
                    "category_ids": [],
                })
        elif scope == "full_and_all_stories":
            raw_text = self.main_window._get_transcript_text_slice(0.0, None) if hasattr(self.main_window, "_get_transcript_text_slice") else ""
            excerpt = generate_wp_excerpt(raw_text, 55) if 'generate_wp_excerpt' in globals() else raw_text[:55]
            new_items.append({
                "task_label": "Full Episode",
                "title": base_name,
                "excerpt": excerpt,
                "start": None,
                "end": None,
                "author_ids": [],
                "author_term_ids": [],
                "category_ids": [],
            })
            for idx, st in enumerate(stories):
                st_title = st.title if st.title else f"{base_name} - Story {idx + 1}"
                raw_text = self.main_window._get_transcript_text_slice(st.start, st.end) if hasattr(self.main_window, "_get_transcript_text_slice") else ""
                st_excerpt = generate_wp_excerpt(raw_text, 55) if 'generate_wp_excerpt' in globals() else raw_text[:55]
                new_items.append({
                    "task_label": f"Story {idx + 1}" + (f": {st.title}" if st.title else ""),
                    "title": st_title,
                    "excerpt": st_excerpt,
                    "start": st.start,
                    "end": st.end,
                    "author_ids": [],
                    "author_term_ids": [],
                    "category_ids": [],
                })

        if not new_items:
            new_items.append({
                "task_label": "Draft Story",
                "title": base_name,
                "excerpt": "",
                "start": None,
                "end": None,
                "author_ids": [],
                "author_term_ids": [],
                "category_ids": [],
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

    def _handle_accept(self):
        if self.radio_local.isChecked():
            formats = {
                "txt": self.cb_txt.isChecked(),
                "docx": self.cb_docx.isChecked(),
                "srt": self.cb_srt.isChecked(),
                "vtt": self.cb_vtt.isChecked(),
                "media": self.cb_media.isChecked(),
            }
            if not any(formats.values()):
                QMessageBox.warning(self, "Export", "Please select at least one format to export.")
                return

            if (formats["txt"] or formats["docx"]) and not self.cb_en.isChecked() and not self.cb_es.isChecked():
                QMessageBox.warning(self, "Export", "Please select at least one language track (English or Spanish).")
                return
        else:
            if not self.wp_cb_en.isChecked() and not self.wp_cb_es.isChecked():
                QMessageBox.warning(self, "Export", "Please select at least one transcript language (English or Spanish) for the WordPress post.")
                return

        self.accept()

    def _populate_wp_export_metadata(self, force_refresh=False):
        """Populate Author and Category widgets from QSettings cache or fresh API request."""
        settings = QSettings("RadioTVStorySegmenter", "RadioTVStorySegmenter")
        
        categories = []
        authors = []

        if not force_refresh:
            cached_cats = settings.value("wp_cached_categories", "")
            cached_auths = settings.value("wp_cached_authors", "")
            if cached_cats and cached_auths:
                try:
                    categories = json.loads(cached_cats)
                    authors = json.loads(cached_auths)
                except Exception:
                    pass

        # Fetch fresh if cache is missing or refresh requested
        if not categories or not authors or force_refresh:
            client = getattr(self.main_window, "_get_wp_client", lambda: None)()
            if client:
                try:
                    categories = client.get_categories() if hasattr(client, "get_categories") else []
                    authors = client.get_authors() if hasattr(client, "get_authors") else []
                    settings.setValue("wp_cached_categories", json.dumps(categories))
                    settings.setValue("wp_cached_authors", json.dumps(authors))
                except Exception as exc:
                    print(f"[WORDPRESS EXPORT UI] Failed to fetch metadata: {exc}")

        self.wp_cached_authors_data = authors or []
        self.wp_cached_categories_data = categories or []

        # Populate Author List Widget
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

        # Populate Category List Widget
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
        """Action handler for Refresh Metadata button."""
        self._populate_wp_export_metadata(force_refresh=True)
        if 0 <= self._current_post_index < len(self.wp_post_items):
            self._load_post_editor_state(self._current_post_index)
        QMessageBox.information(self, "WordPress Metadata", "Author and Category lists refreshed successfully.")

    def get_result(self) -> dict:
        is_local = self.radio_local.isChecked()
        scope = self.scope_combo.currentData()
        
        if is_local:
            formats = {
                "txt": self.cb_txt.isChecked(),
                "docx": self.cb_docx.isChecked(),
                "srt": self.cb_srt.isChecked(),
                "vtt": self.cb_vtt.isChecked(),
                "media": self.cb_media.isChecked(),
            }
            options = {
                "include_speakers": self.cb_speakers.isChecked(),
                "include_timestamps": self.cb_timestamps.isChecked(),
                "include_english": self.cb_en.isChecked(),
                "include_spanish": self.cb_es.isChecked(),
            }
            base = safe_filename(self.filename_edit.text().strip() or "export")
            return {
                "destination": "local",
                "scope": scope,
                "formats": formats,
                "options": options,
                "base": base,
            }
        else:
            return {
                "destination": "wordpress",
                "scope": scope,
                "include_english": self.wp_cb_en.isChecked(),
                "include_spanish": self.wp_cb_es.isChecked(),
                "primary_language": self.wp_primary_lang_combo.currentData(),
                "spanish_presentation": self.wp_pres_combo.currentData(),
                "wp_posts": self.wp_post_items,
            }
            
class ProjectExportMixin:
    def close_project(self, prompt=True):
        if prompt and self.project_dirty:
            answer = QMessageBox.question(
                self,
                "Close Project",
                "Close current project? Unsaved changes will be lost.",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if answer != QMessageBox.StandardButton.Yes:
                return False

        try:
            if not self.stop_video_thumbnail_worker():
                QMessageBox.warning(self, "Thumbnail Worker Still Running", "Video thumbnails are still being generated. Please wait a few seconds and close again.")
                return False
        except Exception:
            pass
        if not self.stop_all_processing(timeout_ms=5000):
            QMessageBox.warning(self, "Close Project", "A processing worker could not be stopped safely. The project was not closed.")
            return False
        self.media_generation += 1
        self.story_job_token += 1

        if self.player:
            self.player.stop()
            self.player.setSource(QUrl())

        self.audio_file = None
        self.project_file = None
        self.transcript = None
        self.diarization = None
        self.speaker_names = {}
        self.segment_speaker_overrides = {}
        self.stories = []
        self.current_selected_story_indices = []
        self.duration = 0
        self.current_position = 0

        self.undo_stack.clear()
        self.activity_snapshots.clear()

        self.set_tools_actions_enabled(False)
        self.save_action.setEnabled(False)
        self.save_as_action.setEnabled(False)

        self.play_button.setText("▶ Play")
        self.time_label.setText("00:00.000 / 00:00.000")
        self.speaker_status.setText("Speaker detection has not been run.")

        self.transcript_view.clear()
        self.transcript_view.set_char_timestamp_map([])
        self.story_list.clear()
        self.activity_list.clear()

        self.start_input.clear()
        self.end_input.clear()
        self.title_input.clear()

        self.timeline.set_duration(1)
        self.timeline.set_position(0)
        self.timeline.set_stories([])
        self.timeline.set_waveform_peaks([])
        self.timeline.set_zoom(1.0)
        self.timeline.scroll_offset = 0.0
        self.timeline.set_audio_filename(None)
        if hasattr(self.timeline, "set_video_thumbnails"):
            self.timeline.set_video_thumbnails([])
        self.video_thumbnail_dir = None

        self.update_window_title()
        self.log_activity("[FILE] Project closed.", mark_dirty=False)
        self.statusBar().showMessage("Project closed.")
        return True

    def new_project(self):
        if self.close_project(prompt=True):
            self.open_audio()

    def project_audio_reference(self):
        if not self.audio_file:
            return None
        try:
            if self.project_file:
                return os.path.relpath(self.audio_file, self.project_file.parent)
        except ValueError:
            pass
        return str(self.audio_file)

    def project_data(self):
        return {
            "format": "Radio & TV Story Segmenter Project",
            "version": PROJECT_VERSION,
            "audio_file": self.project_audio_reference(),
            "audio_file_abs": str(Path(self.audio_file).resolve()) if self.audio_file else None,
            "duration": self.duration,
            "transcript": self.transcript,
            "diarization": self.diarization,
            "speaker_names": self.speaker_names,
            "segment_speaker_overrides": self.segment_speaker_overrides,
            "translations": self.translations,
            "translation_display_mode": self.translation_display_mode,
            "stories": [story.to_dict() for story in self.stories],
            "waveform_peaks": getattr(self.timeline, "waveform_peaks", []),
            "settings": {
                "auto_save_minutes": self.auto_save_minutes,
                "skip_seconds": self.skip_seconds,
                "whisper_model": self.whisper_model,
                "translation_model_variant": self.translation_model_variant,
                "silence_threshold": self.silence_threshold,
                "lead_in_padding": self.lead_in_padding,
                "expected_speakers": getattr(self, "expected_speakers", "auto"),
                "show_speaker_labels": self.show_speaker_labels,
                "show_timestamps": self.show_timestamps,
                "language": self.language,
            },
            "processing_status": dict(self.processing_status),
            "session": {
                "position": self.current_position,
                "timeline_zoom": getattr(self.timeline, "zoom_level", 1.0),
                "timeline_scroll_offset": getattr(self.timeline, "scroll_offset", 0.0),
                "selected_story_indices": list(self.current_selected_story_indices),
                "video_preview_visible": bool(self.video_preview_dialog and self.video_preview_dialog.isVisible()),
            },
        }

    def _write_project_file(self, file_path: str):
        """Writes project state dictionary directly to disk."""
        destination = Path(file_path).expanduser().resolve()
        destination.parent.mkdir(parents=True, exist_ok=True)
        self.project_file = destination

        # Optional: Copy source media file into project folder
        copy_media = str(self.settings_store.value("copy_media_to_project_folder", "false")).lower() in {"1", "true", "yes"}
        if copy_media and self.audio_file and Path(self.audio_file).exists():
            src_media = Path(self.audio_file).resolve()
            media_subfolder = destination.parent / "Media"
            if media_subfolder.is_dir() or str(self.settings_store.value("create_project_subfolders", "true")).lower() in {"1", "true", "yes"}:
                media_subfolder.mkdir(parents=True, exist_ok=True)
                target_media = media_subfolder / src_media.name
            else:
                target_media = destination.parent / src_media.name

            if target_media.resolve() != src_media:
                try:
                    shutil.copy2(src_media, target_media)
                    self.audio_file = target_media
                    self.log_activity(f"[PROJECT] Copied media file to project folder: {target_media.name}", mark_dirty=False)
                except Exception as exc:
                    self.log_activity(f"[WARNING] Could not copy media to project folder: {exc}", mark_dirty=False)

        data = self.project_data()
        errors = self.validate_project_data(data)
        if errors:
            raise ValueError("Validation failed: " + "; ".join(errors))

        temp_path = destination.with_name(destination.name + ".tmp")
        try:
            with open(temp_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
                f.flush()
                os.fsync(f.fileno())
            os.replace(temp_path, destination)
        except Exception:
            try:
                temp_path.unlink(missing_ok=True)
            except Exception:
                pass
            raise

        self.project_dirty = False
        self._remember_saved_project(str(destination))
        self.update_window_title()

    # In project_export.py -> ProjectExportMixin class

    def prepare_export_directories(self, target_base_dir=None, default_name=None, prompt_user=True):
        """Resolves:
          ├── [project_dir]/
          │   ├── [project_file].json
          │   ├── Transcripts/
          │   └── Media/
        If the current project is already saved in a dedicated project directory
        (like Bellevue/) that contains Transcripts/ or Media/, it reuses it directly
        without asking for another folder name or parent directory.
        """
        create_bundle = str(self.settings_store.value("create_project_subfolders", "true")).lower() in {"1", "true", "yes"}

        # 1. Check if an active project is already open in an existing bundle folder
        if self.project_file:
            active_parent = self.project_file.parent
            has_transcripts = (active_parent / "Transcripts").is_dir()
            has_media = (active_parent / "Media").is_dir()

            # If inside a folder like 'Bellevue' with Transcripts/ or Media/ present, reuse it immediately
            if has_transcripts or has_media or active_parent.name == self.project_file.stem:
                transcripts_dir = active_parent / "Transcripts"
                media_dir = active_parent / "Media"
                transcripts_dir.mkdir(parents=True, exist_ok=True)
                media_dir.mkdir(parents=True, exist_ok=True)
                return active_parent, transcripts_dir, media_dir, self.project_file.stem

        # 2. Fallback to passed directory, default project directory, or media folder
        if target_base_dir is None:
            target_base_dir = self.get_default_save_directory()

        fallback_name = safe_filename(
            default_name 
            or (self.project_file.stem if self.project_file else None)
            or (self.audio_file.stem if self.audio_file else "export")
        )

        folder_name = fallback_name
        base_path = Path(target_base_dir)

        # 3. If target_base_dir is already the project folder (e.g. user selected 'Bellevue' or it contains subfolders)
        if (base_path / "Transcripts").is_dir() or (base_path / "Media").is_dir() or base_path.name == fallback_name:
            project_dir = base_path
            transcripts_dir = project_dir / "Transcripts"
            media_dir = project_dir / "Media"
            transcripts_dir.mkdir(parents=True, exist_ok=True)
            media_dir.mkdir(parents=True, exist_ok=True)
            return project_dir, transcripts_dir, media_dir, base_path.name

        # 4. Prompt user only if creating a new subfolder and prompt_user is True
        if prompt_user and create_bundle:
            dialog_name, ok = QInputDialog.getText(
                self,
                "Project Folder Name",
                "Enter folder name for project and export subfolders:",
                QLineEdit.EchoMode.Normal,
                fallback_name
            )
            if not ok:
                return None, None, None, None
            folder_name = safe_filename(dialog_name.strip()) or fallback_name

        if create_bundle:
            project_dir = base_path / folder_name
            transcripts_dir = project_dir / "Transcripts"
            media_dir = project_dir / "Media"
        else:
            project_dir = base_path
            transcripts_dir = base_path
            media_dir = base_path

        project_dir.mkdir(parents=True, exist_ok=True)
        transcripts_dir.mkdir(parents=True, exist_ok=True)
        media_dir.mkdir(parents=True, exist_ok=True)

        return project_dir, transcripts_dir, media_dir, folder_name
        
    def get_default_save_directory(self) -> str:
        """Returns target base directory based on preferences and loaded media."""
        save_with_media = (
            str(self.settings_store.value("save_project_with_media", "false")).lower() in {"1", "true", "yes"}
        )
        if save_with_media and self.audio_file:
            media_path = Path(self.audio_file)
            if media_path.exists():
                return str(media_path.parent)

        if getattr(self, "default_project_directory", ""):
            return str(self.default_project_directory)

        return str(Path.home())

    def save_project_as(self) -> bool:
        if not self.audio_file and not self.transcript:
            return False

        base_name = safe_filename(
            Path(self.audio_file).stem if self.audio_file else "project"
        )
        target_base_dir = Path(self.get_default_save_directory())
        create_bundle = str(self.settings_store.value("create_project_subfolders", "true")).lower() in {"1", "true", "yes"}

        if getattr(self, "batch_active", False) and hasattr(self, "batch_settings"):
            out_setting = self.batch_settings.get("output")
            out_dir = Path(out_setting) if out_setting and os.path.exists(out_setting) else target_base_dir

            if create_bundle:
                project_bundle_dir = out_dir / base_name
                project_bundle_dir.mkdir(parents=True, exist_ok=True)
                file_path = str(project_bundle_dir / f"{base_name}.rtvs")
            else:
                out_dir.mkdir(parents=True, exist_ok=True)
                file_path = str(out_dir / f"{base_name}.rtvs")

            self._write_project_file(file_path)
            self.log_activity(f"[BATCH] Auto-saved project to {file_path}")
            return True

        # Interactive Save As dialog
        if create_bundle:
            initial_path = str(target_base_dir / base_name / f"{base_name}.rtvs")
        else:
            initial_path = str(target_base_dir / f"{base_name}.rtvs")

        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Save Project As",
            initial_path,
            "RadioTV Story Segmenter Projects (*.rtvs);;Legacy Projects (*.json);;All Files (*.*)"
        )
        if file_path:
            target_path = Path(file_path)
            if create_bundle:
                (target_path.parent / "Transcripts").mkdir(parents=True, exist_ok=True)
                (target_path.parent / "Media").mkdir(parents=True, exist_ok=True)

            self._write_project_file(str(target_path))
            return True
        return False

    def ensure_project_for_processing_pipeline(self) -> bool:
        """
        Ensures a project file is established on disk before running multi-stage
        automated pipelines so progress can be safely saved between stages.
        """
        if getattr(self, "project_file", None):
            return True

        if getattr(self, "batch_active", False):
            return bool(self.save_project_as())

        if self.audio_file or self.transcript:
            reply = QMessageBox.question(
                self,
                "Save Project",
                "Multi-stage automated processing saves progress to your project file after each stage.\n\n"
                "Would you like to save this project now?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
                QMessageBox.StandardButton.Yes,
            )
            if reply == QMessageBox.StandardButton.Yes:
                return bool(self.save_project_as())
            return False

        return False

    def validate_project_data(self, data):
        """Return a list of structural project-data problems before saving."""
        errors = []
        if data.get("format") != "Radio & TV Story Segmenter Project":
            errors.append("Invalid project format.")
        duration = data.get("duration", 0)
        try:
            if float(duration) < 0:
                errors.append("Media duration cannot be negative.")
        except (TypeError, ValueError):
            errors.append("Media duration is not numeric.")

        transcript = data.get("transcript")
        if transcript is not None:
            segments = transcript.get("segments") if isinstance(transcript, dict) else None
            if not isinstance(segments, list):
                errors.append("Transcript segments are missing or invalid.")
            else:
                for i, seg in enumerate(segments):
                    if not isinstance(seg, dict):
                        errors.append(f"Transcript segment {i + 1} is invalid.")
                        continue
                    try:
                        if float(seg.get("start", 0)) > float(seg.get("end", 0)):
                            errors.append(f"Transcript segment {i + 1} has an invalid time range.")
                    except (TypeError, ValueError):
                        errors.append(f"Transcript segment {i + 1} has invalid timestamps.")

        stories = data.get("stories", [])
        if not isinstance(stories, list):
            errors.append("Stories data is not a list.")
        else:
            for i, story in enumerate(stories):
                try:
                    start = float(story.get("start", 0))
                    end = float(story.get("end", 0))
                    if start < 0 or end < start:
                        errors.append(f"Story {i + 1} has an invalid time range.")
                except (AttributeError, TypeError, ValueError):
                    errors.append(f"Story {i + 1} is invalid.")
        return errors

    def save_project(self, force=True):
        if not self.audio_file:
            return False
        if not self.project_file:
            return self.save_project_as()
        if not force and not self.project_dirty:
            return True
        if self.save_in_progress:
            return False

        self.save_in_progress = True
        temp_file = self.project_file.with_name(self.project_file.name + ".tmp")
        backup_file = self.project_file.with_name(self.project_file.name + ".backup")
        try:
            self.project_file.parent.mkdir(parents=True, exist_ok=True)

            # Optional: Copy source media file into project folder
            copy_media = str(self.settings_store.value("copy_media_to_project_folder", "false")).lower() in {"1", "true", "yes"}
            if copy_media and self.audio_file and Path(self.audio_file).exists():
                src_media = Path(self.audio_file).resolve()
                media_subfolder = self.project_file.parent / "Media"
                if media_subfolder.is_dir() or str(self.settings_store.value("create_project_subfolders", "true")).lower() in {"1", "true", "yes"}:
                    media_subfolder.mkdir(parents=True, exist_ok=True)
                    target_media = media_subfolder / src_media.name
                else:
                    target_media = self.project_file.parent / src_media.name

                if target_media.resolve() != src_media:
                    try:
                        shutil.copy2(src_media, target_media)
                        self.audio_file = target_media
                        self.log_activity(f"[PROJECT] Copied media file to project folder: {target_media.name}", mark_dirty=False)
                    except Exception as exc:
                        self.log_activity(f"[WARNING] Could not copy media to project folder: {exc}", mark_dirty=False)

            data = self.project_data()
            errors = self.validate_project_data(data)
            if errors:
                message = "Project validation failed:\n\n" + "\n".join(f"• {item}" for item in errors)
                self.log_activity(f"[ERROR] Project validation failed: {'; '.join(errors)}", mark_dirty=False)
                QMessageBox.critical(self, "Project Validation Error", message)
                return False

            with open(temp_file, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
                f.flush()
                os.fsync(f.fileno())

            if self.project_file.exists():
                shutil.copy2(self.project_file, backup_file)
                self.log_activity(f"[PROJECT] Previous project saved as recovery backup: {backup_file.name}", mark_dirty=False)

            os.replace(temp_file, self.project_file)
            # A successful explicit save supersedes its recovery snapshot.
            try:
                self.project_file.with_suffix(self.project_file.suffix + ".autosave").unlink(missing_ok=True)
            except Exception:
                pass
            self.project_dirty = False
            self._remember_saved_project(str(self.project_file))
            self.update_window_title()
            saved_time = QTime.currentTime().toString("hh:mm:ss A")
            if hasattr(self, "save_state_label"):
                self.save_state_label.setText(f"✓ Saved {saved_time}")
            self.statusBar().showMessage(f"Project saved: {self.project_file.name}")
            return True
        except Exception as exc:
            try:
                if temp_file.exists():
                    temp_file.unlink()
            except Exception:
                pass
            self.log_activity(f"[ERROR] Project save failed: {exc}", mark_dirty=False)
            QMessageBox.critical(self, "Save Error", str(exc))
            return False
        finally:
            self.save_in_progress = False

    def find_adjacent_project(self, media_path):
        # A project is now named after its source media file:
        # episode.mp4 -> episode.rtvs (or legacy episode.json)
        candidates = [
            media_path.parent / f"{media_path.stem}.rtvs",
            media_path.parent / f"{media_path.stem}.json",
            media_path.parent / media_path.stem / f"{media_path.stem}.rtvs",
            media_path.parent / media_path.stem / f"{media_path.stem}.json",
        ]
        for candidate in candidates:
            if not candidate.exists() or not candidate.is_file():
                continue
            try:
                with open(candidate, "r", encoding="utf-8") as f:
                    data = json.load(f)
                ref = data.get("audio_file")
                if not ref:
                    continue
                ref_path = Path(ref)
                if not ref_path.is_absolute():
                    ref_path = candidate.parent / ref_path
                if ref_path.resolve() == media_path.resolve():
                    return candidate.resolve()
            except Exception:
                continue
        return None

    def resolve_project_media(self, project_file, audio_reference, audio_file_abs=None):
        # 1. Check remembered absolute path if available and exists on disk
        if audio_file_abs:
            abs_candidate = Path(audio_file_abs).expanduser().resolve()
            if abs_candidate.exists() and abs_candidate.is_file():
                return abs_candidate

        if not audio_reference:
            return None

        ref_path = Path(audio_reference)

        # 2. Check audio_reference if already absolute and exists
        if ref_path.is_absolute():
            cand = ref_path.resolve()
            if cand.exists() and cand.is_file():
                return cand

        proj_dir = project_file.parent

        # 3. Check relative to project_file.parent
        rel_candidate = (proj_dir / ref_path).resolve()
        if rel_candidate.exists() and rel_candidate.is_file():
            return rel_candidate

        # 4. Check inside Media/ subfolder in project dir
        media_candidate = (proj_dir / "Media" / ref_path.name).resolve()
        if media_candidate.exists() and media_candidate.is_file():
            return media_candidate

        # 5. Check direct basename in project directory
        basename_candidate = (proj_dir / ref_path.name).resolve()
        if basename_candidate.exists() and basename_candidate.is_file():
            return basename_candidate

        # 6. Check in default projects directory
        default_dir = getattr(self, "default_project_directory", "")
        if default_dir:
            cand = (Path(default_dir) / ref_path.name).resolve()
            if cand.exists() and cand.is_file():
                return cand

        # 7. Check in last media directory
        last_media = getattr(self, "last_media_directory", "")
        if last_media:
            cand = (Path(last_media) / ref_path.name).resolve()
            if cand.exists() and cand.is_file():
                return cand

        return None

    def load_project_file(self, filename, prompt=True, preserve_media=False):
        project_path = Path(filename).resolve()
        try:
            with open(project_path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception as exc:
            backup_path = project_path.with_name(project_path.name + ".backup")
            if backup_path.exists():
                answer = QMessageBox.question(
                    self, "Project Recovery",
                    f"The project file could not be read:\n\n{project_path.name}\n\n"
                    f"A recovery backup was found ({backup_path.name}). Would you like to open the backup instead?",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                )
                if answer == QMessageBox.StandardButton.Yes:
                    try:
                        with open(backup_path, "r", encoding="utf-8") as f:
                            data = json.load(f)
                        self.log_activity(f"[PROJECT] Recovered project from backup: {backup_path.name}", mark_dirty=False)
                    except Exception as backup_exc:
                        self.log_activity(f"[ERROR] Project recovery backup could not be read: {backup_exc}", mark_dirty=False)
                        if not preserve_media:
                            QMessageBox.critical(self, "Load Error", str(backup_exc))
                        return False
                else:
                    if not preserve_media:
                        QMessageBox.critical(self, "Load Error", str(exc))
                    return False
            else:
                self.log_activity(f"[ERROR] Could not read project file '{project_path.name}': {exc}", mark_dirty=False)
                if not preserve_media:
                    QMessageBox.critical(self, "Load Error", str(exc))
                return False

        if data.get("format") not in (None, "Radio & TV Story Segmenter Project"):
            QMessageBox.warning(self, "Load Project", "This file is not a Radio & TV Story Segmenter project.")
            return False

        if not preserve_media and not self.confirm_stop_processing_for_media_change():
            return False
        if not preserve_media and not self.close_project(prompt=prompt):
            return False

        self.project_file = project_path
        audio_path = self.resolve_project_media(project_path, data.get("audio_file"), data.get("audio_file_abs"))

        if audio_path is None and data.get("audio_file"):
            answer = QMessageBox.question(
                self, "Media File Missing",
                "The media file saved with this project could not be found.\n\nWould you like to locate it?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if answer == QMessageBox.StandardButton.Yes:
                located, _ = QFileDialog.getOpenFileName(
                    self, "Locate Project Media", str(project_path.parent),
                    "Media Files (*.*);;All Files (*)",
                )
                if located:
                    audio_path = Path(located).resolve()

        if audio_path is not None:
            self.stop_waveform_worker()
            self.audio_file = audio_path
            self.player.setSource(QUrl.fromLocalFile(str(audio_path)))
            self.current_media_is_video = self.is_video_file(audio_path)
            self.update_video_preview_state()
            self.timeline.set_audio_filename(audio_path.name)
            self.timeline.set_waveform_peaks([])

            # Restore pre-calculated waveform peaks if present in project data
            cached_peaks = data.get("waveform_peaks")
            if cached_peaks:
                self.timeline.set_waveform_peaks(cached_peaks)
                self.log_activity(f"[WAVEFORM] Loaded cached waveform ({len(cached_peaks):,} peaks).", mark_dirty=False)
            else:
                self.load_waveform_async()
        else:
            self.audio_file = None
            self.current_media_is_video = False
            self.update_video_preview_state()

        self.duration = float(data.get("duration") or 0)
        if self.duration > 0:
            self.timeline.set_duration(self.duration)
            if self.current_media_is_video:
                QTimer.singleShot(0, self.start_video_thumbnail_generation)
        self.transcript = data.get("transcript")
        self.diarization = data.get("diarization")
        self.speaker_names = {str(k): str(v) for k, v in data.get("speaker_names", {}).items() if str(v).strip()}
        self.segment_speaker_overrides = {int(k): str(v) for k, v in data.get("segment_speaker_overrides", {}).items()}
        self.stories = [Story.from_dict(item) for item in data.get("stories", [])]
        self.translations = data.get("translations", {}) if isinstance(data.get("translations", {}), dict) else {}
        self.translation_display_mode = str(data.get("translation_display_mode", "en"))
        if self.translation_display_mode == "bilingual":
            self.translation_display_mode = "split"
        elif self.translation_display_mode not in {"en", "es", "split"}:
            self.translation_display_mode = "en"
        self.update_translation_language_selector()
        if hasattr(self, "transcript_language_selector"):
            idx = self.transcript_language_selector.findData(self.translation_display_mode)
            if idx >= 0:
                self.transcript_language_selector.blockSignals(True)
                self.transcript_language_selector.setCurrentIndex(idx)
                self.transcript_language_selector.blockSignals(False)

        settings = data.get("settings", {})
        self.auto_save_minutes = float(settings.get("auto_save_minutes", data.get("auto_save_minutes", 5)))
        self.skip_seconds = float(settings.get("skip_seconds", data.get("skip_seconds", 5)))
        # Transcription Model is a global user preference, not a project setting.
        saved_global_whisper = str(self.settings_store.value("whisper_model", getattr(self, "whisper_model", "small")) or "small")
        allowed_whisper = {"tiny", "base", "small", "distil-medium.en", "medium", "distil-large-v3", "large-v3", "parakeet-onnx"}
        self.whisper_model = saved_global_whisper if saved_global_whisper in allowed_whisper else "small"
        self.settings_store.setValue("whisper_model", self.whisper_model)
        self.settings_store.sync()
        self.translation_model_variant = str(settings.get("translation_model_variant", data.get("translation_model_variant", "tiny")))
        if self.translation_model_variant not in {"tiny", "standard"}: self.translation_model_variant = "tiny"
        self.silence_threshold = float(settings.get("silence_threshold", data.get("silence_threshold", 3.0)))
        self.lead_in_padding = float(settings.get("lead_in_padding", data.get("lead_in_padding", 0.5)))
        # "expected_speakers" replaces the old "speaker_sensitivity" (1-10) setting;
        # projects saved by older builds only have the latter, which no longer maps
        # to anything meaningful, so such projects just fall back to "auto".
        self.expected_speakers = str(settings.get("expected_speakers", data.get("expected_speakers", "auto")) or "auto")
        self.show_speaker_labels = bool(settings.get("show_speaker_labels", self.show_speaker_labels))
        self.show_timestamps = bool(settings.get("show_timestamps", self.show_timestamps))
        self.language = str(settings.get("language", self.language)) if str(settings.get("language", self.language)) in {"en","es"} else self.language
        self._apply_localization()
        if hasattr(self, "show_speaker_labels_action"):
            self.show_speaker_labels_action.setChecked(self.show_speaker_labels)
            self.show_timestamps_action.setChecked(self.show_timestamps)
        self.timeline.set_skip_seconds(self.skip_seconds)
        if hasattr(self, "skip_display"):
            self.skip_display.setValue(int(self.skip_seconds))
        self.refresh_whisper_model_chooser()
        saved_status = data.get("processing_status", {})
        self.processing_status = {
            "transcription": bool(saved_status.get("transcription", bool(self.transcript))),
            "diarization": bool(saved_status.get("diarization", bool(self.diarization))),
            "stories": bool(saved_status.get("stories", bool(self.stories))),
        }
        self.update_processing_stage_summary()
        self.update_auto_save_timer()

        session = data.get("session", {})
        position = max(0.0, min(float(session.get("position", 0) or 0), self.duration or float("inf")))
        self.current_position = position
        self.timeline.set_position(position)
        self.timeline.set_zoom(float(session.get("timeline_zoom", 1.0) or 1.0))
        self.timeline.scroll_offset = float(session.get("timeline_scroll_offset", 0.0) or 0.0)
        self.current_selected_story_indices = [int(i) for i in session.get("selected_story_indices", []) if 0 <= int(i) < len(self.stories)]

        if self.audio_file:
            self.transcribe_action.setEnabled(True)
            self.diarize_action.setEnabled(True)
            self.auto_detect_action.setEnabled(True)
            self.transcribe_diarize_action.setEnabled(True)
            self.transcribe_diarize_detect_action.setEnabled(True)
            self.save_action.setEnabled(True)
            self.save_as_action.setEnabled(True)
            if hasattr(self, "quick_save_button"):
                self.quick_save_button.setEnabled(True)

        if self.diarization:
            number = self.diarization.get("num_speakers", 0)
            self.speaker_status.setText(f"Speaker detection loaded: {number} speaker(s).")
        else:
            self.speaker_status.setText("Speaker detection has not been run.")

        self.set_tools_actions_enabled(True)
        self.render_transcript()
        self.refresh_story_list()
        self.project_dirty = False
        self.update_window_title()
        self.log_activity(f"[FILE] Loaded project: {project_path.name}", mark_dirty=False)
        self.log_activity(
            f"[PROJECT] Restored transcript={bool(self.transcript)}, diarization={bool(self.diarization)}, "
            f"speaker names={len(self.speaker_names)}, stories={len(self.stories)}.",
            mark_dirty=False,
        )
        self.project_dirty = False
        self.update_window_title()

        if session.get("video_preview_visible") and self.current_media_is_video and self.video_preview_action:
            self.video_preview_action.setChecked(False)
            self.toggle_video_preview(True)

        # Remember this project so launch startup and recent projects track it reliably
        self._remember_saved_project(str(project_path))

        self.statusBar().showMessage("Project loaded.")
        return True

    def load_project(self, filename=None):
        if not filename:
            filename, _ = QFileDialog.getOpenFileName(
                self, "Load Project", self._dialog_directory(),
                "RadioTV Story Segmenter Projects (*.rtvs);;Legacy Projects (*.json);;All Files (*.*)",
            )
        if filename:
            try:
                directory = str(Path(filename).resolve().parent)
                self.settings_store.setValue("last_open_directory", directory)
                self.settings_store.sync()
            except Exception:
                pass
            return self.load_project_file(filename, prompt=True, preserve_media=False)
        return False

    def trigger_export(self):
        """Standard trigger for Export (File menu Ctrl+E / toolbar)."""
        self.open_unified_export_dialog()

    def export_full_transcript(self):
        """Triggered from the Export Transcript button above the transcript view."""
        self.open_unified_export_dialog(initial_scope="full")

    def open_export_scope_dialog(self):
        """Standard trigger for the main toolbar Export button."""
        self.open_unified_export_dialog()

    def open_unified_export_dialog(self, initial_scope=None):
        """Unified Export Dialog entry point for local file exports and WordPress publishing."""
        if not self.transcript and not self.audio_file:
            QMessageBox.warning(self, "Nothing to Export", "There is no transcript or media available to export.")
            return

        if initial_scope is None:
            sel = getattr(self, "current_selected_story_indices", [])
            if sel:
                initial_scope = "selected_stories"
            elif getattr(self, "stories", []):
                initial_scope = "all_stories"
            else:
                initial_scope = "full"

        dialog = UnifiedExportDialog(self, initial_scope=initial_scope)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return

        result = dialog.get_result()
        dest = result.get("destination", "local")
        scope = result.get("scope", "full")

        if dest == "local":
            formats = result.get("formats", {})
            base = result.get("base", "")
            options = result.get("options", {})

            # Check if project already lives in an existing folder containing Transcripts/Media (e.g. Bellevue/)
            if self.project_file and ((self.project_file.parent / "Transcripts").is_dir() or (self.project_file.parent / "Media").is_dir()):
                project_dir, trans_dir, media_dir, chosen_name = self.prepare_export_directories()
            else:
                parent_dir = QFileDialog.getExistingDirectory(self, "Choose Export Location", self._dialog_directory())
                if not parent_dir:
                    return
                project_dir, trans_dir, media_dir, chosen_name = self.prepare_export_directories(
                    parent_dir, default_name=base, prompt_user=True
                )

            if not project_dir:
                return

            # Keep project session file saved at root of the directory
            if self.audio_file or self.transcript:
                self._write_project_file(str(project_dir / f"{chosen_name}.rtvs"))

            # Route exports directly to project_dir
            if scope == "full":
                self.export_full_episode(custom_formats=formats, custom_base=chosen_name, custom_options=options, directory=str(project_dir))
            elif scope == "selected_stories":
                self.export_selected_stories(custom_formats=formats, custom_base=chosen_name, custom_options=options, directory=str(project_dir))
            elif scope == "all_stories":
                self.export_all_stories(custom_formats=formats, custom_base=chosen_name, custom_options=options, directory=str(project_dir))
            elif scope == "full_and_all_stories":
                self.export_full_and_all_stories(custom_formats=formats, custom_base=chosen_name, custom_options=options, directory=str(project_dir))
        else:
            self._handle_wordpress_export_result(result)

    def cancel_export(self):
        """Flag the running export operation to halt at the next iteration."""
        self.export_cancelled = True
        self.log_activity("[EXPORT] Cancel requested by user.")

    def _export_story_files(self, stories_with_indices, formats, base, options, directory, start_idx=0, total_batch=None):
        out = Path(directory)
        create_bundle = str(self.settings_store.value("create_project_subfolders", "true")).lower() in {"1", "true", "yes"}
        if create_bundle:
            transcripts_out = out / "Transcripts"
            media_out = out / "Media"
            transcripts_out.mkdir(parents=True, exist_ok=True)
            if formats.get("media"):
                media_out.mkdir(parents=True, exist_ok=True)
        else:
            transcripts_out = out
            media_out = out

        languages_to_export = []
        batch_direction = options.get("translation_direction")
        if batch_direction and options.get("include_spanish", False):
            source_code, target_code, target_suffix = self.translation_export_spec(options)
            languages_to_export.append((source_code, ""))
            if self.get_translation_item(source_code, target_code):
                languages_to_export.append((target_code, target_suffix))
        else:
            if options.get("include_english", True):
                languages_to_export.append(("en", ""))
            if options.get("include_spanish", False):
                has_es = self.has_spanish_translation() if hasattr(self, "has_spanish_translation") else (
                    self.translation_is_current(self.translation_key("en", "es")) if hasattr(self, "translation_is_current") else False
                )
                if has_es:
                    languages_to_export.append(("es", "_es"))

        doc_base = base if base else (safe_filename(self.audio_file.stem) if self.audio_file else "Story")
        total_stories = total_batch if total_batch is not None else len(stories_with_indices)

        for i, (idx, story) in enumerate(stories_with_indices):
            if getattr(self, "export_cancelled", False):
                self.log_activity("[EXPORT] Export operation stopped by user.")
                return False

            story_title = story.title.strip() if story.title else f"Story {idx + 1}"
            current_count = start_idx + i + 1
            pct = int(((start_idx + i) / max(1, total_stories)) * 100)
            
            # Update inline top-of-window header indicators
            self.set_processing_stage("Exporting Stories", f"{current_count} of {total_stories}: '{story_title}'")
            self.update_processing_progress(pct, f"Exporting {story_title}...")
            QApplication.processEvents()

            story_slug = safe_filename(story.title) if story.title else f"Story_{idx + 1:02d}"
            story_base = f"{doc_base}_{idx + 1:02d}_{story_slug}" if story.title else f"{doc_base}_{idx + 1:02d}"
            segments = self.transcript_for_range(story.start, story.end)

            for lang_code, suffix in languages_to_export:
                file_base = f"{story_base}{suffix}"
                batch_direction = options.get("translation_direction")
                source_code = self.translation_export_spec(options)[0] if batch_direction else "en"
                if lang_code == source_code:
                    blocks = self.build_story_blocks(segments) if segments else []
                else:
                    batch_direction = options.get("translation_direction")
                    if batch_direction:
                        source_code, target_code, _target_suffix = self.translation_export_spec(options)
                        item = self.get_translation_item(source_code, target_code)
                    else:
                        item = self.get_spanish_translation_item() if hasattr(self, "get_spanish_translation_item") else (
                            self.translations.get("en-es") or self.translations.get("en_es") or {}
                        )
                    trans_segs = item.get("segments", []) if item else []
                    source_segs = self.transcript.get("segments", []) if self.transcript else []
                    curr_spk_blocks = []
                    for s_idx, t_seg in enumerate(trans_segs):
                        source_seg = source_segs[s_idx] if s_idx < len(source_segs) else {}
                        s_start = float(t_seg.get("start", source_seg.get("start", 0.0)))
                        s_end = float(t_seg.get("end", source_seg.get("end", s_start + 1.0)))
                        if s_end <= story.start or s_start >= story.end:
                            continue
                        spk = self.get_effective_speaker_name(s_idx, source_seg) if source_seg else ""
                        curr_spk_blocks.append({
                            "speaker": spk,
                            "text": t_seg.get("text", "").strip(),
                            "start": s_start,
                            "end": s_end,
                            "_source_index": s_idx,
                        })
                    blocks = self.build_story_blocks(curr_spk_blocks) if curr_spk_blocks else []

                # Export TXT
                if formats.get("txt"):
                    txt_file = transcripts_out / f"{file_base}.txt"
                    with open(txt_file, "w", encoding="utf-8") as f:
                        source_name = self.audio_file.name if self.audio_file else "Text-only project"
                        lang_label = " (Spanish)" if lang_code == "es" else (" (English)" if lang_code == "en" else "")
                        f.write(f"{story_title}{lang_label}\n{source_name} ({format_time(story.start)} - {format_time(story.end)})\n" + "=" * 70 + "\n\n")
                        for block in blocks:
                            speaker = (block.get("speaker") or "").strip() if options.get("include_speakers", True) else ""
                            p_text = block.get("text", "").strip()
                            if not p_text:
                                continue
                            prefix = ""
                            if options.get("include_timestamps") and block.get("start") is not None:
                                prefix = f"[{format_time(block['start'])}] "
                            if speaker:
                                prefix += f"{speaker}: "
                            f.write(f"{prefix}{p_text}\n\n")

                # Export DOCX
                if formats.get("docx"):
                    docx_file = transcripts_out / f"{file_base}.docx"
                    document = Document()
                    document.styles["Normal"].font.name = "Arial"
                    document.styles["Normal"].font.size = Pt(11)
                    lang_label = " (Spanish)" if lang_code == "es" else (" (English)" if lang_code == "en" else "")
                    document.add_heading(f"{story_title}{lang_label}", 0)
                    if self.audio_file:
                        document.add_paragraph(f"Recording: {self.audio_file.name} ({format_time(story.start)} - {format_time(story.end)})")
                    for block in blocks:
                        speaker = (block.get("speaker") or "").strip() if options.get("include_speakers", True) else ""
                        p_text = block.get("text", "").strip()
                        if not p_text:
                            continue
                        p = document.add_paragraph()
                        if options.get("include_timestamps") and "start" in block and block["start"] is not None:
                            r_time = p.add_run(f"[{format_time(block['start'])}] ")
                            r_time.font.color.rgb = RGBColor(120, 120, 120)
                        if speaker:
                            r_spk = p.add_run(f"{speaker}: ")
                            r_spk.bold = True
                        p.add_run(p_text)
                        p.paragraph_format.space_after = Pt(6)
                    document.save(docx_file)

                # Export Subtitles
                if formats.get("srt"):
                    self.write_subtitles(blocks, transcripts_out / f"{file_base}.srt", "srt", options.get("include_speakers", True))
                if formats.get("vtt"):
                    self.write_subtitles(blocks, transcripts_out / f"{file_base}.vtt", "vtt", options.get("include_speakers", True))

            # Export Media Clip
            if formats.get("media") and self.audio_file:
                media_file = media_out / f"{story_base}{self.audio_file.suffix.lower()}"
                self.extract_media(story.start, story.end, media_file)

        return True

    def export_selected_stories(self, custom_formats=None, custom_base=None, custom_options=None, directory=None):
        indices = getattr(self, "current_selected_story_indices", [])
        if not indices:
            QMessageBox.warning(self, "No Story Selected", "Please select one or more stories to export.")
            return
        stories_to_export = [(i, self.stories[i]) for i in indices if 0 <= i < len(self.stories)]
        if not stories_to_export:
            QMessageBox.warning(self, "No Story Selected", "No valid stories are currently selected.")
            return

        base = custom_base or (safe_filename(self.project_file.stem if self.project_file else (self.audio_file.stem if self.audio_file else "export")))
        if directory is None:
            if self.project_file and ((self.project_file.parent / "Transcripts").is_dir() or (self.project_file.parent / "Media").is_dir()):
                project_dir, _, _, chosen_base = self.prepare_export_directories()
            else:
                parent_dir = QFileDialog.getExistingDirectory(self, "Choose Export Location", self._dialog_directory())
                if not parent_dir:
                    return
                project_dir, _, _, chosen_base = self.prepare_export_directories(parent_dir, default_name=base, prompt_user=True)
            if not project_dir:
                return
            directory = str(project_dir)
            base = chosen_base

        formats = custom_formats or {"txt": True, "docx": True, "srt": False, "vtt": False, "media": False}
        options = custom_options or {"include_speakers": True, "include_timestamps": False, "include_english": True, "include_spanish": False}

        self.export_cancelled = False
        if hasattr(self, "cancel_button"):
            self.cancel_button.show()

        try:
            success = self._export_story_files(stories_to_export, formats, base, options, directory)
            if success and not self.export_cancelled:
                self.update_processing_progress(100, "Export complete.")
                self.log_activity(f"[EXPORT] Exported {len(stories_to_export)} selected story/stories to {directory}")
                QMessageBox.information(self, "Export Complete", f"Exported {len(stories_to_export)} story segment(s) to:\n{directory}")
        except Exception as exc:
            self.log_activity(f"[ERROR] Selected stories export failed: {exc}")
            QMessageBox.critical(self, "Export Error", str(exc))
        finally:
            self.set_processing_stage(None)
            if hasattr(self, "cancel_button"):
                self.cancel_button.hide()

    def export_all_stories(self, custom_formats=None, custom_base=None, custom_options=None, directory=None):
        if not getattr(self, "stories", []):
            QMessageBox.warning(self, "No Stories", "There are no story segments in this project to export.")
            return

        base = custom_base or (safe_filename(self.project_file.stem if self.project_file else (self.audio_file.stem if self.audio_file else "export")))
        if directory is None:
            if self.project_file and ((self.project_file.parent / "Transcripts").is_dir() or (self.project_file.parent / "Media").is_dir()):
                project_dir, _, _, chosen_base = self.prepare_export_directories()
            else:
                parent_dir = QFileDialog.getExistingDirectory(self, "Choose Export Location", self._dialog_directory())
                if not parent_dir:
                    return
                project_dir, _, _, chosen_base = self.prepare_export_directories(parent_dir, default_name=base, prompt_user=True)
            if not project_dir:
                return
            directory = str(project_dir)
            base = chosen_base

        formats = custom_formats or {"txt": True, "docx": True, "srt": False, "vtt": False, "media": False}
        options = custom_options or {"include_speakers": True, "include_timestamps": False, "include_english": True, "include_spanish": False}

        stories_to_export = list(enumerate(self.stories))
        self.export_cancelled = False
        if hasattr(self, "cancel_button"):
            self.cancel_button.show()

        try:
            success = self._export_story_files(stories_to_export, formats, base, options, directory)
            if success and not self.export_cancelled:
                self.update_processing_progress(100, "Export complete.")
                self.log_activity(f"[EXPORT] Exported all {len(stories_to_export)} stories to {directory}")
                QMessageBox.information(self, "Export Complete", f"Exported all {len(stories_to_export)} story segment(s) to:\n{directory}")
        except Exception as exc:
            self.log_activity(f"[ERROR] All stories export failed: {exc}")
            QMessageBox.critical(self, "Export Error", str(exc))
        finally:
            self.set_processing_stage(None)
            if hasattr(self, "cancel_button"):
                self.cancel_button.hide()

    def export_full_and_all_stories(self, custom_formats=None, custom_base=None, custom_options=None, directory=None):
        base = custom_base or (safe_filename(self.project_file.stem if self.project_file else (self.audio_file.stem if self.audio_file else "export")))
        if directory is None:
            if self.project_file and ((self.project_file.parent / "Transcripts").is_dir() or (self.project_file.parent / "Media").is_dir()):
                project_dir, _, _, chosen_base = self.prepare_export_directories()
            else:
                parent_dir = QFileDialog.getExistingDirectory(self, "Choose Export Location", self._dialog_directory())
                if not parent_dir:
                    return
                project_dir, _, _, chosen_base = self.prepare_export_directories(parent_dir, default_name=base, prompt_user=True)
            if not project_dir:
                return
            directory = str(project_dir)
            base = chosen_base

        formats = custom_formats or {"txt": True, "docx": True, "srt": False, "vtt": False, "media": False}
        options = custom_options or {"include_speakers": True, "include_timestamps": False, "include_english": True, "include_spanish": False}
        stories_to_export = list(enumerate(self.stories)) if getattr(self, "stories", []) else []
        total_items = 1 + len(stories_to_export)

        self.export_cancelled = False
        if hasattr(self, "cancel_button"):
            self.cancel_button.show()

        try:
            self.set_processing_stage("Exporting Full & Stories", f"1 of {total_items}: Full Episode")
            self.update_processing_progress(0, "Exporting full episode...")
            QApplication.processEvents()

            ok = self.export_full_episode(
                custom_formats=formats,
                custom_base=base,
                custom_options=options,
                directory=directory,
                show_completion=False,
            )

            if ok and not self.export_cancelled and stories_to_export:
                self._export_story_files(
                    stories_to_export,
                    formats,
                    base,
                    options,
                    directory,
                    start_idx=1,
                    total_batch=total_items,
                )

            if not self.export_cancelled:
                self.update_processing_progress(100, "Export complete.")
                self.log_activity(f"[EXPORT] Exported full episode and all stories to {directory}")
                QMessageBox.information(self, "Export Complete", f"Exported full episode and story segments to:\n{directory}")
        except Exception as exc:
            self.log_activity(f"[ERROR] Full & story export failed: {exc}")
            QMessageBox.critical(self, "Export Error", str(exc))
        finally:
            self.set_processing_stage(None)
            if hasattr(self, "cancel_button"):
                self.cancel_button.hide()

    def _handle_wordpress_export_result(self, result):
        client = getattr(self, "_get_wp_client", lambda: None)()
        if not client:
            return
        wp_posts = result.get("wp_posts", [])
        if not wp_posts:
            QMessageBox.warning(self, "No Posts", "No posts were configured for export.")
            return

        inc_en = result.get("include_english", True)
        inc_es = result.get("include_spanish", False)
        pres = result.get("spanish_presentation", "accordion")
        primary = result.get("primary_language", "en")
        total_posts = len(wp_posts)

        self.export_cancelled = False
        if hasattr(self, "cancel_button"):
            self.cancel_button.show()

        created_posts = []
        failed_posts = []

        try:
            for idx, post in enumerate(wp_posts):
                if getattr(self, "export_cancelled", False):
                    self.log_activity("[WORDPRESS] Export canceled by user.")
                    break

                post_title = post.get("title") or "Untitled Post"
                task_label = post.get("task_label") or post_title
                media_name = safe_filename(post_title) if post_title else "audio"
                media_filename = f"{media_name}.mp3"

                pct = int((idx / max(1, total_posts)) * 100)
                self.set_processing_stage("WordPress Publishing", f"Post {idx + 1} of {total_posts}: '{post_title}'")
                self.update_processing_progress(pct, f"Starting WordPress export for '{post_title}'…")
                QApplication.processEvents()

                def wp_progress(step, step_total, description, _idx=idx, _title=post_title):
                    # Four user-visible steps per post: prepare/convert, upload,
                    # prepare post, and create draft. Keep the overall progress
                    # bar moving across all posts rather than resetting per post.
                    fraction = max(0.0, min(1.0, ((step - 1) / step_total)))
                    overall = ((_idx + fraction) / max(1, total_posts)) * 100
                    self.current_processing_stage_detail = f"Post {_idx + 1} of {total_posts}: Step {step} of {step_total} — {description}"
                    self.update_processing_progress(int(overall), description)
                    QApplication.processEvents()

                try:
                    post_data = self._execute_wordpress_upload(
                        client=client,
                        post_title=post_title,
                        post_excerpt=post.get("excerpt", ""),
                        start=post.get("start"),
                        end=post.get("end"),
                        task_label=task_label,
                        include_english=inc_en,
                        include_spanish=inc_es,
                        spanish_presentation=pres,
                        primary_language=primary,
                        author_ids=post.get("author_ids", []),
                        author_term_ids=post.get("author_term_ids", []),
                        category_ids=post.get("category_ids", []),
                        show_completion_dialog=False,
                        media_filename=media_filename,
                        progress_callback=wp_progress,
                    )
                    if post_data and isinstance(post_data, dict):
                        self.current_processing_stage_detail = f"Post {idx + 1} of {total_posts}: Step 4 of 4 — Export complete"
                        self.update_processing_progress(int(((idx + 1) / max(1, total_posts)) * 100), f"Finished '{post_title}'.")
                        QApplication.processEvents()
                        post_id = post_data.get("id", "Draft")
                        post_link = post_data.get("link") or f"{client.site_url}/?p={post_id}"
                        created_posts.append({
                            "title": post_title,
                            "id": post_id,
                            "link": post_link,
                        })
                except Exception as exc:
                    self.log_activity(f"[WORDPRESS ERROR] Failed to export '{post_title}': {exc}")
                    failed_posts.append({
                        "title": post_title,
                        "error": str(exc),
                    })
        finally:
            self.set_processing_stage(None)
            if hasattr(self, "cancel_button"):
                self.cancel_button.hide()

        # Final summaries
        if created_posts and not failed_posts:
            if len(created_posts) == 1:
                p = created_posts[0]
                QMessageBox.information(
                    self,
                    "WordPress Export Complete",
                    f"Draft post created successfully on {client.site_url}!\n\n"
                    f"Post Title: {p['title']}\n"
                    f"Post ID: {p['id']}\n"
                    f"Status: Draft\n"
                    f"Preview Link: {p['link']}",
                )
            else:
                posts_summary = "\n".join([f"  #{p['id']}: {p['title']}" for p in created_posts])
                QMessageBox.information(
                    self,
                    "WordPress Export Complete",
                    f"All {len(created_posts)} stories have been posted successfully as drafts to {client.site_url}!\n\n"
                    f"Created Posts:\n{posts_summary}",
                )
        elif created_posts and failed_posts:
            success_summary = "\n".join([f"  #{p['id']}: {p['title']}" for p in created_posts])
            fail_summary = "\n".join([f"  {f['title']}: {f['error']}" for f in failed_posts])
            QMessageBox.warning(
                self,
                "WordPress Export Finished with Errors",
                f"Completed {len(created_posts)} of {total_posts} draft posts.\n\n"
                f"Created Posts:\n{success_summary}\n\n"
                f"Failed Posts:\n{fail_summary}",
            )
        elif failed_posts:
            fail_summary = "\n".join([f"  {f['title']}: {f['error']}" for f in failed_posts])
            QMessageBox.critical(
                self,
                "WordPress Export Failed",
                f"None of the {len(failed_posts)} posts could be exported to WordPress.\n\n"
                f"Errors:\n{fail_summary}",
            )

    def export_full_episode(self, custom_formats=None, custom_base=None, custom_options=None, directory=None, show_completion=True, progress_dialog=None, progress_value=0):
        if not self.transcript and not self.audio_file:
            QMessageBox.warning(self, "Nothing to Export", "There is no transcript or media available to export.")
            return False
        if custom_formats is None or custom_base is None or custom_options is None:
            choice = self._choose_export_formats("Export Full Episode")
            if not choice:
                return False
            formats, base, options = choice
        else:
            formats, base, options = custom_formats, custom_base, custom_options

        if directory is None:
            parent_dir = QFileDialog.getExistingDirectory(self, "Choose Export Location", self._dialog_directory())
            if not parent_dir:
                return False
            project_dir, _, _, chosen_base = self.prepare_export_directories(parent_dir, default_name=base, prompt_user=True)
            if not project_dir:
                return False
            directory = str(project_dir)
            base = chosen_base

        out = Path(directory)
        create_bundle = str(self.settings_store.value("create_project_subfolders", "true")).lower() in {"1", "true", "yes"}
        if create_bundle:
            transcripts_out = out / "Transcripts"
            media_out = out / "Media"
            transcripts_out.mkdir(parents=True, exist_ok=True)
            if formats.get("media"):
                media_out.mkdir(parents=True, exist_ok=True)
        else:
            transcripts_out = out
            media_out = out

        created_local_dialog = False
        if progress_dialog is None:
            progress_dialog = QProgressDialog("Preparing export...", "Cancel", 0, 1, self)
            progress_dialog.setWindowTitle("Exporting Files")
            progress_dialog.setWindowModality(Qt.WindowModality.WindowModal)
            progress_dialog.setMinimumDuration(0)
            progress_dialog.setValue(0)
            progress_dialog.show()
            QApplication.processEvents()
            created_local_dialog = True

        try:
            languages_to_export = []
            batch_direction = options.get("translation_direction")
            if batch_direction and options.get("include_spanish", False):
                source_code, target_code, target_suffix = self.translation_export_spec(options)
                languages_to_export.append((source_code, ""))
                if self.get_translation_item(source_code, target_code):
                    languages_to_export.append((target_code, target_suffix))
            else:
                if options.get("include_english", True):
                    languages_to_export.append(("en", ""))
                if options.get("include_spanish", False):
                    has_es = self.has_spanish_translation() if hasattr(self, "has_spanish_translation") else (
                        self.translation_is_current(self.translation_key("en", "es")) if hasattr(self, "translation_is_current") else False
                    )
                    if has_es:
                        languages_to_export.append(("es", "_es"))

            doc_title = base if base else (safe_filename(self.audio_file.stem) if self.audio_file else "Transcript")

            if progress_dialog is not None:
                if progress_dialog.wasCanceled():
                    self.log_activity("[EXPORT] Export canceled by user.")
                    return False
                progress_dialog.setLabelText(f"Exporting Full Episode: '{doc_title}'...")
                progress_dialog.setValue(progress_value)
                QApplication.processEvents()

            for lang_code, suffix in languages_to_export:
                file_base = f"{base}{suffix}"

                batch_direction = options.get("translation_direction")
                source_code = self.translation_export_spec(options)[0] if batch_direction else "en"
                if lang_code == source_code:
                    segments = self.transcript.get("segments", []) if self.transcript else []
                    blocks = self.build_story_blocks(segments) if segments else []
                else:
                    batch_direction = options.get("translation_direction")
                    if batch_direction:
                        source_code, target_code, _target_suffix = self.translation_export_spec(options)
                        item = self.get_translation_item(source_code, target_code)
                    else:
                        item = self.get_spanish_translation_item() if hasattr(self, "get_spanish_translation_item") else (
                            self.translations.get("en-es") or self.translations.get("en_es") or {}
                        )
                    trans_segs = item.get("segments", []) if item else []
                    source_segs = self.transcript.get("segments", []) if self.transcript else []
                    curr_spk_blocks = []
                    for idx, t_seg in enumerate(trans_segs):
                        source_seg = source_segs[idx] if idx < len(source_segs) else {}
                        t_start = float(t_seg.get("start", source_seg.get("start", 0.0)))
                        t_end = float(t_seg.get("end", source_seg.get("end", t_start + 1.0)))
                        spk = self.get_effective_speaker_name(idx, source_seg) if source_seg else ""
                        curr_spk_blocks.append({
                            "speaker": spk,
                            "text": t_seg.get("text", "").strip(),
                            "start": t_start,
                            "end": t_end,
                            "_source_index": idx,
                        })
                    blocks = self.build_story_blocks(curr_spk_blocks) if curr_spk_blocks else []

                # Export TXT to Transcripts subfolder
                if formats.get("txt"):
                    txt_file = transcripts_out / f"{file_base}.txt"
                    with open(txt_file, "w", encoding="utf-8") as f:
                        source_name = self.audio_file.name if self.audio_file else "Text-only project"
                        lang_label = " (Spanish)" if lang_code == "es" else (" (English)" if lang_code == "en" else "")
                        f.write(f"{doc_title}{lang_label}\n{source_name}\n" + "=" * 70 + "\n\n")

                        if self.diarization and lang_code == "en":
                            number = self.diarization.get("num_speakers", 0)
                            f.write(f"Speaker detection: {number} speaker(s) detected.\n\n")

                        for block in blocks:
                            speaker = (block.get("speaker") or "").strip() if options.get("include_speakers", True) else ""
                            paragraph_text = block.get("text", "").strip()
                            if not paragraph_text:
                                continue

                            prefix = ""
                            if options.get("include_timestamps") and block.get("start") is not None:
                                prefix = f"[{format_time(block['start'])}] "
                            if speaker:
                                prefix += f"{speaker}: "

                            f.write(f"{prefix}{paragraph_text}\n\n")

                # Export DOCX to Transcripts subfolder
                if formats.get("docx"):
                    docx_file = transcripts_out / f"{file_base}.docx"
                    document = Document()
                    document.styles["Normal"].font.name = "Arial"
                    document.styles["Normal"].font.size = Pt(11)
                    lang_label = " (Spanish)" if lang_code == "es" else (" (English)" if lang_code == "en" else "")
                    document.add_heading(f"{doc_title}{lang_label}", 0)
                    if self.audio_file:
                        document.add_paragraph(f"Recording: {self.audio_file.name}")

                    if blocks:
                        for block in blocks:
                            speaker = (block.get("speaker") or "").strip() if options.get("include_speakers", True) else ""
                            paragraph_text = block.get("text", "").strip()
                            if not paragraph_text:
                                continue

                            p = document.add_paragraph()
                            time_prefix = ""
                            if options.get("include_timestamps") and "start" in block and block["start"] is not None:
                                time_prefix = f"[{format_time(block['start'])}] "

                            if time_prefix:
                                r_time = p.add_run(time_prefix)
                                r_time.font.color.rgb = RGBColor(120, 120, 120)

                            if speaker:
                                r_spk = p.add_run(f"{speaker}: ")
                                r_spk.bold = True

                            p.add_run(paragraph_text)
                            p.paragraph_format.space_after = Pt(6)
                    document.save(docx_file)

                # Export Subtitles to Transcripts subfolder
                if formats.get("srt"):
                    self.write_subtitles(blocks, transcripts_out / f"{file_base}.srt", "srt", options.get("include_speakers", True))
                if formats.get("vtt"):
                    self.write_subtitles(blocks, transcripts_out / f"{file_base}.vtt", "vtt", options.get("include_speakers", True))

            # Export Media to Media subfolder
            if formats.get("media"):
                if not self.audio_file:
                    raise RuntimeError("Media export is unavailable because this project has no imported media file.")
                media_file = media_out / f"{base}{self.audio_file.suffix.lower()}"
                self.extract_media(0, self.duration, media_file)

            if progress_dialog is not None and created_local_dialog:
                progress_dialog.setValue(1)
                QApplication.processEvents()

            self.log_activity(f"[EXPORT] Exported full episode to {out}")
            if show_completion and not (progress_dialog and progress_dialog.wasCanceled()):
                QMessageBox.information(self, "Export Complete", f"Exported to:\n{out}")
            return True
        except Exception as exc:
            self.log_activity(f"[ERROR] Full episode export failed: {exc}")
            QMessageBox.critical(self, "Export Error", str(exc))
            return False
        finally:
            if created_local_dialog and progress_dialog is not None:
                progress_dialog.close()

    def _choose_export_formats(self, title="Export", allow_media=True):
        dialog = QDialog(self)
        dialog.setWindowTitle(title)
        dialog.setMinimumWidth(380)
        layout = QVBoxLayout(dialog)
        layout.addWidget(QLabel("Choose the formats to export."))

        txt = QCheckBox("Text (.txt)")
        docx = QCheckBox("DOCX (.docx)")
        srt = QCheckBox("SubRip subtitles (.srt)")
        vtt = QCheckBox("WebVTT subtitles (.vtt)")
        media = QCheckBox(f"Media ({self.audio_file.suffix.lower() if self.audio_file else 'source format'})")
        media_available = allow_media and self.audio_file is not None

        txt.setChecked(True)
        docx.setChecked(True)
        media.setChecked(media_available)
        media.setVisible(media_available)

        layout.addWidget(txt)
        layout.addWidget(docx)
        layout.addWidget(srt)
        layout.addWidget(vtt)
        if allow_media:
            layout.addWidget(media)

        default = safe_filename(self.project_file.stem if self.project_file else (self.audio_file.stem if self.audio_file else "export"))
        name = QLineEdit(default)
        form = QFormLayout()
        form.addRow("Base filename:", name)
        layout.addLayout(form)

        buttons = QHBoxLayout()
        ok = QPushButton("Next")
        cancel = QPushButton("Cancel")
        buttons.addStretch()
        buttons.addWidget(ok)
        buttons.addWidget(cancel)
        layout.addLayout(buttons)

        cancel.clicked.connect(dialog.reject)
        ok.clicked.connect(dialog.accept)

        if dialog.exec() != QDialog.DialogCode.Accepted:
            return None

        formats = {"txt": txt.isChecked(), "docx": docx.isChecked(), "srt": srt.isChecked(), "vtt": vtt.isChecked(), "media": media.isChecked() if allow_media else False}
        if not any(formats.values()):
            QMessageBox.warning(self, "Export", "Select at least one export format.")
            return None

        base = safe_filename(name.text().strip() or default)

        opt_dialog = QDialog(self)
        opt_dialog.setWindowTitle("Transcript Content Options")
        opt_dialog.setMinimumWidth(360)
        opt_layout = QVBoxLayout(opt_dialog)
        opt_layout.addWidget(QLabel("Configure content elements for text exports:"))

        include_speakers_cb = QCheckBox("Include Speaker Labels")
        include_speakers_cb.setChecked(True)

        include_timestamps_cb = QCheckBox("Include Timestamps")
        include_timestamps_cb.setChecked(False)

        opt_layout.addWidget(include_speakers_cb)
        opt_layout.addWidget(include_timestamps_cb)

        opt_layout.addSpacing(6)
        opt_layout.addWidget(QLabel("<b>Language Tracks:</b>"))

        include_english_cb = QCheckBox("Include English Transcript")
        include_english_cb.setChecked(True)

        include_spanish_cb = QCheckBox("Include Spanish Transcript")

        es_key = self.translation_key("en", "es")
        has_spanish = self.translation_is_current(es_key)

        if has_spanish:
            include_spanish_cb.setChecked(True)
            include_spanish_cb.setEnabled(True)
        else:
            include_spanish_cb.setChecked(False)
            include_spanish_cb.setEnabled(False)
            include_spanish_cb.setToolTip("Spanish translation is not available or up to date for this project.")

        opt_layout.addWidget(include_english_cb)
        opt_layout.addWidget(include_spanish_cb)

        opt_buttons = QHBoxLayout()
        opt_ok = QPushButton("Export")
        opt_cancel = QPushButton("Cancel")
        opt_buttons.addStretch()
        opt_buttons.addWidget(opt_ok)
        opt_buttons.addWidget(opt_cancel)
        opt_layout.addLayout(opt_buttons)

        opt_cancel.clicked.connect(opt_dialog.reject)
        opt_ok.clicked.connect(opt_dialog.accept)

        if opt_dialog.exec() != QDialog.DialogCode.Accepted:
            return None

        if (formats["txt"] or formats["docx"]) and not include_english_cb.isChecked() and not include_spanish_cb.isChecked():
            QMessageBox.warning(self, "Export Options", "Please select at least one language track (English or Spanish) to export text content.")
            return None

        options = {
            "include_speakers": include_speakers_cb.isChecked(),
            "include_timestamps": include_timestamps_cb.isChecked(),
            "include_english": include_english_cb.isChecked(),
            "include_spanish": include_spanish_cb.isChecked(),
        }

        return formats, base, options

    def _subtitle_timestamp(self, seconds, vtt=False):
        seconds=max(0.0,float(seconds)); h=int(seconds//3600); m=int((seconds%3600)//60); s=seconds%60
        ms=int(round((s-int(s))*1000)); sec=int(s)
        if ms>=1000: sec+=1; ms=0
        return f"{h:02d}:{m:02d}:{sec:02d}{'.' if vtt else ','}{ms:03d}"

    def write_subtitles(self, blocks, path, fmt="srt", include_speakers=True):
        lines=[]
        if fmt == "vtt": lines.append("WEBVTT\n")
        for i, block in enumerate(blocks,1):
            start=block.get("start",0); end=block.get("end", start+1.0)
            text=self.clean_export_text(block.get("text",""), block.get("speaker",""))
            if include_speakers and block.get("speaker"):
                text=f"{block['speaker']}: {text}"
            if not text: continue
            if fmt == "srt":
                lines.extend([str(i), f"{self._subtitle_timestamp(start)} --> {self._subtitle_timestamp(end)}", text, ""])
            else:
                lines.extend([f"{self._subtitle_timestamp(start, True)} --> {self._subtitle_timestamp(end, True)}", text, ""])
        Path(path).write_text("\n".join(lines), encoding="utf-8")

    def extract_media(self, start, end, output_file):
        """Export a media range using the same container/format as the imported file."""
        if not self.audio_file:
            raise RuntimeError("No source media is loaded.")
        output_file = Path(output_file)
        duration = max(0.0, float(end) - float(start))
        if duration <= 0:
            raise RuntimeError("The selected media range is empty.")

        ext = output_file.suffix.lower()
        copy_cmd = [ffmpeg_path() or "ffmpeg", "-y", "-ss", str(start), "-i", str(self.audio_file), "-t", str(duration), "-map", "0", "-c", "copy", str(output_file)]
        result = subprocess.run(copy_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=600)
        if result.returncode == 0:
            return

        codec_args = {
            ".wav": ["-c:a", "pcm_s16le"],
            ".mp3": ["-c:a", "libmp3lame", "-q:a", "2"],
            ".flac": ["-c:a", "flac"],
            ".m4a": ["-c:a", "aac", "-b:a", "192k"],
            ".mp4": ["-c:v", "libx264", "-c:a", "aac", "-b:a", "192k"],
            ".mov": ["-c:v", "libx264", "-c:a", "aac", "-b:a", "192k"],
            ".webm": ["-c:v", "libvpx-vp9", "-c:a", "libopus"],
            ".ogg": ["-c:a", "libvorbis"],
            ".aac": ["-c:a", "aac", "-b:a", "192k"],
        }.get(ext)
        if codec_args is None:
            raise RuntimeError(f"Could not export media in the original format ({ext or 'unknown'}).\n\n{result.stderr}")
        transcode_cmd = [ffmpeg_path() or "ffmpeg", "-y", "-ss", str(start), "-i", str(self.audio_file), "-t", str(duration), "-map", "0"] + codec_args + [str(output_file)]
        result2 = subprocess.run(transcode_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=1800)
        if result2.returncode != 0:
            raise RuntimeError(result2.stderr or result.stderr)

    def extract_audio(self, start, end, output_file):
        # Backward-compatible helper for older project/export code.
        duration=end-start
        command=[ffmpeg_path() or "ffmpeg","-y","-ss",str(start),"-i",str(self.audio_file),"-t",str(duration),"-vn","-codec:a","libmp3lame","-q:a","2",str(output_file)]

        result = subprocess.run(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=600,
        )

        if result.returncode != 0:
            raise RuntimeError(result.stderr)

    def transcript_for_range(self, start, end):
        if not self.transcript:
            return []

        start_time = float(start) if start is not None else 0.0
        end_time = float(end) if end is not None else float("inf")

        result = []
        for source_index, segment in enumerate(self.transcript.get("segments", [])):
            s_start = float(segment.get("start", 0.0))
            s_end = float(segment.get("end", s_start))
            if s_end <= start_time or s_start >= end_time:
                continue
            copied = dict(segment)
            copied["_source_index"] = source_index
            result.append(copied)

        return result

    def speaker_for_segment(self, segment):
        if not segment:
            return ""
        start = segment.get("start", 0.0) if isinstance(segment, dict) else getattr(segment, "start", 0.0)
        end = segment.get("end", start) if isinstance(segment, dict) else getattr(segment, "end", start)
        return self.speaker_at_time(start, end)

    def clean_export_text(self, text, current_speaker=""):
        text = str(text or "").strip()
        if not text:
            return ""

        candidates = set()
        if current_speaker:
            candidates.add(str(current_speaker).strip())
        for value in self.speaker_names.values():
            if value:
                candidates.add(str(value).strip())
        if self.diarization:
            self._ensure_diar_speaker_index()
            candidates.update(self._diar_speaker_labels)

        candidates = sorted((c for c in candidates if c), key=len, reverse=True)
        if not candidates:
            return text

        # Strip speaker labels matched with any standard punctuation (: - —)
        changed = True
        while changed:
            changed = False
            for name in candidates:
                pattern = rf"^\s*{re.escape(name)}\s*[:\-\—]\s*"
                new_text = re.sub(pattern, "", text, count=1, flags=re.IGNORECASE)
                if new_text != text:
                    text = new_text.strip()
                    changed = True
                    break
        return text

    def build_story_blocks(self, segments):
        blocks = []
        current_speaker = None
        current_text = []
        current_words = 0
        current_start = None  # Track the start time of the current block
        current_end = None

        def flush():
            nonlocal current_speaker, current_text, current_words, current_start, current_end
            if not current_text:
                return
            text = " ".join(current_text).strip()
            if text:
                blocks.append({
                    "speaker": current_speaker, 
                    "text": text,
                    "start": current_start,
                    "end": current_end
                })
            current_text = []
            current_words = 0
            current_start = None
            current_end = None

        for seg_idx, segment in enumerate(segments):
            source_idx = segment.get("_source_index", seg_idx)
            text = segment.get("text", "").strip()
            if not text:
                continue

            speaker = (self.get_effective_speaker_name(source_idx, segment) or "").strip()
            text = self.clean_export_text(text, speaker)
            if not text:
                continue
            words = len(text.split())

            speaker_changed = (current_text and speaker != current_speaker)
            reached_word_threshold = (current_words >= MIN_WORDS_PER_PARAGRAPH)
            last_was_sentence_end = current_text and is_sentence_end(current_text[-1])

            if speaker_changed or (reached_word_threshold and last_was_sentence_end):
                flush()

            if not current_text:
                current_speaker = speaker
                current_start = segment.get("start")
            current_end = segment.get("end", current_start)

            current_text.append(text)
            current_words += words

        flush()
        return blocks

    def story_text(self, segments):
        blocks = self.build_story_blocks(segments)
        output = []
        for block in blocks:
            speaker = block["speaker"]
            paragraph = block["text"]
            output.append(f"{speaker}: {paragraph}" if speaker else paragraph)

        return "\n\n".join(output)

    def add_story_to_docx(self, document, segments):
        blocks = self.build_story_blocks(segments)
        for block in blocks:
            speaker = (block["speaker"] or "").strip()
            paragraph = block["text"]
            doc_paragraph = document.add_paragraph()
            if speaker:
                speaker_run = doc_paragraph.add_run(f"{speaker}: ")
                speaker_run.bold = True
            doc_paragraph.add_run(paragraph)

    def closeEvent(self, event):
        self.log_activity("[SYSTEM] Application shutdown requested.")
        self.statusBar().showMessage("Shutting down...")

        model_thread = getattr(self, "_model_install_thread", None)
        if model_thread is not None and model_thread.isRunning():
            self.log_activity("[WARNING] A model installation is still running; close was canceled to prevent an interrupted download.", mark_dirty=False)
            QMessageBox.warning(
                self,
                "Model Installation Still Running",
                "A model or AI component is still being installed. Please wait for the installation to finish before closing the application."
            )
            event.ignore()
            return

        try:
            self.cleanup_transcription_process()
        except Exception as exc:
            self.log_activity(f"[WARNING] Transcription cleanup failed: {exc}")

        try:
            if not self.stop_all_processing(timeout_ms=10000):
                self.log_activity("[WARNING] One or more processing workers are still shutting down. Close was canceled to avoid destroying a running QThread.", mark_dirty=False)
                QMessageBox.warning(
                    self,
                    "Processing Still Running",
                    "A local processing task is still shutting down. The application was not closed to prevent data loss or a thread crash.\n\nPlease wait a few seconds and try closing again."
                )
                event.ignore()
                return
        except Exception as exc:
            self.log_activity(f"[WARNING] Processing cleanup failed: {exc}", mark_dirty=False)
            event.ignore()
            return

        try:
            if getattr(self, "player", None):
                self.player.stop()
                self.player.setSource(QUrl())
        except Exception as exc:
            self.log_activity(f"[WARNING] Media player cleanup failed: {exc}")

        # Waveform extraction uses a QThread and an FFmpeg subprocess.
        # Cancel the worker and wait for the thread before allowing Qt to
        # destroy the window, preventing QThread lifetime crashes.
        try:
            if not self.stop_waveform_worker(timeout_ms=10000):
                self.log_activity("[WARNING] Waveform worker is still shutting down. Close was canceled to avoid destroying a running QThread.", mark_dirty=False)
                QMessageBox.warning(
                    self,
                    "Waveform Still Running",
                    "The waveform worker is still shutting down. The application was not closed to prevent a thread crash.\n\nPlease wait a few seconds and try closing again."
                )
                event.ignore()
                return
        except Exception as exc:
            self.log_activity(f"[WARNING] Waveform cleanup encountered an issue: {exc}", mark_dirty=False)

        try:
            for thread in list(getattr(self, "translation_status_threads", [])):
                if thread.isRunning():
                    thread.quit()
                    thread.wait(5000)
            self.translation_status_threads.clear()
        except Exception as exc:
            self.log_activity(f"[WARNING] Translation status cleanup failed: {exc}", mark_dirty=False)

        try:
            if not self.stop_video_thumbnail_worker():
                self.log_activity("[WARNING] Video thumbnail worker is still stopping. Close was canceled to avoid a QThread lifetime crash.", mark_dirty=False)
                event.ignore()
                return
        except Exception:
            pass
        try:
            self.auto_save_timer.stop()
            self.scrub_timer.stop()
        except Exception:
            pass

        checkpoint_thread = getattr(self, "translation_checkpoint_thread", None)
        if checkpoint_thread is not None and checkpoint_thread.is_alive():
            checkpoint_thread.join(timeout=5.0)

        for save_thread in list(getattr(self, "translation_save_threads", [])):
            if save_thread.is_alive():
                save_thread.join(timeout=5.0)

        try:
            warnings.showwarning = self._original_showwarning
            sys.excepthook = self._original_excepthook
        except Exception:
            pass

        # QSettings writes made during this session (a project just saved,
        # a Preferences change) are not guaranteed to reach disk on their
        # own during interpreter shutdown -- force a flush now, while the
        # app is still fully alive, so the next launch sees them.
        try:
            if getattr(self, "settings_store", None) is not None:
                self.settings_store.sync()
        except Exception as exc:
            self.log_activity(f"[WARNING] Settings sync failed: {exc}", mark_dirty=False)

        self.log_activity("[SYSTEM] Application shutdown cleanup complete.")
        event.accept()

    def perform_stories_export(
        self,
        target_stories=None,
        custom_formats=None,
        custom_base=None,
        custom_options=None,
        directory=None,
        show_completion=False,
    ):
        stories = target_stories if target_stories is not None else getattr(self, "stories", [])
        if not stories:
            return False
        base = custom_base or (safe_filename(self.project_file.stem if self.project_file else (self.audio_file.stem if self.audio_file else "export")))
        formats = custom_formats or {"txt": True, "docx": True, "srt": False, "vtt": False, "media": False}
        options = custom_options or {"include_speakers": True, "include_timestamps": False, "include_english": True, "include_spanish": False}
        stories_to_export = list(enumerate(stories))
        success = self._export_story_files(stories_to_export, formats, base, options, directory)
        if show_completion and success:
            QMessageBox.information(self, "Export Complete", f"Exported {len(stories_to_export)} stories to {directory}")
        return success

    def _get_transcript_text_slice(self, start: float, end: float | None = None) -> str:
        segments = self.transcript_for_range(start, end)
        parts = []
        for s in segments:
            t = s.get("text", "").strip()
            if t:
                parts.append(t)
        return " ".join(parts)
