"""Update manager and GitHub release installer for Radio & TV Segmenter.

Handles:
- Querying the GitHub REST API for latest releases and assets
- Semantic version parsing and comparison against PROJECT_VERSION
- Matching platform-appropriate installer assets (.exe on Windows, .dmg on macOS, .tar.gz on Linux)
- Non-blocking background workers for checking and downloading updates
- Real-time download progress tracking with cancellation support
- Automatic launching of installers with graceful application shutdown
- Visual Qt dialog matching application dark/light theme
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

try:
    from prs_shared import (
        APP_DISPLAY_NAME,
        DEFAULT_GITHUB_REPO,
        INTERNAL_APP_ID,
        PROJECT_VERSION,
        get_app_data_dir,
        get_app_icon,
        get_github_repo,
        QApplication,
        QColor,
        QCursor,
        QDesktopServices,
        QDialog,
        QFrame,
        QHBoxLayout,
        QIcon,
        QLabel,
        QMessageBox,
        QProgressBar,
        QPushButton,
        QSettings,
        QSize,
        QTextBrowser,
        QThread,
        QUrl,
        QVBoxLayout,
        QWidget,
        Signal,
        Qt,
    )
except Exception:
    APP_DISPLAY_NAME = "Radio & TV Segmenter"
    PROJECT_VERSION = "1.9.1"
    DEFAULT_GITHUB_REPO = "bradlinder/RTVS"
    INTERNAL_APP_ID = "RadioTVStorySegmenter"

    def get_github_repo() -> str:
        return os.environ.get("GITHUB_REPO", "").strip() or DEFAULT_GITHUB_REPO

    def get_app_data_dir() -> Path:
        p = Path.home() / f".{INTERNAL_APP_ID.lower()}"
        p.mkdir(parents=True, exist_ok=True)
        return p

    def get_app_icon():
        return None

    try:
        from PySide6.QtCore import Qt, QUrl, Signal, QObject, QThread, QSettings, QSize
        from PySide6.QtGui import QColor, QCursor, QDesktopServices, QIcon
        from PySide6.QtWidgets import (
            QApplication,
            QDialog,
            QFrame,
            QHBoxLayout,
            QLabel,
            QMessageBox,
            QProgressBar,
            QPushButton,
            QTextBrowser,
            QVBoxLayout,
            QWidget,
        )
    except Exception:
        class QObject: pass
        class QThread:
            def __init__(self, parent=None): pass
            def start(self): pass
        class Signal:
            def __init__(self, *args): pass
            def emit(self, *args): pass
            def connect(self, *args): pass
        class QWidget: pass
        class QDialog(QWidget): pass
        class QSettings:
            def __init__(self, *args): pass
            def value(self, key, default=None): return default
        Qt = type("Qt", (), {"CursorShape": type("CS", (), {"PointingHandCursor": None})})
        QApplication = None
        QDesktopServices = None
        QUrl = None
        QColor = None
        QCursor = None
        QIcon = None
        QFrame = None
        QHBoxLayout = None
        QLabel = None
        QMessageBox = None
        QProgressBar = None
        QPushButton = None
        QTextBrowser = None
        QVBoxLayout = None
        QSize = None


def parse_version_tuple(version_str: str) -> tuple[int, ...]:
    """Parse a version string (e.g. 'v1.5', '1.6.0', 'v2.0-beta') into comparable integer tuples."""
    if not version_str:
        return (0, 0, 0)
    cleaned = re.sub(r"^[vV]", "", version_str.strip())
    # Extract digit sequences separated by dots
    parts = []
    for chunk in cleaned.split("."):
        m = re.match(r"^(\d+)", chunk)
        if m:
            parts.append(int(m.group(1)))
        else:
            break
    while len(parts) < 3:
        parts.append(0)
    return tuple(parts)


def is_version_newer(remote_version_str: str, current_version_str: str = PROJECT_VERSION) -> bool:
    """Return True if remote_version_str is strictly newer than current_version_str."""
    try:
        remote_t = parse_version_tuple(remote_version_str)
        curr_t = parse_version_tuple(current_version_str)
        return remote_t > curr_t
    except Exception:
        return False


def format_byte_size(num_bytes: int) -> str:
    """Format bytes into human-readable string (e.g. '78.4 MB')."""
    if num_bytes <= 0:
        return "Unknown size"
    for unit in ["B", "KB", "MB", "GB"]:
        if num_bytes < 1024.0 or unit == "GB":
            return f"{num_bytes:.1f} {unit}" if unit != "B" else f"{num_bytes} B"
        num_bytes /= 1024.0
    return f"{num_bytes:.1f} GB"


def select_best_asset_for_platform(assets: list[dict]) -> dict | None:
    """Select the most suitable release asset dictionary for the current operating system."""
    if not assets:
        return None

    current_os = sys.platform
    candidates: list[tuple[int, dict]] = []

    for asset in assets:
        name = asset.get("name", "").lower()
        score = 0

        if current_os == "win32":
            if name.endswith(".exe"):
                score = 10
                if "radiotv" in name or "segmenter" in name:
                    score += 15
                if "setup" in name or "installer" in name:
                    score += 10
                if "win" in name or "windows" in name:
                    score += 5
                candidates.append((score, asset))
            elif name.endswith(".zip") and "win" in name:
                candidates.append((3, asset))

        elif current_os == "darwin":
            if name.endswith(".dmg"):
                score = 10
                if "radiotv" in name or "segmenter" in name:
                    score += 15
                if "macos" in name or "mac" in name or "darwin" in name:
                    score += 5
                candidates.append((score, asset))
            elif name.endswith(".pkg") or (name.endswith(".zip") and "mac" in name):
                candidates.append((5, asset))

        else:
            # Linux / Unix: Prioritize Debian/Ubuntu packages (.deb) when running on Debian/Ubuntu systems
            is_debian = (
                Path("/etc/debian_version").exists()
                or ("ubuntu" in Path("/etc/os-release").read_text(errors="ignore").lower() if Path("/etc/os-release").exists() else False)
                or ("debian" in Path("/etc/os-release").read_text(errors="ignore").lower() if Path("/etc/os-release").exists() else False)
            )
            if name.endswith(".deb"):
                score = 30 if is_debian else 18
                if "radiotv" in name or "segmenter" in name:
                    score += 5
                candidates.append((score, asset))
            elif name.endswith(".appimage"):
                score = 25
                candidates.append((score, asset))
            elif name.endswith(".tar.gz") or name.endswith(".tgz"):
                score = 15
                if "linux" in name or "x86_64" in name:
                    score += 5
                candidates.append((score, asset))
            elif name.endswith(".rpm"):
                score = 30 if not is_debian and Path("/etc/redhat-release").exists() else 8
                candidates.append((score, asset))

    if candidates:
        candidates.sort(key=lambda x: x[0], reverse=True)
        return candidates[0][1]

    return None


def fetch_latest_release(repo: str) -> dict:
    """Query GitHub API for the latest release metadata for the given repo."""
    url = f"https://api.github.com/repos/{repo}/releases/latest"
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": f"RadioTVSegmenter/{PROJECT_VERSION} (Python/{sys.version.split()[0]})",
            "Accept": "application/vnd.github.v3+json",
        },
    )
    with urllib.request.urlopen(req, timeout=12) as response:
        status = response.getcode()
        if status != 200:
            raise RuntimeError(f"GitHub API returned HTTP status {status}")
        raw = response.read().decode("utf-8")
        return json.loads(raw)


def launch_and_install(file_path: str, parent: QWidget | None = None) -> bool:
    """Launch the downloaded installer executable or mount package, then close the app."""
    path = Path(file_path).resolve()
    if not path.is_file():
        if parent:
            QMessageBox.critical(parent, "Update Error", f"The downloaded file was not found:\n{path}")
        return False

    if sys.platform == "win32":
        try:
            # Launch Inno Setup or executable installer. shell=True is not
            # needed to start an executable directly and cmd.exe's quoting
            # doesn't fully protect paths containing shell-special
            # characters, so launch it without a shell.
            subprocess.Popen([str(path)])
            return True
        except Exception as exc:
            if parent:
                QMessageBox.critical(parent, "Launch Error", f"Failed to execute installer:\n{exc}")
            return False

    elif sys.platform == "darwin":
        try:
            subprocess.Popen(["open", str(path)])
            return True
        except Exception as exc:
            if parent:
                QMessageBox.critical(parent, "Launch Error", f"Failed to open disk image:\n{exc}")
            return False

    else:
        # Linux
        try:
            if path.name.endswith(".AppImage"):
                path.chmod(0o755)
                subprocess.Popen([str(path)])
                return True
            elif path.name.endswith(".deb"):
                # Launch the native Debian/Ubuntu package installer GUI (e.g., Ubuntu Software, GDebi, QApt)
                subprocess.Popen(["xdg-open", str(path)])
                return True
            else:
                # Open the downloads directory in the system file manager
                subprocess.Popen(["xdg-open", str(path.parent)])
                return True
        except Exception as exc:
            if parent:
                QMessageBox.critical(parent, "Launch Error", f"Failed to open package location:\n{exc}")
            return False


class CheckUpdateWorker(QThread):
    """Worker thread that checks GitHub for the latest release."""
    update_available = Signal(dict, dict, bool)  # release_info, asset_info, is_newer
    up_to_date = Signal(str, str)                # current_ver, remote_tag
    error = Signal(str)                          # error message

    def __init__(self, repo: str | None = None, parent: QObject | None = None):
        super().__init__(parent)
        self.repo = repo or get_github_repo()

    def run(self):
        try:
            release_data = fetch_latest_release(self.repo)
            tag_name = release_data.get("tag_name", "")
            if not tag_name:
                self.error.emit("GitHub release does not have a valid tag name.")
                return

            assets = release_data.get("assets", [])
            best_asset = select_best_asset_for_platform(assets) or {}
            is_newer = is_version_newer(tag_name, PROJECT_VERSION)

            if is_newer:
                self.update_available.emit(release_data, best_asset, True)
            else:
                self.up_to_date.emit(PROJECT_VERSION, tag_name)

        except urllib.error.HTTPError as http_err:
            if http_err.code == 404:
                self.error.emit(
                    f"No published releases found for repository '{self.repo}'.\n"
                    "Make sure releases have been published on GitHub."
                )
            elif http_err.code == 403:
                self.error.emit(
                    "GitHub API rate limit exceeded or access forbidden.\n"
                    "Please try again later or visit the GitHub repository in your browser."
                )
            else:
                self.error.emit(f"GitHub API error (HTTP {http_err.code}): {http_err.reason}")
        except urllib.error.URLError as url_err:
            self.error.emit(
                f"Network connection failed: {url_err.reason}.\n"
                "Please verify your internet connection and try again."
            )
        except Exception as exc:
            self.error.emit(f"Failed to check for updates: {exc}")


class DownloadUpdateWorker(QThread):
    """Worker thread that downloads the release asset file with chunked progress."""
    progress = Signal(int, int, int, str)  # percent, downloaded_bytes, total_bytes, speed_str
    finished = Signal(str)                 # downloaded_file_path
    error = Signal(str)                    # error message

    def __init__(self, download_url: str, file_name: str, parent: QObject | None = None):
        super().__init__(parent)
        self.download_url = download_url
        self.file_name = file_name
        self._is_cancelled = False

    def cancel(self):
        self._is_cancelled = True

    def run(self):
        try:
            updates_dir = get_app_data_dir() / "updates"
            updates_dir.mkdir(parents=True, exist_ok=True)
            destination = updates_dir / self.file_name
            temp_dest = destination.with_suffix(destination.suffix + ".download")

            req = urllib.request.Request(
                self.download_url,
                headers={"User-Agent": f"RadioTVSegmenter/{PROJECT_VERSION}"},
            )

            start_time = time.time()
            with urllib.request.urlopen(req, timeout=30) as response:
                total_bytes = int(response.headers.get("Content-Length", 0))
                downloaded = 0
                chunk_size = 64 * 1024

                with open(temp_dest, "wb") as f_out:
                    while True:
                        if self._is_cancelled:
                            f_out.close()
                            if temp_dest.exists():
                                temp_dest.unlink(missing_ok=True)
                            self.error.emit("Download cancelled by user.")
                            return

                        chunk = response.read(chunk_size)
                        if not chunk:
                            break
                        f_out.write(chunk)
                        downloaded += len(chunk)

                        elapsed = time.time() - start_time
                        speed = downloaded / elapsed if elapsed > 0 else 0
                        speed_str = f"{format_byte_size(int(speed))}/s"

                        percent = int((downloaded / total_bytes) * 100) if total_bytes > 0 else 0
                        self.progress.emit(percent, downloaded, total_bytes, speed_str)

            if temp_dest.exists():
                shutil.move(str(temp_dest), str(destination))
                self.finished.emit(str(destination))
            else:
                self.error.emit("Downloaded file could not be finalized.")

        except Exception as exc:
            self.error.emit(f"Download failed: {exc}")


class CheckUpdateDialog(QDialog):
    """User-facing dialog for checking, reviewing, downloading, and installing updates."""

    def __init__(self, parent: QWidget | None = None, auto_start: bool = True):
        super().__init__(parent)
        self.setWindowTitle(f"Check for Updates — {APP_DISPLAY_NAME}")
        self.setMinimumWidth(560)
        self.setMinimumHeight(440)
        self.resize(580, 460)

        self.repo = get_github_repo()
        self.release_info: dict = {}
        self.asset_info: dict = {}
        self.downloaded_path: str | None = None
        self.check_worker: CheckUpdateWorker | None = None
        self.download_worker: DownloadUpdateWorker | None = None

        self._build_ui()

        if auto_start:
            self.start_check()

    def _build_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(20, 20, 20, 20)
        main_layout.setSpacing(14)

        # Header area with icon and title
        header_layout = QHBoxLayout()
        header_layout.setSpacing(14)

        icon = get_app_icon()
        self.icon_label = QLabel()
        if not icon.isNull():
            self.icon_label.setPixmap(icon.pixmap(48, 48))
        self.icon_label.setFixedSize(48, 48)
        header_layout.addWidget(self.icon_label)

        title_vbox = QVBoxLayout()
        title_vbox.setSpacing(2)

        self.title_label = QLabel(APP_DISPLAY_NAME)
        self.title_label.setStyleSheet("font-size: 16px; font-weight: bold;")
        title_vbox.addWidget(self.title_label)

        self.version_label = QLabel(f"Current version: v{PROJECT_VERSION}  •  Repository: {self.repo}")
        self.version_label.setStyleSheet("font-size: 12px; color: #777;")
        title_vbox.addWidget(self.version_label)

        header_layout.addLayout(title_vbox)
        header_layout.addStretch()
        main_layout.addLayout(header_layout)

        # Separator line
        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setFrameShadow(QFrame.Shadow.Sunken)
        main_layout.addWidget(line)

        # Status & Message Area
        self.status_label = QLabel("Connecting to GitHub...")
        self.status_label.setStyleSheet("font-size: 13px; font-weight: 500;")
        main_layout.addWidget(self.status_label)

        # Progress bar (used during check and download)
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 0)  # Indeterminate at start
        self.progress_bar.setTextVisible(True)
        self.progress_bar.setFixedHeight(18)
        main_layout.addWidget(self.progress_bar)

        # Release Notes / Details Box
        self.notes_label = QLabel("Release Notes:")
        self.notes_label.setStyleSheet("font-size: 12px; font-weight: bold; margin-top: 6px;")
        self.notes_label.hide()
        main_layout.addWidget(self.notes_label)

        self.notes_browser = QTextBrowser()
        self.notes_browser.setOpenExternalLinks(True)
        self.notes_browser.setStyleSheet(
            "QTextBrowser { border: 1px solid #ccc; border-radius: 4px; padding: 8px; font-size: 12px; }"
        )
        self.notes_browser.hide()
        main_layout.addWidget(self.notes_browser, 1)

        # Asset info label
        self.asset_info_label = QLabel("")
        self.asset_info_label.setStyleSheet("font-size: 12px; color: #555;")
        self.asset_info_label.hide()
        main_layout.addWidget(self.asset_info_label)

        # Bottom Button Bar
        self.btn_layout = QHBoxLayout()
        self.btn_layout.setSpacing(10)

        self.github_link_btn = QPushButton("View on GitHub")
        self.github_link_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.github_link_btn.clicked.connect(self._open_github_release)
        self.github_link_btn.hide()
        self.btn_layout.addWidget(self.github_link_btn)

        self.btn_layout.addStretch()

        self.action_btn = QPushButton("Check Again")
        self.action_btn.setStyleSheet(
            "QPushButton { font-weight: bold; padding: 6px 16px; }"
        )
        self.action_btn.clicked.connect(self._handle_primary_action)
        self.btn_layout.addWidget(self.action_btn)

        self.close_btn = QPushButton("Close")
        self.close_btn.clicked.connect(self._handle_close)
        self.btn_layout.addWidget(self.close_btn)

        main_layout.addLayout(self.btn_layout)

    def start_check(self):
        """Start querying the GitHub API for updates."""
        self.status_label.setText(f"Checking for updates from {self.repo}...")
        self.progress_bar.show()
        self.progress_bar.setRange(0, 0)
        self.notes_label.hide()
        self.notes_browser.hide()
        self.asset_info_label.hide()
        self.github_link_btn.hide()
        self.action_btn.setEnabled(False)

        self.check_worker = CheckUpdateWorker(self.repo, self)
        self.check_worker.update_available.connect(self._on_update_available)
        self.check_worker.up_to_date.connect(self._on_up_to_date)
        self.check_worker.error.connect(self._on_check_error)
        self.check_worker.start()

    def _on_up_to_date(self, current_ver: str, remote_tag: str):
        self.progress_bar.hide()
        self.status_label.setText(
            f"✓ Radio & TV Segmenter is up to date!\n\n"
            f"You are running version {current_ver}, which is the latest available release ({remote_tag})."
        )
        self.status_label.setStyleSheet("font-size: 13px; color: #2e7d32; font-weight: bold;")
        self.action_btn.setText("Check Again")
        self.action_btn.setEnabled(True)
        self.github_link_btn.show()

    def _on_update_available(self, release_info: dict, asset_info: dict, is_newer: bool):
        self.release_info = release_info
        self.asset_info = asset_info
        tag = release_info.get("tag_name", "Unknown")
        name = release_info.get("name", tag)
        body = release_info.get("body", "No release notes provided.")

        self.progress_bar.hide()
        self.status_label.setText(f"★ A new update is available: {name}")
        self.status_label.setStyleSheet("font-size: 14px; color: #1976d2; font-weight: bold;")

        # Display Release Notes
        self.notes_label.show()
        self.notes_browser.show()
        # Basic HTML formatting for notes
        formatted_body = body.replace("\r\n", "\n").replace("\n", "<br>")
        self.notes_browser.setHtml(
            f"<div style='font-family: sans-serif; line-height: 1.4;'>"
            f"<b>Release:</b> {name} ({tag})<br>"
            f"<hr style='border: 0; border-top: 1px solid #ddd;'>"
            f"{formatted_body}"
            f"</div>"
        )

        # Asset details
        if asset_info and asset_info.get("browser_download_url"):
            asset_name = asset_info.get("name", "installer package")
            asset_size = format_byte_size(asset_info.get("size", 0))
            self.asset_info_label.setText(f"Platform installer: <b>{asset_name}</b> ({asset_size})")
            self.asset_info_label.show()
            self.action_btn.setText("Download and Install")
        else:
            self.asset_info_label.setText("No automated binary package detected for your OS. Visit GitHub to download.")
            self.asset_info_label.show()
            self.action_btn.setText("Open Download Page")

        self.action_btn.setEnabled(True)
        self.github_link_btn.show()

    def _on_check_error(self, message: str):
        self.progress_bar.hide()
        self.status_label.setText(f"Update Check Error:\n{message}")
        self.status_label.setStyleSheet("font-size: 13px; color: #d32f2f;")
        self.action_btn.setText("Retry Check")
        self.action_btn.setEnabled(True)
        self.github_link_btn.show()

    def _handle_primary_action(self):
        btn_text = self.action_btn.text()
        if btn_text in ("Check Again", "Retry Check"):
            self.start_check()
        elif btn_text == "Download and Install":
            self.start_download()
        elif btn_text == "Open Download Page":
            self._open_github_release()
        elif btn_text == "Install & Restart":
            self._install_and_restart()

    def start_download(self):
        """Start downloading the platform installer asset."""
        download_url = self.asset_info.get("browser_download_url")
        file_name = self.asset_info.get("name", f"RadioTVSegmenter-Update-{self.release_info.get('tag_name')}.exe")

        if not download_url:
            self._open_github_release()
            return

        self.status_label.setText(f"Downloading update: {file_name}...")
        self.status_label.setStyleSheet("font-size: 13px; font-weight: bold;")
        self.progress_bar.show()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.action_btn.setEnabled(False)
        self.close_btn.setText("Cancel")

        self.download_worker = DownloadUpdateWorker(download_url, file_name, self)
        self.download_worker.progress.connect(self._on_download_progress)
        self.download_worker.finished.connect(self._on_download_finished)
        self.download_worker.error.connect(self._on_download_error)
        self.download_worker.start()

    def _on_download_progress(self, percent: int, downloaded: int, total: int, speed_str: str):
        self.progress_bar.setValue(percent)
        down_str = format_byte_size(downloaded)
        tot_str = format_byte_size(total) if total > 0 else "unknown"
        self.status_label.setText(f"Downloading update... {down_str} of {tot_str} ({percent}%) • {speed_str}")

    def _on_download_finished(self, file_path: str):
        self.downloaded_path = file_path
        self.progress_bar.setValue(100)
        self.status_label.setText("✓ Download complete! Ready to install.")
        self.status_label.setStyleSheet("font-size: 14px; color: #2e7d32; font-weight: bold;")
        self.action_btn.setText("Install & Restart")
        self.action_btn.setEnabled(True)
        self.close_btn.setText("Later")

    def _on_download_error(self, message: str):
        self.status_label.setText(f"Download Error:\n{message}")
        self.status_label.setStyleSheet("font-size: 13px; color: #d32f2f;")
        self.action_btn.setText("Retry Download")
        self.action_btn.setEnabled(True)
        self.close_btn.setText("Close")

    def _install_and_restart(self):
        """Launch the downloaded installer and cleanly terminate the application."""
        if not self.downloaded_path:
            return

        confirm = QMessageBox.question(
            self,
            "Install Update",
            f"Radio & TV Segmenter will now launch the update installer and exit.\n\n"
            f"Proceed with update?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.Yes,
        )
        if confirm != QMessageBox.StandardButton.Yes:
            return

        success = launch_and_install(self.downloaded_path, parent=self)
        if success:
            self.accept()
            QApplication.instance().quit()

    def _open_github_release(self):
        url = self.release_info.get("html_url") or f"https://github.com/{self.repo}/releases"
        QDesktopServices.openUrl(QUrl(url))

    def _handle_close(self):
        # If the initial GitHub check is still running, detach its signals
        # before closing. The network call it's waiting on can take up to
        # its own timeout to return, so we don't block the UI on it here --
        # but without disconnecting, it would otherwise emit into slots on
        # this dialog after Qt has already torn it down.
        if self.check_worker and self.check_worker.isRunning():
            try:
                self.check_worker.update_available.disconnect(self._on_update_available)
                self.check_worker.up_to_date.disconnect(self._on_up_to_date)
                self.check_worker.error.disconnect(self._on_check_error)
            except Exception:
                pass
        if self.download_worker and self.download_worker.isRunning():
            self.download_worker.cancel()
            self.download_worker.wait(2000)
        self.reject()


class UpdaterMixin:
    """Mixin for MainWindow to provide update checking and startup checks."""

    def check_for_updates(self, interactive: bool = True):
        """Open the Check for Updates dialog."""
        dialog = CheckUpdateDialog(self, auto_start=True)
        if interactive:
            dialog.exec()
        else:
            dialog.show()

    def trigger_silent_update_check(self):
        """Perform a silent background update check without showing UI unless an update is found."""
        try:
            settings = QSettings(INTERNAL_APP_ID, INTERNAL_APP_ID)
            auto_check = str(settings.value("auto_check_updates", "true")).lower() in {"1", "true", "yes"}
            if not auto_check:
                return
        except Exception:
            pass

        repo = get_github_repo()
        worker = CheckUpdateWorker(repo, self)

        def on_update(release_info, asset_info, is_newer):
            if is_newer:
                tag = release_info.get("tag_name", "")
                self.log_activity(f"[UPDATE] New version {tag} available from GitHub.", mark_dirty=False)
                if hasattr(self, "statusBar"):
                    self.statusBar().showMessage(f"★ Update Available: {tag} — Use Help > Check for Updates to install.", 15000)

        worker.update_available.connect(on_update)
        worker.start()
        # Keep reference so it doesn't get garbage collected immediately
        self._silent_update_worker = worker
