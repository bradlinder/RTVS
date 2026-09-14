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
        action_id="export_zip",
        name="Export Project Archive (.zip)...",
        category="File & Project",
        default_seq="Ctrl+Shift+E",
        default_mac="Meta+Shift+E",
        description="Export current project state, transcripts, and media into a self-contained portable .zip archive",
        attr_name="export_zip_action",
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
        action_id="export_stories",
        name="Export Selected Stories...",
        category="File & Project",
        default_seq="Ctrl+Alt+E",
        default_mac="Meta+Alt+E",
        description="Export selected story segments into text, subtitle, or DOCX files",
        attr_name="export_stories_action",
    ),
    ShortcutDef(
        action_id="batch_processing_file",
        name="Batch Processing...",
        category="File & Project",
        default_seq="Ctrl+Shift+B",
        default_mac="Meta+Shift+B",
        description="Batch process multiple media files through AI pipeline",
        attr_name="batch_processing_action",
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
        default_seq="Ctrl+Shift+Z",
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
    # Transcript Editing & Formatting
    # -------------------------------------------------------------
    ShortcutDef(
        action_id="add_comment",
        name="Add / Edit Comment...",
        category="Transcript Editing & Formatting",
        default_seq="Ctrl+M",
        default_mac="Meta+M",
        description="Add a comment to the current transcript segment or active text selection",
        attr_name="add_comment_action",
    ),
    ShortcutDef(
        action_id="delete_comment",
        name="Delete Comment",
        category="Transcript Editing & Formatting",
        default_seq="Ctrl+Alt+D",
        default_mac="Meta+Alt+D",
        description="Delete comment card or comment anchored to target segment",
        attr_name="delete_comment_action",
    ),
    ShortcutDef(
        action_id="toggle_edit_mode",
        name="Toggle Transcript Edit Mode",
        category="Transcript Editing & Formatting",
        default_seq="F2",
        default_mac="F2",
        description="Switch between interactive playback/selection mode and text editing mode",
        attr_name="transcript_edit_mode_action",
    ),
    ShortcutDef(
        action_id="fmt_bold",
        name="Bold Text",
        category="Transcript Editing & Formatting",
        default_seq="Ctrl+B",
        default_mac="Meta+B",
        description="Apply or remove bold formatting on selected transcript text",
        attr_name="fmt_bold_action",
    ),
    ShortcutDef(
        action_id="fmt_italic",
        name="Italic Text",
        category="Transcript Editing & Formatting",
        default_seq="Ctrl+I",
        default_mac="Meta+I",
        description="Apply or remove italic formatting on selected transcript text",
        attr_name="fmt_italic_action",
    ),
    ShortcutDef(
        action_id="fmt_underline",
        name="Underline Text",
        category="Transcript Editing & Formatting",
        default_seq="Ctrl+U",
        default_mac="Meta+U",
        description="Apply or remove underline formatting on selected transcript text",
        attr_name="fmt_underline_action",
    ),
    ShortcutDef(
        action_id="fmt_strikethrough",
        name="Strikethrough Text",
        category="Transcript Editing & Formatting",
        default_seq="Ctrl+K",
        default_mac="Meta+K",
        description="Apply or remove strikethrough formatting on selected transcript text",
        attr_name="fmt_strike_action",
    ),
    ShortcutDef(
        action_id="fmt_highlight",
        name="Highlight Text (Yellow)",
        category="Transcript Editing & Formatting",
        default_seq="Ctrl+Shift+H",
        default_mac="Meta+Shift+H",
        description="Apply or remove yellow highlight on selected transcript text",
        attr_name="fmt_highlight_action",
    ),
    ShortcutDef(
        action_id="remove_highlight",
        name="Remove Highlight",
        category="Transcript Editing & Formatting",
        default_seq="Ctrl+Alt+H",
        default_mac="Meta+Alt+H",
        description="Remove background highlighting across the entire contiguous highlighted section",
        attr_name="fmt_remove_highlight_action",
    ),
    ShortcutDef(
        action_id="fmt_clear",
        name="Clear Text Formatting",
        category="Transcript Editing & Formatting",
        default_seq="Ctrl+\\",
        default_mac="Meta+\\",
        description="Remove bold, italic, and other rich formatting from selection",
        attr_name="fmt_clear_action",
    ),
    ShortcutDef(
        action_id="split_speaker",
        name="Split Speaker Segment",
        category="Transcript Editing & Formatting",
        default_seq="Shift+Return",
        default_mac="Shift+Return",
        description="Split speaker segment at current text cursor position",
        attr_name="fmt_split_action",
    ),
    ShortcutDef(
        action_id="remove_speaker_label",
        name="Remove Speaker Label",
        category="Transcript Editing & Formatting",
        default_seq="Ctrl+Shift+K",
        default_mac="Meta+Shift+K",
        description="Remove speaker label marker at target segment cursor",
        attr_name="remove_speaker_label_action",
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
        action_id="toggle_comments",
        name="Toggle Comments Sidebar",
        category="Panels & Views",
        default_seq="Ctrl+Alt+C",
        default_mac="Meta+Alt+C",
        description="Show or hide the interactive comments and annotations sidebar dock",
        attr_name="toggle_comments_action",
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
        default_seq="Ctrl+Shift+V",
        default_mac="Meta+Shift+V",
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
    ShortcutDef(
        action_id="theme_dark",
        name="Switch to Dark Theme",
        category="Panels & Views",
        default_seq="",
        default_mac="",
        description="Switch application visual theme to dark mode",
        attr_name="dark_theme_action",
    ),
    ShortcutDef(
        action_id="theme_light",
        name="Switch to Light Theme",
        category="Panels & Views",
        default_seq="",
        default_mac="",
        description="Switch application visual theme to light mode",
        attr_name="light_theme_action",
    ),
    ShortcutDef(
        action_id="theme_hc",
        name="Switch to High Contrast Theme",
        category="Panels & Views",
        default_seq="",
        default_mac="",
        description="Switch application visual theme to high contrast mode",
        attr_name="hc_theme_action",
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
        action_id="transcribe_diarize",
        name="Transcribe & Detect Speakers...",
        category="AI Pipeline & Tools",
        default_seq="",
        default_mac="",
        description="Run speech transcription and speaker diarization in sequence",
        attr_name="transcribe_diarize_action",
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
        default_seq="",
        default_mac="",
        description="Review and delete cached waveforms, thumbnails, and temp files",
        attr_name="clear_cache_action",
    ),
    ShortcutDef(
        action_id="manage_models",
        name="Manage AI Models...",
        category="AI Pipeline & Tools",
        default_seq="Ctrl+Alt+M",
        default_mac="Meta+Alt+M",
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
    ShortcutDef(
        action_id="manage_speakers",
        name="Manage Speakers & Detection Clusters...",
        category="AI Pipeline & Tools",
        default_seq="Ctrl+Alt+P",
        default_mac="Meta+Alt+P",
        description="Open speaker management dialog to rename, merge, or re-cluster speaker voices",
        attr_name="manage_speakers_action",
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
        default_seq="F8",
        default_mac="F8",
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
        action_id="add_to_glossary",
        name="Add Selected Text to Glossary",
        category="Settings & Diagnostics",
        default_seq="Ctrl+Alt+V",
        default_mac="Meta+Alt+V",
        description="Add highlighted text string directly to Whisper custom vocabulary glossary",
        attr_name="add_to_glossary_action",
    ),
    ShortcutDef(
        action_id="lang_en",
        name="Switch Interface to English",
        category="Settings & Diagnostics",
        default_seq="",
        default_mac="",
        description="Set interface language to English",
        attr_name="lang_en_action",
    ),
    ShortcutDef(
        action_id="lang_es",
        name="Switch Interface to Spanish",
        category="Settings & Diagnostics",
        default_seq="",
        default_mac="",
        description="Set interface language to Spanish (Español)",
        attr_name="lang_es_action",
    ),
    ShortcutDef(
        action_id="check_updates",
        name="Check for Updates...",
        category="Settings & Diagnostics",
        default_seq="Ctrl+Shift+U",
        default_mac="Meta+Shift+U",
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
        action_id="play_selection",
        name="Play Selected Text",
        category="Playback & Navigation",
        default_seq="Ctrl+Space",
        default_mac="Meta+Space",
        description="Start media playback for the active text selection span",
        attr_name="play_selection_action",
    ),
    ShortcutDef(
        action_id="clear_selection",
        name="Clear Text Selection",
        category="Playback & Navigation",
        default_seq="Esc",
        default_mac="Esc",
        description="Deselect active text selection in the transcript editor",
        attr_name="clear_selection_action",
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

    # -------------------------------------------------------------
    # Story Management
    # -------------------------------------------------------------
    ShortcutDef(
        action_id="add_selection_story",
        name="Add Selected Text to New Story",
        category="Story Management",
        default_seq="Ctrl+Alt+N",
        default_mac="Meta+Alt+N",
        description="Create a new story segment from current transcript text selection",
        attr_name="add_selection_story_action",
    ),
    ShortcutDef(
        action_id="set_story_start",
        name="Set Story Start Time to Playhead",
        category="Story Management",
        default_seq="Ctrl+[",
        default_mac="Meta+[",
        description="Set start timestamp of selected story to current media playhead position",
        attr_name="set_story_start_action",
    ),
    ShortcutDef(
        action_id="set_story_end",
        name="Set Story End Time to Playhead",
        category="Story Management",
        default_seq="Ctrl+]",
        default_mac="Meta+]",
        description="Set end timestamp of selected story to current media playhead position",
        attr_name="set_story_end_action",
    ),
    ShortcutDef(
        action_id="delete_story",
        name="Delete Selected Story",
        category="Story Management",
        default_seq="Delete",
        default_mac="Delete",
        description="Remove selected story segment from the project stories list",
        attr_name="delete_story_action",
    ),
    ShortcutDef(
        action_id="merge_stories",
        name="Merge Selected Stories",
        category="Story Management",
        default_seq="Ctrl+Shift+M",
        default_mac="Meta+Shift+M",
        description="Merge multiple selected story items into a single contiguous story",
        attr_name="merge_stories_action",
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
        """Update shortcuts on all QAction and QShortcut objects on MainWindow,
        configuring ApplicationShortcut context so in-focus app shortcuts reliably override other apps."""
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
                            if hasattr(target, "setContext"):
                                target.setContext(Qt.ShortcutContext.ApplicationShortcut)
                        else:
                            target.setShortcut(qt_seq)
                            if hasattr(target, "setShortcutContext"):
                                target.setShortcutContext(Qt.ShortcutContext.ApplicationShortcut)
                            if hasattr(window, "addAction") and target not in window.actions():
                                window.addAction(target)
                    except Exception as exc:
                        print(f"[SHORTCUTS] Failed to apply shortcut {cur_seq} to {defn.attr_name}: {exc}")

        # Update toolbar buttons and controls to dynamically display current shortcuts in tooltips
        button_tooltips = {
            "toggle_comments": ("comments_toggle_btn", "Toggle Comments Sidebar & Annotations"),
            "toggle_edit_mode": ("transcript_mode_toggle_btn", "Switch to Text Editing Mode"),
            "transcript_font_up": ("transcript_font_up_btn", "Increase Transcript Font Size"),
            "transcript_font_down": ("transcript_font_down_btn", "Decrease Transcript Font Size"),
            "transcript_font_reset": ("transcript_font_reset_btn", "Reset Transcript Font Size"),
            "fmt_bold": ("fmt_bold_btn", "Bold"),
            "fmt_italic": ("fmt_italic_btn", "Italic"),
            "fmt_underline": ("fmt_underline_btn", "Underline"),
            "fmt_strikethrough": ("fmt_strike_btn", "Strikethrough"),
            "fmt_highlight": ("fmt_highlight_btn", "Highlight Text (Yellow)"),
            "fmt_clear": ("fmt_clear_btn", "Clear Formatting"),
            "split_speaker": ("fmt_split_btn", "Split Speaker Segment at Cursor"),
            "play_pause": ("play_pause_btn", "Play / Pause playback"),
            "set_story_start": ("set_story_start_btn", "Set start time of selected story"),
            "set_story_end": ("set_story_end_btn", "Set end time of selected story"),
            "add_story": ("add_story_btn", "Add story from active selection"),
            "export_stories": ("export_stories_btn", "Unified Export"),
        }

        for action_id, (attr_name, base_text) in button_tooltips.items():
            if hasattr(window, attr_name):
                btn = getattr(window, attr_name)
                if btn is not None:
                    seq_str = self.get_current_shortcut(action_id)
                    if seq_str and seq_str not in ("None", "<none>"):
                        disp_str = format_sequence_display(seq_str)
                        btn.setToolTip(f"{base_text} ({disp_str})")
                    else:
                        btn.setToolTip(base_text)


class KeySequenceRecorderEdit(QLineEdit):
    """Interactive input widget that captures key presses and formats them into a shortcut sequence."""

    keySequenceChanged = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setReadOnly(True)
        self.is_recording = False
        self.current_seq = ""
        self.setPlaceholderText("Click here and press shortcut keys...")
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
        self.setText("Press desired key combination (or Esc to cancel)...")
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

    def mousePressEvent(self, event):
        super().mousePressEvent(event)
        if not self.is_recording:
            self.start_recording()

    def focusInEvent(self, event):
        super().focusInEvent(event)
        if not self.is_recording:
            self.start_recording()

    def focusOutEvent(self, event):
        if self.is_recording:
            self.stop_recording()
        super().focusOutEvent(event)

    def keyPressEvent(self, event):
        if not self.is_recording:
            super().keyPressEvent(event)
            return

        key = event.key()

        # Ignore standalone modifier keys while user is holding them down
        if key in (
            Qt.Key.Key_Control, Qt.Key.Key_Shift, Qt.Key.Key_Alt, Qt.Key.Key_Meta,
            Qt.Key.Key_AltGr, Qt.Key.Key_Super_L, Qt.Key.Key_Super_R,
            getattr(Qt.Key, "Key_Hyper_L", 0), getattr(Qt.Key, "Key_Hyper_R", 0)
        ):
            event.accept()
            return

        # Pressing Escape cancels recording without changing the current shortcut
        if key == Qt.Key.Key_Escape:
            self.stop_recording()
            self.clearFocus()
            event.accept()
            return

        # Pressing Backspace or Delete while recording clears the shortcut
        mod_flags = event.modifiers()
        has_ctrl_or_alt = bool(mod_flags & (Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.AltModifier | Qt.KeyboardModifier.MetaModifier))
        if key in (Qt.Key.Key_Backspace, Qt.Key.Key_Delete) and not has_ctrl_or_alt:
            self.current_seq = "None"
            self.stop_recording()
            self.clearFocus()
            self.keySequenceChanged.emit("None")
            event.accept()
            return

        # Safely determine active modifier prefixes without converting KeyboardModifiers object to int
        mod_prefix = []
        if bool(mod_flags & Qt.KeyboardModifier.ControlModifier):
            mod_prefix.append("Ctrl")
        if bool(mod_flags & Qt.KeyboardModifier.AltModifier):
            mod_prefix.append("Alt")
        if bool(mod_flags & Qt.KeyboardModifier.ShiftModifier):
            mod_prefix.append("Shift")
        if bool(mod_flags & Qt.KeyboardModifier.MetaModifier):
            mod_prefix.append("Meta")

        # Convert the pressed key into a standard portable text representation
        key_seq_single = QKeySequence(key)
        key_text = key_seq_single.toString(QKeySequence.SequenceFormat.PortableText)
        if not key_text:
            key_text = chr(key) if 32 <= key <= 126 else f"Key_{key}"

        if mod_prefix:
            new_seq_str = "+".join(mod_prefix + [key_text])
        else:
            new_seq_str = key_text

        # Canonicalize via QKeySequence validation
        test_seq = QKeySequence(new_seq_str)
        if test_seq.toString():
            new_seq_str = test_seq.toString(QKeySequence.SequenceFormat.PortableText)

        self.current_seq = new_seq_str
        self.stop_recording()
        self.clearFocus()
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
        self._sort_column = 0  # 0 = Action (Alphabetical default), 1 = Category
        self._sort_order = Qt.SortOrder.AscendingOrder

        self._init_ui()
        self._populate_table()
        self._sort_table()

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

        # Arrange / Sort Tab Toggle Buttons
        sort_lbl = QLabel("Arrange By:")
        self.btn_sort_action = QPushButton("Action (Alphabetical)")
        self.btn_sort_action.setCheckable(True)
        self.btn_sort_action.setChecked(True)
        self.btn_sort_action.setToolTip("Arrange shortcuts alphabetically by Action Name (A-Z)")
        self.btn_sort_action.clicked.connect(self._sort_by_action_name)

        self.btn_sort_category = QPushButton("Category")
        self.btn_sort_category.setCheckable(True)
        self.btn_sort_category.setChecked(False)
        self.btn_sort_category.setToolTip("Arrange shortcuts grouped by functional Category")
        self.btn_sort_category.clicked.connect(self._sort_by_category)

        filter_bar.addWidget(sort_lbl)
        filter_bar.addWidget(self.btn_sort_action)
        filter_bar.addWidget(self.btn_sort_category)

        layout.addLayout(filter_bar)

        # Shortcut Lookup Tool (Lookup assigned command for any key combination)
        self.lookup_matched_action_id: Optional[str] = None
        self.lookup_group = QGroupBox("🔍 Shortcut Lookup Tool (Find Bound Action)")
        lookup_layout = QVBoxLayout(self.lookup_group)
        lookup_layout.setSpacing(6)

        lookup_input_row = QHBoxLayout()
        lookup_input_row.setSpacing(8)

        self.lookup_edit = KeySequenceRecorderEdit(self)
        self.lookup_edit.setToolTip("Click and press any key combination to look up what action it triggers")
        self.lookup_edit.keySequenceChanged.connect(self._on_lookup_sequence_changed)
        lookup_input_row.addWidget(self.lookup_edit, 2)

        self.lookup_clear_btn = QPushButton("Clear Lookup")
        self.lookup_clear_btn.setToolTip("Clear lookup input")
        self.lookup_clear_btn.clicked.connect(self._clear_lookup)
        lookup_input_row.addWidget(self.lookup_clear_btn)

        lookup_layout.addLayout(lookup_input_row)

        # Lookup Result Card
        self.lookup_result_card = QFrame()
        self.lookup_result_card.setStyleSheet(
            "QFrame { background-color: #1e293b; border: 1px solid #334155; border-radius: 4px; padding: 6px 10px; }"
        )
        lookup_res_layout = QHBoxLayout(self.lookup_result_card)
        lookup_res_layout.setContentsMargins(6, 4, 6, 4)

        self.lookup_result_lbl = QLabel("💡 Click the box above and press any key combination to look up its assigned function.")
        self.lookup_result_lbl.setStyleSheet("color: #cbd5e1; font-size: 12px;")
        self.lookup_result_lbl.setWordWrap(True)
        lookup_res_layout.addWidget(self.lookup_result_lbl, 1)

        self.lookup_jump_btn = QPushButton("📍 Select in Table")
        self.lookup_jump_btn.setStyleSheet(
            "QPushButton { background-color: #0284c7; color: white; font-weight: bold; border-radius: 4px; padding: 4px 10px; }"
            "QPushButton:hover { background-color: #0369a1; }"
        )
        self.lookup_jump_btn.setVisible(False)
        self.lookup_jump_btn.clicked.connect(self._on_lookup_jump_clicked)
        lookup_res_layout.addWidget(self.lookup_jump_btn)

        lookup_layout.addWidget(self.lookup_result_card)
        layout.addWidget(self.lookup_group)

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
        header.setSectionsClickable(True)
        header.setSortIndicatorShown(True)
        header.sectionClicked.connect(self._on_header_section_clicked)

        self.table.itemSelectionChanged.connect(self._on_row_selected)
        self.table.itemDoubleClicked.connect(lambda item: self.recorder_edit.start_recording() if not self.recorder_edit.is_recording else None)
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

        # Table double click triggers shortcut recording
        self.table.itemDoubleClicked.connect(lambda item: self._toggle_recording() if not self.recorder_edit.is_recording else None)

        # Bottom bulk actions row
        bottom_bar = QHBoxLayout()
        self.reset_all_btn = QPushButton("Restore All to Factory Defaults")
        self.reset_all_btn.setToolTip("Reset all keyboard shortcuts back to initial installation defaults")
        self.reset_all_btn.clicked.connect(self._confirm_reset_all)
        bottom_bar.addWidget(self.reset_all_btn)
        bottom_bar.addStretch()

        self.apply_btn = QPushButton("Save & Apply Shortcuts")
        self.apply_btn.setToolTip("Persist shortcut changes and immediately activate them across the application")
        self.apply_btn.setStyleSheet(
            "QPushButton { background-color: #2563eb; color: white; font-weight: bold; border-radius: 4px; padding: 6px 16px; }"
            "QPushButton:hover { background-color: #3b82f6; }"
        )
        self.apply_btn.clicked.connect(self._on_save_clicked)
        bottom_bar.addWidget(self.apply_btn)

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

    def _on_header_section_clicked(self, logical_index: int):
        if self._sort_column == logical_index:
            if self._sort_order == Qt.SortOrder.AscendingOrder:
                self._sort_order = Qt.SortOrder.DescendingOrder
            else:
                self._sort_order = Qt.SortOrder.AscendingOrder
        else:
            self._sort_column = logical_index
            self._sort_order = Qt.SortOrder.AscendingOrder

        self._update_sort_toggle_buttons()
        self._sort_table()

    def _sort_by_action_name(self):
        self._sort_column = 0
        self._sort_order = Qt.SortOrder.AscendingOrder
        self._update_sort_toggle_buttons()
        self._sort_table()

    def _sort_by_category(self):
        self._sort_column = 1
        self._sort_order = Qt.SortOrder.AscendingOrder
        self._update_sort_toggle_buttons()
        self._sort_table()

    def _update_sort_toggle_buttons(self):
        if hasattr(self, "btn_sort_action") and hasattr(self, "btn_sort_category"):
            self.btn_sort_action.setChecked(self._sort_column == 0)
            self.btn_sort_category.setChecked(self._sort_column == 1)

    def _sort_table(self):
        sel_id = self.selected_action_id

        row_data = []
        for r in range(self.table.rowCount()):
            items = [self.table.item(r, c) for c in range(5)]
            if not items[0]:
                continue
            act_id = items[0].data(Qt.ItemDataRole.UserRole)
            row_data.append({
                "action_id": act_id,
                "items": [it.clone() for it in items]
            })

        reverse = (self._sort_order == Qt.SortOrder.DescendingOrder)

        if self._sort_column == 0:  # Action Name
            row_data.sort(key=lambda d: (d["items"][0].text().lower(), d["items"][1].text().lower()), reverse=reverse)
        elif self._sort_column == 1:  # Category
            row_data.sort(key=lambda d: (d["items"][1].text().lower(), d["items"][0].text().lower()), reverse=reverse)
        elif self._sort_column == 2:  # Current Shortcut
            row_data.sort(key=lambda d: (d["items"][2].text().lower(), d["items"][0].text().lower()), reverse=reverse)
        elif self._sort_column == 3:  # Default Shortcut
            row_data.sort(key=lambda d: (d["items"][3].text().lower(), d["items"][0].text().lower()), reverse=reverse)
        elif self._sort_column == 4:  # Status
            row_data.sort(key=lambda d: (d["items"][4].text().lower(), d["items"][0].text().lower()), reverse=reverse)

        self.table.setRowCount(0)
        self.table.setRowCount(len(row_data))
        for r, data in enumerate(row_data):
            for c, item in enumerate(data["items"]):
                self.table.setItem(r, c, item)

        header = self.table.horizontalHeader()
        header.setSortIndicator(self._sort_column, self._sort_order)

        self._filter_table()

        if sel_id:
            for r in range(self.table.rowCount()):
                it = self.table.item(r, 0)
                if it and it.data(Qt.ItemDataRole.UserRole) == sel_id:
                    self.table.selectRow(r)
                    break

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
            self.clear_btn.setEnabled(True)
            self.reset_item_btn.setEnabled(True)
            self._check_conflict(cur_seq)

    def _clear_lookup(self):
        if self.lookup_edit.is_recording:
            self.lookup_edit.stop_recording()
        self.lookup_edit.set_sequence("")
        self.lookup_matched_action_id = None
        self.lookup_result_lbl.setText("💡 Click the box above and press any key combination to look up its assigned function.")
        self.lookup_jump_btn.setVisible(False)

    def _on_lookup_sequence_changed(self, seq_str: str):
        if not seq_str or seq_str in ("None", "<none>", ""):
            self._clear_lookup()
            return

        norm_candidate = normalize_sequence_string(seq_str).lower()
        matched_defn = None

        for defn in self.mgr.get_definitions():
            cur = self.pending_shortcuts.get(defn.action_id, self.mgr.get_default_shortcut(defn.action_id))
            if cur and cur not in ("None", "<none>") and normalize_sequence_string(cur).lower() == norm_candidate:
                matched_defn = defn
                break

        if matched_defn:
            self.lookup_matched_action_id = matched_defn.action_id
            disp_seq = format_sequence_display(seq_str)
            desc_text = f" — {matched_defn.description}" if matched_defn.description else ""
            self.lookup_result_lbl.setText(
                f"🎯 <b>Bound to: <span style='color: #38bdf8;'>{matched_defn.name}</span></b> "
                f"<span style='color: #94a3b8;'>[{matched_defn.category}]</span><br>"
                f"<span style='color: #cbd5e1; font-size: 11px;'>Shortcut: <b>{disp_seq}</b>{desc_text}</span>"
            )
            self.lookup_jump_btn.setVisible(True)
        else:
            self.lookup_matched_action_id = None
            disp_seq = format_sequence_display(seq_str)
            self.lookup_result_lbl.setText(
                f"⚪ <b>Unassigned / Available:</b> No action is currently bound to <b>'{disp_seq}'</b>. "
                f"This shortcut combination is available to assign."
            )
            self.lookup_jump_btn.setVisible(False)

    def _on_lookup_jump_clicked(self):
        if not self.lookup_matched_action_id:
            return
        # Reset search filters so all rows are visible
        self.search_input.clear()
        self.cat_combo.setCurrentIndex(0)

        for row in range(self.table.rowCount()):
            item = self.table.item(row, 0)
            if item and item.data(Qt.ItemDataRole.UserRole) == self.lookup_matched_action_id:
                self.table.selectRow(row)
                self.table.scrollToItem(item, QAbstractItemView.ScrollHint.PositionAtCenter)
                self.table.setFocus()
                break

    def _on_recorded_sequence(self, new_seq: str):
        if not self.selected_action_id:
            return

        if not new_seq or new_seq in ("None", "<none>", ""):
            self._clear_selected_shortcut()
            return

        # Check for conflict with another registered action
        norm_candidate = normalize_sequence_string(new_seq).lower()
        conflicting_defn = None
        for defn in self.mgr.get_definitions():
            if defn.action_id == self.selected_action_id:
                continue
            cur = self.pending_shortcuts.get(defn.action_id, self.mgr.get_default_shortcut(defn.action_id))
            if cur and cur not in ("None", "<none>") and normalize_sequence_string(cur).lower() == norm_candidate:
                conflicting_defn = defn
                break

        if conflicting_defn:
            cur_defn = self.mgr.get_definition(self.selected_action_id)
            cur_name = cur_defn.name if cur_defn else self.selected_action_id
            seq_display = format_sequence_display(new_seq)

            msg_box = QMessageBox(self)
            msg_box.setWindowTitle("Keyboard Shortcut Conflict")
            msg_box.setIcon(QMessageBox.Icon.Warning)
            msg_box.setText(
                f"The key combination <b>'{seq_display}'</b> is already assigned to:<br><br>"
                f"• <b>{conflicting_defn.name}</b> <i>({conflicting_defn.category})</i><br><br>"
                f"Which function would you like this shortcut to trigger?"
            )
            btn_reassign = msg_box.addButton(f"Apply to '{cur_name}' (Reassign)", QMessageBox.ButtonRole.AcceptRole)
            btn_keep_old = msg_box.addButton(f"Keep with '{conflicting_defn.name}'", QMessageBox.ButtonRole.RejectRole)
            msg_box.setDefaultButton(btn_reassign)

            msg_box.exec()

            if msg_box.clickedButton() == btn_reassign:
                # Reassign: Clear old assignment and assign to current selected action
                self._apply_pending_change(conflicting_defn.action_id, "None")
                self._apply_pending_change(self.selected_action_id, new_seq)
                self.recorder_edit.set_sequence(new_seq)
                self.conflict_frame.setVisible(False)
            else:
                # Keep with old function: Restore previous shortcut for selected action and immediately re-open recording for user to pick another key combo
                prev_seq = self.pending_shortcuts.get(
                    self.selected_action_id, self.mgr.get_default_shortcut(self.selected_action_id)
                )
                self.recorder_edit.set_sequence(prev_seq)
                self.conflict_frame.setVisible(False)
                # Re-engage recorder so user can enter a different key combo
                self.recorder_edit.start_recording()
        else:
            self._apply_pending_change(self.selected_action_id, new_seq)
            self.conflict_frame.setVisible(False)

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

    def _on_save_clicked(self):
        self.save_shortcuts()
        QMessageBox.information(
            self,
            "Shortcuts Applied",
            "Keyboard shortcuts have been saved and applied successfully.",
            QMessageBox.StandardButton.Ok,
        )

    def save_shortcuts(self):
        """Commit all pending shortcut changes to QSettings and apply to the MainWindow."""
        for action_id, seq in self.pending_shortcuts.items():
            self.mgr.set_shortcut(action_id, seq)
        self.mgr.save()
        if self.parent_window:
            self.mgr.apply_to_window(self.parent_window)
