"""Unified Export Dialog for Radio & TV Story Segmenter.

Dynamically discovers export destinations from enabled plugins via PluginManager.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

try:
    from PySide6.QtCore import Qt, QSettings
    from PySide6.QtWidgets import (
        QButtonGroup,
        QCheckBox,
        QComboBox,
        QDialog,
        QFileDialog,
        QFrame,
        QHBoxLayout,
        QLabel,
        QLineEdit,
        QMessageBox,
        QPushButton,
        QRadioButton,
        QScrollArea,
        QSpinBox,
        QStackedWidget,
        QTabWidget,
        QVBoxLayout,
        QWidget,
    )
    GUI_AVAILABLE = True
except ImportError:
    GUI_AVAILABLE = False
    Qt = None
    QSettings = None
    QDialog = object

from prs_shared import (
    INTERNAL_APP_ID,
    CollapsibleSection,
    format_time,
    safe_filename,
)
from plugins.base import ExportDestination


class UnifiedExportDialog(QDialog):
    """Unified Export Center supporting Local Files and dynamic plugin destinations."""

    def __init__(self, main_window: Any, initial_scope: str = "full", initial_dest: Optional[str] = None, parent: Optional[QWidget] = None):
        super().__init__(parent or main_window)
        self.main_window = main_window
        self.setWindowTitle("Export")
        self.setMinimumWidth(780)
        self.setMinimumHeight(520)
        self.resize(840, 620)

        self._plugin_destinations: List[Tuple[QRadioButton, ExportDestination, QWidget]] = []
        self._temp_preview_files = set()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(8)

        # Header bar with Expand / Collapse All control
        hdr_row = QHBoxLayout()
        hdr_row.setContentsMargins(2, 0, 2, 0)
        hdr_label = QLabel("<b>Unified Export Center</b>")
        hdr_label.setStyleSheet("font-size: 13px; color: #f1f5f9;")
        self.toggle_all_btn = QPushButton("▾ Collapse All")
        self.toggle_all_btn.setToolTip("Toggle expand/collapse for all sections on the current page")
        self.toggle_all_btn.setStyleSheet("""
            QPushButton {
                background-color: #1e293b;
                color: #94a3b8;
                border: 1px solid #334155;
                border-radius: 4px;
                padding: 3px 10px;
                font-size: 11px;
                font-weight: 500;
            }
            QPushButton:hover {
                background-color: #334155;
                color: #f1f5f9;
            }
        """)
        self.toggle_all_btn.clicked.connect(self._toggle_all_sections)
        hdr_row.addWidget(hdr_label)
        hdr_row.addStretch()
        hdr_row.addWidget(self.toggle_all_btn)
        layout.addLayout(hdr_row)

        # Export Destination Selection
        self.dest_section = CollapsibleSection("Export Destination", self, is_expanded=True)
        dest_content_layout = QHBoxLayout()
        self.dest_button_group = QButtonGroup(self)

        self.radio_local = QRadioButton("Local Files (Media && Transcripts)")
        self.radio_local.setChecked(True)
        self.dest_button_group.addButton(self.radio_local)
        dest_content_layout.addWidget(self.radio_local)

        # Scope Selection
        is_music = getattr(self.main_window, "story_detection_mode", "voice") == "music"
        term_plural = "Songs" if is_music else "Stories"
        self.scope_section = CollapsibleSection("Export Scope", self, is_expanded=True)
        self.scope_combo = QComboBox()
        self.scope_combo.addItem(f"Selected {term_plural}", "selected_stories")
        self.scope_combo.addItem(f"All {term_plural}", "all_stories")
        self.scope_combo.addItem("Full Episode", "full")
        self.scope_combo.addItem(f"Full Episode & All {term_plural}", "full_and_all_stories")

        idx = self.scope_combo.findData(initial_scope)
        if idx >= 0:
            self.scope_combo.setCurrentIndex(idx)
        else:
            selected_rows = getattr(self.main_window, "current_selected_story_indices", [])
            if selected_rows:
                self.scope_combo.setCurrentIndex(0)
            elif getattr(self.main_window, "stories", []):
                self.scope_combo.setCurrentIndex(1)
            else:
                self.scope_combo.setCurrentIndex(2)

        self.scope_section.add_widget(self.scope_combo)
        layout.addWidget(self.dest_section)
        layout.addWidget(self.scope_section)

        # Stacked Widget for Destinations
        self.stacked_widget = QStackedWidget()

        # Page 0: Local Files
        local_page = self._create_local_page()
        self.stacked_widget.addWidget(local_page)

        # Dynamically discover plugin destinations
        plugin_mgr = getattr(self.main_window, "plugin_manager", None)
        registered_dests: List[ExportDestination] = []
        if plugin_mgr and hasattr(plugin_mgr, "get_export_destinations"):
            registered_dests = plugin_mgr.get_export_destinations()

        for dest in registered_dests:
            radio = QRadioButton(dest.title)
            self.dest_button_group.addButton(radio)
            dest_content_layout.addWidget(radio)

            page_widget = dest.create_widget(self.stacked_widget, self.main_window)
            self.stacked_widget.addWidget(page_widget)
            self._plugin_destinations.append((radio, dest, page_widget))
            radio.toggled.connect(self._on_dest_changed)

        self.dest_section.add_layout(dest_content_layout)
        if not registered_dests:
            self.dest_section.setVisible(False)

        layout.addWidget(self.stacked_widget)

        self.radio_local.toggled.connect(self._on_dest_changed)
        self.scope_combo.currentIndexChanged.connect(self._on_scope_changed)

        # Bottom Buttons
        btns = QHBoxLayout()
        self.save_defaults_btn = QPushButton("Save Options as Default")
        self.save_defaults_btn.setToolTip("Save the current export options as the default for future exports.")
        btns.addWidget(self.save_defaults_btn)
        btns.addStretch()
        self.export_btn = QPushButton("Export Files...")
        self.export_btn.setDefault(True)
        self.cancel_btn = QPushButton("Cancel")
        btns.addWidget(self.export_btn)
        btns.addWidget(self.cancel_btn)
        layout.addLayout(btns)

        self.save_defaults_btn.clicked.connect(lambda: self.save_options_to_settings(as_default=True))
        self.cancel_btn.clicked.connect(self.reject)
        self.export_btn.clicked.connect(self._handle_accept)

        self._load_saved_options()

        # Handle initial_dest routing
        if initial_dest:
            for r, d, _ in self._plugin_destinations:
                if d.id == initial_dest:
                    r.setChecked(True)
                    break

        self._on_dest_changed()

    def _create_local_page(self) -> QWidget:
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

        self.formats_section = CollapsibleSection("Export Formats", self, is_expanded=True, subtitle="TXT, DOCX, PDF, Media...")
        self.cb_txt = QCheckBox("Text transcript (.txt)")
        self.cb_docx = QCheckBox("Word document (.docx)")
        self.cb_pdf = QCheckBox("PDF document (.pdf)")
        self.cb_srt = QCheckBox("SubRip subtitles (.srt)")
        self.cb_vtt = QCheckBox("WebVTT subtitles (.vtt)")
        self.cb_cue = QCheckBox("CUE sheet (.cue)")
        self.cb_tracklist = QCheckBox("Tracklist / YouTube Chapters (.txt)")

        audio_file = getattr(self.main_window, "audio_file", None)
        media_ext = audio_file.suffix.lower() if audio_file else "media"
        self.cb_media = QCheckBox(f"Media clip ({media_ext})")

        is_music_mode = getattr(self.main_window, "story_detection_mode", "") == "music"
        self.cb_txt.setChecked(not is_music_mode)
        self.cb_docx.setChecked(not is_music_mode)
        self.cb_pdf.setChecked(not is_music_mode)
        self.cb_cue.setChecked(is_music_mode)
        self.cb_tracklist.setChecked(is_music_mode)
        self.cb_media.setChecked(audio_file is not None)
        self.cb_media.setEnabled(audio_file is not None)

        self.formats_section.add_widget(self.cb_txt)
        self.formats_section.add_widget(self.cb_docx)
        self.formats_section.add_widget(self.cb_pdf)
        self.formats_section.add_widget(self.cb_srt)
        self.formats_section.add_widget(self.cb_vtt)
        self.formats_section.add_widget(self.cb_cue)
        self.formats_section.add_widget(self.cb_tracklist)
        self.formats_section.add_widget(self.cb_media)
        local_layout.addWidget(self.formats_section)

        # Content & Language options
        self.content_section = CollapsibleSection("Content & Language Options", self, is_expanded=True, subtitle="Speakers, Timestamps, Comments")
        self.cb_speakers = QCheckBox("Include Speaker Labels")
        self.cb_speakers.setChecked(True)
        self.cb_timestamps = QCheckBox("Include Timestamps")
        self.cb_timestamps.setChecked(False)
        self.cb_notes = QCheckBox("Include Comments")
        self.cb_notes.setToolTip("Include transcript comments in exported DOCX and PDF documents")
        self.cb_notes.setChecked(True)

        self.cb_en = QCheckBox("English")
        self.cb_en.setChecked(True)
        has_spanish = bool(getattr(self.main_window, "spanish_transcript", None))
        self.cb_es = QCheckBox("Spanish (Translated)")
        self.cb_es.setChecked(has_spanish)
        self.cb_es.setEnabled(has_spanish)
        if not has_spanish:
            self.cb_es.setToolTip("Spanish translation is not available for this project. Generate a translation first to enable.")

        self.content_section.add_widget(self.cb_speakers)
        self.content_section.add_widget(self.cb_timestamps)
        self.content_section.add_widget(self.cb_notes)

        lang_layout = QHBoxLayout()
        lang_layout.addWidget(self.cb_en)
        lang_layout.addWidget(self.cb_es)
        lang_layout.addStretch()
        self.content_section.add_layout(lang_layout)
        local_layout.addWidget(self.content_section)

        # Location & Filename Section
        self.loc_section = CollapsibleSection("Export Location & Filename", self, is_expanded=True)
        fn_row = QHBoxLayout()
        fn_row.addWidget(QLabel("Base Filename:"))
        default_name = Path(audio_file).stem if audio_file else "export"
        self.filename_edit = QLineEdit(default_name)
        fn_row.addWidget(self.filename_edit)
        self.loc_section.add_layout(fn_row)

        self.loc_group = QButtonGroup(self)
        self.loc_radio_default = QRadioButton("Project Folder (or prompt on export)")
        self.loc_radio_custom = QRadioButton("Custom Folder:")
        self.loc_radio_default.setChecked(True)
        self.loc_group.addButton(self.loc_radio_default)
        self.loc_group.addButton(self.loc_radio_custom)
        self.loc_section.add_widget(self.loc_radio_default)

        custom_row = QHBoxLayout()
        custom_row.addWidget(self.loc_radio_custom)
        self.loc_custom_path_edit = QLineEdit()
        self.loc_custom_path_edit.setEnabled(False)
        custom_row.addWidget(self.loc_custom_path_edit, 1)
        self.loc_browse_btn = QPushButton("Browse...")
        self.loc_browse_btn.setEnabled(False)
        self.loc_browse_btn.clicked.connect(self._browse_custom_export_location)
        custom_row.addWidget(self.loc_browse_btn)
        self.loc_section.add_layout(custom_row)

        self.loc_radio_default.toggled.connect(self._on_location_radio_toggled)
        self.loc_radio_custom.toggled.connect(self._on_location_radio_toggled)
        local_layout.addWidget(self.loc_section)

        local_layout.addStretch()
        local_scroll.setWidget(local_scroll_content)
        local_page_layout.addWidget(local_scroll)
        return local_page

    def _on_location_radio_toggled(self):
        use_custom = self.loc_radio_custom.isChecked()
        self.loc_custom_path_edit.setEnabled(use_custom)
        self.loc_browse_btn.setEnabled(use_custom)

    def _browse_custom_export_location(self):
        initial = self.loc_custom_path_edit.text().strip() or str(Path.home())
        folder = QFileDialog.getExistingDirectory(self, "Select Export Location", initial)
        if folder:
            self.loc_custom_path_edit.setText(folder)
            self.loc_radio_custom.setChecked(True)

    def _toggle_all_sections(self):
        all_sections = [self.dest_section, self.scope_section]
        curr_widget = self.stacked_widget.currentWidget()
        if curr_widget:
            child_sections = curr_widget.findChildren(CollapsibleSection)
            all_sections.extend(child_sections)

        active_sections = [s for s in all_sections if s is not None and s.isVisible()]
        if not active_sections:
            return
        any_expanded = any(s.is_expanded() for s in active_sections)
        new_state = not any_expanded
        for s in active_sections:
            s.set_expanded(new_state)
        self.toggle_all_btn.setText("▾ Collapse All" if new_state else "▸ Expand All")

    def _on_dest_changed(self):
        if self.radio_local.isChecked():
            self.stacked_widget.setCurrentIndex(0)
            self.export_btn.setText("Export Files...")
            return

        for radio, dest, widget in self._plugin_destinations:
            if radio.isChecked():
                self.stacked_widget.setCurrentWidget(widget)
                btn_lbl = getattr(dest, "button_label", None) or f"Export {getattr(dest, 'title', 'Files')}..."
                self.export_btn.setText(btn_lbl)
                break

    def _on_scope_changed(self):
        scope = self.scope_combo.currentData()
        stories = getattr(self.main_window, "stories", []) or []
        for _, dest, _ in self._plugin_destinations:
            dest.on_scope_changed(scope, stories)

    def _load_saved_options(self):
        settings = QSettings(INTERNAL_APP_ID, INTERNAL_APP_ID)
        self.cb_txt.setChecked(str(settings.value("export_opt_fmt_txt", "true")).lower() in {"1", "true", "yes"})
        self.cb_docx.setChecked(str(settings.value("export_opt_fmt_docx", "true")).lower() in {"1", "true", "yes"})
        self.cb_pdf.setChecked(str(settings.value("export_opt_fmt_pdf", "true")).lower() in {"1", "true", "yes"})
        self.cb_srt.setChecked(str(settings.value("export_opt_fmt_srt", "false")).lower() in {"1", "true", "yes"})
        self.cb_vtt.setChecked(str(settings.value("export_opt_fmt_vtt", "false")).lower() in {"1", "true", "yes"})
        self.cb_cue.setChecked(str(settings.value("export_opt_fmt_cue", "false")).lower() in {"1", "true", "yes"})
        self.cb_tracklist.setChecked(str(settings.value("export_opt_fmt_tracklist", "false")).lower() in {"1", "true", "yes"})
        if self.cb_media.isEnabled():
            self.cb_media.setChecked(str(settings.value("export_opt_fmt_media", "false")).lower() in {"1", "true", "yes"})

        self.cb_speakers.setChecked(str(settings.value("export_opt_include_speakers", "true")).lower() in {"1", "true", "yes"})
        self.cb_timestamps.setChecked(str(settings.value("export_opt_include_timestamps", "false")).lower() in {"1", "true", "yes"})
        self.cb_notes.setChecked(str(settings.value("export_opt_include_notes", "true")).lower() in {"1", "true", "yes"})
        self.cb_en.setChecked(str(settings.value("export_opt_include_en", "true")).lower() in {"1", "true", "yes"})
        if self.cb_es.isEnabled():
            self.cb_es.setChecked(str(settings.value("export_opt_include_es", "false")).lower() in {"1", "true", "yes"})

        use_custom_loc = str(settings.value("export_opt_custom_loc_enabled", "false")).lower() in {"1", "true", "yes"}
        saved_custom_dir = str(settings.value("export_opt_custom_dir", "") or "").strip()
        if saved_custom_dir and os.path.isdir(saved_custom_dir):
            self.loc_custom_path_edit.setText(saved_custom_dir)
            if use_custom_loc:
                self.loc_radio_custom.setChecked(True)
        self._on_location_radio_toggled()

    def save_options_to_settings(self, as_default: bool = False):
        settings = QSettings(INTERNAL_APP_ID, INTERNAL_APP_ID)
        settings.setValue("export_opt_fmt_txt", self.cb_txt.isChecked())
        settings.setValue("export_opt_fmt_docx", self.cb_docx.isChecked())
        settings.setValue("export_opt_fmt_pdf", self.cb_pdf.isChecked())
        settings.setValue("export_opt_fmt_srt", self.cb_srt.isChecked())
        settings.setValue("export_opt_fmt_vtt", self.cb_vtt.isChecked())
        settings.setValue("export_opt_fmt_cue", self.cb_cue.isChecked())
        settings.setValue("export_opt_fmt_tracklist", self.cb_tracklist.isChecked())
        settings.setValue("export_opt_fmt_media", self.cb_media.isChecked())

        settings.setValue("export_opt_include_speakers", self.cb_speakers.isChecked())
        settings.setValue("export_opt_include_timestamps", self.cb_timestamps.isChecked())
        settings.setValue("export_opt_include_notes", self.cb_notes.isChecked())
        settings.setValue("export_opt_include_en", self.cb_en.isChecked())
        settings.setValue("export_opt_include_es", self.cb_es.isChecked())

        settings.setValue("export_opt_custom_loc_enabled", self.loc_radio_custom.isChecked())
        custom_dir = self.loc_custom_path_edit.text().strip()
        if custom_dir:
            settings.setValue("export_opt_custom_dir", custom_dir)

        settings.sync()
        if as_default:
            QMessageBox.information(self, "Export Options", "Current export options have been saved as defaults.")

    def _handle_accept(self):
        if self.radio_local.isChecked():
            if self.loc_radio_custom.isChecked():
                custom_path = self.loc_custom_path_edit.text().strip()
                if not custom_path or not os.path.isdir(custom_path):
                    QMessageBox.warning(self, "Export Location", "Please select a valid directory for the custom export location.")
                    return

            formats = {
                "txt": self.cb_txt.isChecked(),
                "docx": self.cb_docx.isChecked(),
                "pdf": self.cb_pdf.isChecked(),
                "srt": self.cb_srt.isChecked(),
                "vtt": self.cb_vtt.isChecked(),
                "media": self.cb_media.isChecked(),
                "cue": self.cb_cue.isChecked(),
                "tracklist": self.cb_tracklist.isChecked(),
            }
            if not any(formats.values()):
                QMessageBox.warning(self, "Export", "Please select at least one format to export.")
                return

            if (formats["txt"] or formats["docx"] or formats["pdf"]) and not self.cb_en.isChecked() and not self.cb_es.isChecked():
                QMessageBox.warning(self, "Export", "Please select at least one language track (English or Spanish).")
                return
        else:
            for radio, dest, _ in self._plugin_destinations:
                if radio.isChecked():
                    valid, err = dest.validate()
                    if not valid:
                        QMessageBox.warning(self, "Export", err or "Export validation failed.")
                        return
                    break

        self.accept()

    def get_result(self) -> Dict[str, Any]:
        scope = self.scope_combo.currentData()
        if self.radio_local.isChecked():
            formats = {
                "txt": self.cb_txt.isChecked(),
                "docx": self.cb_docx.isChecked(),
                "pdf": self.cb_pdf.isChecked(),
                "srt": self.cb_srt.isChecked(),
                "vtt": self.cb_vtt.isChecked(),
                "media": self.cb_media.isChecked(),
                "cue": self.cb_cue.isChecked(),
                "tracklist": self.cb_tracklist.isChecked(),
            }
            options = {
                "include_speakers": self.cb_speakers.isChecked(),
                "include_timestamps": self.cb_timestamps.isChecked(),
                "include_comments": self.cb_notes.isChecked(),
                "include_notes": self.cb_notes.isChecked(),
                "include_english": self.cb_en.isChecked(),
                "include_spanish": self.cb_es.isChecked(),
            }
            base = safe_filename(self.filename_edit.text().strip() or "export")
            export_dir = None
            if self.loc_radio_custom.isChecked() and self.loc_custom_path_edit.text().strip():
                export_dir = self.loc_custom_path_edit.text().strip()
            return {
                "destination": "local",
                "scope": scope,
                "formats": formats,
                "options": options,
                "base": base,
                "export_dir": export_dir,
            }

        for radio, dest, _ in self._plugin_destinations:
            if radio.isChecked():
                data = dest.get_export_data()
                return {
                    "destination": dest.id,
                    "scope": scope,
                    **data,
                }

        return {"destination": "local", "scope": scope}

    def done(self, r: int):
        if r != QDialog.DialogCode.Accepted:
            for temp_f in self._temp_preview_files:
                try:
                    if temp_f and Path(temp_f).exists():
                        Path(temp_f).unlink(missing_ok=True)
                except Exception:
                    pass
        super().done(r)
