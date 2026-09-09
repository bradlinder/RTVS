"""WordPress Publisher Plugin for Radio & TV Segmenter.

Allows direct publishing of audio/video stories to WordPress with
custom excerpt, author assignment, categories, and custom featured image
(local file or video frame grab at playhead/story timestamp).
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, Callable, List, Optional

from PySide6.QtCore import Qt, QThread, Signal, QObject
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QMessageBox,
    QGroupBox,
    QFormLayout,
    QComboBox,
    QTextEdit,
    QFileDialog,
    QRadioButton,
    QButtonGroup,
    QProgressBar,
    QWidget,
)

from prs_shared import (
    INTERNAL_APP_ID,
    PROJECT_VERSION,
    QSettings,
    ffmpeg_path,
    format_time,
    safe_filename,
)
from plugins.base import BasePlugin, PluginManifest
from wordpress_export import (
    WordPressClient,
    _get_wp_password,
    _set_wp_password,
    generate_wp_excerpt,
)


def capture_video_frame(video_path: str, timestamp: float, output_path: str) -> bool:
    """Extract a high quality single frame from a video using fast seeking FFmpeg."""
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


class WordPressPublishDialog(QDialog):
    """Publish a story or project to WordPress with featured image selection."""

    def __init__(self, plugin: Plugin, parent: Any = None, story: Any = None):
        super().__init__(parent)
        self.plugin = plugin
        self.app = plugin.app
        self.story = story
        self.settings = QSettings(INTERNAL_APP_ID, INTERNAL_APP_ID)
        self.temp_dir = tempfile.mkdtemp(prefix="rtvs_wp_")
        self.captured_frame_path: Optional[str] = None
        self.custom_image_path: Optional[str] = None

        self.setWindowTitle("Publish Story to WordPress")
        self.setMinimumSize(640, 580)
        self.setup_ui()
        self.load_metadata()

    def setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        # Connection info header
        site_url = str(self.settings.value("wp_site_url", "") or "").rstrip("/")
        username = str(self.settings.value("wp_username", "") or "")
        header_text = f"<b>WordPress Site:</b> {site_url or '<i>Not configured</i>'} ({username or 'No user'})"
        self.conn_label = QLabel(header_text)
        layout.addWidget(self.conn_label)

        # Post fields
        post_group = QGroupBox("Post Details")
        form = QFormLayout(post_group)

        self.title_edit = QLineEdit()
        form.addRow("Title:", self.title_edit)

        self.excerpt_edit = QTextEdit()
        self.excerpt_edit.setMaximumHeight(70)
        form.addRow("Excerpt:", self.excerpt_edit)

        self.status_combo = QComboBox()
        self.status_combo.addItem("Draft", "draft")
        self.status_combo.addItem("Pending Review", "pending")
        self.status_combo.addItem("Publish Immediately", "publish")
        form.addRow("Status:", self.status_combo)

        layout.addWidget(post_group)

        # Featured Image Group
        img_group = QGroupBox("Featured Image (Thumbnail)")
        img_layout = QVBoxLayout(img_group)

        self.img_button_group = QButtonGroup(self)
        self.rad_no_img = QRadioButton("No featured image")
        self.rad_frame_grab = QRadioButton("Grab frame from video at current position")
        self.rad_file_img = QRadioButton("Choose image file from computer...")

        self.img_button_group.addButton(self.rad_no_img)
        self.img_button_group.addButton(self.rad_frame_grab)
        self.img_button_group.addButton(self.rad_file_img)

        img_layout.addWidget(self.rad_no_img)
        img_layout.addWidget(self.rad_frame_grab)
        img_layout.addWidget(self.rad_file_img)

        # Preview preview & picker row
        picker_row = QHBoxLayout()
        self.file_path_label = QLabel("No file selected")
        self.file_path_label.setStyleSheet("color: #64748b; font-size: 11px;")
        self.browse_btn = QPushButton("Browse...")
        self.browse_btn.clicked.connect(self.on_browse_image)
        self.browse_btn.setEnabled(False)
        picker_row.addWidget(self.browse_btn)
        picker_row.addWidget(self.file_path_label, stretch=1)
        img_layout.addLayout(picker_row)

        self.preview_label = QLabel()
        self.preview_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview_label.setFixedHeight(120)
        self.preview_label.setStyleSheet("background: #1e293b; border-radius: 6px; border: 1px solid #334155;")
        self.preview_label.setText("No Image Preview")
        img_layout.addWidget(self.preview_label)

        # Logic for radio toggles
        has_video = bool(getattr(self.app, "current_media_is_video", False) and getattr(self.app, "audio_file", None))
        self.rad_frame_grab.setEnabled(has_video)
        if has_video:
            self.rad_frame_grab.setChecked(True)
        else:
            self.rad_no_img.setChecked(True)

        self.rad_no_img.toggled.connect(self.on_image_mode_changed)
        self.rad_frame_grab.toggled.connect(self.on_image_mode_changed)
        self.rad_file_img.toggled.connect(self.on_image_mode_changed)

        layout.addWidget(img_group)

        # Progress bar
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        layout.addWidget(self.progress_bar)

        # Buttons
        btn_layout = QHBoxLayout()
        self.config_btn = QPushButton("Configure Credentials...")
        self.config_btn.clicked.connect(self.on_configure_credentials)
        btn_layout.addWidget(self.config_btn)

        btn_layout.addStretch()

        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(self.cancel_btn)

        self.publish_btn = QPushButton("Publish Post")
        self.publish_btn.setStyleSheet("font-weight: bold; background-color: #2563eb; color: white; padding: 6px 16px;")
        self.publish_btn.clicked.connect(self.on_publish)
        btn_layout.addWidget(self.publish_btn)

        layout.addLayout(btn_layout)

    def load_metadata(self):
        title = ""
        content = ""
        timestamp = 0.0

        if self.story:
            title = getattr(self.story, "title", "Untitled Story")
            start = getattr(self.story, "start", 0.0)
            end = getattr(self.story, "end", 0.0)
            timestamp = start
            if hasattr(self.app, "get_story_transcript"):
                content = self.app.get_story_transcript(self.story)
            elif hasattr(self.app, "transcript"):
                content = str(self.app.transcript)
        elif hasattr(self.app, "stories") and self.app.stories:
            sel_indices = getattr(self.app, "current_selected_story_indices", [])
            idx = sel_indices[0] if sel_indices else 0
            if 0 <= idx < len(self.app.stories):
                st = self.app.stories[idx]
                title = st.title
                timestamp = st.start
                if hasattr(self.app, "get_story_transcript"):
                    content = self.app.get_story_transcript(st)

        if not title and hasattr(self.app, "audio_file") and self.app.audio_file:
            title = Path(self.app.audio_file).stem

        self.title_edit.setText(title)
        self.excerpt_edit.setText(generate_wp_excerpt(content))
        self.target_timestamp = timestamp

        if self.rad_frame_grab.isChecked():
            self.do_capture_frame()

    def do_capture_frame(self):
        media_file = getattr(self.app, "audio_file", None)
        if not media_file or not Path(media_file).exists():
            return
        out = os.path.join(self.temp_dir, "frame_grab.jpg")
        pos = getattr(self.app, "current_position", self.target_timestamp)
        if capture_video_frame(str(media_file), pos, out):
            self.captured_frame_path = out
            pix = QPixmap(out).scaled(200, 110, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
            self.preview_label.setPixmap(pix)
            self.rad_frame_grab.setText(f"Grab frame from video (at {format_time(pos)})")

    def on_image_mode_changed(self):
        if self.rad_no_img.isChecked():
            self.browse_btn.setEnabled(False)
            self.preview_label.clear()
            self.preview_label.setText("No Featured Image")
        elif self.rad_frame_grab.isChecked():
            self.browse_btn.setEnabled(False)
            self.do_capture_frame()
        elif self.rad_file_img.isChecked():
            self.browse_btn.setEnabled(True)
            if self.custom_image_path and Path(self.custom_image_path).exists():
                pix = QPixmap(self.custom_image_path).scaled(200, 110, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
                self.preview_label.setPixmap(pix)
            else:
                self.preview_label.clear()
                self.preview_label.setText("Click Browse to select image file")

    def on_browse_image(self):
        fn, _ = QFileDialog.getOpenFileName(
            self,
            "Select Featured Image",
            "",
            "Image Files (*.jpg *.jpeg *.png *.webp);;All Files (*.*)",
        )
        if fn:
            self.custom_image_path = fn
            self.file_path_label.setText(Path(fn).name)
            pix = QPixmap(fn).scaled(200, 110, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
            self.preview_label.setPixmap(pix)

    def on_configure_credentials(self):
        from wordpress_export import WordPressSettingsDialog
        dlg = WordPressSettingsDialog(self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            site_url = str(self.settings.value("wp_site_url", "") or "").rstrip("/")
            username = str(self.settings.value("wp_username", "") or "")
            self.conn_label.setText(f"<b>WordPress Site:</b> {site_url} ({username})")

    def on_publish(self):
        site_url = str(self.settings.value("wp_site_url", "") or "").rstrip("/")
        username = str(self.settings.value("wp_username", "") or "")
        password = _get_wp_password(username)

        if not site_url or not username or not password:
            QMessageBox.warning(
                self,
                "WordPress Not Configured",
                "Please configure your WordPress Site URL, Username, and Application Password first.",
            )
            self.on_configure_credentials()
            return

        client = WordPressClient(site_url, username, password)

        # Image to upload
        img_to_upload: Optional[str] = None
        if self.rad_frame_grab.isChecked() and self.captured_frame_path:
            img_to_upload = self.captured_frame_path
        elif self.rad_file_img.isChecked() and self.custom_image_path:
            img_to_upload = self.custom_image_path

        self.publish_btn.setEnabled(False)
        self.progress_bar.setVisible(True)
        self.progress_bar.setRange(0, 0)  # indeterminate

        title = self.title_edit.text().strip() or "Untitled Story"
        excerpt = self.excerpt_edit.toPlainText().strip()
        status = self.status_combo.currentData() or "draft"

        # Content
        content = ""
        if self.story and hasattr(self.app, "get_story_transcript"):
            content = self.app.get_story_transcript(self.story)
        elif hasattr(self.app, "transcript_view") and hasattr(self.app.transcript_view, "toPlainText"):
            content = self.app.transcript_view.toPlainText()

        # Format content with paragraphs
        if content:
            paras = [f"<p>{p.strip()}</p>" for p in content.split("\n\n") if p.strip()]
            formatted_content = "\n".join(paras) if paras else f"<p>{content}</p>"
        else:
            formatted_content = "<p></p>"

        # Run background publish
        worker = WordPressPublishWorker(client, title, formatted_content, excerpt, status, img_to_upload)
        worker.finished_signal.connect(self.on_publish_finished)
        self._worker_thread = worker
        worker.start()

    def on_publish_finished(self, success: bool, msg: str, post_data: Any):
        self.publish_btn.setEnabled(True)
        self.progress_bar.setVisible(False)
        if success:
            post_id = post_data.get("id") if isinstance(post_data, dict) else None
            post_link = post_data.get("link") if isinstance(post_data, dict) else ""
            
            # Save post ID in story metadata for backward & forward compatibility
            if self.story and post_id:
                if not hasattr(self.story, "metadata") or not isinstance(self.story.metadata, dict):
                    self.story.metadata = {}
                self.story.metadata["wp_post_id"] = post_id
                self.story.metadata["wp_post_link"] = post_link
                if hasattr(self.app, "save_project"):
                    self.app.save_project(force=False)

            info = f"Story successfully published to WordPress!\n\nPost ID: {post_id}\nStatus: {post_data.get('status', 'draft')}"
            if post_link:
                info += f"\nURL: {post_link}"
            QMessageBox.information(self, "Published Successfully", info)
            self.accept()
        else:
            QMessageBox.critical(self, "Publishing Error", f"Failed to publish to WordPress:\n\n{msg}")

    def closeEvent(self, event):
        try:
            shutil.rmtree(self.temp_dir, ignore_errors=True)
        except Exception:
            pass
        super().closeEvent(event)


class WordPressPublishWorker(QThread):
    finished_signal = Signal(bool, str, object)

    def __init__(self, client: WordPressClient, title: str, content: str, excerpt: str, status: str, image_path: Optional[str]):
        super().__init__()
        self.client = client
        self.title = title
        self.content = content
        self.excerpt = excerpt
        self.status = status
        self.image_path = image_path

    def run(self):
        try:
            featured_media_id = None
            if self.image_path and Path(self.image_path).exists():
                upload_res = self.client.upload_media(self.image_path)
                featured_media_id = upload_res.get("id")

            # Create post
            post_res = self.client.create_post(
                title=self.title,
                content=self.content,
                excerpt=self.excerpt,
                status=self.status,
            )

            # If featured media was uploaded, attach it
            if featured_media_id and post_res.get("id"):
                import requests
                post_id = post_res["id"]
                url = f"{self.client.api_base}/posts/{post_id}"
                requests.post(url, auth=self.client._get_auth(), json={"featured_media": featured_media_id}, timeout=20)
                post_res["featured_media"] = featured_media_id

            self.finished_signal.emit(True, "Success", post_res)
        except Exception as exc:
            self.finished_signal.emit(False, str(exc), None)


class Plugin(BasePlugin):
    """WordPress Plugin implementation hooking into RTVS."""

    def on_load(self) -> bool:
        return True

    def get_export_actions(self) -> List[tuple[str, Callable]]:
        return [
            ("Publish to WordPress...", self.open_publish_dialog),
        ]

    def get_preferences_widget(self, parent: Any = None) -> Any:
        from wordpress_export import WordPressSettingsDialog
        # Return settings sub-widget
        box = QGroupBox("WordPress Publishing", parent)
        layout = QVBoxLayout(box)
        lbl = QLabel("Configure WordPress REST API endpoint, username, and application password.")
        layout.addWidget(lbl)
        btn = QPushButton("Configure WordPress Credentials...")
        btn.clicked.connect(lambda: WordPressSettingsDialog(parent or self.app).exec())
        layout.addWidget(btn)
        return box

    def open_publish_dialog(self):
        dlg = WordPressPublishDialog(self, parent=self.app)
        dlg.exec()
