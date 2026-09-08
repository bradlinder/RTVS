"""Targeted QSS for the Radio & TV Segmenter visual design system.

The application structure remains unchanged; this layer establishes a
consistent charcoal/slate/cyan broadcast-workstation aesthetic.
"""

TARGETED_QSS = """
/* ========================================================================
   CORE SURFACES, TYPOGRAPHY & FOCUS
   ======================================================================== */
QWidget {
    outline: none;
}

QLabel { color: #d7dde5; }

QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox, QDateEdit, QTimeEdit {
    background: #181b20;
    color: #f0f3f6;
    border: 1px solid #282c35;
    border-radius: 6px;
    padding: 5px 9px;
    selection-background-color: #38bdf8;
    selection-color: #081018;
}

QLineEdit:hover, QComboBox:hover, QSpinBox:hover, QDoubleSpinBox:hover {
    border-color: #3a414f;
}

QLineEdit:focus, QComboBox:focus, QSpinBox:focus, QDoubleSpinBox:focus {
    border-color: #38bdf8;
}

QPushButton {
    background: #20242b;
    color: #dfe5ec;
    border: 1px solid #282c35;
    border-radius: 6px;
    padding: 6px 12px;
}

QPushButton:hover {
    background: #282c35;
    border-color: #3a414f;
    color: #ffffff;
}

QPushButton:pressed { background: #181b20; }
QPushButton:disabled { color: #5c6570; border-color: #20242b; background: #16191d; }

/* ========================================================================
   MINIMALIST SCROLLBARS
   ======================================================================== */
QScrollBar:vertical {
    background: transparent;
    width: 8px;
    margin: 2px 1px;
    border: none;
}
QScrollBar::handle:vertical {
    background: #282c35;
    min-height: 28px;
    border-radius: 4px;
}
QScrollBar::handle:vertical:hover { background: #3a414f; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical,
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {
    background: transparent; border: none; height: 0px;
}
QScrollBar:horizontal {
    background: transparent;
    height: 8px;
    margin: 1px 2px;
    border: none;
}
QScrollBar::handle:horizontal {
    background: #282c35;
    min-width: 28px;
    border-radius: 4px;
}
QScrollBar::handle:horizontal:hover { background: #3a414f; }
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal,
QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal {
    background: transparent; border: none; width: 0px;
}

/* ========================================================================
   MENU BAR & MENUS
   ======================================================================== */
QMenuBar {
    background: transparent;
    color: #f0f3f6;
    spacing: 2px;
    padding: 2px 4px;
}
QMenuBar::item {
    background: transparent;
    border-radius: 6px;
    padding: 5px 9px;
}
QMenuBar::item:selected, QMenuBar::item:pressed { background: #1e222a; }
QMenu {
    background: #181b20;
    color: #f0f3f6;
    border: 1px solid #282c35;
    border-radius: 8px;
    padding: 6px;
}
QMenu::item {
    background: transparent;
    border-radius: 5px;
    padding: 6px 14px;
    margin: 1px 0;
    min-width: 150px;
}
QMenu::item:selected { background: #1e222a; color: #ffffff; }
QMenu::item:disabled { color: #5c6570; }
QMenu::separator { height: 1px; background: #282c35; margin: 5px 7px; }

/* ========================================================================
   SPLITTERS
   ======================================================================== */
QSplitter::handle { background: #282c35; }
QSplitter::handle:hover, QSplitter::handle:pressed { background: #38bdf8; }
QSplitter[orientation="horizontal"]::handle { width: 1px; margin: 0 1px; }
QSplitter[orientation="vertical"]::handle { height: 1px; margin: 1px 0; }

/* ========================================================================
   TRANSPORT / PLAYBACK
   ======================================================================== */
QPushButton#play_button {
    background: #38bdf8;
    color: #081018;
    font-weight: 700;
    font-size: 13px;
    border: none;
    border-radius: 16px;
    padding: 6px 20px;
    min-height: 20px;
    min-width: 72px;
}
QPushButton#play_button:hover { background: #67d3ff; }
QPushButton#play_button:pressed { background: #0ea5e9; }

QPushButton#quick_save_button, QPushButton#add_story_btn, QPushButton#find_next_btn,
QPushButton#translate_button {
    background: #20242b;
    color: #f0f3f6;
    border: 1px solid #303743;
    border-radius: 6px;
    padding: 6px 14px;
    font-size: 12px;
    font-weight: 600;
}
QPushButton#quick_save_button:hover, QPushButton#add_story_btn:hover,
QPushButton#find_next_btn:hover, QPushButton#translate_button:hover {
    background: #282c35;
    border-color: #38bdf8;
    color: #ffffff;
}

QPushButton#skip_backward_button, QPushButton#skip_forward_button {
    background: transparent;
    color: #8b949e;
    border: 1px solid #282c35;
    border-radius: 14px;
    padding: 4px 10px;
    font-size: 11px;
    font-weight: 600;
}
QPushButton#skip_backward_button:hover, QPushButton#skip_forward_button:hover {
    background: #181b20; border-color: #38bdf8; color: #f0f3f6;
}

QLabel#time_label {
    font-family: "Cascadia Code", "JetBrains Mono", "Fira Code", "Consolas", monospace;
    font-size: 13px;
    font-weight: 600;
    color: #38bdf8;
    background: #121417;
    border: 1px solid #282c35;
    border-radius: 6px;
    padding: 4px 12px;
    min-width: 170px;
}

/* ========================================================================
   PROGRESS / STATUS
   ======================================================================== */
QProgressBar {
    background: #181b20;
    border: 1px solid #282c35;
    border-radius: 6px;
    text-align: center;
    color: #f0f3f6;
    font-size: 11px;
    font-weight: 600;
    min-height: 14px;
    max-height: 14px;
}
QProgressBar::chunk {
    background: #38bdf8;
    border-radius: 5px;
}
QLabel#processing_stage_label { color: #38bdf8; font-size: 11px; font-weight: 700; }
QPushButton#cancel_button {
    background: #2d181a; color: #f87171; border: 1px solid #4d2325;
    border-radius: 6px; padding: 4px 12px; font-size: 11px; font-weight: 600;
}
QPushButton#cancel_button:hover { background: #451e22; border-color: #ef4444; color: #ffffff; }

/* ========================================================================
   TRANSCRIPT
   ======================================================================== */
QTextEdit#transcript_view, QPlainTextEdit#transcript_view {
    background: #121417;
    color: #f0f3f6;
    border: 1px solid #282c35;
    border-radius: 8px;
    padding: 12px;
    selection-background-color: #38bdf8;
    selection-color: #081018;
}
QTextEdit#transcript_view:focus, QPlainTextEdit#transcript_view:focus { border-color: #38bdf8; }
QLineEdit#transcript_search_input {
    background: #181b20; color: #f0f3f6; border: 1px solid #282c35;
    border-radius: 6px; padding: 5px 10px; font-size: 12px;
}
QLineEdit#transcript_search_input:focus { border-color: #38bdf8; background: #1e222a; }

QPushButton#transcript_font_down_btn, QPushButton#transcript_font_reset_btn,
QPushButton#transcript_font_up_btn {
    background: #181b20;
    color: #8b949e;
    border: 1px solid #282c35;
    border-radius: 5px;
    padding: 4px 8px;
    min-width: 28px;
    min-height: 20px;
    font-weight: 700;
}
QPushButton#transcript_font_down_btn:hover, QPushButton#transcript_font_reset_btn:hover,
QPushButton#transcript_font_up_btn:hover {
    background: #20242b; color: #f0f3f6; border-color: #38bdf8;
}

/* ========================================================================
   STORIES / ACTIVITY CARDS
   ======================================================================== */
QWidget#stories_panel, QWidget#activity_panel {
    background: #181b20;
    border: 1px solid #282c35;
    border-radius: 8px;
}
QLabel#stories_section_header, QLabel#activity_section_header {
    color: #f0f3f6;
    background: transparent;
    border: none;
    border-bottom: 1px solid #282c35;
    padding: 3px 2px 7px 2px;
    font-size: 11px;
    font-weight: 700;
}
QListWidget#story_list {
    background: #121417; border: 1px solid #282c35; border-radius: 8px;
    padding: 4px; outline: none;
}
QListWidget#story_list::item {
    background: #181b20; border: 1px solid #282c35; border-left: 3px solid #315c85;
    border-radius: 6px; margin: 3px 2px; padding: 8px 10px; color: #dfe5ec;
}
QListWidget#story_list::item:hover { background: #1e222a; border-color: #3a414f; border-left-color: #38bdf8; }
QListWidget#story_list::item:selected {
    background: #1c2730; border-color: #38bdf8; border-left-color: #38bdf8;
    color: #ffffff; font-weight: 600;
}

/* Action hierarchy */
QPushButton#add_story_btn, QPushButton#export_stories_btn {
    background: #38bdf8; color: #081018; border-color: #38bdf8; font-weight: 700;
}
QPushButton#add_story_btn:hover, QPushButton#export_stories_btn:hover { background: #67d3ff; border-color: #67d3ff; }
QPushButton#set_story_start_btn, QPushButton#set_story_end_btn {
    background: #182230;
    color: #38bdf8;
    border: 1px solid #29384d;
    border-radius: 5px;
    padding: 5px 8px;
    font-size: 11px;
    font-weight: 600;
}
QPushButton#set_story_start_btn:hover, QPushButton#set_story_end_btn:hover {
    background: #1e2c3f;
    border-color: #38bdf8;
    color: #ffffff;
}
QPushButton#set_story_start_btn:pressed, QPushButton#set_story_end_btn:pressed {
    background: #0284c7;
    border-color: #0284c7;
    color: #081018;
}
QPushButton#select_all_stories_btn, QPushButton#export_activity_btn {
    background: transparent; color: #8b949e; border-color: #3a414f;
}
QPushButton#select_all_stories_btn:hover, QPushButton#export_activity_btn:hover {
    background: #20242b; color: #f0f3f6; border-color: #8b949e;
}
QPushButton#delete_story_btn, QPushButton#clear_activity_btn {
    background: transparent; color: #8b7a7d; border-color: #33272a;
}
QPushButton#delete_story_btn:hover, QPushButton#clear_activity_btn:hover {
    background: #2d181a; color: #f87171; border-color: #4d2325;
}
QPushButton#delete_story_btn:pressed, QPushButton#clear_activity_btn:pressed {
    background: #451e22; color: #ffffff; border-color: #ef4444;
}

/* ========================================================================
   TIMELINE / RULER SURFACES
   ======================================================================== */
QWidget#timeline, QWidget#timeline_canvas {
    background: #111317;
}
"""
