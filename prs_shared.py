import html
from bisect import bisect_right
import copy
import hashlib
import json
import re
import struct
import subprocess
import shutil
import sys
import threading
from datetime import datetime
import os
import warnings
import traceback
import tempfile
from pathlib import Path

from docx import Document
from docx.shared import Pt, RGBColor

from faster_whisper import WhisperModel

from html.parser import HTMLParser

from PySide6.QtCore import (
    Qt,
    QUrl,
    Signal,
    QObject,
    QThread,
    QRectF,
    QPointF,
    QEvent,
    QTimer,
    QTime,
    QProcess,
    QProcessEnvironment,
    QSettings,
    QSize,
)

from PySide6.QtGui import (
    QColor,
    QPainter,
    QPen,
    QAction,
    QActionGroup,
    QUndoStack,
    QUndoCommand,
    QKeySequence,
    QPalette,
    QTextCursor,
    QTextCharFormat,
    QTextDocument,
    QShortcut,
    QPixmap,
    QIcon,
    QCursor,
    QDesktopServices,
)

from PySide6.QtWidgets import (
    QApplication,
    QMainWindow,
    QWidget,
    QFileDialog,
    QMessageBox,
    QPushButton,
    QRadioButton,
    QButtonGroup,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QAbstractItemView,
    QTextEdit,
    QTextBrowser,
    QLineEdit,
    QHBoxLayout,
    QVBoxLayout,
    QSplitter,
    QGroupBox,
    QFormLayout,
    QProgressBar,
    QInputDialog,
    QSpinBox,
    QSlider,
    QComboBox,
    QCompleter,
    QToolTip,
    QMenu,
    QDialog,
    QCheckBox,
    QDoubleSpinBox,
    QScrollBar,
    QFrame,
    QStackedWidget,
    QProgressDialog,
    QScrollArea,
    QSizePolicy,
)

from PySide6.QtMultimedia import QMediaPlayer, QAudioOutput
from PySide6.QtMultimediaWidgets import QVideoWidget


class ResizableTextEdit(QWidget):
    """Multi-line text editor defaulted to ~2 lines of height with a drag handle for vertical expansion."""

    def __init__(self, text: str = "", parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)

        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

        self.text_edit = QTextEdit()
        self.text_edit.setPlainText(text)
        self.text_edit.setAcceptRichText(False)
        self.text_edit.setTabChangesFocus(True)
        self.text_edit.setLineWrapMode(QTextEdit.LineWrapMode.WidgetWidth)
        self.text_edit.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.text_edit.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        # Compute ~2 lines height based on font metrics
        fm = self.text_edit.fontMetrics()
        line_height = fm.lineSpacing()
        self._min_h = max(44, line_height * 2 + 12)
        self.text_edit.setFixedHeight(self._min_h)
        self.setFixedHeight(self._min_h + 10)

        # Visual resize grip bar at bottom
        self.grip = QFrame()
        self.grip.setObjectName("resizable_text_grip")
        self.grip.setFixedHeight(8)
        self.grip.setCursor(Qt.CursorShape.SizeVerCursor)
        self.grip.setToolTip("Drag down/up to resize excerpt box")
        self.grip.mousePressEvent = self._grip_press
        self.grip.mouseMoveEvent = self._grip_move
        self.grip.mouseReleaseEvent = self._grip_release

        layout.addWidget(self.text_edit)
        layout.addWidget(self.grip)

        self._resizing = False
        self._start_y = 0
        self._start_h = self._min_h
        self._start_win_h = 0

    def _grip_press(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._resizing = True
            self._start_y = event.globalPosition().y() if hasattr(event, "globalPosition") else event.globalY()
            self._start_h = self.text_edit.height()
            win = self.window()
            if win:
                self._start_win_h = win.height()
            event.accept()

    def _grip_move(self, event):
        if self._resizing:
            global_y = event.globalPosition().y() if hasattr(event, "globalPosition") else event.globalY()
            dy = global_y - self._start_y
            new_h = max(self._min_h, min(450, int(self._start_h + dy)))
            old_h = self.text_edit.height()
            if new_h != old_h:
                self.text_edit.setFixedHeight(new_h)
                self.setFixedHeight(new_h + 10)
                self.updateGeometry()
                win = self.window()
                if win and hasattr(self, "_start_win_h") and self._start_win_h > 0:
                    win_delta = new_h - self._start_h
                    target_win_h = max(win.minimumHeight(), int(self._start_win_h + win_delta))
                    win.resize(win.width(), target_win_h)
                    if win.layout():
                        win.layout().activate()
                    win.updateGeometry()
            event.accept()

    def _grip_release(self, event):
        self._resizing = False
        event.accept()

    def sizeHint(self) -> QSize:
        return QSize(self.text_edit.sizeHint().width(), self.text_edit.height() + 10)

    def minimumSizeHint(self) -> QSize:
        return QSize(self.text_edit.minimumSizeHint().width(), self._min_h + 10)

    def toPlainText(self) -> str:
        return self.text_edit.toPlainText()

    def setPlainText(self, text: str):
        self.text_edit.setPlainText(text)

    def setText(self, text: str):
        self.text_edit.setPlainText(text)

    def setToolTip(self, tip: str):
        self.text_edit.setToolTip(tip)

    def setAcceptRichText(self, accept: bool):
        self.text_edit.setAcceptRichText(accept)

    def setTabChangesFocus(self, tab: bool):
        self.text_edit.setTabChangesFocus(tab)

    def setEnabled(self, enabled: bool):
        super().setEnabled(enabled)
        self.text_edit.setEnabled(enabled)
        self.grip.setEnabled(enabled)

    def setReadOnly(self, ro: bool):
        self.text_edit.setReadOnly(ro)

    @property
    def textChanged(self):
        return self.text_edit.textChanged


# ============================================================
# Application constants
# ============================================================

# Display branding shown to the user (title bar, About box, installers).
APP_DISPLAY_NAME = "Radio & TV Segmenter"
PROJECT_VERSION = "1.7.4"
DEFAULT_GITHUB_REPO = "bradlinder/RTVS"

# Internal identifiers are intentionally left as "RadioTVStorySegmenter" (the
# original project name) rather than renamed to match APP_DISPLAY_NAME: this
# is the QSettings org/app name and the per-user app-data folder name, and
# changing it would orphan existing beta users' saved preferences and
# downloaded Whisper model cache on upgrade. Only user-facing text changes.
INTERNAL_APP_ID = "RadioTVStorySegmenter"

HELPER_PROTOCOL_VERSION = "1.0"
WAVEFORM_ANALYSIS_RATE = 8000
WAVEFORM_POINTS_PER_SECOND = 200
MIN_WORDS_PER_PARAGRAPH = 100
MAX_ACTIVITY_SNAPSHOTS = 50


def get_github_repo() -> str:
    """Return the configured GitHub repository owner/repo string."""
    env_repo = os.environ.get("GITHUB_REPO", "").strip()
    if env_repo:
        return env_repo
    try:
        settings = QSettings(INTERNAL_APP_ID, INTERNAL_APP_ID)
        val = str(settings.value("github_repo", "") or "").strip()
        if val:
            return val
    except Exception:
        pass
    return DEFAULT_GITHUB_REPO


def get_app_data_dir() -> Path:
    """Return the per-user writable application-data directory.

    Installed applications must not write mutable data beside the executable
    (for example, Program Files on Windows).
    """
    if sys.platform == "win32":
        root = os.environ.get("LOCALAPPDATA") or os.environ.get("APPDATA")
        base = Path(root) if root else Path.home() / "AppData" / "Local"
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support"
    else:
        base = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))
    path = base / INTERNAL_APP_ID
    path.mkdir(parents=True, exist_ok=True)
    return path


def get_models_storage_dir() -> Path:
    """Return the directory configured for storing downloaded models.
    Defaults to get_app_data_dir() / 'models' if not customized in settings."""
    settings = QSettings("RadioTVSegmenter", "RadioTVStorySegmenter")
    custom = settings.value("models_dir", "")
    if custom and isinstance(custom, str) and custom.strip():
        p = Path(custom.strip())
        try:
            p.mkdir(parents=True, exist_ok=True)
            return p
        except Exception:
            pass
    default_path = get_app_data_dir() / "models"
    default_path.mkdir(parents=True, exist_ok=True)
    return default_path


def set_models_storage_dir(new_path=None) -> Path:
    """Set and persist a custom models storage directory."""
    settings = QSettings("RadioTVSegmenter", "RadioTVStorySegmenter")
    if not new_path or not str(new_path).strip():
        settings.remove("models_dir")
        target = get_app_data_dir() / "models"
    else:
        p = Path(str(new_path).strip())
        p.mkdir(parents=True, exist_ok=True)
        settings.setValue("models_dir", str(p.resolve()))
        target = p
    hf_dir = target / "huggingface"
    hf_dir.mkdir(parents=True, exist_ok=True)
    os.environ["HF_HOME"] = str(hf_dir.resolve())
    return target


def get_bundled_runtime_dir() -> Path:
    """Locate the installed/bundled runtime resource directory."""
    candidates = []
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        candidates.append(Path(meipass) / "runtime")
    if getattr(sys, "frozen", False):
        candidates.append(Path(sys.executable).resolve().parent / "runtime")
    candidates.append(Path(__file__).resolve().parent / "runtime")
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return candidates[-1]


def find_bundled_executable(name: str) -> str | None:
    """Find a bundled executable first, then fall back to PATH."""
    filename = name + (".exe" if os.name == "nt" and not name.lower().endswith(".exe") else "")
    for root in (get_bundled_runtime_dir() / "bin", get_bundled_runtime_dir()):
        candidate = root / filename
        if candidate.is_file():
            return str(candidate)
    return shutil.which(name)


def ffmpeg_path() -> str | None:
    return find_bundled_executable("ffmpeg")


def ffprobe_path() -> str | None:
    return find_bundled_executable("ffprobe")


def platform_seq(key_str: str) -> QKeySequence:
    """Return a QKeySequence adapted for macOS vs Windows/Linux.

    - Replaces 'Ctrl+' with 'Meta+' (Command ⌘) on macOS.
    - Leaves standard Ctrl/Shift/Alt unmodified on Windows/Linux.
    """
    if sys.platform == "darwin":
        # Meta in Qt key strings corresponds to Command (⌘) on macOS
        key_str = key_str.replace("Ctrl+", "Meta+")
    return QKeySequence(key_str)
    
def get_app_icon() -> QIcon:
    """Return the application QIcon loaded from bundled resources or fallback to empty."""
    icon_paths = []

    # 1. PyInstaller temporary extraction directory (_MEIPASS)
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        p = Path(meipass)
        icon_paths.extend([
            p / "resources" / "icon.ico",
            p / "resources" / "icon.png",
            p / "resources" / "icon.svg",
            p / "icon.ico",
            p / "icon.png",
        ])

    # 2. Frozen binary folder, alongside the exe, and inside _internal/
    if getattr(sys, "frozen", False):
        app_dir = Path(sys.executable).resolve().parent
        icon_paths.extend([
            app_dir / "resources" / "icon.ico",
            app_dir / "resources" / "icon.png",
            app_dir / "resources" / "icon.svg",
            app_dir / "_internal" / "resources" / "icon.ico",
            app_dir / "_internal" / "resources" / "icon.png",
            app_dir / "_internal" / "resources" / "icon.svg",
            app_dir / "icon.ico",
            app_dir / "icon.png",
        ])

    # 3. Source directory
    src_dir = Path(__file__).resolve().parent
    icon_paths.extend([
        src_dir / "resources" / "icon.ico",
        src_dir / "resources" / "icon.png",
        src_dir / "resources" / "icon.svg",
        src_dir / "icon.ico",
        src_dir / "icon.png",
    ])

    for path in icon_paths:
        if path.is_file():
            icon = QIcon(str(path))
            if not icon.isNull():
                return icon

    return QIcon()

def get_license_file_path(filename: str = "NOTICES.txt") -> Path | None:
    """Return the path to a licensing or notice file, checking bundle and source paths."""
    candidates = []
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        candidates.append(Path(meipass) / filename)
        candidates.append(Path(meipass) / "resources" / filename)
    if getattr(sys, "frozen", False):
        app_dir = Path(sys.executable).resolve().parent
        candidates.append(app_dir / filename)
        candidates.append(app_dir / "resources" / filename)
        candidates.append(app_dir.parent / "Resources" / filename)
    src_dir = Path(__file__).resolve().parent
    candidates.append(src_dir / filename)
    candidates.append(src_dir / "resources" / filename)
    for p in candidates:
        if p.is_file():
            return p
    return None


# ============================================================
# Utilities
# ============================================================

def format_time(seconds):
    seconds = max(0, float(seconds))
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    millis = int((seconds - int(seconds)) * 1000)

    if hours:
        return f"{hours:02d}:{minutes:02d}:{secs:02d}.{millis:03d}"
    return f"{minutes:02d}:{secs:02d}.{millis:03d}"


def parse_time(value):
    value = value.strip()
    try:
        return float(value)
    except ValueError:
        pass

    parts = value.split(":")
    if len(parts) == 2:
        return float(parts[0]) * 60 + float(parts[1])
    if len(parts) == 3:
        return (
            float(parts[0]) * 3600
            + float(parts[1]) * 60
            + float(parts[2])
        )
    raise ValueError(f"Invalid time: {value}")


def safe_filename(text):
    text = text.strip()
    if not text:
        text = "Untitled Story"
    text = re.sub(r'[<>:"/\\|?*]', "", text)
    text = re.sub(r"\s+", "_", text)
    return text[:100]


def is_sentence_end(text):
    return bool(re.search(r"[.!?]+[\"'”’)\]]*$", text.strip()))


# ============================================================
# Find & Replace Dialog
# ============================================================

class FindReplaceDialog(QDialog):
    def __init__(self, text_edit, parent=None):
        super().__init__(parent)
        self.text_edit = text_edit
        self.setWindowTitle("Find and Replace")
        self.setFixedWidth(360)

        layout = QVBoxLayout(self)
        form = QFormLayout()

        self.find_input = QLineEdit()
        self.replace_input = QLineEdit()
        self.case_checkbox = QCheckBox("Match Case")

        form.addRow("Find:", self.find_input)
        form.addRow("Replace with:", self.replace_input)
        layout.addLayout(form)
        layout.addWidget(self.case_checkbox)

        btn_layout = QHBoxLayout()
        self.find_next_btn = QPushButton("Find Next")
        self.replace_btn = QPushButton("Replace")
        self.replace_all_btn = QPushButton("Replace All")

        btn_layout.addWidget(self.find_next_btn)
        btn_layout.addWidget(self.replace_btn)
        btn_layout.addWidget(self.replace_all_btn)
        layout.addLayout(btn_layout)

        self.find_next_btn.clicked.connect(self.find_next)
        self.replace_btn.clicked.connect(self.replace)
        self.replace_all_btn.clicked.connect(self.replace_all)

        self.shortcut_find_next = QShortcut(QKeySequence("Ctrl+G"), self)
        self.shortcut_find_next.activated.connect(self.find_next)

    def get_flags(self):
        flags = QTextDocument.FindFlag(0)
        if self.case_checkbox.isChecked():
            flags |= QTextDocument.FindFlag.FindCaseSensitively
        return flags

    def find_next(self):
        target = self.find_input.text()
        if not target:
            return False

        found = self.text_edit.find(target, self.get_flags())
        if not found:
            cursor = self.text_edit.textCursor()
            cursor.movePosition(QTextCursor.Start)
            self.text_edit.setTextCursor(cursor)
            found = self.text_edit.find(target, self.get_flags())

        return found

    def replace(self):
        target = self.find_input.text()
        if not target:
            return

        cursor = self.text_edit.textCursor()
        if cursor.hasSelection():
            cursor.insertText(self.replace_input.text())
        self.find_next()

    def replace_all(self):
        target = self.find_input.text()
        replacement = self.replace_input.text()
        if not target:
            return

        # Perform cursor-based forward pass to prevent infinite matching loops
        cursor = self.text_edit.textCursor()
        cursor.beginEditBlock()
        cursor.movePosition(QTextCursor.Start)
        self.text_edit.setTextCursor(cursor)

        count = 0
        flags = self.get_flags()
        while self.text_edit.find(target, flags):
            match_cursor = self.text_edit.textCursor()
            match_cursor.insertText(replacement)
            count += 1

        cursor.endEditBlock()
        QMessageBox.information(self, "Replace All", f"Replaced {count} occurrence(s).")
        
class ExportDialog(QDialog):
    def __init__(self, parent=None, has_media=True, default_name="export"):
        super().__init__(parent)
        self.has_media = has_media
        self.default_name = default_name
        self.setWindowTitle("Export Options")
        self.setMinimumWidth(380)

        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)

        # Export Scope Selection
        scope_group = QGroupBox("Export Scope")
        scope_layout = QVBoxLayout(scope_group)
        self.scope_combo = QComboBox()
        self.scope_combo.addItem("Full Episode", "full")
        self.scope_combo.addItem("All Stories", "all_stories")
        self.scope_combo.addItem("Selected Stories Only", "selected_stories")
        self.scope_combo.addItem("Full Episode & All Stories", "full_and_all_stories")
        scope_layout.addWidget(self.scope_combo)
        layout.addWidget(scope_group)

        # Export Format Options
        format_group = QGroupBox("Export Formats")
        format_layout = QVBoxLayout(format_group)

        self.txt_checkbox = QCheckBox("Text (.txt)")
        self.txt_checkbox.setChecked(True)

        self.docx_checkbox = QCheckBox("Word Document (.docx)")
        self.docx_checkbox.setChecked(True)

        self.media_checkbox = QCheckBox("Export Audio / Video Clips")
        if not self.has_media:
            self.media_checkbox.setChecked(False)
            self.media_checkbox.setEnabled(False)
            self.media_checkbox.setToolTip("No media file is associated with this document.")
        else:
            self.media_checkbox.setChecked(True)
            self.media_checkbox.setToolTip("Export corresponding media clips for each story segment.")

        format_layout.addWidget(self.txt_checkbox)
        format_layout.addWidget(self.docx_checkbox)
        format_layout.addWidget(self.media_checkbox)
        layout.addWidget(format_group)

        # Base Filename Input
        form_layout = QFormLayout()
        self.filename_input = QLineEdit(self.default_name)
        form_layout.addRow("Base Filename:", self.filename_input)
        layout.addLayout(form_layout)

        # Action Buttons
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        self.export_btn = QPushButton("Export")
        self.cancel_btn = QPushButton("Cancel")
        btn_layout.addWidget(self.export_btn)
        btn_layout.addWidget(self.cancel_btn)
        layout.addLayout(btn_layout)

        # Connections
        self.export_btn.clicked.connect(self.accept)
        self.cancel_btn.clicked.connect(self.reject)

    def get_settings(self):
        return {
            "scope": self.scope_combo.currentData(),
            "txt": self.txt_checkbox.isChecked(),
            "docx": self.docx_checkbox.isChecked(),
            "media": self.media_checkbox.isChecked(),
            "filename": self.filename_input.text().strip() or self.default_name,
        }

# ============================================================
# Data model
# ============================================================

class Story:
    def __init__(
        self,
        start=0,
        end=0,
        title="Untitled Story",
        suggestion=False,
    ):
        self.start = float(start)
        self.end = float(end)
        self.title = title
        self.suggestion = suggestion

    def to_dict(self):
        return {
            "start": self.start,
            "end": self.end,
            "title": self.title,
            "suggestion": self.suggestion,
        }

    @classmethod
    def from_dict(cls, data):
        return cls(
            start=data.get("start", 0),
            end=data.get("end", 0),
            title=data.get("title", "Untitled Story"),
            suggestion=data.get("suggestion", False),
        )


# ============================================================
# Undo / Redo Commands
# ============================================================

class SetStoriesCommand(QUndoCommand):
    def __init__(self, main_window, old_stories, new_stories, description="Modify Stories"):
        super().__init__(description)
        self.main_window = main_window
        self.old_stories = [Story.from_dict(s.to_dict()) for s in old_stories]
        self.new_stories = [Story.from_dict(s.to_dict()) for s in new_stories]

    def undo(self):
        self.main_window.stories = [Story.from_dict(s.to_dict()) for s in self.old_stories]
        self.main_window.refresh_story_list()
        self.main_window.save_project()

    def redo(self):
        self.main_window.stories = [Story.from_dict(s.to_dict()) for s in self.new_stories]
        self.main_window.refresh_story_list()
        self.main_window.save_project()


class SelectStoriesCommand(QUndoCommand):
    def __init__(self, main_window, old_selection, new_selection, description="Change Story Selection"):
        super().__init__(description)
        self.main_window = main_window
        self.old_selection = list(old_selection)
        self.new_selection = list(new_selection)

    def undo(self):
        self.main_window.apply_story_selection_indices(self.old_selection)

    def redo(self):
        self.main_window.apply_story_selection_indices(self.new_selection)


class ProjectStateCommand(QUndoCommand):
    """Undo/redo a complete editable project state.

    This is intentionally broader than story-only undo. Transcript text,
    speaker labels/overrides, translations, diarization and story data all
    travel together so Ctrl+Z / Ctrl+Shift+Z can restore a coherent project.
    """
    def __init__(self, main_window, before_state, after_state, description="Modify Project"):
        super().__init__(description)
        self.main_window = main_window
        # These states are already plain JSON-safe data (dict/list/str/
        # number/bool/None) produced by _capture_project_state(), so a
        # native deepcopy gives the same isolation as the previous
        # json.dumps/json.loads round-trip for a fraction of the CPU cost.
        self.before_state = copy.deepcopy(before_state)
        self.after_state = copy.deepcopy(after_state)

    def undo(self):
        self.main_window._restore_project_state_for_undo(self.before_state)

    def redo(self):
        self.main_window._restore_project_state_for_undo(self.after_state)


# ============================================================
# Custom ListWidget
# ============================================================

class StoryListWidget(QListWidget):
    deleteRequested = Signal()
    exportRequested = Signal()
    exportStoryWordPressRequested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self._show_context_menu)

    def _show_context_menu(self, pos):
        item = self.itemAt(pos)
        if not item:
            return
        menu = QMenu(self)
        export_action = menu.addAction("Export Story...")
        export_action.triggered.connect(self.exportRequested.emit)
        wp_action = menu.addAction("Export Draft to WordPress...")
        wp_action.triggered.connect(self.exportStoryWordPressRequested.emit)
        menu.addSeparator()
        delete_action = menu.addAction("Delete Story")
        delete_action.triggered.connect(self.deleteRequested.emit)
        menu.exec(self.mapToGlobal(pos))

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key.Key_Delete, Qt.Key.Key_Backspace):
            self.deleteRequested.emit()
            event.accept()
            return
        super().keyPressEvent(event)


# ============================================================
# Interactive Transcript Edit Widget
# ============================================================

def transcript_text_view_stylesheet(mode):
    """Shared look for every transcript-style text view (the main editable
    transcript, and the read-only translation / bilingual views), so they
    always match -- same font size, same line height, same theme colors --
    instead of drifting when only one of them gets updated.
    """
    if mode == "light":
        return """
            QTextEdit, QTextBrowser {
                background-color: #ffffff;
                color: #111111;
                border: 1px solid #c5c5cb;
                font-size: 15px;
                line-height: 1.7;
            }
        """
    elif mode == "high_contrast":
        return """
            QTextEdit, QTextBrowser {
                background-color: #000000;
                color: #ffffff;
                border: 2px solid #ffff00;
                font-size: 15px;
                line-height: 1.7;
            }
        """
    return """
        QTextEdit, QTextBrowser {
            background-color: #161b22;
            color: #ffffff;
            border: 1px solid #30363d;
            font-size: 15px;
            line-height: 1.7;
        }
    """


class InteractiveTranscriptEdit(QTextEdit):
    linkClicked = Signal(QUrl)
    editingModeChanged = Signal(bool)
    requestInsertSpeaker = Signal(int, float, str)
    requestSplitAtCursor = Signal(int, float)
    requestRemoveSpeakerAtBlock = Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptRichText(True)
        self.is_editing_mode = False
        self.setReadOnly(True)
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self.show_context_menu)

        self.current_theme = "dark"
        self.active_highlight_anchor = None
        self.anchor_ranges = {}
        self.time_anchor_index = []
        self.time_anchor_starts = []

        self.char_timestamp_map = []
        self._context_menu_cursor_position = None

        # Text selection state and preferences
        self.selection_mode = "replace"  # "replace" or "keep"
        self.saved_selections = []  # List of dicts for multi-selection mode
        self._is_left_down = False
        self._is_left_dragging = False
        self._left_press_pos = None
        self._pending_click_href = None
        self._is_right_down = False
        self._is_right_dragging = False
        self._right_press_pos = None
        self._right_press_cursor_pos = None
        self._suppress_next_context_menu = False

        self.apply_theme_style("dark")

    def set_selection_mode(self, mode):
        self.selection_mode = mode if mode in ("replace", "keep") else "replace"
        if self.selection_mode == "replace" and self.saved_selections:
            self.saved_selections = []
            self.update_extra_selections()

    def set_char_timestamp_map(self, mapping):
        self.char_timestamp_map = mapping

    def has_active_selection(self):
        cursor = self.textCursor()
        if cursor.hasSelection() and (cursor.selectionEnd() - cursor.selectionStart() > 0):
            return True
        if getattr(self, "saved_selections", None) and len(self.saved_selections) > 0:
            return True
        return False

    def clear_all_selections(self):
        cursor = self.textCursor()
        if cursor.hasSelection():
            cursor.clearSelection()
            self.setTextCursor(cursor)
        self.saved_selections = []
        self.setExtraSelections([])
        main_win = self.window()
        if hasattr(main_win, "timeline"):
            main_win.timeline.set_transcript_selection_range(None, None)
        if hasattr(main_win, "statusBar"):
            main_win.statusBar().showMessage("Cleared transcript selection.")

    def get_time_range_for_char_span(self, start_pos, end_pos):
        if not self.char_timestamp_map:
            return None
        s_pos = min(start_pos, end_pos)
        e_pos = max(start_pos, end_pos)
        overlaps = []
        for item in self.char_timestamp_map:
            if len(item) >= 4:
                a, b, ts_start, ts_end = item[0], item[1], item[2], item[3]
            else:
                a, b, ts_start = item
                ts_end = ts_start
            if b > s_pos and a < e_pos:
                overlaps.append((float(ts_start), float(ts_end)))
        if not overlaps:
            return None
        return min(x[0] for x in overlaps), max(x[1] for x in overlaps)

    def get_selected_time_range(self):
        cursor = self.textCursor()
        if cursor.hasSelection():
            s_pos = min(cursor.selectionStart(), cursor.selectionEnd())
            e_pos = max(cursor.selectionStart(), cursor.selectionEnd())
            res = self.get_time_range_for_char_span(s_pos, e_pos)
            if res is not None:
                return res
        if getattr(self, "saved_selections", None):
            return (
                min(s["start_time"] for s in self.saved_selections),
                max(s["end_time"] for s in self.saved_selections),
            )
        return None

    def get_all_selected_story_ranges(self):
        """Returns a list of dicts: [{'start_time': float, 'end_time': float, 'text': str, ...}, ...]"""
        if self.selection_mode == "keep" and self.saved_selections:
            return sorted(self.saved_selections, key=lambda x: x.get("start_time", 0.0))

        cursor = self.textCursor()
        if cursor.hasSelection() and (cursor.selectionEnd() - cursor.selectionStart() > 0):
            s_pos = min(cursor.selectionStart(), cursor.selectionEnd())
            e_pos = max(cursor.selectionStart(), cursor.selectionEnd())
            t_range = self.get_time_range_for_char_span(s_pos, e_pos)
            if not t_range:
                main_win = self.window()
                st = getattr(main_win, "current_position", 0.0)
                t_range = (st, st + 5.0)
            return [{
                "start_char": s_pos,
                "end_char": e_pos,
                "start_time": t_range[0],
                "end_time": t_range[1],
                "text": cursor.selectedText().strip(),
            }]
        return []

    def update_extra_selections(self):
        if not hasattr(self, "saved_selections"):
            self.saved_selections = []
        if not self.saved_selections:
            self.setExtraSelections([])
            return

        fmt = QTextCharFormat()
        if getattr(self, "current_theme", "dark") == "light":
            fmt.setBackground(QColor(186, 215, 255, 170))
            fmt.setForeground(QColor(15, 23, 42))
        else:
            fmt.setBackground(QColor(40, 105, 215, 170))
            fmt.setForeground(QColor(255, 255, 255))

        extras = []
        for sel in self.saved_selections:
            extra = QTextEdit.ExtraSelection()
            extra.format = fmt
            cursor = QTextCursor(self.document())
            cursor.setPosition(sel["start_char"])
            cursor.setPosition(sel["end_char"], QTextCursor.MoveMode.KeepAnchor)
            extra.cursor = cursor
            extras.append(extra)

        self.setExtraSelections(extras)

    def _on_selection_completed(self, cursor):
        if not cursor.hasSelection():
            return
        start_char = min(cursor.selectionStart(), cursor.selectionEnd())
        end_char = max(cursor.selectionStart(), cursor.selectionEnd())
        if end_char <= start_char:
            return

        t_range = self.get_time_range_for_char_span(start_char, end_char)
        if not t_range:
            main_win = self.window()
            start_t = getattr(main_win, "current_position", 0.0)
            end_t = start_t + 5.0
            t_range = (start_t, end_t)

        selected_text = cursor.selectedText().strip()

        if self.selection_mode == "keep":
            # Multi-selection mode: accumulate selections without clearing previous ones
            merged = False
            for s in self.saved_selections:
                if not (end_char < s["start_char"] or start_char > s["end_char"]):
                    s["start_char"] = min(s["start_char"], start_char)
                    s["end_char"] = max(s["end_char"], end_char)
                    merged_tr = self.get_time_range_for_char_span(s["start_char"], s["end_char"])
                    if merged_tr:
                        s["start_time"], s["end_time"] = merged_tr
                    c = QTextCursor(self.document())
                    c.setPosition(s["start_char"])
                    c.setPosition(s["end_char"], QTextCursor.MoveMode.KeepAnchor)
                    s["text"] = c.selectedText().strip()
                    merged = True
                    break
            if not merged:
                self.saved_selections.append({
                    "start_char": start_char,
                    "end_char": end_char,
                    "start_time": t_range[0],
                    "end_time": t_range[1],
                    "text": selected_text
                })

            # Clear active cursor selection so extraSelections render clearly
            temp_cursor = QTextCursor(cursor)
            temp_cursor.clearSelection()
            self.setTextCursor(temp_cursor)
            self.update_extra_selections()

            main_win = self.window()
            if hasattr(main_win, "statusBar"):
                count = len(self.saved_selections)
                main_win.statusBar().showMessage(f"Selected {count} sections. Right-click or click 'Add Story' to save.")
        else:
            # Single selection mode: replace previous selection
            self.saved_selections = []
            self.setExtraSelections([])
            main_win = self.window()
            if hasattr(main_win, "timeline") and t_range:
                main_win.timeline.set_transcript_selection_range(t_range[0], t_range[1])
            if hasattr(main_win, "statusBar") and t_range:
                main_win.statusBar().showMessage(f"Transcript selection: {format_time(t_range[0])} – {format_time(t_range[1])}")

    def apply_theme_style(self, mode):
        self.current_theme = mode
        self.setStyleSheet(transcript_text_view_stylesheet(mode))
        self.update_extra_selections()

    def set_editing_mode(self, enabled):
        if self.is_editing_mode == enabled:
            return
        self.is_editing_mode = enabled
        self.setReadOnly(not enabled)
        if enabled:
            self.clear_highlight()
        self.editingModeChanged.emit(enabled)

    def mousePressEvent(self, event):
        if self.is_editing_mode:
            super().mousePressEvent(event)
            return

        pos = event.position().toPoint() if hasattr(event, "position") else event.pos()

        if event.button() == Qt.MouseButton.LeftButton:
            self._left_press_pos = pos
            self._is_left_down = True
            self._is_left_dragging = False
            self._pending_click_href = None

            # Check if clicked on a timestamp/word link
            hit_cursor = self.cursorForPosition(pos)
            href = hit_cursor.charFormat().anchorHref()
            if not href and hit_cursor.position() > 0:
                probe = QTextCursor(hit_cursor)
                probe.setPosition(max(0, hit_cursor.position() - 1))
                href = probe.charFormat().anchorHref()

            if href and (href.startswith("word:") or href.startswith("time:")):
                self._pending_click_href = href

            if self.selection_mode == "replace" and self.saved_selections:
                self.saved_selections = []
                self.update_extra_selections()

            super().mousePressEvent(event)
            return

        elif event.button() == Qt.MouseButton.RightButton:
            self._right_press_pos = pos
            self._is_right_down = True
            self._is_right_dragging = False
            self._right_press_cursor_pos = self.cursorForPosition(pos).position()
            self._suppress_next_context_menu = False
            event.accept()
            return

        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self.is_editing_mode:
            super().mouseMoveEvent(event)
            return

        pos = event.position().toPoint() if hasattr(event, "position") else event.pos()
        drag_dist = QApplication.startDragDistance() if hasattr(QApplication, "startDragDistance") else 4
        if drag_dist < 4:
            drag_dist = 4

        if getattr(self, "_is_left_down", False):
            press_pos = getattr(self, "_left_press_pos", pos)
            if (pos - press_pos).manhattanLength() >= drag_dist:
                self._is_left_dragging = True
            super().mouseMoveEvent(event)
            return

        if getattr(self, "_is_right_down", False):
            press_pos = getattr(self, "_right_press_pos", pos)
            if (pos - press_pos).manhattanLength() >= drag_dist:
                self._is_right_dragging = True
                curr_pos = self.cursorForPosition(pos).position()
                start_pos = getattr(self, "_right_drag_start_cursor_pos", curr_pos)

                cursor = QTextCursor(self.document())
                cursor.setPosition(start_pos)
                cursor.setPosition(curr_pos, QTextCursor.MoveMode.KeepAnchor)
                self.setTextCursor(cursor)
                event.accept()
                return

        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if self.is_editing_mode:
            super().mouseReleaseEvent(event)
            return

        pos = event.position().toPoint() if hasattr(event, "position") else event.pos()

        if event.button() == Qt.MouseButton.LeftButton:
            was_dragging = getattr(self, "_is_left_dragging", False)
            self._is_left_down = False
            self._is_left_dragging = False
            pending_href = getattr(self, "_pending_click_href", None)
            self._pending_click_href = None

            super().mouseReleaseEvent(event)

            cursor = self.textCursor()
            has_sel = cursor.hasSelection() and (cursor.selectionEnd() - cursor.selectionStart() > 0)

            if not was_dragging and not has_sel:
                # Single Left-Click without dragging -> seek/navigation
                if self.selection_mode == "replace":
                    self.clear_all_selections()

                if pending_href and (pending_href.startswith("word:") or pending_href.startswith("time:")):
                    self.linkClicked.emit(QUrl(pending_href))
                    event.accept()
                    return
                else:
                    hit_cursor = self.cursorForPosition(pos)
                    href = hit_cursor.charFormat().anchorHref()
                    if href and (href.startswith("word:") or href.startswith("time:")):
                        self.linkClicked.emit(QUrl(href))
                        event.accept()
                        return
            else:
                # Left-drag selection completed
                if has_sel:
                    self._on_selection_completed(cursor)
                event.accept()
                return

        elif event.button() == Qt.MouseButton.RightButton:
            was_right_dragging = getattr(self, "_is_right_dragging", False)
            self._is_right_down = False
            self._is_right_dragging = False

            if was_right_dragging:
                self._suppress_next_context_menu = True
                cursor = self.textCursor()
                if cursor.hasSelection() and (cursor.selectionEnd() - cursor.selectionStart() > 0):
                    self._on_selection_completed(cursor)
                event.accept()
                return
            else:
                self._suppress_next_context_menu = False
                self.show_context_menu(pos)
                event.accept()
                return

        super().mouseReleaseEvent(event)

    def _nearest_word_anchor(self, cursor):
        """Return the word anchor nearest the actual QTextDocument cursor."""
        pos = cursor.position()
        best = None
        best_distance = None
        for href, (start_pos, end_pos) in self.anchor_ranges.items():
            if not href.startswith("word:"):
                continue
            if start_pos <= pos <= end_pos:
                distance = 0
            elif pos < start_pos:
                distance = start_pos - pos
            else:
                distance = pos - end_pos
            if best_distance is None or distance < best_distance:
                parts = href.split(":")
                if len(parts) >= 3 and parts[2].isdigit():
                    try:
                        best = (float(parts[1]), int(parts[2]), href)
                        best_distance = distance
                    except ValueError:
                        pass

        # Fallback to char_timestamp_map if anchor_ranges has no match
        if best is None and getattr(self, "char_timestamp_map", None):
            for entry in self.char_timestamp_map:
                c_start, c_end = entry[0], entry[1]
                ts = entry[2]
                s_idx = entry[4] if len(entry) >= 5 else None
                if c_start <= pos <= c_end and s_idx is not None:
                    return (float(ts), int(s_idx), f"word:{ts}:{s_idx}")

        return best

    def get_timestamp_at_cursor(self, cursor):
        nearest = self._nearest_word_anchor(cursor)
        if nearest is not None:
            return nearest[0]
        # Search the current block in the document for any anchor
        block = cursor.block()
        it = block.begin()
        while not it.atEnd():
            frag = it.fragment()
            if frag.isValid():
                href = frag.charFormat().anchorHref()
                if href and href.startswith("word:"):
                    parts = href.split(":")
                    if len(parts) >= 2:
                        try:
                            return float(parts[1])
                        except ValueError:
                            pass
            it += 1
        main_win = self.window()
        return getattr(main_win, "current_position", 0.0)

    def get_segment_index_at_cursor(self, cursor):
        nearest = self._nearest_word_anchor(cursor)
        if nearest is not None:
            return nearest[1]
        # Search current block for segment index
        block = cursor.block()
        it = block.begin()
        while not it.atEnd():
            frag = it.fragment()
            if frag.isValid():
                href = frag.charFormat().anchorHref()
                if href and href.startswith("word:"):
                    parts = href.split(":")
                    if len(parts) >= 3 and parts[2].isdigit():
                        return int(parts[2])
                elif href and href.startswith("speaker:"):
                    parts = href.split(":")
                    if len(parts) >= 2 and parts[1].isdigit():
                        return int(parts[1])
            it += 1
        return None

    def move_cursor_to_segment_start(self, seg_idx):
        """Best-effort: places the caret at the first word of seg_idx after
        a render_transcript() refresh, so editing can continue in place."""
        target_href = None
        for _start, _end, href in self.time_anchor_index:
            if href.endswith(f":{seg_idx}"):
                target_href = href
                break
        if not target_href:
            return
        positions = self.anchor_ranges.get(target_href)
        if not positions:
            return
        cursor = QTextCursor(self.document())
        cursor.setPosition(positions[0])
        self.setTextCursor(cursor)
        self.ensureCursorVisible()

    def keyPressEvent(self, event):
        # The application owns undo/redo for project edits.  Do this before
        # QTextEdit's native undo stack so Ctrl+Z / Ctrl+Shift+Z is consistent
        # with speaker-label, story and other project-state operations.
        if event.matches(QKeySequence.StandardKey.Undo):
            main_win = self.window()
            if hasattr(main_win, "flush_pending_transcript_undo"):
                main_win.flush_pending_transcript_undo()
            if hasattr(main_win, "undo_stack"):
                main_win.undo_stack.undo()
                event.accept()
                return
        if event.matches(QKeySequence.StandardKey.Redo):
            main_win = self.window()
            if hasattr(main_win, "flush_pending_transcript_undo"):
                main_win.flush_pending_transcript_undo()
            if hasattr(main_win, "undo_stack"):
                main_win.undo_stack.redo()
                event.accept()
                return

        if self.is_editing_mode and event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            cursor = self.textCursor()

            if event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
                # Shift+Enter: add a speaker label break (split the segment here).
                seg_idx = self.get_segment_index_at_cursor(cursor)
                if seg_idx is None:
                    seg_idx = cursor.blockNumber()
                split_time = self.get_timestamp_at_cursor(cursor)
                self.requestSplitAtCursor.emit(seg_idx, split_time)
                event.accept()
                return

            ts = self.get_timestamp_at_cursor(cursor)
            time_str = format_time(ts)

            cursor.insertBlock()

            ts_html = (
                f'<a href="time:{ts}" style="color:#8b949e !important; text-decoration:none;">'
                f'<b>{time_str}</b></a>&nbsp;'
            )
            cursor.insertHtml(ts_html)
            event.accept()
            return

        if self.is_editing_mode and event.key() == Qt.Key.Key_Backspace and self.textCursor().atBlockStart():
            cursor = self.textCursor()
            seg_idx = self.get_segment_index_at_cursor(cursor)
            if seg_idx is not None and seg_idx > 0:
                self.requestRemoveSpeakerAtBlock.emit(seg_idx)
                event.accept()
                return

        if event.key() == Qt.Key.Key_Escape:
            if self.has_active_selection():
                self.clear_all_selections()
                event.accept()
                return
            if self.is_editing_mode:
                self.set_editing_mode(False)
                event.accept()
                return

        if event.matches(QKeySequence.StandardKey.Find):
            main_win = self.window()
            if hasattr(main_win, "open_find_replace"):
                main_win.open_find_replace()
                event.accept()
                return

        super().keyPressEvent(event)

    def show_context_menu(self, position):
        """Context menu for both viewing and editing modes.  Speaker labels
        are interactive targets, while right-clicking anywhere else offers a
        speaker insertion at the nearest transcript timestamp.
        """
        if getattr(self, "_suppress_next_context_menu", False):
            self._suppress_next_context_menu = False
            return

        hit_cursor = self.cursorForPosition(position)
        href = hit_cursor.charFormat().anchorHref()
        if not href and hit_cursor.position() > 0:
            probe = QTextCursor(hit_cursor)
            probe.setPosition(max(0, hit_cursor.position() - 1))
            href = probe.charFormat().anchorHref()

        speaker_target = None
        if href and href.startswith("speaker:"):
            parts = href.split(":", 2)
            if len(parts) >= 3 and parts[1].isdigit():
                speaker_target = (int(parts[1]), parts[2])

        # Preserve active text selection when right-clicking so the user can easily
        # add the selection to a story, play it, or clear it from the context menu.
        if not self.has_active_selection():
            self.setTextCursor(hit_cursor)

        # Store the exact document position that opened the menu.  QAction
        # execution can otherwise move the QTextCursor, which used to make a
        # speaker insertion land at an unrelated earlier timestamp.
        self._context_menu_cursor_position = hit_cursor.position()

        menu = self.createStandardContextMenu() if self.is_editing_mode else QMenu(self)
        main_win = self.window()

        if self.has_active_selection():
            ranges = self.get_all_selected_story_ranges()
            count = len(ranges)
            title = f"Add Selected Sections to New Stories ({count})" if count > 1 else "Add Selected Text to New Story"
            add_selection = QAction(title, self)
            add_selection.triggered.connect(lambda: main_win.add_selection_to_story())
            menu.addAction(add_selection)

            play_selection = QAction("Play Selected Text", self)
            play_selection.triggered.connect(lambda: main_win.play_transcript_selection())
            menu.addAction(play_selection)

            clear_selection = QAction("Clear Selection", self)
            clear_selection.setShortcut(QKeySequence("Esc"))
            clear_selection.triggered.connect(self.clear_all_selections)
            menu.addAction(clear_selection)

            menu.addSeparator()

        # Speaker controls are deliberately available in BOTH modes.
        if speaker_target:
            seg_idx, raw_speaker = speaker_target
            
            change_menu = menu.addMenu("Change Speaker To")
            known_speakers = []
            if hasattr(main_win, "get_all_known_speakers"):
                known_speakers = main_win.get_all_known_speakers()
            for spk in known_speakers:
                action = change_menu.addAction(spk)
                action.triggered.connect(
                    lambda _, i=seg_idx, s=raw_speaker, name=spk: main_win.execute_speaker_rename(i, s, name)
                )
            change_menu.addSeparator()
            new_change_action = change_menu.addAction("Add New Speaker...")
            new_change_action.triggered.connect(
                lambda _, i=seg_idx, s=raw_speaker: main_win.execute_speaker_rename(i, s, "__NEW__")
            )

            remove_action = QAction("Remove Speaker Label", self)
            remove_action.setEnabled(seg_idx > 0)
            remove_action.triggered.connect(
                lambda _, i=seg_idx: main_win.remove_speaker_label_at_segment(i)
            )
            menu.addAction(remove_action)
            menu.addSeparator()

        insert_menu = menu.addMenu("Add Speaker Label Here")
        target_cursor = hit_cursor
        target_seg_idx = self.get_segment_index_at_cursor(target_cursor)
        if target_seg_idx is None:
            target_seg_idx = target_cursor.blockNumber()
        target_time = self.get_timestamp_at_cursor(target_cursor)

        known_speakers = []
        if hasattr(main_win, "get_all_known_speakers"):
            known_speakers = main_win.get_all_known_speakers()
        for spk in known_speakers:
            action = insert_menu.addAction(spk)
            action.triggered.connect(
                lambda _, s=target_seg_idx, t=target_time, name=spk: self.requestInsertSpeaker.emit(s, t, name)
            )
        insert_menu.addSeparator()
        new_spk_action = insert_menu.addAction("Add New Speaker...")
        new_spk_action.triggered.connect(
            lambda _, s=target_seg_idx, t=target_time: self.requestInsertSpeaker.emit(s, t, "__NEW__")
        )

        if not self.is_editing_mode:
            add_vocab = QAction("Add Selected Text to Glossary", self)
            add_vocab.setEnabled(self.has_active_selection())
            def _add_vocab_from_selection():
                ranges = self.get_all_selected_story_ranges()
                txt = ranges[0]["text"] if ranges else self.textCursor().selectedText()
                main_win.add_to_glossary(txt)
            add_vocab.triggered.connect(_add_vocab_from_selection)
            menu.addAction(add_vocab)

            edit_action = QAction("Edit Transcript", self)
            edit_action.triggered.connect(lambda: self.set_editing_mode(True))
            menu.addAction(edit_action)
        else:
            find_action = QAction("Find and Replace...", self)
            find_action.setShortcut(QKeySequence.StandardKey.Find)
            find_action.triggered.connect(lambda: main_win.open_find_replace())
            menu.addAction(find_action)

            menu.addSeparator()
            exit_action = QAction("Exit Editing Mode", self)
            exit_action.triggered.connect(lambda: self.set_editing_mode(False))
            menu.addAction(exit_action)

        menu.exec(self.mapToGlobal(position))

    def rebuild_anchor_index(self):
        """Index transcript anchors once so playback highlighting is O(1) lookup."""
        self.anchor_ranges = {}
        doc = self.document()
        block = doc.begin()
        while block.isValid():
            it = block.begin()
            while not it.atEnd():
                fragment = it.fragment()
                if fragment.isValid():
                    href = fragment.charFormat().anchorHref()
                    if href:
                        self.anchor_ranges[href] = (
                            fragment.position(),
                            fragment.position() + fragment.length(),
                        )
                it += 1
            block = block.next()

    def set_time_anchor_index(self, entries):
        self.time_anchor_index = sorted(entries, key=lambda item: item[0])
        self.time_anchor_starts = [item[0] for item in self.time_anchor_index]

    def clear_highlight(self):
        if not self.active_highlight_anchor:
            return

        positions = self.anchor_ranges.get(self.active_highlight_anchor)
        if positions:
            doc = self.document()
            cursor = QTextCursor(doc)
            cursor.setPosition(positions[0])
            cursor.setPosition(positions[1], QTextCursor.KeepAnchor)
            clean_fmt = QTextCharFormat()
            clean_fmt.setAnchor(True)
            clean_fmt.setAnchorHref(self.active_highlight_anchor)
            # Restore regular theme text color
            if self.current_theme == "light":
                clean_color = "#111111"
            elif self.current_theme == "high_contrast":
                clean_color = "#ffffff"
            else:
                clean_color = "#ffffff"
            clean_fmt.setForeground(QColor(clean_color))
            cursor.setCharFormat(clean_fmt)

        self.active_highlight_anchor = None

    def highlight_word_at_time(self, seconds, transcript_data):
        if self.is_editing_mode or not transcript_data:
            return

        target_anchor = None
        if self.time_anchor_index:
            idx = bisect_right(self.time_anchor_starts, seconds) - 1
            if idx >= 0:
                start_time, end_time, anchor = self.time_anchor_index[idx]
                # Allow a small tolerance window or match if within the timestamp block
                if start_time <= seconds <= end_time or (seconds - end_time) < 0.3:
                    target_anchor = anchor
            elif self.time_anchor_starts and seconds < self.time_anchor_starts[0]:
                target_anchor = self.time_anchor_index[0][2]

        if not target_anchor or target_anchor == self.active_highlight_anchor:
            return

        self.clear_highlight()

        doc = self.document()
        positions = self.anchor_ranges.get(target_anchor)
        if not positions:
            self.rebuild_anchor_index()
            positions = self.anchor_ranges.get(target_anchor)

        target_cursor = None
        if positions:
            target_cursor = QTextCursor(doc)
            target_cursor.setPosition(positions[0])
            target_cursor.setPosition(positions[1], QTextCursor.KeepAnchor)
            
            # Apply active highlight style (e.g., bright blue or accent color highlight)
            highlight_fmt = QTextCharFormat()
            highlight_fmt.setAnchor(True)
            highlight_fmt.setAnchorHref(target_anchor)
            if self.current_theme == "light":
                highlight_color = "#0056b3"
            elif self.current_theme == "high_contrast":
                highlight_color = "#ffff00"
            else:
                highlight_color = "#58a6ff"
            highlight_fmt.setForeground(QColor(highlight_color)) # Accent highlight color
            target_cursor.setCharFormat(highlight_fmt)

        if target_cursor:
            self.active_highlight_anchor = target_anchor

            cursor_rect = self.cursorRect(target_cursor)
            viewport_rect = self.viewport().rect()
            v_scroll = self.verticalScrollBar()

            if cursor_rect.bottom() > viewport_rect.bottom():
                v_scroll.setValue(v_scroll.value() + viewport_rect.height() // 3)
            elif cursor_rect.top() < viewport_rect.top():
                v_scroll.setValue(max(0, v_scroll.value() - viewport_rect.height() // 3))

# ============================================================
# Document Reading Utilities
# ============================================================

def read_document_text(path: Path) -> str:
    ext = path.suffix.lower()

    if ext == ".docx":
        doc = Document(str(path))
        return "\n".join(p.text for p in doc.paragraphs)

    elif ext == ".pdf":
        text_pages = []
        try:
            import pypdf
            reader = pypdf.PdfReader(str(path))
            for page in reader.pages:
                extracted = page.extract_text()
                if extracted:
                    text_pages.append(extracted)
            return "\n".join(text_pages)
        except ImportError:
            try:
                import PyPDF2
                reader = PyPDF2.PdfReader(str(path))
                for page in reader.pages:
                    extracted = page.extract_text()
                    if extracted:
                        text_pages.append(extracted)
                return "\n".join(text_pages)
            except ImportError:
                try:
                    import pdfplumber
                    with pdfplumber.open(str(path)) as pdf:
                        for page in pdf.pages:
                            extracted = page.extract_text()
                            if extracted:
                                text_pages.append(extracted)
                    return "\n".join(text_pages)
                except ImportError:
                    raise RuntimeError(
                        "PDF support requires 'pypdf'. Install it with:\npip install pypdf"
                    )

    elif ext in (".html", ".htm"):
        try:
            raw_html = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            raw_html = path.read_text(encoding="utf-8-sig", errors="ignore")

        class HTMLTextParser(HTMLParser):
            def __init__(self):
                super().__init__()
                self.pieces = []
            def handle_data(self, data):
                self.pieces.append(data)

        parser = HTMLTextParser()
        parser.feed(raw_html)
        return "".join(parser.pieces)

    else:
        try:
            return path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            try:
                return path.read_text(encoding="utf-8-sig")
            except UnicodeDecodeError:
                return path.read_text(encoding="latin-1", errors="replace")


# ============================================================
# Story Auto-Detection VAD Worker
# ============================================================

class StoryAutoDetectWorker(QObject):
    finished = Signal(list)
    progress = Signal(str, int)
    error = Signal(str)

    def __init__(self, audio_file, silence_threshold=3.0, lead_in_padding=0.5, audio_duration=0, transcript_segments=None, whisper_model="tiny", **kwargs):
        super().__init__()
        self.audio_file = str(audio_file)
        self.silence_threshold = float(silence_threshold)
        self.lead_in_padding = float(lead_in_padding)
        self.audio_duration = float(audio_duration)
        self.transcript_segments = transcript_segments or []
        self.whisper_model = whisper_model or "tiny"
        self._is_cancelled = False

    def cancel(self):
        self._is_cancelled = True

    def run(self):
        try:
            speech_chunks = []
            if self.transcript_segments:
                self.progress.emit("[Step 1/3] Using transcript timestamps for instant story detection...", 30)
                for seg in self.transcript_segments:
                    start = seg.get("start", 0.0) if isinstance(seg, dict) else getattr(seg, "start", 0.0)
                    end = seg.get("end", start) if isinstance(seg, dict) else getattr(seg, "end", start)
                    if end > start:
                        speech_chunks.append((float(start), float(end)))

            if not speech_chunks:
                # Story detection falls back to faster-whisper VAD-enabled speech segmentation
                self.progress.emit("[Step 1/3] Loading CPU Voice Activity Detection (Whisper VAD)...", 20)
                model_name = self.whisper_model if self.whisper_model else "tiny"
                model = WhisperModel(model_name, device="cpu", compute_type="int8", download_root=str(get_models_storage_dir()))

                if self._is_cancelled:
                    self.error.emit("Process canceled by user.")
                    return

                self.progress.emit("[Step 2/3] Analyzing speech intervals and audio gaps...", 50)

                segments, info = model.transcribe(
                    self.audio_file,
                    vad_filter=True,
                    vad_parameters=dict(min_silence_duration_ms=int(self.silence_threshold * 1000)),
                )

                for seg in segments:
                    if self._is_cancelled:
                        self.error.emit("Process canceled by user.")
                        return
                    speech_chunks.append((seg.start, seg.end))

            self.progress.emit("[Step 3/3] Clustering speech boundaries into stories...", 85)

            if not speech_chunks:
                self.finished.emit([])
                return

            detected_stories = []
            curr_start = max(0.0, speech_chunks[0][0] - self.lead_in_padding)
            curr_end = speech_chunks[0][1]

            for idx in range(1, len(speech_chunks)):
                prev_end = speech_chunks[idx - 1][1]
                next_start = speech_chunks[idx][0]
                gap = next_start - prev_end

                if gap >= self.silence_threshold:
                    detected_stories.append(Story(
                        start=curr_start,
                        end=curr_end + self.lead_in_padding,
                        title=f"Story {len(detected_stories) + 1}"
                    ))
                    curr_start = max(0.0, next_start - self.lead_in_padding)
                    curr_end = speech_chunks[idx][1]
                else:
                    curr_end = speech_chunks[idx][1]

            if curr_start < curr_end:
                detected_stories.append(Story(
                    start=curr_start,
                    end=curr_end + self.lead_in_padding,
                    title=f"Story {len(detected_stories) + 1}"
                ))

            self.progress.emit("Story detection complete.", 100)
            self.finished.emit(detected_stories)

        except Exception as exc:
            if not self._is_cancelled:
                self.error.emit(str(exc))

# ============================================================
# Transcription worker
# ============================================================

# Transcription is executed by the same isolated local helper process used
# for Speaker Detection. This keeps ML model loading out of the Qt GUI process.



# ============================================================
# Speaker diarization worker
# ============================================================



# ============================================================
# Waveform Extraction Worker (48,000 Samples)
# ============================================================

class WaveformWorker(QObject):
    finished = Signal(list, bool)

    def __init__(self, audio_file, points_per_second=WAVEFORM_POINTS_PER_SECOND):
        super().__init__()
        self.audio_file = str(audio_file)
        self.points_per_second = points_per_second
        self._cancel_event = threading.Event()
        self._process = None

    def cancel(self):
        """Thread-safe cancellation request; also stops the FFmpeg child process."""
        self._cancel_event.set()
        process = self._process
        if process is not None and process.poll() is None:
            try:
                process.kill()
            except Exception:
                pass

    def run(self):
        """Build a compact peak envelope without loading the whole recording into RAM."""
        process = None
        try:
            # Keep the waveform envelope bounded for multi-hour recordings.
            # We still stream decoded PCM through FFmpeg; only the compact peak
            # envelope is retained in memory.
            effective_pps = int(self.points_per_second)
            try:
                probe = subprocess.run(
                    [ffprobe_path() or "ffprobe", "-v", "error", "-show_entries", "format=duration",
                     "-of", "default=noprint_wrappers=1:nokey=1", self.audio_file],
                    stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True, timeout=10, check=True,
                )
                duration = float(probe.stdout.strip() or 0)
                max_points = 800_000
                if duration > 0 and duration * effective_pps > max_points:
                    effective_pps = max(20, int(max_points / duration))
            except Exception:
                pass
            samples_per_peak = max(1, WAVEFORM_ANALYSIS_RATE // max(1, effective_pps))
            cmd = [
                ffmpeg_path() or "ffmpeg", "-i", self.audio_file,
                "-f", "s16le", "-ac", "1",
                "-ar", str(WAVEFORM_ANALYSIS_RATE),
                "-v", "quiet", "pipe:1",
            ]
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                bufsize=1024 * 1024,
            )
            self._process = process

            peaks = []
            max_possible_val = 32768.0
            samples_in_peak = 0
            peak_value = 0

            while True:
                if self._cancel_event.is_set():
                    try:
                        process.kill()
                    except Exception:
                        pass
                    process.wait()
                    self.finished.emit([], True)
                    return

                raw = process.stdout.read(64 * 1024)
                if not raw:
                    break

                if self._cancel_event.is_set():
                    try:
                        process.kill()
                    except Exception:
                        pass
                    process.wait()
                    self.finished.emit([], True)
                    return

                sample_count = len(raw) // 2
                if sample_count:
                    samples = struct.unpack(f"<{sample_count}h", raw[:sample_count * 2])
                    for sample in samples:
                        peak_value = max(peak_value, abs(sample))
                        samples_in_peak += 1
                        if samples_in_peak == samples_per_peak:
                            peaks.append(peak_value / max_possible_val)
                            samples_in_peak = 0
                            peak_value = 0

            return_code = process.wait()
            if self._cancel_event.is_set():
                self.finished.emit([], True)
                return
            if return_code != 0:
                self.finished.emit([], False)
                return

            if samples_in_peak:
                peaks.append(peak_value / max_possible_val)

            self.finished.emit(peaks, False)
        except Exception:
            if process is not None:
                try:
                    process.kill()
                    process.wait()
                except Exception:
                    pass
            self.finished.emit([], self._cancel_event.is_set())
        finally:
            self._process = None


# ============================================================
# Timeline Canvas (With Right-Click Select & Easy Playhead Scrubbing)
# ============================================================

# ============================================================
# Timeline Canvas (With Right-Click Select & Easy Playhead Scrubbing)
# ============================================================

class VideoThumbnailWorker(QObject):
    finished = Signal(object)
    error = Signal(str)

    def __init__(self, media_path, duration, output_dir, count=36):
        super().__init__()
        self.media_path = Path(media_path)
        self.duration = max(0.1, float(duration or 0))
        self.output_dir = Path(output_dir)
        self.count = max(8, min(48, int(count)))
        self._cancelled = False
        self._process = None

    def cancel(self):
        self._cancelled = True
        process = self._process
        if process is not None and process.poll() is None:
            try:
                process.kill()
            except Exception:
                pass

    def run(self):
        try:
            self.output_dir.mkdir(parents=True, exist_ok=True)
            fps = self.count / self.duration
            vf = f"fps={fps:.8f},scale=180:-2:force_original_aspect_ratio=decrease"
            pattern = str(self.output_dir / "thumb_%03d.jpg")
            cmd = [ffmpeg_path() or "ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", str(self.media_path), "-vf", vf, "-q:v", "4", pattern]
            self._process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            _stdout, stderr = self._process.communicate()
            returncode = self._process.returncode
            if self._cancelled:
                self.finished.emit([])
                return
            if returncode != 0:
                raise RuntimeError(stderr.strip() or "FFmpeg could not create video thumbnails.")
            files = sorted(self.output_dir.glob("thumb_*.jpg"))
            if not files:
                raise RuntimeError("No video thumbnails were generated.")
            actual_count = len(files)
            items = []
            for i, path in enumerate(files):
                if self._cancelled:
                    break
                timestamp = (i / max(1, actual_count - 1)) * self.duration if actual_count > 1 else 0.0
                items.append((timestamp, str(path)))
            self.finished.emit(items)
        except Exception as exc:
            if not self._cancelled:
                self.error.emit(str(exc))
            else:
                self.finished.emit([])
        finally:
            self._process = None


class TimelineCanvas(QWidget):
    positionClicked = Signal(float)
    scrubPositionChanged = Signal(float)
    storyRegionUpdated = Signal(int, float, float)
    newRegionStarted = Signal(float, float)
    newRegionUpdated = Signal(float, float)
    multiSelectionChanged = Signal(list)
    dragOperationFinished = Signal()
    scrollOffsetChanged = Signal(float)
    zoomChanged = Signal()
    mediaDropped = Signal(str)
    selectionRangeChanged = Signal(object, object)
    storyCreatedFromSelection = Signal(float, float)

    RULER_HEIGHT = 24
    EDGE_HANDLE_THRESHOLD = 8
    CURSOR_GRAB_THRESHOLD = 12
    DRAG_PIXEL_THRESHOLD = 5

    def __init__(self, parent=None):
        super().__init__(parent)

        self.duration = 1
        self.position = 0
        self.skip_seconds = 5
        self.is_playing = False
        self.audio_file_name = None

        self.selection_start = None
        self.selection_end = None
        self.is_right_dragging = False
        self.active_selection_handle = None

        self.stories = []
        self.waveform_peaks = []
        self.waveform_levels = []
        self.video_thumbnails = []
        self.show_waveform = True
        self.show_thumbnails = True
        self.thumbnail_position = "above"
        self.selected_story_indices = []
        self.transcript_selection_range = None

        self.zoom_level = 1.0
        self.min_zoom = 1.0
        self.max_zoom = 80.0
        self.scroll_offset = 0.0

        self.is_panning = False
        self.pan_start_x = 0
        self.pan_start_offset = 0.0

        self.is_left_down = False
        self.is_scrubbing = False
        self.left_down_x = 0
        self.has_dragged = False
        self.selection_start_time = 0.0

        self.is_box_selecting = False
        self.box_start_time = 0.0

        self.active_edge_target = None

        self.waveform_pixmap = None
        self.pixmap_dirty = True
        self.buffered_total_width = 0

        # Background generation activity indicators
        self.active_background_tasks = set()
        self.background_status_text = ""
        self.show_background_banner = False
        self._background_delay_timer = QTimer(self)
        self._background_delay_timer.setSingleShot(True)
        self._background_delay_timer.setInterval(1500)  # Show if taking > 1.5s
        self._background_delay_timer.timeout.connect(self._activate_background_banner)

        self.setMinimumHeight(120)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setMouseTracking(True)
        self.setAcceptDrops(True)

    def set_background_generation_active(self, task_name: str, active: bool):
        """Set generation state for 'waveform' or 'thumbnails'."""
        if active:
            self.active_background_tasks.add(task_name)
            if not self._background_delay_timer.isActive() and not self.show_background_banner:
                self._background_delay_timer.start()
        else:
            self.active_background_tasks.discard(task_name)
            if not self.active_background_tasks:
                self._background_delay_timer.stop()
                self.show_background_banner = False
                self.background_status_text = ""
                self.update()
                return

        self._update_background_status_text()
        if self.show_background_banner:
            self.update()

    def _activate_background_banner(self):
        if self.active_background_tasks:
            self.show_background_banner = True
            self._update_background_status_text()
            self.update()

    def _update_background_status_text(self):
        labels = []
        if "waveform" in self.active_background_tasks:
            labels.append("audio waveform")
        if "thumbnails" in self.active_background_tasks:
            labels.append("video thumbnails")
        if labels:
            self.background_status_text = f"Generating {' and '.join(labels)}..."
        else:
            self.background_status_text = ""

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            local_files = [u.toLocalFile() for u in event.mimeData().urls() if u.isLocalFile()]
            if local_files:
                event.acceptProposedAction()
                return
        event.ignore()

    def dropEvent(self, event):
        for url in event.mimeData().urls():
            if url.isLocalFile():
                self.mediaDropped.emit(url.toLocalFile())
                event.acceptProposedAction()
                return
        event.ignore()

    def set_audio_filename(self, filename):
        self.audio_file_name = filename
        self.pixmap_dirty = True
        self.update()

    def set_duration(self, duration):
        self.duration = max(1, duration)
        self.clamp_scroll_offset()
        self.zoomChanged.emit()
        self.pixmap_dirty = True
        self.update()

    def set_position(self, position):
        self.position = position
        self.ensure_position_visible(self.position)
        self.update()

    def set_playing_state(self, is_playing):
        self.is_playing = is_playing

    def ensure_position_visible(self, target_time):
        if self.zoom_level <= 1.0:
            return

        vis_dur = self.visible_duration()

        if self.is_playing:
            self.scroll_offset = target_time - (vis_dur / 2.0)
            self.clamp_scroll_offset()
        else:
            view_start = self.scroll_offset
            view_end = self.scroll_offset + vis_dur
            margin = vis_dur * 0.05
            if target_time < (view_start + margin) or target_time > (view_end - margin):
                self.scroll_offset = target_time - (vis_dur / 2.0)
                self.clamp_scroll_offset()

    def set_transcript_selection_range(self, start, end):
        if start is None or end is None:
            self.transcript_selection_range = None
        else:
            self.transcript_selection_range = (max(0.0, float(start)), min(self.duration, float(end)))
        self.update()

    def set_stories(self, stories, selected_indices=None):
        self.stories = stories
        self.selected_story_indices = selected_indices if selected_indices is not None else []
        self.update()

    def set_waveform_peaks(self, peaks):
        self.waveform_peaks = peaks or []
        self.waveform_levels = []
        if self.waveform_peaks:
            level = list(self.waveform_peaks)
            self.waveform_levels.append(level)
            while len(level) > 4:
                next_level = []
                for i in range(0, len(level), 4):
                    next_level.append(max(level[i:i + 4]))
                level = next_level
                self.waveform_levels.append(level)
        self.pixmap_dirty = True
        self.update()

    def set_timeline_views(self, show_waveform=True, show_thumbnails=True):
        self.show_waveform = bool(show_waveform)
        self.show_thumbnails = bool(show_thumbnails)
        self.pixmap_dirty = True
        self.update()

    def set_video_thumbnails(self, thumbnails):
        self.video_thumbnails = []
        for timestamp, filename in thumbnails or []:
            pix = QPixmap(str(filename))
            if not pix.isNull():
                self.video_thumbnails.append((float(timestamp), pix))
        self.pixmap_dirty = True
        self.update()

    def set_skip_seconds(self, seconds):
        self.skip_seconds = max(1, int(seconds))

    def visible_duration(self):
        return self.duration / self.zoom_level

    def clamp_scroll_offset(self):
        max_offset = max(0.0, self.duration - self.visible_duration())
        self.scroll_offset = max(0.0, min(max_offset, self.scroll_offset))
        self.scrollOffsetChanged.emit(self.scroll_offset)

    def time_to_x(self, time_val, width):
        if self.visible_duration() <= 0:
            return 0
        return ((time_val - self.scroll_offset) / self.visible_duration()) * width

    def x_to_time(self, x_val, width):
        ratio = x_val / max(1, width)
        return self.scroll_offset + (ratio * self.visible_duration())

    def find_edge_at_pos(self, pos_x, width):
        for index, story in enumerate(self.stories):
            start_x = self.time_to_x(story.start, width)
            end_x = self.time_to_x(story.end, width)

            if abs(pos_x - start_x) <= self.EDGE_HANDLE_THRESHOLD:
                return (index, 'start')
            elif abs(pos_x - end_x) <= self.EDGE_HANDLE_THRESHOLD:
                return (index, 'end')
        return None

    def is_near_playhead(self, pos_x, width):
        cursor_x = self.time_to_x(self.position, width)
        return abs(pos_x - cursor_x) <= self.CURSOR_GRAB_THRESHOLD

    def set_zoom(self, new_zoom, center_x=None):
        if center_x is None:
            center_x = self.width() / 2.0

        focus_time = self.x_to_time(center_x, self.width())

        self.zoom_level = max(self.min_zoom, min(self.max_zoom, new_zoom))

        new_visible = self.visible_duration()
        ratio = center_x / max(1, self.width())
        self.scroll_offset = focus_time - (ratio * new_visible)

        self.clamp_scroll_offset()
        self.zoomChanged.emit()
        self.pixmap_dirty = True
        self.update()

    def resizeEvent(self, event):
        self.pixmap_dirty = True
        super().resizeEvent(event)

    def wheelEvent(self, event):
        modifiers = event.modifiers()
        delta = event.angleDelta().y()

        if modifiers & Qt.KeyboardModifier.ShiftModifier:
            pan_delta = (delta / 120.0) * (self.visible_duration() * 0.1)
            self.scroll_offset -= pan_delta
            self.clamp_scroll_offset()
            self.update()
        else:
            mouse_x = event.position().x()
            if delta > 0:
                self.set_zoom(self.zoom_level * 1.15, mouse_x)
            elif delta < 0:
                self.set_zoom(self.zoom_level / 1.15, mouse_x)

        event.accept()

    def mousePressEvent(self, event):
        self.setFocus()
        pos_x = event.position().x()
        width = self.width()

        if event.button() == Qt.MouseButton.MiddleButton:
            self.is_panning = True
            self.pan_start_x = pos_x
            self.pan_start_offset = self.scroll_offset
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
            event.accept()
            return

        # --- RIGHT-CLICK: Drag Selection, Handle Adjustments, or Context Menu ---
        if event.button() == Qt.MouseButton.RightButton:
            curr_t = max(0.0, min(self.duration, self.x_to_time(pos_x, width)))

            # Check if clicking a handle on an existing right-click selection
            if self.selection_start is not None and self.selection_end is not None:
                x_start = self.time_to_x(self.selection_start, width)
                x_end = self.time_to_x(self.selection_end, width)
                x_min = min(x_start, x_end)
                x_max = max(x_start, x_end)

                if abs(pos_x - x_min) <= self.EDGE_HANDLE_THRESHOLD:
                    self.active_selection_handle = "start" if x_start <= x_end else "end"
                    self.is_right_dragging = True
                    self.setCursor(Qt.CursorShape.SizeHorCursor)
                    event.accept()
                    return
                elif abs(pos_x - x_max) <= self.EDGE_HANDLE_THRESHOLD:
                    self.active_selection_handle = "end" if x_start <= x_end else "start"
                    self.is_right_dragging = True
                    self.setCursor(Qt.CursorShape.SizeHorCursor)
                    event.accept()
                    return
                elif x_min < pos_x < x_max:
                    self._show_selection_context_menu(event.globalPosition().toPoint() if hasattr(event, "globalPosition") else event.globalPos())
                    event.accept()
                    return

            # Check if grabbing an existing story edge
            edge_hit = self.find_edge_at_pos(pos_x, width)
            if edge_hit:
                self.active_edge_target = edge_hit
                self.setCursor(Qt.CursorShape.SizeHorCursor)
                event.accept()
                return

            # Otherwise, begin drawing a new selection region
            self.selection_start = curr_t
            self.selection_end = curr_t
            self.active_selection_handle = "end"
            self.is_right_dragging = True
            self.selectionRangeChanged.emit(self.selection_start, self.selection_end)
            self.update()
            event.accept()
            return

        # --- LEFT-CLICK: Check for Story Boundary Handles First, Else Scrub ---
        if event.button() == Qt.MouseButton.LeftButton:
            edge_hit = self.find_edge_at_pos(pos_x, width)
            if edge_hit:
                self.active_edge_target = edge_hit
                self.setCursor(Qt.CursorShape.SizeHorCursor)
                event.accept()
                return

            time = max(0, min(self.duration, self.x_to_time(pos_x, width)))
            self.is_left_down = True
            self.is_scrubbing = True
            self.positionClicked.emit(time)
            self.scrubPositionChanged.emit(time)
            event.accept()
            return

    def mouseMoveEvent(self, event):
        pos_x = event.position().x()
        width = self.width()

        if self.is_panning:
            dx = pos_x - self.pan_start_x
            dt = (dx / max(1, width)) * self.visible_duration()
            self.scroll_offset = self.pan_start_offset - dt
            self.clamp_scroll_offset()
            self.update()
            event.accept()
            return

        # --- RIGHT-CLICK DRAG: Update Selection Region and Handles ---
        if self.is_right_dragging:
            curr_time = max(0.0, min(self.duration, self.x_to_time(pos_x, width)))
            if self.active_selection_handle == "start":
                self.selection_start = curr_time
            elif self.active_selection_handle == "end":
                self.selection_end = curr_time

            s = min(self.selection_start, self.selection_end)
            e = max(self.selection_start, self.selection_end)
            self.selectionRangeChanged.emit(s, e)
            self.update()
            event.accept()
            return

        # --- LEFT-CLICK DRAG: Continuous Audio Scrubbing ---
        if self.is_left_down and self.is_scrubbing:
            curr_time = max(0, min(self.duration, self.x_to_time(pos_x, width)))
            self.scrubPositionChanged.emit(curr_time)
            event.accept()
            return

        if self.active_edge_target:
            idx, edge_type = self.active_edge_target
            if 0 <= idx < len(self.stories):
                curr_time = max(0, min(self.duration, self.x_to_time(pos_x, width)))
                story = self.stories[idx]

                if edge_type == 'start':
                    new_start = min(curr_time, story.end - 0.1)
                    self.storyRegionUpdated.emit(idx, new_start, story.end)
                elif edge_type == 'end':
                    new_end = max(curr_time, story.start + 0.1)
                    self.storyRegionUpdated.emit(idx, story.start, new_end)

            event.accept()
            return

        if self.is_near_playhead(pos_x, width) or self.find_edge_at_pos(pos_x, width):
            self.setCursor(Qt.CursorShape.SizeHorCursor)
        else:
            self.unsetCursor()

        if not (self.is_panning or self.is_left_down or self.is_right_dragging):
            hover_time = max(0, min(self.duration, self.x_to_time(pos_x, width)))
            mins = int(hover_time // 60)
            secs = int(hover_time % 60)
            millis = int((hover_time - int(hover_time)) * 1000)

            tooltip_text = f"{mins:02d}:{secs:02d}.{millis:03d}"
            QToolTip.showText(event.globalPosition().toPoint(), tooltip_text, self)

        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.MiddleButton:
            self.is_panning = False
            self.unsetCursor()
            event.accept()
            return

        # --- RIGHT-CLICK RELEASE: Finalize Selection Boundaries ---
        if event.button() == Qt.MouseButton.RightButton:
            if self.is_right_dragging:
                self.is_right_dragging = False
                self.active_selection_handle = None
                self.unsetCursor()
                if self.selection_start is not None and self.selection_end is not None:
                    if abs(self.selection_start - self.selection_end) < 0.05:
                        self.selection_start = None
                        self.selection_end = None
                        self.selectionRangeChanged.emit(None, None)
                    else:
                        s = min(self.selection_start, self.selection_end)
                        e = max(self.selection_start, self.selection_end)
                        self.selection_start, self.selection_end = s, e
                        self.selectionRangeChanged.emit(s, e)
                self.update()
                event.accept()
                return

            if self.active_edge_target:
                self.active_edge_target = None
                self.dragOperationFinished.emit()
                event.accept()
                return

        # --- LEFT-CLICK RELEASE: Finalize Edge Adjustment or End Scrubbing ---
        if event.button() == Qt.MouseButton.LeftButton:
            if self.active_edge_target:
                self.active_edge_target = None
                self.unsetCursor()
                self.dragOperationFinished.emit()
                event.accept()
                return

            if self.is_left_down:
                self.is_left_down = False
                self.is_scrubbing = False
                event.accept()
                return

        super().mouseReleaseEvent(event)

    def _show_selection_context_menu(self, global_pos):
        if self.selection_start is None or self.selection_end is None:
            return
        s = min(self.selection_start, self.selection_end)
        e = max(self.selection_start, self.selection_end)
        menu = QMenu(self)
        add_action = menu.addAction("Add Story from Selection")
        clear_action = menu.addAction("Clear Selection")
        selected = menu.exec(global_pos)
        if selected == add_action:
            self.storyCreatedFromSelection.emit(s, e)
        elif selected == clear_action:
            self.selection_start = None
            self.selection_end = None
            self.selectionRangeChanged.emit(None, None)
            self.update()

    def keyPressEvent(self, event):
        if event.matches(QKeySequence.StandardKey.Undo):
            main_win = self.window()
            if hasattr(main_win, "undo_stack"):
                main_win.undo_stack.undo()
                event.accept()
                return

        if event.matches(QKeySequence.StandardKey.Redo):
            main_win = self.window()
            if hasattr(main_win, "undo_stack"):
                main_win.undo_stack.redo()
                event.accept()
                return

        if event.key() in (Qt.Key.Key_Plus, Qt.Key.Key_Equal):
            self.set_zoom(self.zoom_level * 1.2)
            event.accept()
            return

        if event.key() == Qt.Key.Key_Minus:
            self.set_zoom(self.zoom_level / 1.2)
            event.accept()
            return

        if event.key() == Qt.Key.Key_A or (event.key() == Qt.Key.Key_Left and event.modifiers() & Qt.KeyboardModifier.ShiftModifier):
            self.scroll_offset -= self.visible_duration() * 0.1
            self.clamp_scroll_offset()
            self.update()
            event.accept()
            return

        if event.key() == Qt.Key.Key_D or (event.key() == Qt.Key.Key_Right and event.modifiers() & Qt.KeyboardModifier.ShiftModifier):
            self.scroll_offset += self.visible_duration() * 0.1
            self.clamp_scroll_offset()
            self.update()
            event.accept()
            return

        if event.key() == Qt.Key.Key_Left:
            self.positionClicked.emit(max(0, self.position - self.skip_seconds))
            event.accept()
            return

        if event.key() == Qt.Key.Key_Right:
            self.positionClicked.emit(min(self.duration, self.position + self.skip_seconds))
            event.accept()
            return

        if event.key() == Qt.Key.Key_Home:
            self.positionClicked.emit(0)
            event.accept()
            return

        if event.key() == Qt.Key.Key_End:
            self.positionClicked.emit(self.duration)
            event.accept()
            return

        super().keyPressEvent(event)

    def set_thumbnail_position(self, position):
        if position in ("above", "below") and self.thumbnail_position != position:
            self.thumbnail_position = position
            self.pixmap_dirty = True
            self.update()

    def render_waveform_buffer(self, total_pixel_width, height):
        dpi_scale = self.devicePixelRatioF()
        phys_width = int(total_pixel_width * dpi_scale)
        phys_height = int(height * dpi_scale)

        pixmap = QPixmap(phys_width, phys_height)
        pixmap.setDevicePixelRatio(dpi_scale)
        pixmap.fill(QColor("#181b20"))

        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        available = max(20, height - self.RULER_HEIGHT)
        has_thumbs = bool(self.video_thumbnails and self.show_thumbnails)

        if has_thumbs and self.show_waveform:
            thumbnail_height = int(available * 0.5)
            waveform_height = available - thumbnail_height
        elif has_thumbs:
            thumbnail_height = available
            waveform_height = 0
        elif self.show_waveform:
            thumbnail_height = 0
            waveform_height = available
        else:
            thumbnail_height = 0
            waveform_height = 0

        if self.thumbnail_position == "below" and self.show_waveform and has_thumbs:
            waveform_y = self.RULER_HEIGHT
            thumbnail_y = self.RULER_HEIGHT + waveform_height
        else:
            thumbnail_y = self.RULER_HEIGHT
            waveform_y = self.RULER_HEIGHT + thumbnail_height

        middle_y = waveform_y + (waveform_height / 2.0)

        if has_thumbs and thumbnail_height > 0:
            for timestamp, pix in self.video_thumbnails:
                x = int((timestamp / max(0.001, self.duration)) * total_pixel_width)
                thumb_w = max(90, int(total_pixel_width / max(8, len(self.video_thumbnails)) * 0.95))
                scaled = pix.scaled(
                    thumb_w,
                    max(16, thumbnail_height - 2),
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
                draw_y = thumbnail_y + (thumbnail_height - scaled.height()) // 2
                painter.drawPixmap(x - scaled.width() // 2, draw_y, scaled)
                painter.setPen(QPen(QColor("#4a4f58"), 1))
                painter.drawRect(x - scaled.width() // 2, draw_y, scaled.width(), scaled.height())

        if self.show_waveform and self.waveform_peaks and waveform_height > 0:
            painter.setPen(QPen(QColor("#5a81a8"), 1.0))
            levels = self.waveform_levels or [self.waveform_peaks]
            level_index = 0
            while level_index + 1 < len(levels) and (len(levels[level_index]) / max(1, total_pixel_width)) > 2.0:
                level_index += 1
            peaks = levels[level_index]
            total_peaks = len(peaks)
            for x in range(total_pixel_width):
                start_idx = int((x / max(1, total_pixel_width)) * total_peaks)
                end_idx = int(((x + 1) / max(1, total_pixel_width)) * total_peaks)
                end_idx = max(start_idx + 1, end_idx)
                end_idx = min(total_peaks, end_idx)
                if start_idx >= total_peaks:
                    continue

                amplitude = max(peaks[start_idx:end_idx]) * (waveform_height * 0.88)
                if amplitude > 0.5:
                    painter.drawLine(
                        QPointF(x + 0.5, middle_y - amplitude / 2.0),
                        QPointF(x + 0.5, middle_y + amplitude / 2.0)
                    )
        elif self.show_waveform and waveform_height > 0:
            painter.setPen(QPen(QColor("#2c323d"), 1))
            painter.drawLine(QPointF(0, middle_y), QPointF(total_pixel_width, middle_y))

        painter.end()
        return pixmap

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        width = self.width()
        height = self.height()
        waveform_height = height - self.RULER_HEIGHT

        total_pixel_width = max(width, int(width * self.zoom_level))

        if (self.pixmap_dirty or self.waveform_pixmap is None or 
            self.buffered_total_width != total_pixel_width or 
            self.waveform_pixmap.height() != height):
            
            self.waveform_pixmap = self.render_waveform_buffer(total_pixel_width, height)
            self.buffered_total_width = total_pixel_width
            self.pixmap_dirty = False

        scroll_x = (self.scroll_offset / self.duration) * total_pixel_width
        painter.drawPixmap(int(-scroll_x), 0, self.waveform_pixmap)

        ruler_rect = QRectF(0, 0, width, self.RULER_HEIGHT)
        painter.fillRect(ruler_rect, QColor("#111317"))
        painter.setPen(QPen(QColor("#2c323d"), 1))
        painter.drawLine(QPointF(0, self.RULER_HEIGHT), QPointF(width, self.RULER_HEIGHT))

        visible_dur = self.visible_duration()
        target_ticks = max(2, width // 100)
        base_interval = visible_dur / target_ticks

        nice_intervals = [1, 2, 5, 10, 15, 30, 60, 120, 300, 600, 900, 1800, 3600]
        chosen_interval = nice_intervals[-1]
        for step in nice_intervals:
            if base_interval <= step:
                chosen_interval = step
                break

        painter.setFont(self.font())
        painter.setPen(QPen(QColor("#8a95a5"), 1))

        start_tick = (self.scroll_offset // chosen_interval) * chosen_interval
        t = start_tick

        while t <= self.scroll_offset + visible_dur:
            x = self.time_to_x(t, width)
            if 0 <= x <= width:
                painter.drawLine(QPointF(x, self.RULER_HEIGHT - 6), QPointF(x, self.RULER_HEIGHT))

                mins = int(t // 60)
                secs = int(t % 60)
                hrs = int(mins // 60)
                mins = mins % 60

                label = f"{hrs}:{mins:02d}:{secs:02d}" if hrs > 0 else f"{mins:02d}:{secs:02d}"
                text_rect = QRectF(x + 3, 2, 60, self.RULER_HEIGHT - 4)
                painter.drawText(text_rect, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, label)

            t += chosen_interval

        audio_name = getattr(self, "audio_file_name", None)
        if audio_name:
            painter.setPen(QPen(QColor("#f2cc60"), 1))
            filename_rect = QRectF(8, self.RULER_HEIGHT + 4, 300, 18)
            painter.drawText(filename_rect, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, f"Audio: {audio_name}")

        if self.transcript_selection_range:
            sel_start, sel_end = self.transcript_selection_range
            sx = self.time_to_x(sel_start, width)
            ex = self.time_to_x(sel_end, width)
            left = max(0, min(width, sx))
            right = max(0, min(width, ex))
            if right > left:
                painter.fillRect(QRectF(left, self.RULER_HEIGHT, right-left, waveform_height), QColor(88, 166, 255, 70))
                painter.setPen(QPen(QColor("#58a6ff"), 2))
                painter.drawLine(QPointF(left, self.RULER_HEIGHT), QPointF(left, height))
                painter.drawLine(QPointF(right, self.RULER_HEIGHT), QPointF(right, height))

        # Draw active right-click drag selection with adjustable edge handles
        if self.selection_start is not None and self.selection_end is not None:
            sx = self.time_to_x(self.selection_start, width)
            ex = self.time_to_x(self.selection_end, width)
            left = max(0.0, min(float(width), min(sx, ex)))
            right = max(0.0, min(float(width), max(sx, ex)))
            if right > left:
                painter.fillRect(QRectF(left, self.RULER_HEIGHT, right - left, waveform_height), QColor(88, 166, 255, 55))
                painter.setPen(QPen(QColor("#58a6ff"), 2))
                painter.drawRect(QRectF(left, self.RULER_HEIGHT, right - left, waveform_height))
                painter.fillRect(QRectF(left - 3, self.RULER_HEIGHT, 6, waveform_height), QColor("#58a6ff"))
                painter.fillRect(QRectF(right - 3, self.RULER_HEIGHT, 6, waveform_height), QColor("#58a6ff"))

        colors = [
            QColor("#315c85"),
            QColor("#386b59"),
            QColor("#795d31"),
            QColor("#674f7c"),
        ]

        for index, story in enumerate(self.stories):
            start_x = self.time_to_x(story.start, width)
            end_x = self.time_to_x(story.end, width)

            if end_x < 0 or start_x > width:
                continue

            color = colors[index % len(colors)]
            fill_color = QColor(color)

            if index in self.selected_story_indices:
                fill_color.setAlpha(130)
                pen_width = 3
                line_color = QColor("#ffffff")
            else:
                fill_color.setAlpha(60)
                pen_width = 2
                line_color = color.darker(150)

            rect_start = max(0, start_x)
            rect_end = min(width, end_x)

            painter.fillRect(
                QRectF(rect_start, self.RULER_HEIGHT, max(1, rect_end - rect_start), waveform_height),
                fill_color,
            )

            painter.setPen(QPen(line_color, pen_width))
            if 0 <= start_x <= width:
                painter.drawLine(QPointF(start_x, self.RULER_HEIGHT), QPointF(start_x, height))
            if 0 <= end_x <= width:
                painter.drawLine(QPointF(end_x, self.RULER_HEIGHT), QPointF(end_x, height))

        # Draw Playhead Line
        cursor_x = self.time_to_x(self.position, width)
        if 0 <= cursor_x <= width:
            painter.setPen(QPen(QColor("#ff5c5c"), 2))
            painter.drawLine(QPointF(cursor_x, 0), QPointF(cursor_x, height))

        # Draw Background Task Status Banner (Waveform / Thumbnail Generation)
        if self.show_background_banner and self.background_status_text:
            painter.save()
            font = self.font()
            font.setPointSize(9)
            font.setBold(True)
            painter.setFont(font)

            fm = painter.fontMetrics()
            text_w = fm.horizontalAdvance(self.background_status_text)
            badge_w = text_w + 24
            badge_h = 24
            badge_x = (width - badge_w) / 2.0
            badge_y = self.RULER_HEIGHT + 8

            badge_rect = QRectF(badge_x, badge_y, badge_w, badge_h)
            painter.setPen(QPen(QColor("#58a6ff"), 1.5))
            painter.setBrush(QColor(18, 20, 24, 230))
            painter.drawRoundedRect(badge_rect, 4.0, 4.0)

            painter.setPen(QColor("#f0f6fc"))
            painter.drawText(badge_rect, Qt.AlignmentFlag.AlignCenter, self.background_status_text)
            painter.restore()


class TimelineWidget(QWidget):
    mediaDropped = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptDrops(True)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.canvas = TimelineCanvas()
        self.scrollbar = QScrollBar(Qt.Orientation.Horizontal)

        layout.addWidget(self.canvas, 1)
        layout.addWidget(self.scrollbar)

        self.canvas.scrollOffsetChanged.connect(self.update_scrollbar_from_canvas)
        self.canvas.mediaDropped.connect(self.mediaDropped.emit)
        self.canvas.zoomChanged.connect(self.update_scrollbar_range)
        self.scrollbar.valueChanged.connect(self.update_canvas_from_scrollbar)

        self.selectionRangeChanged = self.canvas.selectionRangeChanged
        self.storyCreatedFromSelection = self.canvas.storyCreatedFromSelection

        self.is_internal_scrollbar_update = False
        self.update_scrollbar_range()

    def set_background_generation_active(self, task_name: str, active: bool):
        if hasattr(self, "canvas") and hasattr(self.canvas, "set_background_generation_active"):
            self.canvas.set_background_generation_active(task_name, active)

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls() and any(url.isLocalFile() for url in event.mimeData().urls()):
            event.acceptProposedAction()
            return
        event.ignore()

    def dropEvent(self, event):
        for url in event.mimeData().urls():
            if url.isLocalFile():
                self.mediaDropped.emit(url.toLocalFile())
                event.acceptProposedAction()
                return
        event.ignore()

    def update_scrollbar_range(self):
        self.is_internal_scrollbar_update = True
        total = int(self.canvas.duration * 1000)
        visible = int(self.canvas.visible_duration() * 1000)

        self.scrollbar.setRange(0, max(0, total - visible))
        self.scrollbar.setPageStep(visible)
        self.scrollbar.setSingleStep(max(100, visible // 10))
        self.is_internal_scrollbar_update = False
        self.update_scrollbar_from_canvas(self.canvas.scroll_offset)

    def update_scrollbar_from_canvas(self, offset):
        if self.is_internal_scrollbar_update:
            return

        self.is_internal_scrollbar_update = True
        self.scrollbar.setValue(int(offset * 1000))
        self.is_internal_scrollbar_update = False

    def update_canvas_from_scrollbar(self, val):
        if self.is_internal_scrollbar_update:
            return

        self.is_internal_scrollbar_update = True
        self.canvas.scroll_offset = val / 1000.0
        self.canvas.clamp_scroll_offset()
        self.canvas.update()
        self.is_internal_scrollbar_update = False

    def __getattr__(self, name):
        return getattr(self.canvas, name)


# ============================================================
# Main Window
# ============================================================



class TranslationWorker(QObject):
    """Local OPUS-MT translation/model-management worker."""
    progress = Signal(int, str)
    checkpoint = Signal(object, str, int)
    finished = Signal(object, str)
    cancelled = Signal(object, str)
    error = Signal(str)
    model_status = Signal(str, str, bool, str)
    model_status_finished = Signal()

    MODEL_REPOS = {
        "tiny": {("en", "es"): "Helsinki-NLP/opus-mt_tiny_eng-spa", ("es", "en"): "Helsinki-NLP/opus-mt_tiny_spa-eng"},
        "standard": {("en", "es"): "Helsinki-NLP/opus-mt-en-es", ("es", "en"): "Helsinki-NLP/opus-mt-es-en"},
        "opus-mt": {("en", "es"): "Helsinki-NLP/opus-mt-en-es", ("es", "en"): "Helsinki-NLP/opus-mt-es-en"},
    }
    MODEL_FILES = (
        "config.json",
        "generation_config.json",
        "model.safetensors",
        "source.spm",
        "target.spm",
        "tokenizer_config.json",
        "special_tokens_map.json",
        "added_tokens.json",
        "vocab.json",
        "vocab.spm",
    )

    def __init__(
        self,
        segments=None,
        from_code="en",
        to_code="es",
        install_if_missing=False,
        installation_only=False,
        resume_results=None,
        model_variant="standard",
        status_only=False,
        parent=None,
        transcript=None,
        variant=None,
        device="cpu",
        **kwargs,
    ):
        # Force parent to None so Qt doesn't bind this object to the GUI thread
        super().__init__(None)

        if transcript is not None:
            if isinstance(transcript, dict):
                segments = transcript.get("segments", [])
            elif isinstance(transcript, list):
                segments = transcript
        elif isinstance(segments, dict):
            segments = segments.get("segments", [])

        self.segments = list(segments) if segments is not None else []
        self.from_code = from_code
        self.to_code = to_code
        self.install_if_missing = install_if_missing
        self.installation_only = installation_only
        self.resume_results = resume_results or []

        eff_variant = variant or model_variant or "standard"
        if eff_variant == "opus-mt":
            eff_variant = "standard"
        self.model_variant = eff_variant
        self.status_only = status_only
        self.translation_device = device
        self._cancelled = False
        self._is_cancelled = False
        
        # Defer model handles so they instantiate inside run() on the QThread
        self.model = None
        self.tokenizer = None

    @classmethod
    def model_root(cls, variant="tiny"):
        return get_models_storage_dir() / f"opus-mt-{variant}"

    @classmethod
    def model_dir(cls, from_code, to_code, variant="tiny"):
        return cls.model_root(variant) / f"{from_code}-{to_code}"

    @classmethod
    def _model_is_installed_in_dir(cls, directory):
        directory = Path(directory)
        marker = directory / ".complete"
        if not marker.is_file():
            return False
        required = ["config.json", "tokenizer_config.json", "source.spm", "target.spm"]
        if not all((directory / name).is_file() and (directory / name).stat().st_size > 0 for name in required):
            return False
        weights = [directory / "model.safetensors", directory / "pytorch_model.bin"]
        if not any(path.is_file() and path.stat().st_size > 0 for path in weights):
            return False
        return True

    @classmethod
    def model_is_installed(cls, from_code, to_code, variant="tiny"):
        return cls._model_is_installed_in_dir(cls.model_dir(from_code, to_code, variant))

    @classmethod
    def model_repo(cls, from_code, to_code, variant="tiny"):
        return cls.MODEL_REPOS.get(variant, {}).get((from_code, to_code))

    def cancel(self):
        self._cancelled = True

    def _download_file(self, repo, filename, destination, progress_start, progress_end, label):
        import urllib.request
        import urllib.error

        destination.parent.mkdir(parents=True, exist_ok=True)
        temp = destination.with_suffix(destination.suffix + ".download")
        url = f"https://huggingface.co/{repo}/resolve/main/{filename}?download=true"
        request = urllib.request.Request(url, headers={"User-Agent": "Radio-TV-Story-Segmenter/60-opus-mt-tiny"})
        try:
            with urllib.request.urlopen(request, timeout=60) as response, temp.open("wb") as out:
                total = int(response.headers.get("Content-Length") or 0)
                downloaded = 0
                while True:
                    if self._cancelled:
                        raise InterruptedError("Model download canceled.")
                    chunk = response.read(1024 * 1024)
                    if not chunk:
                        break
                    out.write(chunk)
                    downloaded += len(chunk)
                    if total:
                        fraction = min(1.0, downloaded / total)
                        pct = int(progress_start + (progress_end - progress_start) * fraction)
                        self.progress.emit(pct, f"{label} ({downloaded / (1024 * 1024):.0f} / {total / (1024 * 1024):.0f} MB)")
                out.flush()
                os.fsync(out.fileno())
            if not temp.exists() or temp.stat().st_size == 0:
                raise RuntimeError(f"Downloaded model file '{filename}' is empty.")
            os.replace(temp, destination)
        except InterruptedError:
            try:
                temp.unlink(missing_ok=True)
            except Exception:
                pass
            raise
        except Exception as exc:
            try:
                temp.unlink(missing_ok=True)
            except Exception:
                pass
            if isinstance(exc, urllib.error.HTTPError):
                raise RuntimeError(f"Could not download {filename} (HTTP {exc.code}).") from exc
            raise RuntimeError(f"Could not download {filename}: {exc}") from exc

    def _ensure_model_installed(self):
        """Download a complete Hugging Face snapshot into a staging directory and publish atomically."""
        from_code, to_code = self.from_code, self.to_code
        repo = self.model_repo(from_code, to_code, self.model_variant)
        if not repo:
            raise RuntimeError(f"No OPUS-MT {self.model_variant} model is configured for {from_code.upper()} → {to_code.upper()}.")
        if self.model_is_installed(from_code, to_code, self.model_variant) and not self.installation_only:
            self.progress.emit(5, f"OPUS-MT {self.model_variant} model is installed; loading it…")
            return self.model_dir(from_code, to_code, self.model_variant)
        try:
            from huggingface_hub import snapshot_download
        except Exception as exc:
            raise RuntimeError("The translation download component (huggingface_hub) is unavailable. Install the translation prerequisites.") from exc
        final_dir = self.model_dir(from_code, to_code, self.model_variant)
        staging_dir = final_dir.with_name(final_dir.name + ".installing")
        backup_dir = final_dir.with_name(final_dir.name + ".backup")
        self.progress.emit(2, f"Preparing OPUS-MT {self.model_variant} model download…")
        try:
            if staging_dir.exists(): shutil.rmtree(staging_dir, ignore_errors=True)
            staging_dir.mkdir(parents=True, exist_ok=True)
            snapshot_download(repo_id=repo, local_dir=str(staging_dir), resume_download=True)
            if self._cancelled: raise InterruptedError("Model download canceled.")
            marker = staging_dir / ".complete"
            marker.write_text(f"{repo}\n{self.model_variant}\n{datetime.now().isoformat()}\n", encoding="utf-8")
            self.progress.emit(90, f"Verifying OPUS-MT {self.model_variant} model files…")
            if not self._model_is_installed_in_dir(staging_dir):
                raise RuntimeError("The translation model download completed, but required model files are missing or empty.")
            if backup_dir.exists(): shutil.rmtree(backup_dir, ignore_errors=True)
            if final_dir.exists(): final_dir.rename(backup_dir)
            staging_dir.rename(final_dir)
            if backup_dir.exists(): shutil.rmtree(backup_dir, ignore_errors=True)
            self.progress.emit(100, f"OPUS-MT {self.model_variant} model installed and verified.")
            return final_dir
        except Exception:
            try:
                if staging_dir.exists(): shutil.rmtree(staging_dir, ignore_errors=True)
            except Exception: pass
            raise

    def _load_local_translation(self):
        if not self.model_is_installed(self.from_code, self.to_code, self.model_variant):
            return None
        try:
            import torch
            from transformers import AutoModelForSeq2SeqLM, AutoTokenizer
        except Exception as exc:
            raise RuntimeError(
                f"OPUS-MT {self.model_variant} requires the local translation prerequisites. "
                "Install them with: pip install -r requirements_translation.txt"
            ) from exc

        model_dir = self.model_dir(self.from_code, self.to_code, self.model_variant)
        tokenizer = AutoTokenizer.from_pretrained(str(model_dir), local_files_only=True, use_fast=False)
        model = AutoModelForSeq2SeqLM.from_pretrained(str(model_dir), local_files_only=True)
        model.eval()
        # Translation remains CPU-only in this version. Hardware acceleration is
        # deliberately not advertised until a backend is fully integrated and tested.
        device = "cpu"
        model = model.to(device)
        self.translation_device = device
        return tokenizer, model, torch

    def _translate_batches(self, tokenizer, model, torch):
        results = list(self.resume_results)
        start_index = len(results)
        total = max(1, len(self.segments))
        if start_index > len(self.segments):
            results = []
            start_index = 0

        batch_size = 8
        for batch_start in range(start_index, len(self.segments), batch_size):
            if self._cancelled:
                self.cancelled.emit(results, f"{self.from_code}-{self.to_code}")
                return None
                
            batch = self.segments[batch_start:batch_start + batch_size]
            texts = [str(seg.get("text", "")).strip() for seg in batch]
            
            self.progress.emit(
                10 + int((batch_start / total) * 85),
                f"Translating segments {batch_start + 1}–{min(batch_start + len(batch), len(self.segments))} of {total}…",
            )
            
            nonempty_indices = [i for i, text in enumerate(texts) if text]
            translated_by_index = {i: "" for i in range(len(batch))}
            
            if nonempty_indices:
                nonempty_texts = [texts[i] for i in nonempty_indices]
                
                # Tokenize each source transcript segment cleanly
                encoded = tokenizer(
                    nonempty_texts,
                    return_tensors="pt",
                    padding=True,
                    truncation=True,
                    max_length=512, 
                )
                
                if getattr(self, "translation_device", "cpu") != "cpu":
                    try:
                        encoded = {k: v.to(self.translation_device) for k, v in encoded.items()}
                    except Exception:
                        self.translation_device = "cpu"

                # =============================================================
                # TRANSLATION CODE PATCH
                # =============================================================
                with torch.inference_mode():
                    generated = model.generate(
                        **encoded,
                        num_beams=2,
                        max_new_tokens=256,
                        early_stopping=True,
                    )
                # =============================================================
                    
                decoded = tokenizer.batch_decode(generated, skip_special_tokens=True)
                for idx, text in zip(nonempty_indices, decoded):
                    translated_by_index[idx] = text.strip()

            # Reconstruct 1:1 segment mappings so timestamps, speakers, and sentence structures match perfectly
            for i, segment in enumerate(batch):
                translated = translated_by_index[i]
                results.append({
                    "text": translated if translated else segment.get("text", ""),
                    "start": float(segment.get("start", 0)),
                    "end": float(segment.get("end", 0)),
                })
                
            completed = batch_start + len(batch)
            pct = 10 + int((completed / total) * 85)
            self.progress.emit(pct, f"Translated {completed} of {total} segments…")
            self.checkpoint.emit(results, f"{self.from_code}-{self.to_code}", completed)
            
        return results

    def run(self):
        try:
            if self.status_only:
                try:
                    for from_code, to_code in self.status_pairs:
                        if self._cancelled:
                            return
                        ok = self.model_is_installed(from_code, to_code, self.model_variant)
                        message = f"OPUS-MT {self.model_variant} installed" if ok else f"OPUS-MT {self.model_variant} not installed"
                        self.model_status.emit(from_code, to_code, ok, message)
                except Exception as exc:
                    for from_code, to_code in self.status_pairs:
                        self.model_status.emit(from_code, to_code, False, f"Unavailable: {exc}")
                finally:
                    self.model_status_finished.emit()
                return

            model_dir = self._ensure_model_installed()
            if self._cancelled or model_dir is None:
                self.cancelled.emit(self.resume_results, f"{self.from_code}-{self.to_code}")
                return
            if self.installation_only:
                self.progress.emit(100, "OPUS-MT model installed and ready.")
                self.finished.emit([], f"{self.from_code}-{self.to_code}")
                return

            self.progress.emit(5, "Loading OPUS-MT model into memory…")
            tokenizer, model, torch = self._load_local_translation()
            if self._cancelled:
                self.cancelled.emit(self.resume_results, f"{self.from_code}-{self.to_code}")
                return
            results = self._translate_batches(tokenizer, model, torch)
            if results is not None and not self._cancelled:
                self.progress.emit(100, "Translation complete.")
                self.finished.emit(results, f"{self.from_code}-{self.to_code}")
        except Exception as exc:
            if not self._cancelled:
                self.error.emit(str(exc))
            else:
                self.cancelled.emit(self.resume_results, f"{self.from_code}-{self.to_code}")       

class BatchFileListWidget(QListWidget):
    filesDropped = Signal(list)
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptDrops(True)
    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            event.ignore()
    def dropEvent(self, event):
        paths=[u.toLocalFile() for u in event.mimeData().urls() if u.isLocalFile()]
        if paths:
            self.filesDropped.emit(paths)
            event.acceptProposedAction()
        else:
            event.ignore()

class BatchProcessingDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Batch Processing")
        self.resize(680, 640)
        
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Add media files or documents. Choose to run the full automated pipeline or select specific processes."))

        # File List View
        self.files = BatchFileListWidget()
        self.files.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        layout.addWidget(self.files, 1)

        row = QHBoxLayout()
        add = QPushButton("Add Files…")
        rem = QPushButton("Remove Selected")
        row.addWidget(add)
        row.addWidget(rem)
        row.addStretch()
        layout.addLayout(row)

        # Output / Project Directory Selector
        dir_group = QGroupBox("Target Save Location")
        dir_layout = QHBoxLayout(dir_group)
        self.output = QLineEdit()
        self.output.setPlaceholderText("Default (project folder or media file directory if empty)")
        browse = QPushButton("Browse Folder…")
        dir_layout.addWidget(self.output, 1)
        dir_layout.addWidget(browse)
        layout.addWidget(dir_group)

        # --- Section 1: Pipeline & Process Selection ---
        proc_group = QGroupBox("1. Processing Pipeline Selection")
        proc_layout = QVBoxLayout(proc_group)

        self.pipeline_full_radio = QRadioButton("Run Full Processing Pipeline (Transcribe + Diarize + Detect Stories)")
        self.pipeline_full_radio.setChecked(True)
        self.pipeline_custom_radio = QRadioButton("Select Specific Processes to Run:")
        
        proc_layout.addWidget(self.pipeline_full_radio)
        proc_layout.addWidget(self.pipeline_custom_radio)

        # Custom process checkboxes
        self.custom_proc_widget = QWidget()
        custom_proc_layout = QHBoxLayout(self.custom_proc_widget)
        custom_proc_layout.setContentsMargins(20, 0, 0, 0)
        self.proc_transcribe = QCheckBox("Transcription")
        self.proc_transcribe.setChecked(True)
        self.proc_diarize = QCheckBox("Diarization")
        self.proc_diarize.setChecked(True)
        self.proc_stories = QCheckBox("Story Detection")
        self.proc_stories.setChecked(True)
        self.proc_translate = QCheckBox("Spanish Translation")
        self.proc_translate.setChecked(False)

        custom_proc_layout.addWidget(self.proc_transcribe)
        custom_proc_layout.addWidget(self.proc_diarize)
        custom_proc_layout.addWidget(self.proc_stories)
        custom_proc_layout.addWidget(self.proc_translate)
        proc_layout.addWidget(self.custom_proc_widget)
        self.custom_proc_widget.setEnabled(False)

        self.pipeline_custom_radio.toggled.connect(self.custom_proc_widget.setEnabled)
        layout.addWidget(proc_group)

        # --- Section 2: Project & Save Options ---
        opts_group = QGroupBox("2. Project & Save Options")
        opts_layout = QVBoxLayout(opts_group)

        self.save_project_check = QCheckBox("Auto-save updated project (.json) files to specified directory (or default)")
        self.save_project_check.setChecked(True)
        opts_layout.addWidget(self.save_project_check)

        self.skip_existing_check = QCheckBox("Skip re-processing if requested output files already exist")
        self.skip_existing_check.setChecked(True)
        opts_layout.addWidget(self.skip_existing_check)

        layout.addWidget(opts_group)

        # --- Section 3: Output Formats & Scope (for standard exports) ---
        self.export_group = QGroupBox("3. Output Formats & Scope")
        export_layout = QVBoxLayout(self.export_group)

        self.save_project_only_check = QCheckBox("Save projects only (do not export text or media files)")
        self.save_project_only_check.setChecked(False)
        self.save_project_only_check.setToolTip("Run the selected processing and save the resulting project files without creating transcript, subtitle, document, or media exports.")
        export_layout.addWidget(self.save_project_only_check)

        scope_row = QHBoxLayout()
        scope_row.addWidget(QLabel("Export Scope:"))
        self.scope_combo = QComboBox()
        self.scope_combo.addItem("Full Transcripts Only", "full")
        self.scope_combo.addItem("Individual Stories Only", "stories")
        self.scope_combo.addItem("Full Transcripts + Individual Stories", "both")
        scope_row.addWidget(self.scope_combo, 1)
        export_layout.addLayout(scope_row)

        fmt_row = QHBoxLayout()
        self.fmt_txt = QCheckBox("TXT (.txt)")
        self.fmt_docx = QCheckBox("DOCX (.docx)")
        self.fmt_srt = QCheckBox("SRT (.srt)")
        self.fmt_vtt = QCheckBox("VTT (.vtt)")
        self.fmt_txt.setChecked(True)
        self.fmt_docx.setChecked(True)
        fmt_row.addWidget(self.fmt_txt)
        fmt_row.addWidget(self.fmt_docx)
        fmt_row.addWidget(self.fmt_srt)
        fmt_row.addWidget(self.fmt_vtt)
        export_layout.addLayout(fmt_row)

        details_row = QHBoxLayout()
        self.include_speakers = QCheckBox("Include speaker labels")
        self.include_speakers.setChecked(True)
        self.include_times = QCheckBox("Include timestamps")
        self.include_times.setChecked(False)
        self.translate_check = QCheckBox("Translate outputs to Spanish (_es)")
        details_row.addWidget(self.include_speakers)
        details_row.addWidget(self.include_times)
        details_row.addWidget(self.translate_check)
        export_layout.addLayout(details_row)

        self.doc_direction = QComboBox()
        self.doc_direction.addItem("English → Spanish", "en-es")
        self.doc_direction.addItem("Spanish → English", "es-en")
        doc_row = QHBoxLayout()
        doc_row.addWidget(QLabel("Document Translation Direction:"))
        doc_row.addWidget(self.doc_direction)
        export_layout.addLayout(doc_row)

        layout.addWidget(self.export_group)

        def _on_save_project_only_toggled(checked):
            # Keep the group accessible but disable the file format & scope pickers
            self.scope_combo.setEnabled(not checked)
            self.fmt_txt.setEnabled(not checked)
            self.fmt_docx.setEnabled(not checked)
            self.fmt_srt.setEnabled(not checked)
            self.fmt_vtt.setEnabled(not checked)
            self.include_speakers.setEnabled(not checked)
            self.include_times.setEnabled(not checked)
            self.translate_check.setEnabled(not checked)

        self.save_project_only_check.toggled.connect(_on_save_project_only_toggled)

        # Dialog Action Buttons
        btns = QHBoxLayout()
        self.start = QPushButton("Start Batch")
        cancel = QPushButton("Cancel")
        btns.addStretch()
        btns.addWidget(self.start)
        btns.addWidget(cancel)
        layout.addLayout(btns)

        # Signal Connections
        add.clicked.connect(self.add_files)
        rem.clicked.connect(lambda: [self.files.takeItem(self.files.row(i)) for i in self.files.selectedItems()])
        browse.clicked.connect(self.choose_output)
        cancel.clicked.connect(self.reject)
        self.start.clicked.connect(self.accept)
        
        self.files.filesDropped.connect(self.add_paths)
        self.files.model().rowsInserted.connect(self.auto_detect_options)
        self.files.model().rowsRemoved.connect(self.auto_detect_options)

    def add_paths(self, paths):
        for f in paths:
            if Path(f).is_file() and not any(self.files.item(i).text() == f for i in range(self.files.count())):
                self.files.addItem(f)
        self.auto_detect_options()

    def add_files(self):
        filters = "All Supported Files (*.*)"
        parent = self.parent()
        settings = getattr(parent, "settings_store", None)
        default_dir = ""
        if settings is not None:
            default_dir = str(settings.value("batch_add_files_directory", "") or "")
        if not default_dir:
            default_dir = getattr(parent, "_dialog_directory", lambda: "")()
        files, _ = QFileDialog.getOpenFileNames(self, "Add Files", default_dir, filters)
        if files and settings is not None:
            settings.setValue("batch_add_files_directory", str(Path(files[0]).resolve().parent))
        self.add_paths(files)

    def choose_output(self):
        d = QFileDialog.getExistingDirectory(
            self, "Choose Output Folder", getattr(self.parent(), "_dialog_directory", lambda: "")()
        )
        if d:
            self.output.setText(d)

    def auto_detect_options(self):
        """Auto-detect available options based on imported file extensions."""
        file_paths = [self.files.item(i).text() for i in range(self.files.count())]
        
        has_media = any(
            Path(p).suffix.lower() in {
                ".mp3", ".wav", ".m4a", ".flac", ".mp4", ".mov", ".mkv", ".avi", ".webm"
            } for p in file_paths
        )
        has_docs = any(
            Path(p).suffix.lower() in {
                ".txt", ".docx", ".pdf", ".html", ".htm", ".md"
            } for p in file_paths
        )

        # Adjust option controls depending on file types found in queue
        self.include_speakers.setEnabled(has_media)
        self.include_times.setEnabled(has_media)
        self.fmt_srt.setEnabled(has_media)
        self.fmt_vtt.setEnabled(has_media)
        self.scope_combo.setEnabled(has_media)
        self.doc_direction.setVisible(has_docs and not has_media)

# ============================================================
# Global Subprocess & Child Process Management
# ============================================================

_REGISTERED_PROCESSES = set()


def register_process(proc):
    """Register a QProcess or subprocess.Popen instance to track its lifecycle."""
    if proc is not None:
        _REGISTERED_PROCESSES.add(proc)


def unregister_process(proc):
    """Unregister a process when it exits naturally or is cleaned up."""
    _REGISTERED_PROCESSES.discard(proc)


def terminate_all_registered_processes():
    """Terminate and wait on all active child processes upon application close."""
    for proc in list(_REGISTERED_PROCESSES):
        if proc is None:
            continue
        try:
            # Handle PySide6 QProcess
            if hasattr(proc, "state"):
                if proc.state() != QProcess.ProcessState.NotRunning:
                    proc.kill()
                    proc.waitForFinished(1000)
            # Handle standard Python subprocess.Popen
            elif hasattr(proc, "poll") and proc.poll() is None:
                proc.kill()
        except Exception:
            pass
    _REGISTERED_PROCESSES.clear()
