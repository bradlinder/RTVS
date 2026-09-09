"""Radio & TV Segmenter — Plugin Base Interfaces and Manifest."""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional


@dataclass
class PluginManifest:
    """Metadata describing a plugin, parsed from manifest.json."""
    id: str
    name: str
    version: str = "1.0.0"
    description: str = ""
    author: str = ""
    website: str = ""
    min_app_version: str = "2.6.0"
    category: str = "tools"  # "export", "ai", "tools", "ui"
    entry_point: str = "plugin:Plugin"
    dependencies: List[str] = field(default_factory=list)
    icon: Optional[str] = None
    enabled_by_default: bool = True

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> PluginManifest:
        return cls(
            id=str(data.get("id", "")).strip(),
            name=str(data.get("name", "Unnamed Plugin")),
            version=str(data.get("version", "1.0.0")),
            description=str(data.get("description", "")),
            author=str(data.get("author", "")),
            website=str(data.get("website", "")),
            min_app_version=str(data.get("min_app_version", "2.6.0")),
            category=str(data.get("category", "tools")),
            entry_point=str(data.get("entry_point", "plugin:Plugin")),
            dependencies=list(data.get("dependencies", [])),
            icon=data.get("icon"),
            enabled_by_default=bool(data.get("enabled_by_default", True)),
        )

    @classmethod
    def from_file(cls, path: Path | str) -> PluginManifest:
        p = Path(path)
        with open(p, "r", encoding="utf-8") as f:
            data = json.load(f)
        manifest = cls.from_dict(data)
        if not manifest.id:
            manifest.id = p.parent.name
        return manifest


class BasePlugin:
    """Base class for all Radio & TV Segmenter plugins.
    
    Plugins can hook into:
    - Main application window events and state
    - Export menu and Unified Export Center
    - Tools menu
    - Application Preferences
    - Project save/load metadata
    """

    def __init__(self, manifest: PluginManifest, app: Any = None):
        self.manifest = manifest
        self.app = app
        self._enabled = True

    @property
    def id(self) -> str:
        return self.manifest.id

    @property
    def name(self) -> str:
        return self.manifest.name

    @property
    def version(self) -> str:
        return self.manifest.version

    def is_enabled(self) -> bool:
        return self._enabled

    def set_enabled(self, enabled: bool) -> None:
        if self._enabled == enabled:
            return
        self._enabled = enabled
        if enabled:
            self.on_enable()
        else:
            self.on_disable()

    def on_load(self) -> bool:
        """Called immediately after the plugin module is loaded.
        Return False if prerequisites fail.
        """
        return True

    def on_unload(self) -> None:
        """Called when plugin is about to be unloaded or application closes."""
        pass

    def on_enable(self) -> None:
        """Called when the user enables the plugin."""
        pass

    def on_disable(self) -> None:
        """Called when the user disables the plugin."""
        pass

    def get_export_actions(self) -> List[tuple[str, Callable]]:
        """Return list of (Action Label, callback_function) for Export menu."""
        return []

    def get_tools_actions(self) -> List[tuple[str, Callable]]:
        """Return list of (Action Label, callback_function) for Tools menu."""
        return []

    def get_preferences_widget(self, parent: Any = None) -> Any:
        """Return a QWidget to be embedded into the Preferences dialog, or None."""
        return None

    def save_preferences(self, widget: Any) -> None:
        """Called when the user saves the Preferences dialog."""
        pass

    def on_project_loaded(self, project_data: Dict[str, Any]) -> None:
        """Called when an .rtvs project is loaded. Allows reading plugin metadata."""
        pass

    def on_project_saving(self, project_data: Dict[str, Any]) -> None:
        """Called before an .rtvs project is saved. Allows injecting plugin metadata."""
        pass
