"""YouTube Video Publisher Plugin for Radio & TV Segmenter.

Allows uploading segmented broadcast stories or full programs to YouTube with:
- Automated chapter timestamps generated from story boundaries
- Custom video thumbnails (local file or video frame grab at playhead)
- Tags, categories, and privacy status (private, unlisted, public)
- Secure OAuth 2.0 with PKCE and OS keyring storage
- Resumable chunked upload with real-time progress reporting
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
import secrets
import shutil
import subprocess
import sys
import tempfile
import threading
import urllib.parse
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

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
    QCheckBox,
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


def _get_keyring():
    try:
        import keyring
        return keyring
    except Exception:
        return None


def get_stored_refresh_token() -> str:
    kr = _get_keyring()
    if kr is not None:
        try:
            token = kr.get_password(INTERNAL_APP_ID, "youtube_refresh_token")
            if token:
                return token
        except Exception:
            pass
    settings = QSettings(INTERNAL_APP_ID, INTERNAL_APP_ID)
    return str(settings.value("youtube_refresh_token", "") or "")


def set_stored_refresh_token(token: str) -> None:
    kr = _get_keyring()
    saved = False
    if kr is not None:
        try:
            kr.set_password(INTERNAL_APP_ID, "youtube_refresh_token", token)
            saved = True
        except Exception:
            pass
    settings = QSettings(INTERNAL_APP_ID, INTERNAL_APP_ID)
    if not saved:
        settings.setValue("youtube_refresh_token", token)
    else:
        settings.remove("youtube_refresh_token")
    settings.sync()


class OAuthCallbackHandler(BaseHTTPRequestHandler):
    """Temporary local HTTP handler catching Google OAuth redirect."""
    server: OAuthServer

    def do_GET(self):
        query = urllib.parse.urlparse(self.path).query
        params = urllib.parse.parse_qs(query)
        code = params.get("code", [None])[0]
        error = params.get("error", [None])[0]

        if code:
            self.server.auth_code = code
            body = (
                "<html><body style='font-family: sans-serif; text-align: center; padding: 50px; background: #0f172a; color: #f8fafc;'>"
                "<h2>Authorization Successful!</h2>"
                "<p>You can now close this browser tab and return to Radio & TV Segmenter.</p>"
                "</body></html>"
            )
            self.send_response(200)
        else:
            self.server.auth_error = error or "Unknown authorization failure"
            body = f"<html><body><h2>Authorization Failed</h2><p>{self.server.auth_error}</p></body></html>"
            self.send_response(400)

        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(body.encode("utf-8"))

    def log_message(self, format, *args):
        pass  # Suppress console HTTP logging


class OAuthServer(HTTPServer):
    def __init__(self, server_address, RequestHandlerClass):
        super().__init__(server_address, RequestHandlerClass)
        self.auth_code: Optional[str] = None
        self.auth_error: Optional[str] = None


class YouTubeOAuthManager:
    """Manages YouTube Data API v3 OAuth 2.0 PKCE authentication flow."""

    AUTH_URI = "https://accounts.google.com/o/oauth2/v2/auth"
    TOKEN_URI = "https://oauth2.googleapis.com/token"
    SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]

    def __init__(self):
        self.settings = QSettings(INTERNAL_APP_ID, INTERNAL_APP_ID)

    def get_client_credentials(self) -> tuple[str, str]:
        cid = str(self.settings.value("youtube_client_id", "") or "").strip()
        csecret = str(self.settings.value("youtube_client_secret", "") or "").strip()
        return cid, csecret

    def is_authenticated(self) -> bool:
        cid, _ = self.get_client_credentials()
        rtoken = get_stored_refresh_token()
        return bool(cid and rtoken)

    def run_pkce_flow(self, parent_widget=None) -> tuple[bool, str]:
        import requests
        client_id, client_secret = self.get_client_credentials()
        if not client_id:
            return False, "Google Cloud OAuth Client ID is required."

        # Generate PKCE verifier & challenge
        verifier = secrets.token_urlsafe(64)
        challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode("utf-8")).digest()).decode("utf-8").rstrip("=")

        # Start ephemeral loopback server
        server = OAuthServer(("127.0.0.1", 0), OAuthCallbackHandler)
        port = server.server_port
        redirect_uri = f"http://127.0.0.1:{port}"

        params = {
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "scope": " ".join(self.SCOPES),
            "code_challenge": challenge,
            "code_challenge_method": "S256",
            "access_type": "offline",
            "prompt": "consent",
        }
        auth_url = f"{self.AUTH_URI}?{urllib.parse.urlencode(params)}"

        # Open web browser
        webbrowser.open(auth_url)

        # Wait for callback in thread or handle single request
        server.timeout = 120  # 2 minutes timeout
        server.handle_request()

        if not server.auth_code:
            err = server.auth_error or "Authentication timed out or was cancelled."
            return False, err

        # Exchange code for tokens
        token_data = {
            "client_id": client_id,
            "client_secret": client_secret,
            "code": server.auth_code,
            "code_verifier": verifier,
            "grant_type": "authorization_code",
            "redirect_uri": redirect_uri,
        }
        try:
            resp = requests.post(self.TOKEN_URI, data=token_data, timeout=20)
            if resp.status_code != 200:
                return False, f"Token exchange failed (HTTP {resp.status_code}): {resp.text}"
            res_json = resp.json()
            refresh_token = res_json.get("refresh_token")
            if refresh_token:
                set_stored_refresh_token(refresh_token)
            return True, "Successfully authorized with YouTube!"
        except Exception as exc:
            return False, f"Error communicating with Google OAuth: {exc}"

    def get_access_token(self) -> tuple[Optional[str], str]:
        import requests
        client_id, client_secret = self.get_client_credentials()
        refresh_token = get_stored_refresh_token()
        if not client_id or not refresh_token:
            return None, "Not authenticated with YouTube."

        data = {
            "client_id": client_id,
            "client_secret": client_secret,
            "refresh_token": refresh_token,
            "grant_type": "refresh_token",
        }
        try:
            resp = requests.post(self.TOKEN_URI, data=data, timeout=20)
            if resp.status_code == 200:
                return resp.json().get("access_token"), "OK"
            return None, f"Failed to refresh YouTube token (HTTP {resp.status_code}): {resp.text}"
        except Exception as exc:
            return None, f"Network error during token refresh: {exc}"


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


class YouTubeSettingsDialog(QDialog):
    """Dialog to configure Google Cloud OAuth credentials for YouTube API."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.oauth_mgr = YouTubeOAuthManager()
        self.setWindowTitle("YouTube API Configuration")
        self.setMinimumSize(540, 360)
        self.setup_ui()

    def setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        info = QLabel(
            "<b>YouTube Data API Setup</b><br>"
            "<span style='color: #64748b; font-size: 12px;'>"
            "To publish videos directly to YouTube, provide an OAuth 2.0 Client ID for a 'Desktop App' "
            "from the Google Cloud Console with YouTube Data API v3 enabled.</span>"
        )
        info.setWordWrap(True)
        layout.addWidget(info)

        form_group = QGroupBox("Google Cloud Credentials")
        form = QFormLayout(form_group)

        cid, csecret = self.oauth_mgr.get_client_credentials()
        self.cid_edit = QLineEdit(cid)
        self.csecret_edit = QLineEdit(csecret)
        self.csecret_edit.setEchoMode(QLineEdit.EchoMode.Password)

        form.addRow("Client ID:", self.cid_edit)
        form.addRow("Client Secret (optional):", self.csecret_edit)
        layout.addWidget(form_group)

        # Status & Auth button
        auth_group = QGroupBox("Account Authorization")
        auth_layout = QVBoxLayout(auth_group)

        self.auth_status_label = QLabel()
        self.update_auth_status()
        auth_layout.addWidget(self.auth_status_label)

        self.login_btn = QPushButton("Sign in with Google...")
        self.login_btn.clicked.connect(self.on_login_clicked)
        auth_layout.addWidget(self.login_btn)

        layout.addWidget(auth_group)

        # Buttons
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        close_btn = QPushButton("Save & Close")
        close_btn.clicked.connect(self.on_save)
        btn_layout.addWidget(close_btn)

        layout.addLayout(btn_layout)

    def update_auth_status(self):
        if self.oauth_mgr.is_authenticated():
            self.auth_status_label.setText("<span style='color: #22c55e;'>✔ Connected to YouTube</span>")
        else:
            self.auth_status_label.setText("<span style='color: #f59e0b;'>⚠ Not connected</span>")

    def on_login_clicked(self):
        cid = self.cid_edit.text().strip()
        csecret = self.csecret_edit.text().strip()
        if not cid:
            QMessageBox.warning(self, "Missing Client ID", "Please enter your Google OAuth Client ID first.")
            return

        settings = QSettings(INTERNAL_APP_ID, INTERNAL_APP_ID)
        settings.setValue("youtube_client_id", cid)
        settings.setValue("youtube_client_secret", csecret)
        settings.sync()

        ok, msg = self.oauth_mgr.run_pkce_flow(self)
        if ok:
            QMessageBox.information(self, "Authorization Successful", msg)
        else:
            QMessageBox.warning(self, "Authorization Failed", msg)
        self.update_auth_status()

    def on_save(self):
        settings = QSettings(INTERNAL_APP_ID, INTERNAL_APP_ID)
        settings.setValue("youtube_client_id", self.cid_edit.text().strip())
        settings.setValue("youtube_client_secret", self.csecret_edit.text().strip())
        settings.sync()
        self.accept()


class YouTubeUploadWorker(QThread):
    progress_signal = Signal(int, str)  # percent, status message
    finished_signal = Signal(bool, str, str)  # success, video_id, error_or_url

    def __init__(
        self,
        oauth_mgr: YouTubeOAuthManager,
        video_path: str,
        title: str,
        description: str,
        tags: List[str],
        category_id: str,
        privacy_status: str,
        thumbnail_path: Optional[str],
    ):
        super().__init__()
        self.oauth_mgr = oauth_mgr
        self.video_path = video_path
        self.title = title
        self.description = description
        self.tags = tags
        self.category_id = category_id
        self.privacy_status = privacy_status
        self.thumbnail_path = thumbnail_path
        self._is_cancelled = False

    def cancel(self):
        self._is_cancelled = True

    def run(self):
        import requests
        token, err = self.oauth_mgr.get_access_token()
        if not token:
            self.finished_signal.emit(False, "", f"Authentication error: {err}")
            return

        video_file = Path(self.video_path)
        if not video_file.exists():
            self.finished_signal.emit(False, "", f"Video file not found: {self.video_path}")
            return

        total_size = video_file.stat().st_size

        # 1. Initialize Resumable Upload session
        self.progress_signal.emit(5, "Initializing YouTube resumable upload...")
        init_url = "https://www.googleapis.com/upload/youtube/v3/videos?uploadType=resumable&part=snippet,status"
        metadata = {
            "snippet": {
                "title": self.title,
                "description": self.description,
                "tags": self.tags,
                "categoryId": self.category_id,
            },
            "status": {
                "privacyStatus": self.privacy_status,
                "selfDeclaredMadeForKids": False,
            },
        }

        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json; charset=UTF-8",
            "X-Upload-Content-Length": str(total_size),
            "X-Upload-Content-Type": "video/*",
        }

        try:
            init_resp = requests.post(init_url, headers=headers, json=metadata, timeout=30)
            if init_resp.status_code != 200:
                self.finished_signal.emit(False, "", f"Failed to initiate YouTube upload (HTTP {init_resp.status_code}): {init_resp.text[:300]}")
                return

            upload_url = init_resp.headers.get("Location")
            if not upload_url:
                self.finished_signal.emit(False, "", "YouTube did not provide a resumable upload URL.")
                return

            # 2. Upload video in 8 MB chunks
            chunk_size = 8 * 1024 * 1024  # 8 MB
            uploaded_bytes = 0
            video_id = ""

            with open(video_file, "rb") as f:
                while uploaded_bytes < total_size:
                    if self._is_cancelled:
                        self.finished_signal.emit(False, "", "Upload cancelled by user.")
                        return

                    chunk = f.read(chunk_size)
                    chunk_len = len(chunk)
                    start_byte = uploaded_bytes
                    end_byte = start_byte + chunk_len - 1

                    chunk_headers = {
                        "Authorization": f"Bearer {token}",
                        "Content-Length": str(chunk_len),
                        "Content-Range": f"bytes {start_byte}-{end_byte}/{total_size}",
                    }

                    put_resp = requests.put(upload_url, headers=chunk_headers, data=chunk, timeout=60)
                    uploaded_bytes += chunk_len
                    pct = int(10 + (uploaded_bytes / total_size) * 80)
                    mb_done = uploaded_bytes / (1024 * 1024)
                    mb_total = total_size / (1024 * 1024)
                    self.progress_signal.emit(pct, f"Uploading video... {mb_done:.1f} / {mb_total:.1f} MB ({pct}%)")

                    if put_resp.status_code in (200, 201):
                        res_json = put_resp.json()
                        video_id = res_json.get("id", "")
                        break
                    elif put_resp.status_code != 308:
                        self.finished_signal.emit(False, "", f"Upload chunk failed (HTTP {put_resp.status_code}): {put_resp.text[:300]}")
                        return

            if not video_id:
                self.finished_signal.emit(False, "", "YouTube upload finished without returning a video ID.")
                return

            # 3. Upload custom thumbnail if requested
            if self.thumbnail_path and Path(self.thumbnail_path).exists():
                self.progress_signal.emit(95, "Uploading custom thumbnail...")
                thumb_url = f"https://www.googleapis.com/upload/youtube/v3/thumbnails/set?videoId={video_id}"
                with open(self.thumbnail_path, "rb") as tf:
                    t_resp = requests.post(
                        thumb_url,
                        headers={"Authorization": f"Bearer {token}", "Content-Type": "image/jpeg"},
                        data=tf,
                        timeout=30,
                    )
                    if t_resp.status_code not in (200, 201):
                        print(f"[YOUTUBE] Thumbnail upload warning (HTTP {t_resp.status_code}): {t_resp.text}")

            video_url = f"https://youtu.be/{video_id}"
            self.progress_signal.emit(100, "Upload completed successfully!")
            self.finished_signal.emit(True, video_id, video_url)

        except Exception as exc:
            self.finished_signal.emit(False, "", f"Upload error: {exc}")


class YouTubePublishDialog(QDialog):
    """Dialog for publishing video to YouTube with chapter markers and thumbnails."""

    def __init__(self, plugin: Plugin, parent=None, story=None):
        super().__init__(parent)
        self.plugin = plugin
        self.app = plugin.app
        self.story = story
        self.oauth_mgr = YouTubeOAuthManager()
        self.temp_dir = tempfile.mkdtemp(prefix="rtvs_yt_")
        self.captured_frame_path: Optional[str] = None
        self.custom_image_path: Optional[str] = None
        self._worker: Optional[YouTubeUploadWorker] = None

        self.setWindowTitle("Publish Video to YouTube")
        self.setMinimumSize(660, 620)
        self.setup_ui()
        self.load_project_data()

    def setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        # Connection Header
        conn_row = QHBoxLayout()
        self.status_label = QLabel()
        self.update_conn_status()
        conn_row.addWidget(self.status_label, stretch=1)

        cfg_btn = QPushButton("Configure YouTube Credentials...")
        cfg_btn.clicked.connect(self.on_open_config)
        conn_row.addWidget(cfg_btn)
        layout.addLayout(conn_row)

        # Video Metadata Group
        meta_group = QGroupBox("Video Information")
        form = QFormLayout(meta_group)

        self.title_edit = QLineEdit()
        form.addRow("Title:", self.title_edit)

        self.desc_edit = QTextEdit()
        self.desc_edit.setMinimumHeight(120)
        form.addRow("Description:", self.desc_edit)

        self.tags_edit = QLineEdit()
        self.tags_edit.setPlaceholderText("broadcast, news, segment (comma-separated)")
        form.addRow("Tags:", self.tags_edit)

        self.privacy_combo = QComboBox()
        self.privacy_combo.addItem("Unlisted (Recommended for review)", "unlisted")
        self.privacy_combo.addItem("Private", "private")
        self.privacy_combo.addItem("Public", "public")
        form.addRow("Privacy:", self.privacy_combo)

        self.category_combo = QComboBox()
        self.category_combo.addItem("News & Politics (25)", "25")
        self.category_combo.addItem("People & Blogs (22)", "22")
        self.category_combo.addItem("Education (27)", "27")
        self.category_combo.addItem("Entertainment (24)", "24")
        form.addRow("Category:", self.category_combo)

        layout.addWidget(meta_group)

        # Custom Thumbnail Group
        thumb_group = QGroupBox("Video Thumbnail")
        thumb_layout = QVBoxLayout(thumb_group)

        self.thumb_button_group = QButtonGroup(self)
        self.rad_auto_thumb = QRadioButton("YouTube auto-generated thumbnail")
        self.rad_frame_grab = QRadioButton("Grab frame from video at playhead")
        self.rad_file_thumb = QRadioButton("Choose image file from disk...")

        self.thumb_button_group.addButton(self.rad_auto_thumb)
        self.thumb_button_group.addButton(self.rad_frame_grab)
        self.thumb_button_group.addButton(self.rad_file_thumb)

        thumb_layout.addWidget(self.rad_auto_thumb)
        thumb_layout.addWidget(self.rad_frame_grab)
        thumb_layout.addWidget(self.rad_file_thumb)

        pick_row = QHBoxLayout()
        self.browse_btn = QPushButton("Browse Image...")
        self.browse_btn.clicked.connect(self.on_browse_thumb)
        self.browse_btn.setEnabled(False)
        self.thumb_path_label = QLabel("No file selected")
        self.thumb_path_label.setStyleSheet("color: #64748b; font-size: 11px;")
        pick_row.addWidget(self.browse_btn)
        pick_row.addWidget(self.thumb_path_label, stretch=1)
        thumb_layout.addLayout(pick_row)

        self.preview_label = QLabel("No Thumbnail Preview")
        self.preview_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview_label.setFixedHeight(120)
        self.preview_label.setStyleSheet("background: #1e293b; border-radius: 6px; border: 1px solid #334155;")
        thumb_layout.addWidget(self.preview_label)

        has_video = bool(getattr(self.app, "current_media_is_video", False) and getattr(self.app, "audio_file", None))
        self.rad_frame_grab.setEnabled(has_video)
        if has_video:
            self.rad_frame_grab.setChecked(True)
        else:
            self.rad_auto_thumb.setChecked(True)

        self.rad_auto_thumb.toggled.connect(self.on_thumb_mode_changed)
        self.rad_frame_grab.toggled.connect(self.on_thumb_mode_changed)
        self.rad_file_thumb.toggled.connect(self.on_thumb_mode_changed)

        layout.addWidget(thumb_group)

        # Progress bar
        self.status_msg = QLabel("")
        self.status_msg.setStyleSheet("color: #94a3b8; font-size: 11px;")
        layout.addWidget(self.status_msg)

        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        layout.addWidget(self.progress_bar)

        # Bottom Buttons
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(self.cancel_btn)

        self.upload_btn = QPushButton("Upload to YouTube")
        self.upload_btn.setStyleSheet("font-weight: bold; background-color: #dc2626; color: white; padding: 6px 16px;")
        self.upload_btn.clicked.connect(self.on_start_upload)
        btn_layout.addWidget(self.upload_btn)

        layout.addLayout(btn_layout)

    def update_conn_status(self):
        if self.oauth_mgr.is_authenticated():
            self.status_label.setText("<b>YouTube:</b> <span style='color: #22c55e;'>Connected</span>")
        else:
            self.status_label.setText("<b>YouTube:</b> <span style='color: #f59e0b;'>Not Connected</span>")

    def on_open_config(self):
        dlg = YouTubeSettingsDialog(self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self.update_conn_status()

    def load_project_data(self):
        media_file = getattr(self.app, "audio_file", None)
        title = Path(media_file).stem if media_file else "Broadcast Recording"

        # Generate chapter timestamps from stories
        chapters = []
        stories = getattr(self.app, "stories", [])
        if stories:
            # YouTube requires first chapter to be at 00:00
            first_start = stories[0].start
            if first_start > 0.5:
                chapters.append("00:00 Introduction")
            for st in stories:
                t_str = format_time(st.start, include_hours=False)
                # YouTube timestamps format mm:ss or hh:mm:ss
                if st.start >= 3600:
                    h = int(st.start // 3600)
                    m = int((st.start % 3600) // 60)
                    s = int(st.start % 60)
                    ts = f"{h}:{m:02d}:{s:02d}"
                else:
                    m = int(st.start // 60)
                    s = int(st.start % 60)
                    ts = f"{m:02d}:{s:02d}"
                chapters.append(f"{ts} {st.title}")

        desc_lines = [
            f"Segmented broadcast recording: {title}",
            "",
            "Chapters:",
            "\n".join(chapters) if chapters else "00:00 Program Start",
            "",
            "Produced with Radio & TV Segmenter.",
        ]

        self.title_edit.setText(title)
        self.desc_edit.setPlainText("\n".join(desc_lines))

        if self.rad_frame_grab.isChecked():
            self.do_capture_frame()

    def do_capture_frame(self):
        media_file = getattr(self.app, "audio_file", None)
        if not media_file or not Path(media_file).exists():
            return
        out = os.path.join(self.temp_dir, "yt_frame_grab.jpg")
        pos = getattr(self.app, "current_position", 0.0)
        if capture_video_frame(str(media_file), pos, out):
            self.captured_frame_path = out
            pix = QPixmap(out).scaled(200, 110, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
            self.preview_label.setPixmap(pix)
            self.rad_frame_grab.setText(f"Grab frame from video (at {format_time(pos)})")

    def on_thumb_mode_changed(self):
        if self.rad_auto_thumb.isChecked():
            self.browse_btn.setEnabled(False)
            self.preview_label.clear()
            self.preview_label.setText("YouTube will choose standard thumbnail")
        elif self.rad_frame_grab.isChecked():
            self.browse_btn.setEnabled(False)
            self.do_capture_frame()
        elif self.rad_file_thumb.isChecked():
            self.browse_btn.setEnabled(True)
            if self.custom_image_path and Path(self.custom_image_path).exists():
                pix = QPixmap(self.custom_image_path).scaled(200, 110, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
                self.preview_label.setPixmap(pix)
            else:
                self.preview_label.clear()
                self.preview_label.setText("Click Browse to select image file")

    def on_browse_thumb(self):
        fn, _ = QFileDialog.getOpenFileName(
            self,
            "Select YouTube Thumbnail",
            "",
            "Image Files (*.jpg *.jpeg *.png *.webp);;All Files (*.*)",
        )
        if fn:
            self.custom_image_path = fn
            self.thumb_path_label.setText(Path(fn).name)
            pix = QPixmap(fn).scaled(200, 110, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
            self.preview_label.setPixmap(pix)

    def on_start_upload(self):
        if not self.oauth_mgr.is_authenticated():
            QMessageBox.warning(self, "Not Connected", "Please sign in with Google to authorize YouTube uploads.")
            self.on_open_config()
            return

        media_file = getattr(self.app, "audio_file", None)
        if not media_file or not Path(media_file).exists():
            QMessageBox.warning(self, "No Video File", "No media file is loaded in the project.")
            return

        thumb_to_upload: Optional[str] = None
        if self.rad_frame_grab.isChecked() and self.captured_frame_path:
            thumb_to_upload = self.captured_frame_path
        elif self.rad_file_thumb.isChecked() and self.custom_image_path:
            thumb_to_upload = self.custom_image_path

        title = self.title_edit.text().strip() or "Broadcast Recording"
        description = self.desc_edit.toPlainText().strip()
        tags = [t.strip() for t in self.tags_edit.text().split(",") if t.strip()]
        category_id = self.category_combo.currentData() or "25"
        privacy = self.privacy_combo.currentData() or "unlisted"

        self.upload_btn.setEnabled(False)
        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(0)
        self.status_msg.setText("Starting upload...")

        worker = YouTubeUploadWorker(
            oauth_mgr=self.oauth_mgr,
            video_path=str(media_file),
            title=title,
            description=description,
            tags=tags,
            category_id=category_id,
            privacy_status=privacy,
            thumbnail_path=thumb_to_upload,
        )
        worker.progress_signal.connect(self.on_upload_progress)
        worker.finished_signal.connect(self.on_upload_finished)
        self._worker = worker
        worker.start()

    def on_upload_progress(self, pct: int, msg: str):
        self.progress_bar.setValue(pct)
        self.status_msg.setText(msg)

    def on_upload_finished(self, success: bool, video_id: str, message: str):
        self.upload_btn.setEnabled(True)
        self.progress_bar.setVisible(False)
        if success:
            QMessageBox.information(
                self,
                "YouTube Upload Complete",
                f"Video was uploaded successfully!\n\nVideo ID: {video_id}\nURL: {message}",
            )
            self.accept()
        else:
            QMessageBox.critical(self, "Upload Failed", f"YouTube upload failed:\n\n{message}")

    def closeEvent(self, event):
        if self._worker and self._worker.isRunning():
            self._worker.cancel()
            self._worker.wait(2000)
        try:
            shutil.rmtree(self.temp_dir, ignore_errors=True)
        except Exception:
            pass
        super().closeEvent(event)


class Plugin(BasePlugin):
    """YouTube Video Publisher plugin hooking into RTVS."""

    def on_load(self) -> bool:
        return True

    def get_export_actions(self) -> List[tuple[str, Callable]]:
        return [
            ("Publish to YouTube...", self.open_publish_dialog),
        ]

    def get_preferences_widget(self, parent=None) -> Any:
        box = QGroupBox("YouTube Video Publishing", parent)
        layout = QVBoxLayout(box)
        lbl = QLabel("Connect Radio & TV Segmenter to YouTube Data API v3.")
        layout.addWidget(lbl)
        btn = QPushButton("Configure YouTube Credentials...")
        btn.clicked.connect(lambda: YouTubeSettingsDialog(parent or self.app).exec())
        layout.addWidget(btn)
        return box

    def open_publish_dialog(self):
        dlg = YouTubePublishDialog(self, parent=self.app)
        dlg.exec()
