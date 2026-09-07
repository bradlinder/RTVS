"""Theme Tokens for Radio & TV Story Segmenter.

Defines a centralized ThemeTokens dataclass maintaining a broadcast-grade
zinc/slate dark aesthetic and provides direct QColor, QPen, and QBrush helpers
to keep custom QPainter drawing in lockstep with Qt stylesheets.
"""

from dataclasses import dataclass
from typing import Tuple

try:
    from PySide6.QtGui import QColor, QPen, QBrush
    from PySide6.QtCore import Qt
except ImportError:
    try:
        from PyQt6.QtGui import QColor, QPen, QBrush
        from PyQt6.QtCore import Qt
    except ImportError:
        # Fallback dummy definitions if GUI bindings are unavailable in headless test
        QColor = None
        QPen = None
        QBrush = None
        Qt = None


@dataclass
class ThemeTokens:
    """Centralized color and style tokens for custom QPainter drawing & QSS."""

    # Surfaces
    bg_window: str = "#121417"
    bg_surface: str = "#181b20"
    bg_card: str = "#1e222a"
    border_subtle: str = "#282c35"
    border_focus: str = "#38bdf8"
    ruler_bg: str = "#111317"
    ruler_border: str = "#2c323d"
    ruler_text: str = "#8a95a5"

    # Accents & Text
    accent_primary: str = "#38bdf8"
    accent_hover: str = "#67d3ff"
    accent_active: str = "#0ea5e9"
    text_primary: str = "#f0f3f6"
    text_secondary: str = "#8b949e"
    text_muted: str = "#5c6570"

    # Waveform & Playback
    waveform_fill: str = "#3b82f6"
    waveform_stroke: str = "#64748b"
    waveform_baseline: str = "#2c323d"
    playhead: str = "#ff4d4f"
    timecode_text: str = "#38bdf8"
    audio_label_text: str = "#f2cc60"

    # Drag Selections & Handles
    selection_fill: str = "#38bdf8"
    selection_border: str = "#38bdf8"
    selection_handle: str = "#38bdf8"
    transcript_selection_fill: str = "#38bdf8"

    # Story Segment Palette & Highlights
    story_palette: Tuple[str, ...] = (
        "#315c85",
        "#386b59",
        "#795d31",
        "#674f7c",
    )
    story_selected_border: str = "#ffffff"
    story_selected_alpha: int = 130
    story_unselected_alpha: int = 60
    speaker_tag_bg: str = "#1f242d"
    speaker_tag_border: str = "#2e3644"
    speaker_tag_text: str = "#93c5fd"

    # Status HUD & Overlays
    status_banner_bg: str = "#121418"
    status_banner_border: str = "#58a6ff"
    status_banner_text: str = "#f0f6fc"
    progress_bar_chunk: str = "#007acc"
    progress_bar_bg: str = "#181b20"

    def color(self, hex_or_name: str, alpha: int = 255) -> QColor:
        """Return a QColor instance with an optional alpha channel (0-255)."""
        c = QColor(hex_or_name)
        if alpha != 255:
            c.setAlpha(alpha)
        return c

    def pen(
        self,
        hex_or_name: str,
        width: float = 1.0,
        style=None,
        alpha: int = 255,
    ) -> QPen:
        """Return a configured QPen with color, width, style, and alpha."""
        if style is None and Qt is not None:
            style = Qt.PenStyle.SolidLine
        c = self.color(hex_or_name, alpha)
        p = QPen(c, width)
        if style is not None:
            p.setStyle(style)
        return p

    def brush(
        self,
        hex_or_name: str,
        alpha: int = 255,
        style=None,
    ) -> QBrush:
        """Return a configured QBrush with color, style, and alpha."""
        if style is None and Qt is not None:
            style = Qt.BrushStyle.SolidPattern
        c = self.color(hex_or_name, alpha)
        if style is not None:
            return QBrush(c, style)
        return QBrush(c)

    # ------------------------------------------------------------------
    # Convenience drawing helpers for TimelineCanvas
    # ------------------------------------------------------------------

    def waveform_brush(self, opacity: float = 0.6) -> QBrush:
        """Return QBrush for the waveform envelope with specified opacity (0.0 - 1.0)."""
        alpha = int(max(0.0, min(1.0, opacity)) * 255)
        return self.brush(self.waveform_fill, alpha=alpha)

    def playhead_pen(self, width: float = 2.0) -> QPen:
        """Return QPen for the active timeline playhead line."""
        return self.pen(self.playhead, width=width)

    def ruler_background_color(self) -> QColor:
        """Return QColor for the timeline ruler background strip."""
        return self.color(self.ruler_bg)

    def ruler_tick_pen(self) -> QPen:
        """Return QPen for ruler division tick marks and text labels."""
        return self.pen(self.ruler_text, width=1.0)

    def ruler_divider_pen(self) -> QPen:
        """Return QPen for the border line between ruler and waveform canvas."""
        return self.pen(self.ruler_border, width=1.0)

    def selection_rect_brush(self, is_transcript: bool = False) -> QBrush:
        """Return QBrush for timeline/transcript selection overlays."""
        alpha = 70 if is_transcript else 55
        token = self.transcript_selection_fill if is_transcript else self.selection_fill
        return self.brush(token, alpha=alpha)

    def selection_rect_pen(self) -> QPen:
        """Return QPen for selection range bounding border."""
        return self.pen(self.selection_border, width=2.0)

    def selection_handle_brush(self) -> QBrush:
        """Return QBrush for dragging edge handles."""
        return self.brush(self.selection_handle, alpha=255)

    def story_segment_brush(self, index: int, is_selected: bool = False) -> QBrush:
        """Return QBrush for story region with index-based palette and selection alpha."""
        base_color = self.story_palette[index % len(self.story_palette)]
        alpha = self.story_selected_alpha if is_selected else self.story_unselected_alpha
        return self.brush(base_color, alpha=alpha)

    def story_segment_pen(self, index: int, is_selected: bool = False) -> QPen:
        """Return QPen for story region boundary line."""
        if is_selected:
            return self.pen(self.story_selected_border, width=3.0)
        base_color = self.story_palette[index % len(self.story_palette)]
        c = self.color(base_color).darker(150)
        return QPen(c, 2.0)


# ---------------------------------------------------------------------------
# Light / High-Contrast presets
# ---------------------------------------------------------------------------
# These mirror the QSS/QPalette colors already used for the rest of the UI in
# each mode (see playback_preferences.py's set_theme()), so the timeline
# looks like it belongs with the surrounding window rather than always
# rendering in the dark palette above regardless of the active theme.

_LIGHT_TOKEN_OVERRIDES = dict(
    bg_window="#f4f5f7",
    bg_surface="#ffffff",
    bg_card="#e9eaee",
    border_subtle="#c5c9d0",
    border_focus="#1971c2",
    ruler_bg="#e5e7eb",
    ruler_border="#b0b4ba",
    ruler_text="#4b5563",
    accent_primary="#1971c2",
    accent_hover="#4593d6",
    accent_active="#1864ab",
    text_primary="#111111",
    text_secondary="#4b5563",
    text_muted="#9ca3af",
    waveform_fill="#1971c2",
    waveform_stroke="#6b7280",
    waveform_baseline="#c5c9d0",
    playhead="#dc2626",
    timecode_text="#1971c2",
    audio_label_text="#a16207",
    selection_fill="#1971c2",
    selection_border="#1971c2",
    selection_handle="#1971c2",
    transcript_selection_fill="#1971c2",
    story_palette=("#4a7fb5", "#4a8f78", "#a67c3d", "#8a6ba3"),
    story_selected_border="#111111",
    story_selected_alpha=130,
    story_unselected_alpha=60,
    speaker_tag_bg="#eef2f7",
    speaker_tag_border="#c5c9d0",
    speaker_tag_text="#1971c2",
    status_banner_bg="#ffffff",
    status_banner_border="#1971c2",
    status_banner_text="#111111",
    progress_bar_chunk="#1971c2",
    progress_bar_bg="#e5e7eb",
)

# High contrast pushes saturation/contrast to the extreme (pure black
# background, near-max alpha overlays) rather than the low-alpha tinted
# look of dark/light -- subtle alpha blending is exactly what a
# high-contrast mode needs to avoid. Story palette hues are chosen to stay
# clearly distinguishable from the yellow waveform and cyan playhead used
# elsewhere in this mode.
_HIGH_CONTRAST_TOKEN_OVERRIDES = dict(
    bg_window="#000000",
    bg_surface="#000000",
    bg_card="#1a1a1a",
    border_subtle="#ffffff",
    border_focus="#ffff00",
    ruler_bg="#000000",
    ruler_border="#ffff00",
    ruler_text="#ffffff",
    accent_primary="#ffff00",
    accent_hover="#ffffff",
    accent_active="#00ffff",
    text_primary="#ffffff",
    text_secondary="#ffff00",
    text_muted="#cccccc",
    waveform_fill="#ffff00",
    waveform_stroke="#ffffff",
    waveform_baseline="#666666",
    playhead="#00ffff",
    timecode_text="#ffff00",
    audio_label_text="#00ffff",
    selection_fill="#ffff00",
    selection_border="#ffff00",
    selection_handle="#ffff00",
    transcript_selection_fill="#ffff00",
    story_palette=("#ff8800", "#ff00ff", "#00ff00", "#3399ff"),
    story_selected_border="#ffffff",
    story_selected_alpha=190,
    story_unselected_alpha=100,
    speaker_tag_bg="#000000",
    speaker_tag_border="#ffff00",
    speaker_tag_text="#ffffff",
    status_banner_bg="#000000",
    status_banner_border="#ffff00",
    status_banner_text="#ffffff",
    progress_bar_chunk="#ffff00",
    progress_bar_bg="#000000",
)


def theme_tokens_for_mode(mode: str) -> "ThemeTokens":
    """Return the ThemeTokens preset matching a Preferences theme_mode value
    ('dark', 'light', or 'high_contrast'). Unknown values fall back to dark
    (the dataclass defaults), matching set_theme()'s own fallback in
    playback_preferences.py.
    """
    if mode == "light":
        return ThemeTokens(**_LIGHT_TOKEN_OVERRIDES)
    if mode == "high_contrast":
        return ThemeTokens(**_HIGH_CONTRAST_TOKEN_OVERRIDES)
    return ThemeTokens()
