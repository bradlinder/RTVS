"""Radio & TV Segmenter — Plugin Manager and Discovery Engine."""
from __future__ import annotations

import importlib
import importlib.util
import json
import os
import shutil
import sys
import tempfile
import urllib.error
import urllib.request
import zipfile
from pathlib import Path
from typing import Any, Dict, List, Optional

from prs_shared import INTERNAL_APP_ID, PROJECT_VERSION, QSettings, get_github_repo
from plugins.base import BasePlugin, PluginManifest

from PySide6.QtCore import Qt, QSize, QThread, Signal
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
    QAbstractItemView,
    QMessageBox,
    QFileDialog,
    QCheckBox,
    QGroupBox,
    QTextEdit,
    QWidget,
    QProgressBar,
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
        """Scans user plugin directory and loads manifests of installed plugins."""
        self.manifests.clear()
        self.plugin_paths.clear()

        # Only discover plugins installed in the user's plugin directory
        user_dir = self.get_user_plugins_dir()
        if user_dir.exists() and user_dir.is_dir():
            for item in user_dir.iterdir():
                if item.name.startswith("."):
                    continue
                if item.is_dir():
                    manifest_file = item / "manifest.json"
                    if manifest_file.exists():
                        try:
                            manifest = PluginManifest.from_file(manifest_file)
                            self.manifests[manifest.id] = manifest
                            self.plugin_paths[manifest.id] = item
                        except Exception as exc:
                            print(f"[PLUGINS] Failed to load manifest from {manifest_file}: {exc}")
                elif item.is_file() and item.name.endswith(".rtvs-addon"):
                    try:
                        with zipfile.ZipFile(item, "r") as zf:
                            if "manifest.json" in zf.namelist():
                                m_data = json.loads(zf.read("manifest.json").decode("utf-8"))
                                manifest = PluginManifest.from_dict(m_data)
                                if manifest.id not in self.manifests:
                                    self.manifests[manifest.id] = manifest
                                    self.plugin_paths[manifest.id] = item
                    except Exception as exc:
                        print(f"[PLUGINS] Failed to read addon manifest from {item}: {exc}")

        # Ensure .rtvs-addon packages are generated in bundled directory for export/download
        self.ensure_packaged_addons()

        return self.manifests

    def ensure_packaged_addons(self) -> None:
        """Ensures that all bundled directory-based plugins have .rtvs-addon files created."""
        bundled_dir = self.get_bundled_plugins_dir()
        if bundled_dir.exists() and bundled_dir.is_dir():
            for item in bundled_dir.iterdir():
                if item.is_dir() and (item / "manifest.json").exists():
                    plugin_id = item.name
                    bundled_addon = bundled_dir / f"{plugin_id}.rtvs-addon"
                    if not bundled_addon.exists():
                        try:
                            self.package_addon(item, bundled_addon)
                        except Exception as exc:
                            print(f"[PLUGINS] Could not auto-package {bundled_addon}: {exc}")

    @classmethod
    def get_bundled_addons(cls) -> Dict[str, Path]:
        """Returns a map of plugin_id -> Path of bundled .rtvs-addon packages."""
        res: Dict[str, Path] = {}
        bundled_dir = cls.get_bundled_plugins_dir()
        if bundled_dir.exists() and bundled_dir.is_dir():
            for item in bundled_dir.iterdir():
                if item.is_file() and item.name.endswith(".rtvs-addon"):
                    res[item.stem] = item
                elif item.is_dir() and (item / "manifest.json").exists():
                    addon_file = item / f"{item.name}.rtvs-addon"
                    if addon_file.exists():
                        res[item.name] = addon_file
                    else:
                        root_addon = bundled_dir / f"{item.name}.rtvs-addon"
                        if root_addon.exists():
                            res[item.name] = root_addon
        return res

    def is_plugin_installed(self, plugin_id: str) -> bool:
        """Checks whether the plugin is installed in the system."""
        return plugin_id in self.manifests

    def is_plugin_enabled(self, plugin_id: str) -> bool:
        if not self.is_plugin_installed(plugin_id):
            return False
        manifest = self.manifests.get(plugin_id)
        default_val = manifest.enabled_by_default if manifest else False
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
                self.plugins[plugin_id].set_enabled(False)
                self.plugins[plugin_id].on_unload()
            except Exception as exc:
                print(f"[PLUGINS] Error during unload of {plugin_id}: {exc}")
            del self.plugins[plugin_id]

    def uninstall_plugin(self, plugin_id: str) -> bool:
        """Uninstalls and removes a plugin completely from the system."""
        # Unload if currently loaded
        self.unload_plugin(plugin_id)

        # Clear enabled status and plugin settings
        self.set_plugin_enabled(plugin_id, False)
        self.settings.remove(f"plugins/{plugin_id}")
        self.settings.sync()

        # Remove from user plugins directory
        user_dir = self.get_user_plugins_dir()
        target_dir = user_dir / plugin_id
        if target_dir.exists():
            try:
                shutil.rmtree(target_dir, ignore_errors=True)
            except Exception as exc:
                print(f"[PLUGINS] Error deleting directory {target_dir}: {exc}")

        # Remove standalone addon package in user directory if present
        addon_file = user_dir / f"{plugin_id}.rtvs-addon"
        if addon_file.exists():
            try:
                addon_file.unlink(missing_ok=True)
            except Exception as exc:
                print(f"[PLUGINS] Error removing addon file {addon_file}: {exc}")

        # Check if plugin_path was registered in user directory
        if plugin_id in self.plugin_paths:
            ppath = self.plugin_paths[plugin_id]
            if user_dir in ppath.parents or ppath == target_dir or ppath == addon_file:
                if ppath.is_dir():
                    shutil.rmtree(ppath, ignore_errors=True)
                elif ppath.is_file():
                    try:
                        ppath.unlink(missing_ok=True)
                    except Exception:
                        pass

        if plugin_id in self.manifests:
            del self.manifests[plugin_id]
        if plugin_id in self.plugin_paths:
            del self.plugin_paths[plugin_id]

        self.discover_plugins()

        if self.app and hasattr(self.app, "refresh_plugin_menus"):
            self.app.refresh_plugin_menus()

        return True

    def install_addon(self, package_path: Path | str, enable: bool = False) -> bool:
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
                shutil.rmtree(dest, ignore_errors=True)

            shutil.copytree(source_folder, dest)
            self.discover_plugins()
            self.set_plugin_enabled(manifest.id, enable)
            if enable:
                self.load_plugin(manifest.id)
            else:
                self.unload_plugin(manifest.id)

            if self.app and hasattr(self.app, "refresh_plugin_menus"):
                self.app.refresh_plugin_menus()

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


class GitHubPluginsWorker(QThread):
    """Fetches list of available plugins from GitHub release assets and official catalog."""
    finished = Signal(bool, list, str)

    def __init__(self, repo: str, parent=None):
        super().__init__(parent)
        self.repo = repo

    def run(self):
        plugins_catalog = [
            {
                "id": "youtube",
                "name": "YouTube Video Publisher",
                "category": "export",
                "version": PROJECT_VERSION,
                "description": "Publishes broadcast video stories to YouTube with chapter timestamps, frame grabs/custom thumbnails, tags, and assisted YouTube Studio upload.",
                "author": "Radio & TV Segmenter Team",
                "asset_name": "youtube.rtvs-addon",
                "download_url": f"https://github.com/{self.repo}/releases/download/v{PROJECT_VERSION}/youtube.rtvs-addon",
                "fallback_url": f"https://raw.githubusercontent.com/{self.repo}/main/plugins/youtube.rtvs-addon",
            },
            {
                "id": "wordpress",
                "name": "WordPress Publisher",
                "category": "export",
                "version": PROJECT_VERSION,
                "description": "Publishes segmented audio/video stories, transcripts, excerpts, and custom featured images directly to WordPress posts via the WP REST API.",
                "author": "Radio & TV Segmenter Team",
                "asset_name": "wordpress.rtvs-addon",
                "download_url": f"https://github.com/{self.repo}/releases/download/v{PROJECT_VERSION}/wordpress.rtvs-addon",
                "fallback_url": f"https://raw.githubusercontent.com/{self.repo}/main/plugins/wordpress.rtvs-addon",
            },
            {
                "id": "translation",
                "name": "Language Translation",
                "category": "ai",
                "version": PROJECT_VERSION,
                "description": "Provides local multi-language neural machine translation (MarianMT and NLLB models) with synchronized bilingual split-view editing and translated exports.",
                "author": "Radio & TV Segmenter Team",
                "asset_name": "translation.rtvs-addon",
                "download_url": f"https://github.com/{self.repo}/releases/download/v{PROJECT_VERSION}/translation.rtvs-addon",
                "fallback_url": f"https://raw.githubusercontent.com/{self.repo}/main/plugins/translation.rtvs-addon",
            },
        ]

        # Try querying GitHub Releases API
        api_url = f"https://api.github.com/repos/{self.repo}/releases?per_page=5"
        headers = {"User-Agent": f"RadioTVSegmenter/{PROJECT_VERSION}"}
        req = urllib.request.Request(api_url, headers=headers)

        try:
            with urllib.request.urlopen(req, timeout=8) as response:
                if response.status == 200:
                    releases = json.loads(response.read().decode("utf-8"))
                    asset_map = {}
                    for rel in releases:
                        tag_ver = rel.get("tag_name", "").lstrip("v")
                        for asset in rel.get("assets", []):
                            aname = asset.get("name", "")
                            if aname.endswith(".rtvs-addon"):
                                asset_map[aname] = {
                                    "url": asset.get("browser_download_url"),
                                    "size": asset.get("size", 0),
                                    "version": tag_ver or PROJECT_VERSION,
                                }

                    for item in plugins_catalog:
                        aname = item["asset_name"]
                        if aname in asset_map:
                            item["download_url"] = asset_map[aname]["url"]
                            item["size"] = asset_map[aname]["size"]
                            item["version"] = asset_map[aname]["version"]

                    self.finished.emit(True, plugins_catalog, "")
                    return
        except Exception as exc:
            print(f"[PLUGINS] GitHub releases check failed ({exc}), using standard release catalog.")

        self.finished.emit(True, plugins_catalog, "Connected via official catalog cache.")


class GitHubDownloadWorker(QThread):
    """Downloads an add-on package in background with progress updates."""
    progress = Signal(int, str)
    finished = Signal(bool, str, str)

    def __init__(self, download_url: str, local_dest: Path, fallback_local_addon: Optional[Path] = None, parent=None):
        super().__init__(parent)
        self.download_url = download_url
        self.local_dest = local_dest
        self.fallback_local_addon = fallback_local_addon
        self._is_cancelled = False

    def cancel(self):
        self._is_cancelled = True

    def run(self):
        headers = {"User-Agent": f"RadioTVSegmenter/{PROJECT_VERSION}"}
        req = urllib.request.Request(self.download_url, headers=headers)
        success = False
        last_error = ""

        try:
            self.progress.emit(10, "Connecting to GitHub server...")
            with urllib.request.urlopen(req, timeout=15) as response:
                total_size = int(response.headers.get("content-length", 0))
                bytes_so_far = 0
                chunk_size = 32 * 1024
                self.local_dest.parent.mkdir(parents=True, exist_ok=True)

                with open(self.local_dest, "wb") as f:
                    while True:
                        if self._is_cancelled:
                            self.finished.emit(False, "", "Download cancelled by user.")
                            return
                        chunk = response.read(chunk_size)
                        if not chunk:
                            break
                        f.write(chunk)
                        bytes_so_far += len(chunk)
                        if total_size > 0:
                            pct = int((bytes_so_far / total_size) * 85) + 10
                            self.progress.emit(min(pct, 95), f"Downloading ({bytes_so_far // 1024} KB / {total_size // 1024} KB)...")
                        else:
                            self.progress.emit(50, f"Downloading ({bytes_so_far // 1024} KB)...")
                success = True
        except Exception as exc:
            last_error = str(exc)
            print(f"[PLUGINS] Download from {self.download_url} failed: {exc}")

        if not success and self.fallback_local_addon and self.fallback_local_addon.exists():
            try:
                self.progress.emit(60, "Copying from local package cache...")
                self.local_dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(self.fallback_local_addon, self.local_dest)
                success = True
            except Exception as copy_exc:
                last_error = str(copy_exc)

        if success and self.local_dest.exists() and self.local_dest.stat().st_size > 0:
            self.progress.emit(100, "Download complete!")
            self.finished.emit(True, str(self.local_dest), "")
        else:
            self.finished.emit(False, "", f"Failed to download plugin: {last_error or 'Network error'}")


class GitHubPluginsDialog(QDialog):
    """Browses, downloads, installs, and manages add-ons directly from GitHub releases."""

    def __init__(self, manager: PluginManager, parent=None):
        super().__init__(parent)
        self.manager = manager
        self.repo = get_github_repo()
        self.catalog: List[Dict[str, Any]] = []
        self.download_worker: Optional[GitHubDownloadWorker] = None
        self.fetch_worker: Optional[GitHubPluginsWorker] = None

        self.setWindowTitle("Download Plugins & Extensions from GitHub")
        self.resize(780, 520)
        self.setup_ui()
        self.fetch_plugins()

    def setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        header = QLabel(
            "<b>Download Plugins & Extensions from GitHub</b><br>"
            f"<span style='color: #64748b;'>Browse official extensions published on the GitHub repository releases ({self.repo}). "
            "Install, enable, and manage modular features with one click.</span>"
        )
        layout.addWidget(header)

        self.repo_label = QLabel(f"Connecting to GitHub releases for <b>{self.repo}</b>...")
        layout.addWidget(self.repo_label)

        self.table = QTableWidget()
        self.table.setColumnCount(5)
        self.table.setHorizontalHeaderLabels(["Plugin", "Version", "Category", "Status", "Action"])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.Stretch)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.itemSelectionChanged.connect(self.on_selection_changed)
        self.table.cellClicked.connect(lambda row, col: self.on_selection_changed())
        layout.addWidget(self.table)

        desc_box = QGroupBox("Plugin Description")
        desc_layout = QVBoxLayout(desc_box)
        self.desc_text = QTextEdit()
        self.desc_text.setReadOnly(True)
        self.desc_text.setMaximumHeight(85)
        desc_layout.addWidget(self.desc_text)
        layout.addWidget(desc_box)

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setVisible(False)
        layout.addWidget(self.progress_bar)

        self.progress_label = QLabel("")
        self.progress_label.setVisible(False)
        layout.addWidget(self.progress_label)

        btn_layout = QHBoxLayout()
        self.refresh_btn = QPushButton("Refresh from GitHub")
        self.refresh_btn.clicked.connect(self.fetch_plugins)
        btn_layout.addWidget(self.refresh_btn)

        btn_layout.addStretch()

        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.accept)
        btn_layout.addWidget(close_btn)

        layout.addLayout(btn_layout)

    def fetch_plugins(self):
        self.repo_label.setText(f"Querying GitHub releases for <b>{self.repo}</b>...")
        self.refresh_btn.setEnabled(False)
        self.table.setRowCount(0)

        self.fetch_worker = GitHubPluginsWorker(self.repo, self)
        self.fetch_worker.finished.connect(self.on_plugins_fetched)
        self.fetch_worker.start()

    def on_plugins_fetched(self, success: bool, catalog: list, note: str):
        self.refresh_btn.setEnabled(True)
        self.catalog = catalog
        if note:
            self.repo_label.setText(f"Repository: <b>{self.repo}</b> ({note})")
        else:
            self.repo_label.setText(f"Repository: <b>{self.repo}</b> (Latest Releases)")
        self.render_table()

    def render_table(self):
        self.manager.discover_plugins()
        self.table.setRowCount(0)

        for row, item in enumerate(self.catalog):
            self.table.insertRow(row)
            plugin_id = item["id"]
            is_installed = self.manager.is_plugin_installed(plugin_id)
            is_enabled = self.manager.is_plugin_enabled(plugin_id)

            name_item = QTableWidgetItem(item["name"])
            name_item.setData(Qt.ItemDataRole.UserRole, item)
            self.table.setItem(row, 0, name_item)

            self.table.setItem(row, 1, QTableWidgetItem(f"v{item.get('version', PROJECT_VERSION)}"))
            self.table.setItem(row, 2, QTableWidgetItem(str(item.get("category", "General")).capitalize()))

            if is_installed:
                status_text = "Installed (Enabled)" if is_enabled else "Installed (Disabled)"
            else:
                status_text = "Available"
            self.table.setItem(row, 3, QTableWidgetItem(status_text))

            action_widget = QWidget()
            action_layout = QHBoxLayout(action_widget)
            action_layout.setContentsMargins(4, 2, 4, 2)
            action_layout.setSpacing(6)

            if not is_installed:
                download_btn = QPushButton("Download & Install")
                download_btn.setStyleSheet("font-weight: bold;")
                download_btn.clicked.connect(lambda _, it=item: self.download_and_install_plugin(it))
                action_layout.addWidget(download_btn)
            else:
                toggle_btn = QPushButton("Disable" if is_enabled else "Enable")
                toggle_btn.clicked.connect(lambda _, pid=plugin_id, cur=is_enabled: self.toggle_plugin(pid, not cur))
                action_layout.addWidget(toggle_btn)

                uninstall_btn = QPushButton("Uninstall")
                uninstall_btn.clicked.connect(lambda _, pid=plugin_id, nm=item["name"]: self.uninstall_plugin(pid, nm))
                action_layout.addWidget(uninstall_btn)

            self.table.setCellWidget(row, 4, action_widget)

        if self.table.rowCount() > 0:
            self.table.selectRow(0)

    def on_selection_changed(self):
        row = self.table.currentRow()
        if row < 0:
            selected_rows = self.table.selectionModel().selectedRows()
            if selected_rows:
                row = selected_rows[0].row()
            elif self.table.selectedItems():
                row = self.table.selectedItems()[0].row()

        if row < 0 or row >= self.table.rowCount():
            self.desc_text.clear()
            return

        item_cell = self.table.item(row, 0)
        if not item_cell:
            return
        data = item_cell.data(Qt.ItemDataRole.UserRole)
        if data:
            desc = (
                f"<b>{data['name']}</b> (ID: <code>{data['id']}</code>)<br>"
                f"{data.get('description', '')}<br><br>"
                f"<b>Author:</b> {data.get('author', 'Official')} &nbsp;•&nbsp; "
                f"<b>Download Package:</b> <code>{data.get('asset_name', '')}</code>"
            )
            self.desc_text.setHtml(desc)

    def download_and_install_plugin(self, item: Dict[str, Any]):
        plugin_id = item["id"]
        plugin_name = item["name"]
        asset_name = item.get("asset_name", f"{plugin_id}.rtvs-addon")
        download_url = item.get("download_url") or item.get("fallback_url")

        bundled_addons = self.manager.get_bundled_addons()
        fallback_addon = bundled_addons.get(plugin_id)

        dest_file = Path(tempfile.gettempdir()) / f"rtvs_download_{plugin_id}_{asset_name}"

        self.progress_bar.setValue(0)
        self.progress_bar.setVisible(True)
        self.progress_label.setText(f"Starting download of {plugin_name}...")
        self.progress_label.setVisible(True)

        self.download_worker = GitHubDownloadWorker(download_url, dest_file, fallback_addon, self)
        self.download_worker.progress.connect(self.on_download_progress)
        self.download_worker.finished.connect(lambda ok, path, err, nm=plugin_name, pid=plugin_id: self.on_download_finished(ok, path, err, nm, pid))
        self.download_worker.start()

    def on_download_progress(self, percent: int, msg: str):
        self.progress_bar.setValue(percent)
        self.progress_label.setText(msg)

    def on_download_finished(self, success: bool, file_path: str, error_msg: str, plugin_name: str, plugin_id: str):
        self.progress_bar.setVisible(False)
        self.progress_label.setVisible(False)

        if not success:
            QMessageBox.critical(self, "Download Failed", f"Could not download {plugin_name}:\n{error_msg}")
            return

        try:
            ok = self.manager.install_addon(file_path, enable=False)
            if ok:
                res = QMessageBox.question(
                    self,
                    "Plugin Installed",
                    f"<b>{plugin_name}</b> has been downloaded and installed successfully!\n\n"
                    "Would you like to enable this plugin now?",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                    QMessageBox.StandardButton.Yes,
                )
                if res == QMessageBox.StandardButton.Yes:
                    self.manager.set_plugin_enabled(plugin_id, True)
                    self.manager.load_plugin(plugin_id)
                    if self.manager.app and hasattr(self.manager.app, "refresh_plugin_menus"):
                        self.manager.app.refresh_plugin_menus()

                self.render_table()
            else:
                QMessageBox.warning(self, "Installation Failed", f"Downloaded package for {plugin_name} was invalid or missing manifest.")
        except Exception as exc:
            QMessageBox.critical(self, "Installation Error", f"Failed to install {plugin_name}:\n{exc}")

    def toggle_plugin(self, plugin_id: str, enable: bool):
        self.manager.set_plugin_enabled(plugin_id, enable)
        if enable:
            self.manager.load_plugin(plugin_id)
        else:
            self.manager.unload_plugin(plugin_id)
        if self.manager.app and hasattr(self.manager.app, "refresh_plugin_menus"):
            self.manager.app.refresh_plugin_menus()
        self.render_table()

    def uninstall_plugin(self, plugin_id: str, plugin_name: str):
        res = QMessageBox.question(
            self,
            "Uninstall Plugin",
            f"Are you sure you want to uninstall and remove '{plugin_name}'?\n\n"
            "This will remove the plugin files and disable its features.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if res == QMessageBox.StandardButton.Yes:
            self.manager.uninstall_plugin(plugin_id)
            QMessageBox.information(self, "Plugin Removed", f"'{plugin_name}' has been successfully uninstalled.")
            self.render_table()


class PluginManagerDialog(QDialog):
    """GUI Dialog for viewing, managing, enabling, installing, and removing plugins."""

    def __init__(self, manager: PluginManager, parent: Any = None):
        super().__init__(parent)
        self.manager = manager
        self.setWindowTitle("Manage Plugins & Add-ons")
        self.setMinimumSize(740, 480)
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
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.itemSelectionChanged.connect(self.on_selection_changed)
        self.table.cellClicked.connect(lambda row, col: self.on_selection_changed())
        layout.addWidget(self.table)

        self.empty_label = QLabel(
            "<i>No plugins are currently installed. Use <b>Download from GitHub...</b> to explore and install official add-ons, or click <b>Install Addon...</b> to select a local file.</i>"
        )
        self.empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty_label.setStyleSheet("color: #64748b; padding: 12px;")
        self.empty_label.setVisible(False)
        layout.addWidget(self.empty_label)

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

        download_github_btn = QPushButton("Download from GitHub...")
        download_github_btn.setStyleSheet("font-weight: bold;")
        download_github_btn.clicked.connect(self.on_download_github)
        btn_layout.addWidget(download_github_btn)

        install_btn = QPushButton("Install Addon (.rtvs-addon)...")
        install_btn.clicked.connect(self.on_install_addon)
        btn_layout.addWidget(install_btn)

        self.uninstall_btn = QPushButton("Uninstall Plugin...")
        self.uninstall_btn.setEnabled(False)
        self.uninstall_btn.clicked.connect(self.on_uninstall_plugin)
        btn_layout.addWidget(self.uninstall_btn)

        self.export_btn = QPushButton("Export Addon...")
        self.export_btn.setEnabled(False)
        self.export_btn.clicked.connect(self.on_export_addon)
        btn_layout.addWidget(self.export_btn)

        open_folder_btn = QPushButton("Open Plugins Folder")
        open_folder_btn.clicked.connect(self.on_open_folder)
        btn_layout.addWidget(open_folder_btn)

        btn_layout.addStretch()

        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.accept)
        btn_layout.addWidget(close_btn)

        layout.addLayout(btn_layout)

    def on_download_github(self):
        dlg = GitHubPluginsDialog(self.manager, self)
        dlg.exec()
        self.refresh_list()

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

        is_empty = self.table.rowCount() == 0
        self.empty_label.setVisible(is_empty)
        self.uninstall_btn.setEnabled(not is_empty)
        self.export_btn.setEnabled(not is_empty)

        if not is_empty:
            self.table.selectRow(0)
        else:
            self.desc_text.clear()

    def on_toggle_plugin(self, plugin_id: str, state: int):
        enabled = state == Qt.CheckState.Checked.value or state == 2
        self.manager.set_plugin_enabled(plugin_id, enabled)
        if enabled:
            self.manager.load_plugin(plugin_id)
        else:
            self.manager.unload_plugin(plugin_id)
        if self.manager.app and hasattr(self.manager.app, "refresh_plugin_menus"):
            self.manager.app.refresh_plugin_menus()

    def on_selection_changed(self):
        row = self.table.currentRow()
        if row < 0:
            selected_rows = self.table.selectionModel().selectedRows()
            if selected_rows:
                row = selected_rows[0].row()
            elif self.table.selectedItems():
                row = self.table.selectedItems()[0].row()

        if row < 0 or row >= self.table.rowCount():
            self.desc_text.clear()
            self.uninstall_btn.setEnabled(False)
            self.export_btn.setEnabled(False)
            return

        self.uninstall_btn.setEnabled(True)
        self.export_btn.setEnabled(True)

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

    def on_uninstall_plugin(self):
        row = self.table.currentRow()
        if row < 0:
            selected_rows = self.table.selectionModel().selectedRows()
            if selected_rows:
                row = selected_rows[0].row()
            elif self.table.selectedItems():
                row = self.table.selectedItems()[0].row()

        if row < 0 or row >= self.table.rowCount():
            QMessageBox.information(self, "Uninstall Plugin", "Please select an installed plugin to uninstall.")
            return

        item = self.table.item(row, 1)
        if not item:
            return
        plugin_id = item.data(Qt.ItemDataRole.UserRole)
        manifest = self.manager.manifests.get(plugin_id)
        plugin_name = manifest.name if manifest else plugin_id

        res = QMessageBox.question(
            self,
            "Uninstall Plugin",
            f"Are you sure you want to uninstall and remove '{plugin_name}'?\n\n"
            "This will remove the plugin files and disable all related features.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if res == QMessageBox.StandardButton.Yes:
            self.manager.uninstall_plugin(plugin_id)
            QMessageBox.information(self, "Plugin Removed", f"'{plugin_name}' has been successfully uninstalled.")
            self.refresh_list()

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
            ok = self.manager.install_addon(fn, enable=False)
            if ok:
                res = QMessageBox.question(
                    self,
                    "Addon Installed",
                    f"Plugin was successfully installed from {Path(fn).name}!\n\nWould you like to enable it now?",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                    QMessageBox.StandardButton.Yes,
                )
                if res == QMessageBox.StandardButton.Yes:
                    manifests = self.manager.discover_plugins()
                    for pid in manifests:
                        if not self.manager.is_plugin_enabled(pid):
                            self.manager.set_plugin_enabled(pid, True)
                            self.manager.load_plugin(pid)
                    if self.manager.app and hasattr(self.manager.app, "refresh_plugin_menus"):
                        self.manager.app.refresh_plugin_menus()
                self.refresh_list()
            else:
                QMessageBox.warning(self, "Installation Failed", "Could not install plugin. Make sure it contains a valid manifest.json.")
        except Exception as exc:
            QMessageBox.critical(self, "Installation Error", str(exc))

    def on_export_addon(self):
        row = self.table.currentRow()
        if row < 0:
            selected_rows = self.table.selectionModel().selectedRows()
            if selected_rows:
                row = selected_rows[0].row()
            elif self.table.selectedItems():
                row = self.table.selectedItems()[0].row()

        if row < 0 or row >= self.table.rowCount():
            QMessageBox.information(self, "Export Addon", "Please select a plugin from the list to export.")
            return
        item = self.table.item(row, 1)
        if not item:
            return
        plugin_id = item.data(Qt.ItemDataRole.UserRole)
        folder = self.manager.plugin_paths.get(plugin_id)
        if not folder or not Path(folder).is_dir():
            QMessageBox.warning(self, "Export Addon", f"Plugin directory for '{plugin_id}' not found.")
            return

        default_fn = f"{plugin_id}.rtvs-addon"
        fn, _ = QFileDialog.getSaveFileName(
            self,
            f"Export Plugin Addon ({plugin_id})",
            default_fn,
            "RTVS Add-on Packages (*.rtvs-addon);;ZIP Archives (*.zip);;All Files (*.*)",
        )
        if not fn:
            return
        ok = self.manager.package_addon(folder, fn)
        if ok:
            QMessageBox.information(self, "Export Complete", f"Successfully exported addon to:\n{fn}")
        else:
            QMessageBox.warning(self, "Export Failed", "Could not package addon. Check that manifest.json exists.")

    def on_open_folder(self):
        self.manager.ensure_packaged_addons()
        user_dir = self.manager.get_user_plugins_dir()
        user_dir.mkdir(parents=True, exist_ok=True)
        import subprocess
        if sys.platform == "win32":
            os.startfile(str(user_dir))
        elif sys.platform == "darwin":
            subprocess.Popen(["open", str(user_dir)])
        else:
            subprocess.Popen(["xdg-open", str(user_dir)])
