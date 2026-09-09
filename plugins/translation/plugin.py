"""Language Translation Plugin for Radio & TV Segmenter.

Enables local AI-powered neural machine translation using Helsinki-NLP MarianMT
and Meta NLLB models, split-view synchronized transcript comparison, and bilingual exports.
"""
from __future__ import annotations

from typing import Any, Callable, List, Optional
from PySide6.QtWidgets import QGroupBox, QVBoxLayout, QLabel, QPushButton

from plugins.base import BasePlugin, PluginManifest


class Plugin(BasePlugin):
    """Translation plugin providing local language translation capabilities."""

    def on_load(self) -> bool:
        return True

    def on_enable(self) -> None:
        if self.app:
            if hasattr(self.app, "transcript_language_selector"):
                self.app.transcript_language_selector.setVisible(True)
            if hasattr(self.app, "translation_model_action"):
                self.app.translation_model_action.setVisible(True)

    def on_disable(self) -> None:
        if self.app:
            if hasattr(self.app, "transcript_language_selector"):
                self.app.transcript_language_selector.setVisible(False)
            if hasattr(self.app, "translation_model_action"):
                self.app.translation_model_action.setVisible(False)

    def get_tools_actions(self) -> List[tuple[str, Callable]]:
        actions = []
        if self.app and hasattr(self.app, "show_translation_model_chooser"):
            actions.append(("Translation Model Settings...", self.app.show_translation_model_chooser))
        if self.app and hasattr(self.app, "start_translation"):
            actions.append(("Translate Transcript...", lambda: self.app.start_translation("en", "es")))
        return actions

    def get_preferences_widget(self, parent: Any = None) -> Any:
        box = QGroupBox("Bilingual Translation", parent)
        layout = QVBoxLayout(box)
        lbl = QLabel("Manage local machine translation transformer models (MarianMT & NLLB).")
        layout.addWidget(lbl)
        if self.app and hasattr(self.app, "show_translation_model_chooser"):
            btn = QPushButton("Select Translation Models...")
            btn.clicked.connect(self.app.show_translation_model_chooser)
            layout.addWidget(btn)
        return box
