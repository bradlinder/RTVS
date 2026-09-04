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
        """Fetch PublishPress Authors profiles, including guest authors without users."""
        import requests

        authors: list[dict] = []
        seen: set[int] = set()

        def add_author(item: dict, default_guest: bool = False) -> None:
            try:
                term_id = int(item.get("term_id", item.get("id")))
            except (TypeError, ValueError):
                return
            if term_id in seen:
                return
            name = item.get("display_name") or item.get("name")
            if isinstance(name, dict):
                name = name.get("rendered", "")
            if not name:
                return
            try:
                user_id = int(item.get("user_id") or 0)
            except (TypeError, ValueError):
                user_id = 0
            is_guest = bool(item.get("is_guest", default_guest)) or user_id == 0
            seen.add(term_id)
            authors.append({
                "id": user_id or term_id,
                "term_id": term_id,
                "user_id": user_id,
                "name": str(name),
                "slug": item.get("slug", ""),
                "type": "Guest Author" if is_guest else "PublishPress Author",
                "is_guest": is_guest,
            })

        # PublishPress Authors is the authoritative source. Its author profiles are
        # taxonomy terms, so this includes guest authors with no WP user account.
        try:
            for page in range(1, 11):
                resp = requests.get(
                    f"{self.site_url}/wp-json/publishpress-authors/v1/authors",
                    auth=self._get_auth(),
                    params={"per_page": 100, "page": page}, timeout=15,
                )
                if resp.status_code != 200:
                    break
                data = resp.json()
                if isinstance(data, dict):
                    data = data.get("authors", data.get("data", []))
                if not isinstance(data, list) or not data:
                    break
                for item in data:
                    if isinstance(item, dict):
                        add_author(item)
                if len(data) < 100:
                    break
        except Exception:
            pass

        # Fallback for installations exposing the author taxonomy directly.
        if not authors:
            for taxonomy in ("author", "ppma_author"):
                try:
                    resp = requests.get(
                        f"{self.api_base}/{taxonomy}", auth=self._get_auth(),
                        params={"per_page": 100}, timeout=15,
                    )
                    if resp.status_code == 200:
                        data = resp.json()
                        if isinstance(data, list):
                            for item in data:
                                if isinstance(item, dict):
                                    add_author(item, default_guest=True)
                    if authors:
                        break
                except Exception:
                    continue

        # Final fallback for sites without PublishPress Authors.
        if not authors:
            try:
                resp = requests.get(
                    f"{self.api_base}/users", auth=self._get_auth(),
                    params={"per_page": 100, "_fields": "id,name,slug"}, timeout=15,
                )
                if resp.status_code == 200:
                    for u in resp.json():
                        try:
                            uid = int(u.get("id"))
                        except (TypeError, ValueError):
                            continue
                        authors.append({
                            "id": uid, "term_id": None, "user_id": uid,
                            "name": u.get("name", ""), "slug": u.get("slug", ""),
                            "type": "WP User", "is_guest": False,
                        })
            except Exception:
                pass
        return authors

    def upload_media(self, file_path: str, filename: str | None = None) -> dict:
        """Upload media using WordPress's standard multipart API, with raw fallback."""
        import mimetypes
        import requests
        path = Path(file_path)
        if not path.is_file():
            raise FileNotFoundError(f"Media file not found: {file_path}")
        upload_filename = filename or path.name
        mime_type = mimetypes.guess_type(upload_filename)[0] or mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        if path.suffix.lower() == ".mp3":
            mime_type = "audio/mpeg"
        elif path.suffix.lower() == ".wav":
            mime_type = "audio/wav"
        url = f"{self.api_base}/media"
        errors = []

        # requests generates the required multipart Content-Disposition header,
        # including name="file" and the actual filename.
        try:
            with open(path, "rb") as f:
                resp = requests.post(
                    url, auth=self._get_auth(),
                    files={"file": (upload_filename, f, mime_type)},
                    headers={"Accept": "application/json"}, timeout=180,
                )
            if resp.status_code in (200, 201):
                return resp.json()
            errors.append(f"multipart HTTP {resp.status_code}: {resp.text[:500]}")
        except Exception as exc:
            errors.append(f"multipart exception: {exc}")

        # Raw upload fallback. This path requires Content-Disposition on the request.
        try:
            headers = {
                "Accept": "application/json",
                "Content-Disposition": f'attachment; filename="{upload_filename}"',
                "Content-Type": mime_type,
                "Content-Length": str(path.stat().st_size),
            }
            with open(path, "rb") as f:
                resp = requests.post(url, auth=self._get_auth(), headers=headers, data=f, timeout=180)
            if resp.status_code in (200, 201):
                return resp.json()
            errors.append(f"raw HTTP {resp.status_code}: {resp.text[:500]}")
        except Exception as exc:
            errors.append(f"raw exception: {exc}")
        raise RuntimeError("WordPress Media upload failed (" + "; ".join(errors) + ")")

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
        if author_term_ids:
            payload["ppma_author"] = [int(term_id) for term_id in author_term_ids]

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
        progress_callback=None,
    ) -> dict:
        """Extract media clip, upload to WordPress media library, and create draft post.

        progress_callback, when supplied, receives a human-readable step description
        and a 1-based step number out of four.
        """
        def report_progress(step: int, description: str) -> None:
            if progress_callback:
                try:
                    progress_callback(step, 4, description)
                except Exception:
                    pass

        audio_src = self.audio_file
        if not audio_src or not Path(audio_src).exists():
            raise RuntimeError("No media file is loaded in the active project to export.")

        media_url = ""
        # 1. Prepare the media file. This can take a while for large WAV files.
        report_progress(1, "Preparing audio for WordPress…")
        temp_audio = None
        try:
            target_media = str(audio_src)
            source_suffix = Path(audio_src).suffix.lower()
            needs_clip = start is not None and end is not None and (start > 0 or end < self.duration)
            needs_mp3 = source_suffix == ".wav"

            # Always convert WAV to MP3 for WordPress, including full-file exports.
            # This keeps the actual bytes, extension, and MIME type consistent.
            if needs_clip or needs_mp3:
                report_progress(1, "Converting audio to MP3…")
                temp_dir = Path(tempfile.gettempdir()) / "rtvs_wp_export"
                temp_dir.mkdir(parents=True, exist_ok=True)
                base = Path(safe_filename(media_filename or post_title or "audio_clip")).stem
                if needs_clip:
                    temp_audio = temp_dir / f"{base}_{int(start or 0)}_{int(end or 0)}.mp3"
                else:
                    temp_audio = temp_dir / f"{base}.mp3"
                ff = ffmpeg_path()
                if not ff:
                    raise RuntimeError("FFmpeg is required to convert WAV audio to MP3 for WordPress export, but FFmpeg was not found.")
                import subprocess
                cmd = [str(ff), "-y"]
                if needs_clip:
                    cmd += ["-ss", str(start), "-to", str(end)]
                cmd += ["-i", str(audio_src), "-vn", "-c:a", "libmp3lame", "-b:a", "128k", str(temp_audio)]
                res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                if res.returncode != 0 or not temp_audio.is_file() or temp_audio.stat().st_size == 0:
                    detail = res.stderr.decode("utf-8", errors="replace")[-1200:]
                    raise RuntimeError(f"FFmpeg WAV-to-MP3 conversion failed: {detail}")
                target_media = str(temp_audio)

            report_progress(2, "Uploading audio to WordPress…")
            upload_name = media_filename
            if Path(target_media).suffix.lower() == ".mp3":
                upload_name = f"{Path(media_filename or post_title or Path(target_media).stem).stem}.mp3"

            media_item = client.upload_media(target_media, filename=upload_name)
            media_url = media_item.get("source_url", "")
        finally:
            if temp_audio and temp_audio.exists():
                try:
                    temp_audio.unlink()
                except Exception:
                    pass

        # 3. Build post content HTML. WordPress should mirror the local transcript
        # export style: speaker-labelled paragraphs when enabled, no timestamps,
        # and no redundant "Transcript" heading.
        report_progress(3, "Formatting transcript for WordPress…")
        content_parts = []
        if media_url:
            content_parts.append(
                f'<!-- wp:audio -->\n'
                f'<figure class="wp-block-audio"><audio controls src="{html.escape(media_url, quote=True)}"></audio></figure>\n'
                f'<!-- /wp:audio -->\n'
            )

        def language_blocks(lang_code: str):
            if lang_code == "en":
                segments = self.transcript.get("segments", []) if self.transcript else []
                if start is not None or end is not None:
                    lo = float(start or 0.0)
                    hi = float(end) if end is not None else None
                    segments = [
                        seg for seg in segments
                        if (hi is None or float(seg.get("start", 0.0)) <= hi)
                        and float(seg.get("end", seg.get("start", 0.0))) >= lo
                    ]
                return self.build_story_blocks(segments) if segments else []

            es_data = getattr(self, "translations", {}).get("en-es") or getattr(self, "translations", {}).get("en_es") or {}
            es_segs = es_data.get("segments", []) if isinstance(es_data, dict) else []
            source_segs = self.transcript.get("segments", []) if self.transcript else []
            selected = []
            lo = float(start or 0.0)
            hi = float(end) if end is not None else None
            for idx, t_seg in enumerate(es_segs):
                source_seg = source_segs[idx] if idx < len(source_segs) else {}
                t_start = float(t_seg.get("start", source_seg.get("start", 0.0)))
                t_end = float(t_seg.get("end", source_seg.get("end", t_start + 1.0)))
                if (hi is not None and t_start > hi) or t_end < lo:
                    continue
                selected.append({
                    "speaker": self.get_effective_speaker_name(idx, source_seg) if source_seg else "",
                    "text": t_seg.get("text", "").strip(),
                    "start": t_start,
                    "end": t_end,
                    "_source_index": idx,
                })
            return self.build_story_blocks(selected) if selected else []

        def append_blocks(blocks):
            for block in blocks:
                text = str(block.get("text", "") or "").strip()
                if not text:
                    continue
                speaker = str(block.get("speaker", "") or "").strip()
                if speaker:
                    content_parts.append(
                        f'<p><strong>{html.escape(speaker)}</strong>: {html.escape(text)}</p>'
                    )
                else:
                    content_parts.append(f'<p>{html.escape(text)}</p>')

        en_blocks = language_blocks("en") if include_english else []
        es_blocks = language_blocks("es") if include_spanish else []

        if en_blocks and es_blocks:
            if spanish_presentation == "accordion":
                # 1. Select primary vs secondary text and label
                if primary_language == "es":
                    primary_blocks = es_blocks
                    secondary_blocks = en_blocks
                    btn_text = "Read in English"
                else:
                    primary_blocks = en_blocks
                    secondary_blocks = es_blocks
                    btn_text = "Leer en Español"

                # 2. Button styling on summary tag for the top toggle
                summary_btn_style = (
                    "display: inline-block; "
                    "padding: 8px 18px; "
                    "background-color: #0073aa; "
                    "color: #ffffff; "
                    "border-radius: 4px; "
                    "font-weight: bold; "
                    "cursor: pointer; "
                    "margin-bottom: 16px; "
                    "user-select: none; "
                    "list-style: none; "
                    "outline: none;"
                )

                # 3. Render the secondary language accordion at the top
                content_parts.append(
                    f'<details class="rtvs-language-accordion" style="margin-bottom: 24px;">'
                    f'<summary role="button" style="{summary_btn_style}">{btn_text}</summary>'
                    f'<div class="rtvs-secondary-transcript" style="margin-top: 12px;">'
                )
                append_blocks(secondary_blocks)
                content_parts.append('</div></details>')

                # 4. Render primary language directly below the toggle button
                append_blocks(primary_blocks)
            elif spanish_presentation == "es_first":
                append_blocks(es_blocks)
                content_parts.append('<h2>English</h2>')
                append_blocks(en_blocks)
            else:  # en_first
                append_blocks(en_blocks)
                content_parts.append('<h2>Español</h2>')
                append_blocks(es_blocks)
        elif en_blocks:
            append_blocks(en_blocks)
        elif es_blocks:
            append_blocks(es_blocks)

        full_content = "\n".join(content_parts)

        # 4. Create Post
        report_progress(4, "Creating WordPress draft…")
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
