"""Radio & TV Segmenter — WordPress Export & Settings module.

Provides WordPress REST API publishing capabilities, credential management via
system keyring (with QSettings fallback), and WordPress configuration dialogs.
"""

from __future__ import annotations

import html
import json
import os
import re
import tempfile
from pathlib import Path
from typing import Any

from prs_shared import (
    INTERNAL_APP_ID,
    PROJECT_VERSION,
    QSettings,
    ffmpeg_path,
    format_time,
    safe_filename,
)

from PySide6.QtCore import Qt
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
)


def _get_keyring():
    """Safely return keyring module if available."""
    try:
        import keyring
        return keyring
    except Exception:
        return None


def _get_wp_password(username: str) -> str:
    """Retrieve the stored WordPress application password."""
    if not username:
        return ""
    kr = _get_keyring()
    if kr is not None:
        try:
            pwd = kr.get_password(INTERNAL_APP_ID, f"wp_{username}")
            if pwd:
                return pwd
        except Exception:
            pass
    settings = QSettings(INTERNAL_APP_ID, INTERNAL_APP_ID)
    return str(settings.value(f"wp_pass_{username}", "") or "")


def _set_wp_password(username: str, password: str) -> None:
    """Store the WordPress application password securely."""
    if not username:
        return
    kr = _get_keyring()
    saved_in_keyring = False
    if kr is not None:
        try:
            kr.set_password(INTERNAL_APP_ID, f"wp_{username}", password)
            saved_in_keyring = True
        except Exception:
            pass
    settings = QSettings(INTERNAL_APP_ID, INTERNAL_APP_ID)
    if not saved_in_keyring:
        settings.setValue(f"wp_pass_{username}", password)
    else:
        # Clear fallback if saved in keyring
        settings.remove(f"wp_pass_{username}")


def generate_wp_excerpt(text: str, max_words: int = 55) -> str:
    """Generate a clean WordPress-style post excerpt from text (standard 55 words)."""
    if not text:
        return ""
    # Strip HTML tags
    cleaned = re.sub(r"<[^>]+>", " ", text)
    # Strip speaker tags like [Speaker 1] or Speaker:
    cleaned = re.sub(r"\[[^\]]+\]", " ", cleaned)
    # Strip timestamp annotations
    cleaned = re.sub(r"\b\d{1,2}:\d{2}(?::\d{2})?(?:\.\d+)?\b", " ", cleaned)
    # Collapse multiple whitespace
    words = cleaned.split()
    if len(words) <= max_words:
        return " ".join(words)
    return " ".join(words[:max_words]) + "..."


class WordPressClient:
    """Client for WordPress REST API using Application Passwords."""

    def __init__(self, site_url: str, username: str, password: str):
        self.site_url = site_url.rstrip("/")
        self.username = username
        self.password = password.strip()
        self.api_base = f"{self.site_url}/wp-json/wp/v2"

    def _get_auth(self):
        return (self.username, self.password)

    def test_connection(self) -> tuple[bool, str]:
        """Test credentials against /wp/v2/users/me or /wp/v2/posts."""
        import requests
        try:
            url = f"{self.api_base}/users/me"
            resp = requests.get(url, auth=self._get_auth(), timeout=12)
            if resp.status_code == 200:
                user_data = resp.json()
                name = user_data.get("name", self.username)
                return True, f"Connected successfully as '{name}'."
            elif resp.status_code in (401, 403):
                return False, f"Authentication failed (HTTP {resp.status_code}): Invalid username or application password."
            else:
                return False, f"WordPress server returned HTTP {resp.status_code}: {resp.text[:200]}"
        except Exception as exc:
            return False, f"Connection failed: {exc}"

    def get_categories(self) -> list[dict]:
        """Fetch post categories from WordPress."""
        import requests
        try:
            url = f"{self.api_base}/categories"
            params = {"per_page": 100, "_fields": "id,name,slug,parent"}
            resp = requests.get(url, auth=self._get_auth(), params=params, timeout=15)
            if resp.status_code == 200:
                return resp.json()
        except Exception:
            pass
        return []

    def get_authors(self) -> list[dict]:
        """Fetch users and co-authors for author attribution."""
        import requests
        authors = []
        try:
            # 1. Standard WordPress Users
            url = f"{self.api_base}/users"
            params = {"per_page": 100, "_fields": "id,name,slug"}
            resp = requests.get(url, auth=self._get_auth(), params=params, timeout=15)
            if resp.status_code == 200:
                for u in resp.json():
                    authors.append({
                        "id": u.get("id"),
                        "name": u.get("name"),
                        "slug": u.get("slug"),
                        "type": "WP User",
                        "is_guest": False,
                    })
        except Exception:
            pass

        # 2. Check for Co-Authors Plus guest authors taxonomy if available
        try:
            url_coauthors = f"{self.api_base}/guest-authors"
            resp = requests.get(url_coauthors, auth=self._get_auth(), params={"per_page": 100}, timeout=10)
            if resp.status_code == 200:
                for ga in resp.json():
                    authors.append({
                        "id": ga.get("id"),
                        "name": ga.get("display_name", ga.get("name")),
                        "slug": ga.get("slug"),
                        "type": "Guest Author",
                        "is_guest": True,
                    })
        except Exception:
            pass

        return authors

    def upload_media(self, file_path: str, filename: str | None = None) -> dict:
        """Upload an audio file to the WordPress Media Library."""
        import requests
        path = Path(file_path)
        if not path.is_file():
            raise FileNotFoundError(f"Media file not found: {file_path}")

        upload_filename = filename or path.name
        headers = {
            "Content-Disposition": f'attachment; filename="{upload_filename}"',
            "Content-Type": "audio/mpeg",
        }
        url = f"{self.api_base}/media"
        with open(path, "rb") as f:
            resp = requests.post(url, auth=self._get_auth(), headers=headers, data=f, timeout=120)

        if resp.status_code not in (200, 201):
            raise RuntimeError(f"WordPress Media upload failed (HTTP {resp.status_code}): {resp.text[:300]}")
        return resp.json()

    def create_post(
        self,
        title: str,
        content: str,
        excerpt: str = "",
        status: str = "draft",
        category_ids: list[int] | None = None,
        author_ids: list[int] | None = None,
        author_term_ids: list[int] | None = None,
    ) -> dict:
        """Create a post in WordPress."""
        import requests
        payload: dict[str, Any] = {
            "title": title,
            "content": content,
            "excerpt": excerpt,
            "status": status,
        }
        if category_ids:
            payload["categories"] = category_ids
        if author_ids:
            payload["author"] = author_ids[0]

        url = f"{self.api_base}/posts"
        resp = requests.post(url, auth=self._get_auth(), json=payload, timeout=30)
        if resp.status_code not in (200, 201):
            raise RuntimeError(f"WordPress Post creation failed (HTTP {resp.status_code}): {resp.text[:300]}")
        return resp.json()


class WordPressSettingsDialog(QDialog):
    """Dialog for entering and testing WordPress site credentials."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("WordPress Connection Settings")
        self.setMinimumWidth(480)
        self.settings = QSettings(INTERNAL_APP_ID, INTERNAL_APP_ID)

        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        desc = QLabel(
            "Configure your WordPress site connection using an <b>Application Password</b>.<br>"
            "To generate one in WordPress: go to <i>Users &gt; Profile &gt; Application Passwords</i>."
        )
        desc.setWordWrap(True)
        layout.addWidget(desc)

        group = QGroupBox("WordPress Credentials")
        form = QFormLayout(group)

        self.url_edit = QLineEdit()
        self.url_edit.setPlaceholderText("https://yoursite.com")
        self.url_edit.setText(str(self.settings.value("wp_site_url", "") or ""))

        self.user_edit = QLineEdit()
        self.user_edit.setPlaceholderText("your_username")
        current_user = str(self.settings.value("wp_username", "") or "")
        self.user_edit.setText(current_user)

        self.pass_edit = QLineEdit()
        self.pass_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.pass_edit.setPlaceholderText("xxxx xxxx xxxx xxxx")
        if current_user:
            self.pass_edit.setText(_get_wp_password(current_user))

        form.addRow("Site URL:", self.url_edit)
        form.addRow("Username:", self.user_edit)
        form.addRow("App Password:", self.pass_edit)
        layout.addWidget(group)

        self.status_label = QLabel("")
        self.status_label.setWordWrap(True)
        layout.addWidget(self.status_label)

        btn_box = QHBoxLayout()
        self.test_btn = QPushButton("Test Connection")
        self.save_btn = QPushButton("Save")
        self.cancel_btn = QPushButton("Cancel")

        btn_box.addWidget(self.test_btn)
        btn_box.addStretch()
        btn_box.addWidget(self.save_btn)
        btn_box.addWidget(self.cancel_btn)
        layout.addLayout(btn_box)

        self.test_btn.clicked.connect(self._test_connection)
        self.save_btn.clicked.connect(self._save_settings)
        self.cancel_btn.clicked.connect(self.reject)

    def _test_connection(self):
        url = self.url_edit.text().strip()
        user = self.user_edit.text().strip()
        pwd = self.pass_edit.text().strip()
        if not url or not user or not pwd:
            QMessageBox.warning(self, "Incomplete Settings", "Please enter Site URL, Username, and Password first.")
            return

        self.test_btn.setEnabled(False)
        self.status_label.setText("Testing connection...")
        self.status_label.setStyleSheet("color: #888888;")
        self.repaint()

        client = WordPressClient(url, user, pwd)
        ok, msg = client.test_connection()
        self.test_btn.setEnabled(True)
        if ok:
            self.status_label.setText(f"✓ {msg}")
            self.status_label.setStyleSheet("color: #2ea44f; font-weight: bold;")
        else:
            self.status_label.setText(f"✗ {msg}")
            self.status_label.setStyleSheet("color: #e06c75;")

    def _save_settings(self):
        url = self.url_edit.text().strip()
        user = self.user_edit.text().strip()
        pwd = self.pass_edit.text().strip()

        self.settings.setValue("wp_site_url", url)
        self.settings.setValue("wp_username", user)
        if user and pwd:
            _set_wp_password(user, pwd)

        self.accept()


class WordPressExportMixin:
    """Mixin providing WordPress publishing capabilities to MainWindow."""

    def _get_wp_client(self) -> WordPressClient | None:
        """Instantiate WordPressClient from stored settings if configured."""
        settings = QSettings(INTERNAL_APP_ID, INTERNAL_APP_ID)
        url = str(settings.value("wp_site_url", "") or "").strip()
        user = str(settings.value("wp_username", "") or "").strip()
        pwd = _get_wp_password(user) if user else ""
        if url and user and pwd:
            return WordPressClient(url, user, pwd)
        return None

    def _open_wp_settings(self):
        """Open WordPress Settings configuration dialog."""
        dialog = WordPressSettingsDialog(self)
        dialog.exec()

    def _execute_wordpress_upload(
        self,
        client: WordPressClient,
        post_title: str,
        post_excerpt: str,
        start: float | None,
        end: float | None,
        task_label: str,
        include_english: bool,
        include_spanish: bool,
        spanish_presentation: str,
        primary_language: str,
        author_ids: list[int] | None = None,
        author_term_ids: list[int] | None = None,
        category_ids: list[int] | None = None,
        show_completion_dialog: bool = False,
        media_filename: str | None = None,
    ) -> dict:
        """Extract media clip, upload to WordPress media library, and create draft post."""
        audio_src = self.audio_file
        if not audio_src or not Path(audio_src).exists():
            raise RuntimeError("No media file is loaded in the active project to export.")

        media_url = ""
        # 1. Extract audio clip using ffmpeg if slice start/end is given
        temp_audio = None
        try:
            target_media = str(audio_src)
            if start is not None and end is not None and (start > 0 or end < self.duration):
                temp_dir = Path(tempfile.gettempdir()) / "rtvs_wp_export"
                temp_dir.mkdir(parents=True, exist_ok=True)
                ext = "mp3"
                slice_name = safe_filename(media_filename or post_title or "audio_clip")
                temp_audio = temp_dir / f"{slice_name}_{int(start)}_{int(end)}.{ext}"
                ff = ffmpeg_path()
                if ff:
                    import subprocess
                    cmd = [
                        str(ff), "-y",
                        "-ss", str(start),
                        "-to", str(end),
                        "-i", str(audio_src),
                        "-vn",
                        "-c:a", "libmp3lame",
                        "-b:a", "128k",
                        str(temp_audio)
                    ]
                    res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                    if res.returncode == 0 and temp_audio.is_file():
                        target_media = str(temp_audio)

            # 2. Upload media file to WordPress
            media_item = client.upload_media(target_media, filename=media_filename)
            media_url = media_item.get("source_url", "")
        finally:
            if temp_audio and temp_audio.exists():
                try:
                    temp_audio.unlink()
                except Exception:
                    pass

        # 3. Build post content HTML
        content_parts = []
        if media_url:
            content_parts.append(
                f'<!-- wp:audio -->\n'
                f'<figure class="wp-block-audio"><audio controls src="{html.escape(media_url)}"></audio></figure>\n'
                f'<!-- /wp:audio -->\n'
            )

        # Build transcript text for the story time range
        en_text = ""
        es_text = ""
        if hasattr(self, "_get_transcript_text_slice"):
            if include_english:
                en_text = self._get_transcript_text_slice(start or 0.0, end)
        elif self.transcript:
            segs = self.transcript.get("segments", [])
            selected = [
                s.get("text", "") for s in segs
                if (start is None or s.get("end", 0) >= start) and (end is None or s.get("start", 0) <= end)
            ]
            en_text = " ".join(selected)

        if include_spanish and hasattr(self, "translations"):
            es_data = self.translations.get("en-es") or self.translations.get("en_es") or {}
            es_segs = es_data.get("segments", [])
            selected_es = [
                s.get("text", "") for s in es_segs
                if (start is None or s.get("end", 0) >= start) and (end is None or s.get("start", 0) <= end)
            ]
            es_text = " ".join(selected_es)

        # Format transcript according to presentation preference
        if en_text and es_text:
            if spanish_presentation == "accordion":
                content_parts.append(f"<!-- wp:paragraph --><p>{html.escape(en_text)}</p><!-- /wp:paragraph -->\n")
                content_parts.append(
                    f'<details><summary><b>Transcripción en Español</b></summary>\n'
                    f'<p>{html.escape(es_text)}</p>\n'
                    f'</details>\n'
                )
            else:  # stacked
                content_parts.append(f"<!-- wp:paragraph --><p><b>English Transcript:</b><br>{html.escape(en_text)}</p><!-- /wp:paragraph -->\n")
                content_parts.append(f"<!-- wp:paragraph --><p><b>Transcripción en Español:</b><br>{html.escape(es_text)}</p><!-- /wp:paragraph -->\n")
        elif en_text:
            content_parts.append(f"<!-- wp:paragraph --><p>{html.escape(en_text)}</p><!-- /wp:paragraph -->\n")
        elif es_text:
            content_parts.append(f"<!-- wp:paragraph --><p>{html.escape(es_text)}</p><!-- /wp:paragraph -->\n")

        full_content = "\n".join(content_parts)

        # 4. Create Post
        post_data = client.create_post(
            title=post_title,
            content=full_content,
            excerpt=post_excerpt,
            status="draft",
            category_ids=category_ids,
            author_ids=author_ids,
            author_term_ids=author_term_ids,
        )

        post_id = post_data.get("id")
        self.log_activity(f"[WORDPRESS] Created Draft Post #{post_id}: '{post_title}'")
        return post_data
