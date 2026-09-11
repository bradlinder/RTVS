"""Shortcuts Manager for Radio & TV Story Segmenter.

Provides centralized management, customization, persistence, conflict detection,
and runtime re-binding of all keyboard shortcuts across the application.
"""
from __future__ import annotations

import sys
from dataclasses import dataclass
from typing import Optional, Dict, List

from PySide6.QtCore import Qt, QSettings, Signal, QObject, QEvent
from PySide6.QtGui import QKeySequence, QFont, QColor
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QLineEdit, QTableWidget, QTableWidgetItem, QHeaderView,
    QGroupBox, QComboBox, QMessageBox, QFrame, QDialog,
    QDialogButtonBox, QAbstractItemView
)


@dataclass
class ShortcutDef:
    action_id: str
    name: str
    category: str
    default_seq: str
    default_mac: str = ""
    description: str = ""
    attr_name: str = ""
    is_qshortcut: bool = False
    is_custom_event: bool = False


# Comprehensive registry of all application functions that have keyboard shortcuts assigned.
SHORTCUT_DEFINITIONS: List[ShortcutDef] = [
    # -------------------------------------------------------------
    # File & Project
    # -------------------------------------------------------------
    ShortcutDef(
        action_id="open_media",
        name="Open Media...",
        category="File & Project",
        default_seq="Ctrl+O",
        default_mac="Meta+O",
        description="Select an audio or video file to open and process",
        attr_name="open_media_action",
    ),
    ShortcutDef(
        action_id="open_document",
        name="Open Document...",
        category="File & Project",
        default_seq="Ctrl+Alt+O",
        default_mac="Meta+Alt+O",
        description="Load an external transcript or document file",
        attr_name="open_doc_action",
    ),
    ShortcutDef(
        action_id="new_project",
        name="New Project",
        category="File & Project",
        default_seq="Ctrl+N",
        default_mac="Meta+N",
        description="Start a clean segmentation and transcription project",
        attr_name="new_proj_action",
    ),
    ShortcutDef(
        action_id="open_project",
        name="Open Project Session...",
        category="File & Project",
        default_seq="Ctrl+Shift+O",
        default_mac="Meta+Shift+O",
        description="Open a previously saved .prproj session folder or project file",
        attr_name="open_proj_action",
    ),
    ShortcutDef(
        action_id="close_project",
        name="Close Project Session",
        category="File & Project",
        default_seq="Ctrl+W",
        default_mac="Meta+W",
        description="Close active project and unload current media and timeline",
        attr_name="close_proj_action",
    ),
    ShortcutDef(
        action_id="save_project",
        name="Save Project",
        category="File & Project",
        default_seq="Ctrl+S",
        default_mac="Meta+S",
        description="Save current story segments, transcripts, and timeline metadata",
        attr_name="save_action",
    ),
    ShortcutDef(
        action_id="save_project_as",
        name="Save Project As...",
        category="File & Project",
        default_seq="Ctrl+Shift+S",
        default_mac="Meta+Shift+S",
        description="Save the project under a new name or location",
        attr_name="save_as_action",
    ),
    ShortcutDef(
        action_id="export",
        name="Export Dialog...",
        category="File & Project",
        default_seq="Ctrl+E",
        default_mac="Meta+E",
        description="Open export options for text, DOCX, subtitles, and audio clips",
        attr_name="export_action",
    ),
    ShortcutDef(
        action_id="batch_processing_file",
        name="Batch Processing...",
        category="File & Project",
        default_seq="Ctrl+Shift+B",
        default_mac="Meta+Shift+B",
        description="Batch process multiple media files through AI pipeline",
        attr_name="batch_file_action",
    ),
    ShortcutDef(
        action_id="exit_app",
        name="Exit Application",
        category="File & Project",
        default_seq="Ctrl+Q",
        default_mac="Meta+Q",
        description="Quit Radio & TV Story Segmenter",
        attr_name="exit_action",
    ),

    # -------------------------------------------------------------
    # Edit
    # -------------------------------------------------------------
    ShortcutDef(
        action_id="undo",
        name="Undo",
        category="Edit",
        default_seq="Ctrl+Z",
        default_mac="Meta+Z",
        description="Undo the last transcript edit or story segment change",
        attr_name="undo_action",
    ),
    ShortcutDef(
        action_id="redo",
        name="Redo",
        category="Edit",
        default_seq="Ctrl+Y",
        default_mac="Meta+Shift+Z",
        description="Redo the previously undone edit or operation",
        attr_name="redo_action",
    ),
    ShortcutDef(
        action_id="find",
        name="Find and Replace...",
        category="Edit",
        default_seq="Ctrl+F",
        default_mac="Meta+F",
        description="Search for words or phrases in the transcript editor",
        attr_name="find_action",
    ),
    ShortcutDef(
        action_id="find_next",
        name="Find Next Match",
        category="Edit",
        default_seq="F3",
        default_mac="Meta+G",
        description="Jump to the next search occurrence in the transcript",
        attr_name="shortcut_find_next",
        is_qshortcut=True,
    ),

    # -------------------------------------------------------------
    # Panels & Views
    # -------------------------------------------------------------
    ShortcutDef(
        action_id="toggle_timeline",
        name="Toggle Timeline Panel",
        category="Panels & Views",
        default_seq="Alt+1",
        default_mac="Ctrl+Alt+1",
        description="Show or hide the interactive audio waveform & timeline dock",
        attr_name="toggle_timeline_action",
    ),
    ShortcutDef(
        action_id="toggle_transcript",
        name="Toggle Transcript Panel",
        category="Panels & Views",
        default_seq="Alt+2",
        default_mac="Ctrl+Alt+2",
        description="Show or hide the interactive transcript editor dock",
        attr_name="toggle_transcript_action",
    ),
    ShortcutDef(
        action_id="toggle_stories",
        name="Toggle Stories Panel",
        category="Panels & Views",
        default_seq="Alt+3",
        default_mac="Ctrl+Alt+3",
        description="Show or hide the story segments list and metadata dock",
        attr_name="toggle_stories_action",
    ),
    ShortcutDef(
        action_id="toggle_activity",
        name="Toggle Activity History Panel",
        category="Panels & Views",
        default_seq="Alt+4",
        default_mac="Ctrl+Alt+4",
        description="Show or hide the system activity and diagnostic log dock",
        attr_name="toggle_activity_action",
    ),
    ShortcutDef(
        action_id="toggle_waveform",
        name="Toggle Waveform Display",
        category="Panels & Views",
        default_seq="Ctrl+Alt+W",
        default_mac="Meta+Alt+W",
        description="Toggle acoustic waveform visualization on the timeline",
        attr_name="show_waveform_action",
    ),
    ShortcutDef(
        action_id="toggle_thumbnails",
        name="Toggle Video Thumbnails",
        category="Panels & Views",
        default_seq="Ctrl+Alt+T",
        default_mac="Meta+Alt+T",
        description="Toggle video frame thumbnail strip on the timeline",
        attr_name="show_thumbnails_action",
    ),
    ShortcutDef(
        action_id="toggle_video_preview",
        name="Toggle Video Preview Window",
        category="Panels & Views",
        default_seq="Ctrl+Shift+M",
        default_mac="Meta+Shift+M",
        description="Show or hide the detached video playback preview window",
        attr_name="video_preview_action",
    ),
    ShortcutDef(
        action_id="toggle_speaker_labels",
        name="Toggle Speaker Labels",
        category="Panels & Views",
        default_seq="Ctrl+Alt+S",
        default_mac="Meta+Alt+S",
        description="Show or hide detected speaker names in transcript display",
        attr_name="show_speaker_labels_action",
    ),
    ShortcutDef(
        action_id="toggle_timestamps",
        name="Toggle Timestamps",
        category="Panels & Views",
        default_seq="Ctrl+Alt+I",
        default_mac="Meta+Alt+I",
        description="Show or hide timecode markers in transcript display",
        attr_name="show_timestamps_action",
    ),

    # -------------------------------------------------------------
    # AI Pipeline & Tools
    # -------------------------------------------------------------
    ShortcutDef(
        action_id="transcribe",
        name="Transcribe Audio...",
        category="AI Pipeline & Tools",
        default_seq="Ctrl+T",
        default_mac="Meta+T",
        description="Transcribe media speech using Whisper speech-to-text",
        attr_name="transcribe_action",
    ),
    ShortcutDef(
        action_id="diarize",
        name="Detect Speakers (Diarization)...",
        category="AI Pipeline & Tools",
        default_seq="Ctrl+D",
        default_mac="Meta+D",
        description="Identify and cluster different speakers throughout the recording",
        attr_name="diarize_action",
    ),
    ShortcutDef(
        action_id="auto_detect_stories",
        name="Detect Stories...",
        category="AI Pipeline & Tools",
        default_seq="Ctrl+Shift+A",
        default_mac="Meta+Shift+A",
        description="Automatically detect story boundaries based on acoustic pauses and topics",
        attr_name="auto_detect_action",
    ),
    ShortcutDef(
        action_id="translate",
        name="Translate Transcript...",
        category="AI Pipeline & Tools",
        default_seq="Ctrl+Shift+L",
        default_mac="Meta+Shift+L",
        description="Translate transcript text using Helsinki-NLP translation models",
        attr_name="translate_action",
    ),
    ShortcutDef(
        action_id="multi_stage_pipeline",
        name="Multi-Stage Processing Pipeline...",
        category="AI Pipeline & Tools",
        default_seq="Ctrl+R",
        default_mac="Meta+R",
        description="Run automated end-to-end transcription, diarization, and story detection",
        attr_name="transcribe_diarize_detect_action",
    ),
    ShortcutDef(
        action_id="batch_processing_tools",
        name="Batch Processing (Tools)...",
        category="AI Pipeline & Tools",
        default_seq="Ctrl+B",
        default_mac="Meta+B",
        description="Open batch processing queue dialog from the Tools menu",
        attr_name="batch_processing_action",
    ),
    ShortcutDef(
        action_id="regenerate_waveform",
        name="Regenerate Waveform",
        category="AI Pipeline & Tools",
        default_seq="Ctrl+Shift+W",
        default_mac="Meta+Shift+W",
        description="Recompute peak waveform visualization from source audio",
        attr_name="regen_waveform_action",
    ),
    ShortcutDef(
        action_id="regenerate_thumbnails",
        name="Regenerate Video Thumbnails",
        category="AI Pipeline & Tools",
        default_seq="Ctrl+Shift+T",
        default_mac="Meta+Shift+T",
        description="Re-extract video keyframe thumbnails from source video",
        attr_name="regen_thumbnails_action",
    ),
    ShortcutDef(
        action_id="clear_cache",
        name="Clear Temporary Cache...",
        category="AI Pipeline & Tools",
        default_seq="Ctrl+Alt+C",
        default_mac="Meta+Alt+C",
        description="Review and delete cached waveforms, thumbnails, and temp files",
        attr_name="clear_cache_action",
    ),
    ShortcutDef(
        action_id="manage_models",
        name="Manage AI Models...",
        category="AI Pipeline & Tools",
        default_seq="Ctrl+M",
        default_mac="Meta+M",
        description="Download, inspect, or delete Whisper and translation AI model weights",
        attr_name="manage_models_action",
    ),
    ShortcutDef(
        action_id="manage_plugins",
        name="Manage Plugins & Add-ons...",
        category="AI Pipeline & Tools",
        default_seq="Ctrl+Shift+X",
        default_mac="Meta+Shift+X",
        description="Browse, enable, disable, and install extensions and publishing plugins",
        attr_name="manage_plugins_action",
    ),

    # -------------------------------------------------------------
    # Settings & Diagnostics
    # -------------------------------------------------------------
    ShortcutDef(
        action_id="preferences",
        name="Preferences...",
        category="Settings & Diagnostics",
        default_seq="Ctrl+P",
        default_mac="Meta+,",
        description="Open application preferences and configuration dialog",
        attr_name="pref_action",
    ),
    ShortcutDef(
        action_id="customize_shortcuts",
        name="Customize Keyboard Shortcuts...",
        category="Settings & Diagnostics",
        default_seq="Ctrl+K",
        default_mac="Meta+K",
        description="View, customize, reassign, or reset all application keyboard shortcuts",
        attr_name="shortcuts_pref_action",
    ),
    ShortcutDef(
        action_id="gpu_settings",
        name="GPU Acceleration Settings...",
        category="Settings & Diagnostics",
        default_seq="Ctrl+Alt+G",
        default_mac="Meta+Alt+G",
        description="Configure CUDA, DirectML, and CPU inference acceleration options",
        attr_name="gpu_action",
    ),
    ShortcutDef(
        action_id="glossary",
        name="Glossary & Custom Vocabulary...",
        category="Settings & Diagnostics",
        default_seq="Ctrl+Shift+G",
        default_mac="Meta+Shift+G",
        description="Add custom pronunciation hints and domain-specific words for Whisper",
        attr_name="glossary_action",
    ),
    ShortcutDef(
        action_id="check_updates",
        name="Check for Updates...",
        category="Settings & Diagnostics",
        default_seq="Ctrl+U",
        default_mac="Meta+U",
        description="Query GitHub releases repository for new application versions",
        attr_name="update_action",
    ),

    # -------------------------------------------------------------
    # Help
    # -------------------------------------------------------------
    ShortcutDef(
        action_id="help_shortcuts",
        name="Keyboard Shortcuts Reference",
        category="Help",
        default_seq="F1",
        default_mac="Meta+?",
        description="Display formatted cheat-sheet of active shortcuts",
        attr_name="shortcuts_help_action",
    ),
    ShortcutDef(
        action_id="about",
        name="About Application",
        category="Help",
        default_seq="Shift+F1",
        default_mac="Shift+F1",
        description="View version number, architecture, and copyright information",
        attr_name="about_action",
    ),
    ShortcutDef(
        action_id="diagnostic_logs",
        name="Open Diagnostic Log Folder",
        category="Help",
        default_seq="Ctrl+Shift+K",
        default_mac="Meta+Shift+K",
        description="Open the local folder containing application and AI worker logs",
        attr_name="log_action",
    ),
    ShortcutDef(
        action_id="licenses",
        name="Third-Party Licenses",
        category="Help",
        default_seq="Ctrl+Shift+F1",
        default_mac="Meta+Shift+F1",
        description="Display open-source licenses and attribution for bundled libraries",
        attr_name="licenses_action",
    ),

    # -------------------------------------------------------------
    # Playback & Navigation
    # -------------------------------------------------------------
    ShortcutDef(
        action_id="play_pause",
        name="Play / Pause Playback",
        category="Playback & Navigation",
        default_seq="Space",
        description="Toggle audio and video playback at current timeline position",
        is_custom_event=True,
    ),
    ShortcutDef(
        action_id="seek_backward",
        name="Skip Backward",
        category="Playback & Navigation",
        default_seq="Left",
        description="Jump backward by configured skip duration",
        is_custom_event=True,
    ),
    ShortcutDef(
        action_id="seek_forward",
        name="Skip Forward",
        category="Playback & Navigation",
        default_seq="Right",
        description="Jump forward by configured skip duration",
        is_custom_event=True,
    ),
    ShortcutDef(
        action_id="seek_start",
        name="Seek to Start",
        category="Playback & Navigation",
        default_seq="Home",
        description="Jump playhead immediately to the beginning of the media",
        is_custom_event=True,
    ),
    ShortcutDef(
        action_id="seek_end",
        name="Seek to End",
        category="Playback & Navigation",
        default_seq="End",
        description="Jump playhead immediately to the end of the media",
        is_custom_event=True,
    ),
    ShortcutDef(
        action_id="zoom_in",
        name="Timeline Zoom In",
        category="Playback & Navigation",
        default_seq="+",
        description="Zoom in horizontally on the audio timeline",
        is_custom_event=True,
    ),
    ShortcutDef(
        action_id="zoom_out",
        name="Timeline Zoom Out",
        category="Playback & Navigation",
        default_seq="-",
        description="Zoom out horizontally on the audio timeline",
        is_custom_event=True,
    ),
    ShortcutDef(
        action_id="transcript_font_up",
        name="Increase Transcript Font Size",
        category="Playback & Navigation",
        default_seq="Ctrl++",
        default_mac="Meta++",
        description="Enlarge font size in the interactive transcript view",
        attr_name="shortcut_transcript_font_up",
        is_qshortcut=True,
    ),
    ShortcutDef(
        action_id="transcript_font_down",
        name="Decrease Transcript Font Size",
        category="Playback & Navigation",
        default_seq="Ctrl+-",
        default_mac="Meta+-",
        description="Reduce font size in the interactive transcript view",
        attr_name="shortcut_transcript_font_down",
        is_qshortcut=True,
    ),
    ShortcutDef(
        action_id="transcript_font_reset",
        name="Reset Transcript Font Size",
        category="Playback & Navigation",
        default_seq="Ctrl+0",
        default_mac="Meta+0",
        description="Restore transcript view font size to default",
        attr_name="shortcut_transcript_font_reset",
        is_qshortcut=True,
    ),
]


def get_platform_default(defn: ShortcutDef) -> str:
    """Return the platform-adapted default shortcut string for a definition."""
    if sys.platform == "darwin":
        if defn.default_mac:
            return defn.default_mac
        if "Ctrl+" in defn.default_seq:
            return defn.default_seq.replace("Ctrl+", "Meta+")
    return defn.default_seq


def format_sequence_display(seq_str: str) -> str:
    """Format key sequence into clean user-readable text for current OS."""
    if not seq_str or seq_str in ("None", "<none>", ""):
        return "None"
    seq = QKeySequence(seq_str)
    if not seq.isEmpty():
        native = seq.toString(QKeySequence.SequenceFormat.NativeText)
        if native:
            return native
    return seq_str


def normalize_sequence_string(seq_str: str) -> str:
    """Return portable normalized representation of a shortcut string."""
    if not seq_str or seq_str.strip() in ("", "None", "<none>"):
        return ""
    seq = QKeySequence(seq_str.strip())
    if seq.isEmpty():
        return seq_str.strip()
    return seq.toString(QKeySequence.SequenceFormat.PortableText)


class ShortcutsManager(QObject):
    """Central repository and coordinator for all configurable application shortcuts."""

    shortcutsChanged = Signal()

    def __init__(self, settings_store: Optional[QSettings] = None):
        super().__init__()
        if settings_store is None:
            settings_store = QSettings("RadioTVStorySegmenter", "RadioTVStorySegmenter")
        self.settings_store = settings_store
        self._overrides: Dict[str, str] = {}
        self.load()

    def load(self):
        """Read customized shortcut overrides from QSettings."""
        self._overrides.clear()
        try:
            self.settings_store.beginGroup("keyboard_shortcuts")
            for defn in SHORTCUT_DEFINITIONS:
                val = self.settings_store.value(defn.action_id, None)
                if val is not None and str(val).strip() != "":
                    self._overrides[defn.action_id] = str(val).strip()
            self.settings_store.endGroup()
        except Exception as exc:
            print(f"[SHORTCUTS] Error loading shortcut settings: {exc}")

    def get_definitions(self) -> List[ShortcutDef]:
        return SHORTCUT_DEFINITIONS

    def get_definition(self, action_id: str) -> Optional[ShortcutDef]:
        for defn in SHORTCUT_DEFINITIONS:
            if defn.action_id == action_id:
                return defn
        return None

    def get_default_shortcut(self, action_id: str) -> str:
        defn = self.get_definition(action_id)
        if defn:
            return get_platform_default(defn)
        return ""

    def get_current_shortcut(self, action_id: str) -> str:
        if action_id in self._overrides:
            return self._overrides[action_id]
        return self.get_default_shortcut(action_id)

    def is_customized(self, action_id: str) -> bool:
        if action_id not in self._overrides:
            return False
        default_seq = normalize_sequence_string(self.get_default_shortcut(action_id))
        cur_seq = normalize_sequence_string(self._overrides[action_id])
        return cur_seq != default_seq

    def set_shortcut(self, action_id: str, new_seq: str):
        """Set a shortcut override for action_id. Passing empty string or None sets to None."""
        if not new_seq or new_seq.strip() in ("", "None", "<none>"):
            self._overrides[action_id] = "None"
            return

        normalized = normalize_sequence_string(new_seq)
        default_seq = normalize_sequence_string(self.get_default_shortcut(action_id))
        if normalized == default_seq:
            if action_id in self._overrides:
                del self._overrides[action_id]
        else:
            self._overrides[action_id] = normalized

    def reset_shortcut(self, action_id: str):
        """Reset a single shortcut back to its platform default."""
        if action_id in self._overrides:
            del self._overrides[action_id]

    def reset_all(self):
        """Reset all shortcuts back to application defaults."""
        self._overrides.clear()

    def save(self):
        """Persist all overrides to QSettings and emit notification signal."""
        try:
            self.settings_store.beginGroup("keyboard_shortcuts")
            self.settings_store.remove("")  # remove existing keys in group
            for act_id, seq_str in self._overrides.items():
                self.settings_store.setValue(act_id, seq_str)
            self.settings_store.endGroup()
            self.settings_store.sync()
        except Exception as exc:
            print(f"[SHORTCUTS] Error saving shortcut settings: {exc}")
        self.shortcutsChanged.emit()

    def find_conflict(self, candidate_seq: str, excluding_action_id: str = "") -> Optional[ShortcutDef]:
        """Check if candidate_seq is already bound to another action."""
        if not candidate_seq or candidate_seq.strip() in ("", "None", "<none>"):
            return None
        norm_candidate = normalize_sequence_string(candidate_seq).lower()
        if not norm_candidate:
            return None

        for defn in SHORTCUT_DEFINITIONS:
            if defn.action_id == excluding_action_id:
                continue
            cur = self.get_current_shortcut(defn.action_id)
            if not cur or cur in ("None", "<none>"):
                continue
            if normalize_sequence_string(cur).lower() == norm_candidate:
                return defn
        return None

    def apply_to_window(self, window):
        """Update shortcuts on all QAction and QShortcut objects on MainWindow."""
        from prs_shared import platform_seq

        for defn in SHORTCUT_DEFINITIONS:
            cur_seq = self.get_current_shortcut(defn.action_id)
            if not cur_seq or cur_seq == "None":
                qt_seq = QKeySequence()
            else:
                # platform_seq handles Mac Ctrl->Meta translation if not already done
                qt_seq = platform_seq(cur_seq)

            if defn.attr_name and hasattr(window, defn.attr_name):
                target = getattr(window, defn.attr_name)
                if target is not None:
                    try:
                        if defn.is_qshortcut:
                            target.setKey(qt_seq)
                        else:
                            target.setShortcut(qt_seq)
                    except Exception as exc:
                        print(f"[SHORTCUTS] Failed to apply shortcut {cur_seq} to {defn.attr_name}: {exc}")


class KeySequenceRecorderEdit(QLineEdit):
    """Interactive input widget that captures key presses and formats them into a shortcut sequence."""

    keySequenceChanged = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setReadOnly(True)
        self.is_recording = False
        self.current_seq = ""
        self.setPlaceholderText("Click 'Record' to press shortcut keys...")
        self.setStyleSheet(
            "QLineEdit { font-weight: bold; padding: 5px 8px; border-radius: 4px; border: 1px solid #475569; }"
        )

    def set_sequence(self, seq_str: str):
        self.current_seq = seq_str or ""
        self.setText(format_sequence_display(self.current_seq))

    def get_sequence(self) -> str:
        return self.current_seq

    def start_recording(self):
        self.is_recording = True
        self.setText("Press desired key combination...")
        self.setStyleSheet(
            "QLineEdit { font-weight: bold; padding: 5px 8px; border-radius: 4px; "
            "border: 2px solid #3b82f6; background-color: #1e293b; color: #60a5fa; }"
        )
        self.setFocus()

    def stop_recording(self):
        self.is_recording = False
        self.setStyleSheet(
            "QLineEdit { font-weight: bold; padding: 5px 8px; border-radius: 4px; border: 1px solid #475569; }"
        )
        self.setText(format_sequence_display(self.current_seq))

    def keyPressEvent(self, event):
        if not self.is_recording:
            super().keyPressEvent(event)
            return

        key = event.key()

        # Ignore standalone modifier keys while user is holding them down
        if key in (Qt.Key.Key_Control, Qt.Key.Key_Shift, Qt.Key.Key_Alt, Qt.Key.Key_Meta):
            event.accept()
            return

        # Pressing Escape cancels recording without changing the current shortcut
        if key == Qt.Key.Key_Escape:
            self.stop_recording()
            event.accept()
            return

        # Pressing Backspace or Delete while recording clears the shortcut
        if key in (Qt.Key.Key_Backspace, Qt.Key.Key_Delete) and not (event.modifiers() & ~Qt.KeyboardModifier.KeypadModifier):
            self.current_seq = "None"
            self.stop_recording()
            self.keySequenceChanged.emit("None")
            event.accept()
            return

        modifiers = int(event.modifiers())
        key_seq = QKeySequence(modifiers | key)
        new_seq_str = key_seq.toString(QKeySequence.SequenceFormat.PortableText)

        if not new_seq_str:
            new_seq_str = QKeySequence(key).toString(QKeySequence.SequenceFormat.PortableText)

        self.current_seq = new_seq_str
        self.stop_recording()
        self.keySequenceChanged.emit(self.current_seq)
        event.accept()


class KeyboardShortcutsPage(QWidget):
    """Preferences page that provides a searchable table of all customizable shortcuts,
    an interactive recorder, conflict resolution, and reset controls."""

    def __init__(self, shortcuts_manager: ShortcutsManager, parent_window=None, parent=None):
        super().__init__(parent)
        self.mgr = shortcuts_manager
        self.parent_window = parent_window
        # Working copy of shortcuts so changes can be cancelled or applied
        self.pending_shortcuts: Dict[str, str] = {}
        for defn in self.mgr.get_definitions():
            self.pending_shortcuts[defn.action_id] = self.mgr.get_current_shortcut(defn.action_id)

        self.selected_action_id: Optional[str] = None
        self._init_ui()
        self._populate_table()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(10)

        # Header description
        desc_lbl = QLabel(
            "<b>Customize Keyboard Shortcuts</b><br>"
            "<span style='color: #64748b; font-size: 12px;'>"
            "Select any menu action, playback command, or navigation tool to assign a custom shortcut key. "
            "Conflicts are flagged in real-time, and you can restore system defaults at any time.</span>"
        )
        desc_lbl.setWordWrap(True)
        layout.addWidget(desc_lbl)

        # Search & Category Filter Toolbar
        filter_bar = QHBoxLayout()
        filter_bar.setSpacing(8)

        search_lbl = QLabel("Search:")
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Filter by action name, shortcut, or category...")
        self.search_input.setClearButtonEnabled(True)
        self.search_input.textChanged.connect(self._filter_table)
        filter_bar.addWidget(search_lbl)
        filter_bar.addWidget(self.search_input, 2)

        cat_lbl = QLabel("Category:")
        self.cat_combo = QComboBox()
        self.cat_combo.addItem("All Categories", "all")
        categories = sorted(list({d.category for d in self.mgr.get_definitions()}))
        for c in categories:
            self.cat_combo.addItem(c, c)
        self.cat_combo.currentIndexChanged.connect(self._filter_table)
        filter_bar.addWidget(cat_lbl)
        filter_bar.addWidget(self.cat_combo, 1)

        layout.addLayout(filter_bar)

        # Main Shortcuts Table
        self.table = QTableWidget(self)
        self.table.setColumnCount(5)
        self.table.setHorizontalHeaderLabels(["Action", "Category", "Current Shortcut", "Default", "Status"])
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().setVisible(False)

        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)

        self.table.itemSelectionChanged.connect(self._on_row_selected)
        self.table.itemDoubleClicked.connect(lambda item: self.recorder_btn.click())
        layout.addWidget(self.table, 1)

        # Editor Group Box
        self.edit_group = QGroupBox("Edit Selected Shortcut")
        edit_layout = QVBoxLayout(self.edit_group)
        edit_layout.setSpacing(8)

        action_info_layout = QHBoxLayout()
        self.selected_name_lbl = QLabel("<b>Select an action above to modify its shortcut</b>")
        action_info_layout.addWidget(self.selected_name_lbl)
        action_info_layout.addStretch()
        edit_layout.addLayout(action_info_layout)

        # Recorder row
        record_row = QHBoxLayout()
        record_row.setSpacing(8)

        self.recorder_edit = KeySequenceRecorderEdit(self)
        self.recorder_edit.keySequenceChanged.connect(self._on_recorded_sequence)
        record_row.addWidget(self.recorder_edit, 2)

        self.recorder_btn = QPushButton("Record Shortcut")
        self.recorder_btn.setToolTip("Click to record next key combination")
        self.recorder_btn.clicked.connect(self._toggle_recording)
        record_row.addWidget(self.recorder_btn)

        self.clear_btn = QPushButton("Clear")
        self.clear_btn.setToolTip("Remove shortcut assignment for this action")
        self.clear_btn.clicked.connect(self._clear_selected_shortcut)
        record_row.addWidget(self.clear_btn)

        self.reset_item_btn = QPushButton("Reset to Default")
        self.reset_item_btn.setToolTip("Restore factory default shortcut for this action")
        self.reset_item_btn.clicked.connect(self._reset_selected_shortcut)
        record_row.addWidget(self.reset_item_btn)

        edit_layout.addLayout(record_row)

        # Conflict Banner
        self.conflict_frame = QFrame()
        self.conflict_frame.setStyleSheet(
            "QFrame { background-color: #451a03; border: 1px solid #b45309; border-radius: 4px; padding: 6px; }"
        )
        conflict_layout = QHBoxLayout(self.conflict_frame)
        conflict_layout.setContentsMargins(6, 4, 6, 4)
        self.conflict_lbl = QLabel()
        self.conflict_lbl.setStyleSheet("color: #fef08a; font-size: 12px;")
        conflict_layout.addWidget(self.conflict_lbl, 1)

        self.reassign_btn = QPushButton("Reassign to this Action")
        self.reassign_btn.setStyleSheet(
            "QPushButton { background-color: #b45309; color: white; font-weight: bold; border-radius: 4px; padding: 4px 8px; }"
            "QPushButton:hover { background-color: #d97706; }"
        )
        self.reassign_btn.clicked.connect(self._reassign_conflict)
        conflict_layout.addWidget(self.reassign_btn)

        self.conflict_frame.setVisible(False)
        edit_layout.addWidget(self.conflict_frame)

        layout.addWidget(self.edit_group)

        # Bottom bulk actions row
        bottom_bar = QHBoxLayout()
        self.reset_all_btn = QPushButton("Restore All to Factory Defaults")
        self.reset_all_btn.setToolTip("Reset all keyboard shortcuts back to initial installation defaults")
        self.reset_all_btn.clicked.connect(self._confirm_reset_all)
        bottom_bar.addWidget(self.reset_all_btn)
        bottom_bar.addStretch()

        layout.addLayout(bottom_bar)

    def _populate_table(self):
        self.table.setRowCount(0)
        definitions = self.mgr.get_definitions()
        self.table.setRowCount(len(definitions))

        for row, defn in enumerate(definitions):
            cur = self.pending_shortcuts.get(defn.action_id, self.mgr.get_default_shortcut(defn.action_id))
            default_seq = self.mgr.get_default_shortcut(defn.action_id)

            # Column 0: Action Name & Description
            item_action = QTableWidgetItem(defn.name)
            item_action.setData(Qt.ItemDataRole.UserRole, defn.action_id)
            if defn.description:
                item_action.setToolTip(defn.description)
            self.table.setItem(row, 0, item_action)

            # Column 1: Category
            item_cat = QTableWidgetItem(defn.category)
            self.table.setItem(row, 1, item_cat)

            # Column 2: Current Shortcut
            item_seq = QTableWidgetItem(format_sequence_display(cur))
            item_seq.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            font = item_seq.font()
            font.setBold(True)
            item_seq.setFont(font)
            self.table.setItem(row, 2, item_seq)

            # Column 3: Default Shortcut
            item_def = QTableWidgetItem(format_sequence_display(default_seq))
            item_def.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.table.setItem(row, 3, item_def)

            # Column 4: Status
            is_custom = normalize_sequence_string(cur) != normalize_sequence_string(default_seq)
            status_text = "Custom" if is_custom else "Default"
            item_status = QTableWidgetItem(status_text)
            item_status.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            if is_custom:
                item_status.setForeground(QColor("#38bdf8"))
            else:
                item_status.setForeground(QColor("#94a3b8"))
            self.table.setItem(row, 4, item_status)

        if self.table.rowCount() > 0:
            self.table.selectRow(0)

    def _filter_table(self):
        query = self.search_input.text().strip().lower()
        selected_cat = self.cat_combo.currentData()

        for row in range(self.table.rowCount()):
            item_action = self.table.item(row, 0)
            item_cat = self.table.item(row, 1)
            item_seq = self.table.item(row, 2)

            act_text = item_action.text().lower()
            cat_text = item_cat.text()
            seq_text = item_seq.text().lower()

            matches_cat = (selected_cat == "all") or (cat_text == selected_cat)
            matches_query = (not query) or (query in act_text) or (query in seq_text) or (query in cat_text.lower())

            self.table.setRowHidden(row, not (matches_cat and matches_query))

    def _on_row_selected(self):
        selected_rows = self.table.selectionModel().selectedRows()
        if not selected_rows:
            self.selected_action_id = None
            self.selected_name_lbl.setText("<b>Select an action above to modify its shortcut</b>")
            self.recorder_edit.set_sequence("")
            self.recorder_btn.setEnabled(False)
            self.clear_btn.setEnabled(False)
            self.reset_item_btn.setEnabled(False)
            self.conflict_frame.setVisible(False)
            return

        row = selected_rows[0].row()
        item = self.table.item(row, 0)
        action_id = item.data(Qt.ItemDataRole.UserRole)
        self.selected_action_id = action_id

        defn = self.mgr.get_definition(action_id)
        if defn:
            self.selected_name_lbl.setText(f"<b>{defn.name}</b> &nbsp;<span style='color: #94a3b8; font-size: 12px;'>({defn.category}) — {defn.description}</span>")
            cur_seq = self.pending_shortcuts.get(action_id, self.mgr.get_default_shortcut(action_id))
            self.recorder_edit.set_sequence(cur_seq)
            self.recorder_btn.setEnabled(True)
            self.clear_btn.setEnabled(True)
            self.reset_item_btn.setEnabled(True)
            self._check_conflict(cur_seq)

    def _toggle_recording(self):
        if self.recorder_edit.is_recording:
            self.recorder_edit.stop_recording()
            self.recorder_btn.setText("Record Shortcut")
        else:
            self.recorder_edit.start_recording()
            self.recorder_btn.setText("Cancel Recording")

    def _on_recorded_sequence(self, new_seq: str):
        self.recorder_btn.setText("Record Shortcut")
        if not self.selected_action_id:
            return

        self._check_conflict(new_seq)
        self._apply_pending_change(self.selected_action_id, new_seq)

    def _clear_selected_shortcut(self):
        if not self.selected_action_id:
            return
        self.recorder_edit.set_sequence("None")
        self.conflict_frame.setVisible(False)
        self._apply_pending_change(self.selected_action_id, "None")

    def _reset_selected_shortcut(self):
        if not self.selected_action_id:
            return
        def_seq = self.mgr.get_default_shortcut(self.selected_action_id)
        self.recorder_edit.set_sequence(def_seq)
        self._check_conflict(def_seq)
        self._apply_pending_change(self.selected_action_id, def_seq)

    def _apply_pending_change(self, action_id: str, new_seq: str):
        self.pending_shortcuts[action_id] = new_seq
        # Update row in table
        for row in range(self.table.rowCount()):
            item = self.table.item(row, 0)
            if item and item.data(Qt.ItemDataRole.UserRole) == action_id:
                # Update current shortcut
                self.table.item(row, 2).setText(format_sequence_display(new_seq))
                # Update status
                default_seq = self.mgr.get_default_shortcut(action_id)
                is_custom = normalize_sequence_string(new_seq) != normalize_sequence_string(default_seq)
                status_item = self.table.item(row, 4)
                status_item.setText("Custom" if is_custom else "Default")
                status_item.setForeground(QColor("#38bdf8") if is_custom else QColor("#94a3b8"))
                break

    def _check_conflict(self, candidate_seq: str):
        if not candidate_seq or candidate_seq in ("None", "<none>", ""):
            self.conflict_frame.setVisible(False)
            return

        norm_candidate = normalize_sequence_string(candidate_seq).lower()
        conflicting_defn = None

        for defn in self.mgr.get_definitions():
            if defn.action_id == self.selected_action_id:
                continue
            cur = self.pending_shortcuts.get(defn.action_id, self.mgr.get_default_shortcut(defn.action_id))
            if not cur or cur in ("None", "<none>"):
                continue
            if normalize_sequence_string(cur).lower() == norm_candidate:
                conflicting_defn = defn
                break

        if conflicting_defn:
            self.conflict_lbl.setText(
                f"⚠️ <b>Conflict Detected:</b> '<b>{format_sequence_display(candidate_seq)}</b>' "
                f"is currently assigned to '<b>{conflicting_defn.name}</b>' ({conflicting_defn.category})."
            )
            self.conflicting_action_id = conflicting_defn.action_id
            self.conflict_frame.setVisible(True)
        else:
            self.conflict_frame.setVisible(False)

    def _reassign_conflict(self):
        """Remove shortcut from conflicting action and assign to current selected action."""
        if hasattr(self, "conflicting_action_id") and self.conflicting_action_id:
            # Clear shortcut on conflicting action
            self._apply_pending_change(self.conflicting_action_id, "None")
            self.conflict_frame.setVisible(False)

    def _confirm_reset_all(self):
        reply = QMessageBox.question(
            self,
            "Reset All Shortcuts",
            "Are you sure you want to reset ALL keyboard shortcuts to their factory defaults?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            self.pending_shortcuts.clear()
            for defn in self.mgr.get_definitions():
                self.pending_shortcuts[defn.action_id] = self.mgr.get_default_shortcut(defn.action_id)
            self._populate_table()
            self._on_row_selected()

    def save_shortcuts(self):
        """Commit all pending shortcut changes to QSettings and apply to the MainWindow."""
        for action_id, seq in self.pending_shortcuts.items():
            self.mgr.set_shortcut(action_id, seq)
        self.mgr.save()
        if self.parent_window:
            self.mgr.apply_to_window(self.parent_window)
