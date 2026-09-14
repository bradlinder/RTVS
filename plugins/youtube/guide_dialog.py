"""Interactive Assisted Upload Guide Dialog for YouTube Studio."""
from __future__ import annotations

import html
import os
import webbrowser
from pathlib import Path
from typing import Dict, Optional

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
)


class YouTubeAssistedUploadGuideDialog(QDialog):
    """Post-export interactive guide dialog for YouTube Studio Assisted Publishing."""

    def __init__(self, parent, files_dict: Dict[str, str], metadata: Dict[str, str]):
        super().__init__(parent)
        self.files_dict = files_dict
        self.metadata = metadata
        self.video_title = metadata.get("title", "")
        self.description = metadata.get("description", "")
        self.tags = metadata.get("tags", "")

        self.setWindowTitle("YouTube Studio Assisted Upload - Ready to Upload")
        self.setMinimumWidth(640)
        self.resize(700, 520)

        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        header = QGroupBox()
        h_layout = QVBoxLayout(header)
        banner_title = QLabel("<b>YouTube Studio Assisted Upload Ready!</b>")
        banner_title.setStyleSheet("font-size: 14px; color: #38bdf8;")
        banner_desc = QLabel(
            "Your media file, interactive chapters, thumbnail image, and subtitles have been generated and packaged. "
            "Follow the steps below to upload directly to YouTube Studio in seconds."
        )
        banner_desc.setStyleSheet("color: #cbd5e1; font-size: 12px;")
        banner_desc.setWordWrap(True)
        h_layout.addWidget(banner_title)
        h_layout.addWidget(banner_desc)
        layout.addWidget(header)

        # Exported Files Box
        files_box = QGroupBox("Exported Files")
        fb_layout = QVBoxLayout(files_box)
        fb_layout.setSpacing(5)
        for label, path in files_dict.items():
            if path:
                row = QLabel(f"<b>{label}:</b> <code style='color: #38bdf8;'>{html.escape(str(path))}</code>")
                row.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
                fb_layout.addWidget(row)
        layout.addWidget(files_box)

        # Clipboard Notice
        clip_notice = QLabel("📋 <b>Video Title, Description & Chapters have been copied to your clipboard!</b>")
        clip_notice.setStyleSheet("color: #38bdf8; font-size: 12px; font-weight: bold;")
        layout.addWidget(clip_notice)

        # Step by step guide
        guide_box = QGroupBox("Step-by-Step Instructions")
        guide_layout = QVBoxLayout(guide_box)
        guide_layout.setSpacing(6)

        steps = (
            "<b>1. Open YouTube Studio:</b> Click <i>Open YouTube Studio</i> below or visit <b>studio.youtube.com</b>.<br>"
            "<b>2. Upload Media:</b> In YouTube Studio, click <b>CREATE > Upload videos</b> and drag in your video file.<br>"
            "<b>3. Description & Chapters:</b> Paste (Ctrl+V / Cmd+V) into the description field. Chapter timestamps starting at 00:00 will automatically create interactive video chapters.<br>"
            "<b>4. Thumbnail:</b> Under the Thumbnail section, click <i>Upload thumbnail</i> and choose your exported thumbnail image.<br>"
            "<b>5. Tags:</b> Click <i>SHOW MORE</i>, find <i>Tags</i>, and click <i>Copy Tags</i> below to paste them.<br>"
            "<b>6. Subtitles:</b> In the <i>Video elements</i> tab, click <i>Add subtitles</i> and upload the exported .srt file.<br>"
            "<b>7. Visibility:</b> Set to Unlisted or Public and click <b>Publish</b>."
        )
        lbl_steps = QLabel(steps)
        lbl_steps.setWordWrap(True)
        lbl_steps.setStyleSheet("font-size: 12px; line-height: 1.45;")
        guide_layout.addWidget(lbl_steps)
        layout.addWidget(guide_box)

        # Action Buttons
        btn_box = QHBoxLayout()
        copy_desc_btn = QPushButton("Copy Description & Chapters")
        copy_desc_btn.clicked.connect(self._copy_description)
        copy_title_btn = QPushButton("Copy Title")
        copy_title_btn.clicked.connect(self._copy_title)
        copy_tags_btn = QPushButton("Copy Tags")
        copy_tags_btn.clicked.connect(self._copy_tags)

        open_browser_btn = QPushButton("Open YouTube Studio")
        open_browser_btn.setStyleSheet("font-weight: bold; background-color: #dc2626; color: white; padding: 5px 12px;")
        open_browser_btn.clicked.connect(self._open_youtube_studio)

        open_folder_btn = QPushButton("Open Export Folder")
        open_folder_btn.clicked.connect(self._open_folder)

        btn_box.addWidget(copy_desc_btn)
        btn_box.addWidget(copy_title_btn)
        btn_box.addWidget(copy_tags_btn)
        btn_box.addStretch()
        btn_box.addWidget(open_browser_btn)
        btn_box.addWidget(open_folder_btn)
        layout.addLayout(btn_box)

        # Close
        close_box = QHBoxLayout()
        close_box.addStretch()
        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.accept)
        close_box.addWidget(close_btn)
        layout.addLayout(close_box)

    def _copy_description(self):
        QApplication.clipboard().setText(self.description)
        QMessageBox.information(self, "Copied", "Description and chapter markers copied to clipboard!")

    def _copy_title(self):
        QApplication.clipboard().setText(self.video_title)
        QMessageBox.information(self, "Copied", "Video title copied to clipboard!")

    def _copy_tags(self):
        QApplication.clipboard().setText(self.tags)
        QMessageBox.information(self, "Copied", "Tags copied to clipboard!")

    def _open_youtube_studio(self):
        webbrowser.open("https://studio.youtube.com/channel/UC/videos/upload?d=ud")

    def _open_folder(self):
        folder = None
        for p in self.files_dict.values():
            if p and os.path.exists(p):
                folder = str(Path(p).parent)
                break
        if folder:
            QDesktopServices.openUrl(QUrl.fromLocalFile(folder))
