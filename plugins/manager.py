"""Radio & TV Segmenter — Plugin Manager and Discovery Engine."""
from __future__ import annotations

import importlib
import importlib.util
import json
import os
import shutil
import sys
import zipfile
from pathlib import Path
from typing import Any, Dict, List, Optional

from prs_shared import INTERNAL_APP_ID, PROJECT_VERSION, QSettings
from plugins.base import BasePlugin, PluginManifest

from PySide6.QtCore import Qt, QSize
from PySide6.QtGui import QIcon, QFont
from PySide6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QHeaderView,
    QMessageBox,
    QFileDialog,
    QCheckBox,
    QGroupBox,
    QTextEdit,
    QWidget,
)


class PluginManager:
    """Manages discovery, lifecycle, settings, and GUI injection of plugins."""

    def __init__(self, app: Any = None):
        self.app = app
        self.settings = QSettings(INTERNAL_APP_ID, INTERNAL_APP_ID)
        self.manifests: Dict[str, PluginManifest] = {}
        self.plugins: Dict[str, BasePlugin] = {}
        self.plugin_paths: Dict[str, Path] = {}

    @classmethod
    def get_user_plugins_dir(cls) -> Path:
        """Returns the user-writable plugins folder."""
        if sys.platform == "win32":
            base = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
        elif sys.platform == "darwin":
            base = Path.home() / "Library" / "Application Support"
        else:
            base = Path.home() / ".local" / "share"
        p = base / "RadioTVSegmenter" / "plugins"
        p.mkdir(parents=True, exist_ok=True)
        return p

    @classmethod
    def get_bundled_plugins_dir(cls) -> Path:
        """Returns the application installation plugins folder."""
        if getattr(sys, "frozen", False):
            base = Path(sys.executable).parent
            if sys.platform == "darwin":
                # Inside Contents/MacOS
                bundled = base.parent / "Resources" / "plugins"
                if bundled.exists():
                    return bundled
            return base / "plugins"
        # Development / source tree
        return Path(__file__).resolve().parent.parent / "plugins"

    def discover_plugins(self) -> Dict[str, PluginManifest]:
        """Scans plugin directories and loads manifests without heavy imports."""
        self.manifests.clear()
        self.plugin_paths.clear()

        search_dirs = [
            self.get_bundled_plugins_dir(),
            self.get_user_plugins_dir(),
        ]

        for sdir in search_dirs:
            if not sdir.exists() or not sdir.is_dir():
                continue
            for item in sdir.iterdir():
                if item.is_dir():
                    manifest_file = item / "manifest.json"
                    if manifest_file.exists():
                        try:
                            manifest = PluginManifest.from_file(manifest_file)
                            self.manifests[manifest.id] = manifest
                            self.plugin_paths[manifest.id] = item
                        except Exception as exc:
                            print(f"[PLUGINS] Failed to load manifest from {manifest_file}: {exc}")

        return self.manifests

    def is_plugin_enabled(self, plugin_id: str) -> bool:
        manifest = self.manifests.get(plugin_id)
        default_val = manifest.enabled_by_default if manifest else True
        val = self.settings.value(f"plugins/{plugin_id}/enabled", default_val)
        if isinstance(val, bool):
            return val
        return str(val).lower() in {"1", "true", "yes"}

    def set_plugin_enabled(self, plugin_id: str, enabled: bool) -> None:
        self.settings.setValue(f"plugins/{plugin_id}/enabled", enabled)
        self.settings.sync()
        if plugin_id in self.plugins:
            self.plugins[plugin_id].set_enabled(enabled)

    def load_all_plugins(self) -> None:
        """Discovers and instantiates all enabled plugins."""
        self.discover_plugins()
        for plugin_id, manifest in self.manifests.items():
            if self.is_plugin_enabled(plugin_id):
                self.load_plugin(plugin_id)

    def load_plugin(self, plugin_id: str) -> Optional[BasePlugin]:
        if plugin_id in self.plugins:
            return self.plugins[plugin_id]

        manifest = self.manifests.get(plugin_id)
        folder = self.plugin_paths.get(plugin_id)
        if not manifest or not folder:
            return None

        entry_point = manifest.entry_point or "plugin:Plugin"
        module_name, class_name = entry_point.split(":", 1) if ":" in entry_point else ("plugin", "Plugin")

        try:
            # Try importing directly if inside plugins package
            plugin_cls = None
            try:
                mod = importlib.import_module(f"plugins.{plugin_id}.{module_name}")
                plugin_cls = getattr(mod, class_name)
            except (ImportError, ModuleNotFoundError):
                # Fall back to loading directly from file path
                py_file = folder / f"{module_name}.py"
                if py_file.exists():
                    spec = importlib.util.spec_from_file_location(f"rtvs_plugin_{plugin_id}", py_file)
                    if spec and spec.loader:
                        mod = importlib.util.module_from_spec(spec)
                        sys.modules[f"rtvs_plugin_{plugin_id}"] = mod
                        spec.loader.exec_module(mod)
                        plugin_cls = getattr(mod, class_name)

            if plugin_cls is None:
                print(f"[PLUGINS] Could not find class {class_name} in {plugin_id}")
                return None

            instance: BasePlugin = plugin_cls(manifest, self.app)
            instance.set_enabled(True)
            if instance.on_load():
                self.plugins[plugin_id] = instance
                print(f"[PLUGINS] Successfully loaded plugin: {manifest.name} v{manifest.version}")
                return instance
            else:
                print(f"[PLUGINS] Plugin {manifest.name} on_load returned False; disabling.")
                return None
        except Exception as exc:
            print(f"[PLUGINS] Error loading plugin '{plugin_id}': {exc}")
            import traceback
            traceback.print_exc()
            return None

    def unload_plugin(self, plugin_id: str) -> None:
        if plugin_id in self.plugins:
            try:
                self.plugins[plugin_id].on_unload()
            except Exception as exc:
                print(f"[PLUGINS] Error during unload of {plugin_id}: {exc}")
            del self.plugins[plugin_id]

    def install_addon(self, package_path: Path | str) -> bool:
        """Installs a .rtvs-addon or .zip package into the user plugins directory."""
        package_path = Path(package_path)
        if not package_path.exists():
            return False

        user_dir = self.get_user_plugins_dir()
        temp_extract = user_dir / ".tmp_install"
        shutil.rmtree(temp_extract, ignore_errors=True)
        temp_extract.mkdir(parents=True, exist_ok=True)

        try:
            with zipfile.ZipFile(package_path, "r") as z:
                z.extractall(temp_extract)

            # Find folder with manifest.json
            manifest_file = None
            if (temp_extract / "manifest.json").exists():
                manifest_file = temp_extract / "manifest.json"
                source_folder = temp_extract
            else:
                for sub in temp_extract.iterdir():
                    if sub.is_dir() and (sub / "manifest.json").exists():
                        manifest_file = sub / "manifest.json"
                        source_folder = sub
                        break

            if not manifest_file:
                raise ValueError("The package does not contain a valid manifest.json")

            manifest = PluginManifest.from_file(manifest_file)
            dest = user_dir / manifest.id
            if dest.exists():
                shutil.rmtree(dest)

            shutil.copytree(source_folder, dest)
            self.discover_plugins()
            self.set_plugin_enabled(manifest.id, True)
            self.load_plugin(manifest.id)
            return True
        finally:
            shutil.rmtree(temp_extract, ignore_errors=True)

    @classmethod
    def package_addon(cls, plugin_folder: Path | str, output_zip: Path | str) -> bool:
        """Zips a plugin directory into an .rtvs-addon file."""
        src = Path(plugin_folder)
        dest = Path(output_zip)
        dest.parent.mkdir(parents=True, exist_ok=True)

        if not (src / "manifest.json").exists():
            print(f"[PLUGINS] Cannot package {src}: missing manifest.json")
            return False

        with zipfile.ZipFile(dest, "w", zipfile.ZIP_DEFLATED) as z:
            for root, dirs, files in os.walk(src):
                # Ignore __pycache__ and git
                dirs[:] = [d for d in dirs if d not in {"__pycache__", ".git", ".pytest_cache"}]
                for file in files:
                    if file.endswith((".pyc", ".pyo")):
                        continue
                    full = Path(root) / file
                    rel = full.relative_to(src)
                    z.write(full, rel)
        print(f"[PLUGINS] Packaged addon -> {dest}")
        return True


class PluginManagerDialog(QDialog):
    """GUI Dialog for managing and installing plugins."""

    def __init__(self, manager: PluginManager, parent: Any = None):
        super().__init__(parent)
        self.manager = manager
        self.setWindowTitle("Manage Plugins & Add-ons")
        self.setMinimumSize(720, 480)
        self.setup_ui()
        self.refresh_list()

    def setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        header = QLabel(
            "<b>Installed Plugins & Extensions</b><br>"
            "<span style='color: #64748b;'>Enable, disable, or install optional publishing destinations and workflow extensions.</span>"
        )
        layout.addWidget(header)

        self.table = QTableWidget()
        self.table.setColumnCount(5)
        self.table.setHorizontalHeaderLabels(["Enabled", "Name", "Version", "Category", "Author"])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.Stretch)
        self.table.itemSelectionChanged.connect(self.on_selection_changed)
        layout.addWidget(self.table)

        # Description box
        desc_box = QGroupBox("Plugin Details")
        desc_layout = QVBoxLayout(desc_box)
        self.desc_text = QTextEdit()
        self.desc_text.setReadOnly(True)
        self.desc_text.setMaximumHeight(90)
        desc_layout.addWidget(self.desc_text)
        layout.addWidget(desc_box)

        # Action bar
        btn_layout = QHBoxLayout()
        install_btn = QPushButton("Install Addon (.rtvs-addon)...")
        install_btn.clicked.connect(self.on_install_addon)
        btn_layout.addWidget(install_btn)

        open_folder_btn = QPushButton("Open Plugins Folder")
        open_folder_btn.clicked.connect(self.on_open_folder)
        btn_layout.addWidget(open_folder_btn)

        btn_layout.addStretch()

        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.accept)
        btn_layout.addWidget(close_btn)

        layout.addLayout(btn_layout)

    def refresh_list(self):
        self.manager.discover_plugins()
        self.table.setRowCount(0)
        row = 0
        for plugin_id, manifest in sorted(self.manager.manifests.items(), key=lambda x: x[1].name):
            self.table.insertRow(row)

            # Checkbox
            chk = QCheckBox()
            is_enabled = self.manager.is_plugin_enabled(plugin_id)
            chk.setChecked(is_enabled)
            chk.stateChanged.connect(lambda state, pid=plugin_id: self.on_toggle_plugin(pid, state))
            chk_widget = QWidget()
            chk_layout = QHBoxLayout(chk_widget)
            chk_layout.setContentsMargins(4, 2, 4, 2)
            chk_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
            chk_layout.addWidget(chk)
            self.table.setCellWidget(row, 0, chk_widget)

            # Name item
            name_item = QTableWidgetItem(manifest.name)
            name_item.setData(Qt.ItemDataRole.UserRole, plugin_id)
            self.table.setItem(row, 1, name_item)

            # Version item
            self.table.setItem(row, 2, QTableWidgetItem(f"v{manifest.version}"))

            # Category item
            self.table.setItem(row, 3, QTableWidgetItem(manifest.category.capitalize()))

            # Author item
            self.table.setItem(row, 4, QTableWidgetItem(manifest.author or "Official"))

            row += 1

        if self.table.rowCount() > 0:
            self.table.selectRow(0)

    def on_toggle_plugin(self, plugin_id: str, state: int):
        enabled = state == Qt.CheckState.Checked.value or state == 2
        self.manager.set_plugin_enabled(plugin_id, enabled)
        if enabled:
            self.manager.load_plugin(plugin_id)
        else:
            self.manager.unload_plugin(plugin_id)

    def on_selection_changed(self):
        selected_rows = self.table.selectionModel().selectedRows()
        if not selected_rows:
            self.desc_text.clear()
            return
        row = selected_rows[0].row()
        item = self.table.item(row, 1)
        if not item:
            return
        plugin_id = item.data(Qt.ItemDataRole.UserRole)
        manifest = self.manager.manifests.get(plugin_id)
        if manifest:
            folder = self.manager.plugin_paths.get(plugin_id, "Unknown")
            desc = (
                f"<b>{manifest.name}</b> (ID: <code>{manifest.id}</code>)<br>"
                f"{manifest.description}<br><br>"
                f"<b>Author:</b> {manifest.author or 'Official'} &nbsp;•&nbsp; "
                f"<b>Location:</b> <span style='font-size: 11px;'>{folder}</span>"
            )
            self.desc_text.setHtml(desc)

    def on_install_addon(self):
        fn, _ = QFileDialog.getOpenFileName(
            self,
            "Install Plugin Add-on Package",
            "",
            "RTVS Add-on Packages (*.rtvs-addon *.zip);;All Files (*.*)",
        )
        if not fn:
            return
        try:
            ok = self.manager.install_addon(fn)
            if ok:
                QMessageBox.information(self, "Addon Installed", f"Plugin was successfully installed from {Path(fn).name}!")
                self.refresh_list()
            else:
                QMessageBox.warning(self, "Installation Failed", "Could not install plugin. Make sure it contains a valid manifest.json.")
        except Exception as exc:
            QMessageBox.critical(self, "Installation Error", str(exc))

    def on_open_folder(self):
        user_dir = self.manager.get_user_plugins_dir()
        import subprocess
        if sys.platform == "win32":
            os.startfile(str(user_dir))
        elif sys.platform == "darwin":
            subprocess.Popen(["open", str(user_dir)])
        else:
            subprocess.Popen(["xdg-open", str(user_dir)])
