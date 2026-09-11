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
        """Ensures that all bundled directory-based plugins have up-to-date .rtvs-addon files created."""
        bundled_dir = self.get_bundled_plugins_dir()
        if bundled_dir.exists() and bundled_dir.is_dir():
            for item in bundled_dir.iterdir():
                if item.is_dir() and (item / "manifest.json").exists():
                    plugin_id = item.name
                    bundled_addon = bundled_dir / f"{plugin_id}.rtvs-addon"
                    sub_addon = item / f"{plugin_id}.rtvs-addon"
                    manifest_path = item / "manifest.json"
                    needs_package = not bundled_addon.exists()
                    if not needs_package:
                        try:
                            with zipfile.ZipFile(bundled_addon, "r") as zf:
                                if "manifest.json" in zf.namelist():
                                    data = json.loads(zf.read("manifest.json").decode("utf-8"))
                                    dir_data = json.loads(manifest_path.read_text(encoding="utf-8"))
                                    if data.get("version") != dir_data.get("version"):
                                        needs_package = True
                                else:
                                    needs_package = True
                        except Exception:
                            needs_package = True

                    if needs_package:
                        try:
                            self.package_addon(item, bundled_addon)
                            if sub_addon.exists() or bundled_addon.exists():
                                self.package_addon(item, sub_addon)
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

    def plugin_runtime(self, plugin_id: str) -> dict:
        manifest = self.manifests.get(plugin_id)
        if not manifest:
            return {"type": "core", "name": ""}
        return {"type": manifest.runtime_type, "name": manifest.runtime_name or manifest.id}

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
        manifest = self.manifests.get(plugin_id)
        if manifest and manifest.runtime_type == "isolated":
            try:
                from runtime_manager import RuntimeManager
                runtime_name = manifest.runtime_name or manifest.id
                RuntimeManager().remove_environment(runtime_name)
            except Exception as exc:
                print(f"[PLUGINS] Could not remove isolated runtime for {plugin_id}: {exc}")
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


class GitHubBatchDownloadWorker(QThread):
    """Downloads and installs a batch of add-on packages in sequence with progress updates."""
    progress = Signal(int, str)
    finished = Signal(int, int, list)  # (succeeded_count, failed_count, error_messages)

    def __init__(self, items: List[Dict[str, Any]], manager: PluginManager, enable_after: bool = False, parent=None):
        super().__init__(parent)
        self.items = items
        self.manager = manager
        self.enable_after = enable_after
        self._is_cancelled = False

    def cancel(self):
        self._is_cancelled = True

    def run(self):
        total = len(self.items)
        if total == 0:
            self.finished.emit(0, 0, [])
            return

        succeeded = 0
        failed = 0
        errors = []

        headers = {"User-Agent": f"RadioTVSegmenter/{PROJECT_VERSION}"}
        bundled_addons = self.manager.get_bundled_addons()

        for idx, item in enumerate(self.items):
            if self._is_cancelled:
                errors.append("Batch download cancelled by user.")
                break

            plugin_id = item["id"]
            plugin_name = item["name"]
            asset_name = item.get("asset_name", f"{plugin_id}.rtvs-addon")
            download_url = item.get("download_url") or item.get("fallback_url")
            fallback_addon = bundled_addons.get(plugin_id)

            dest_file = Path(tempfile.gettempdir()) / f"rtvs_download_{plugin_id}_{asset_name}"
            success = False
            last_error = ""

            base_pct = int((idx / total) * 100)
            next_pct = int(((idx + 1) / total) * 100)
            self.progress.emit(base_pct, f"Downloading ({idx + 1}/{total}): {plugin_name}...")

            if download_url:
                try:
                    req = urllib.request.Request(download_url, headers=headers)
                    with urllib.request.urlopen(req, timeout=15) as response:
                        total_size = int(response.headers.get("content-length", 0))
                        bytes_so_far = 0
                        chunk_size = 32 * 1024
                        dest_file.parent.mkdir(parents=True, exist_ok=True)

                        with open(dest_file, "wb") as f:
                            while True:
                                if self._is_cancelled:
                                    break
                                chunk = response.read(chunk_size)
                                if not chunk:
                                    break
                                f.write(chunk)
                                bytes_so_far += len(chunk)
                                if total_size > 0:
                                    item_pct = min(int((bytes_so_far / total_size) * (next_pct - base_pct)), next_pct - base_pct)
                                    self.progress.emit(base_pct + item_pct, f"Downloading ({idx + 1}/{total}): {plugin_name} ({bytes_so_far // 1024} KB / {total_size // 1024} KB)...")
                    if not self._is_cancelled and dest_file.exists() and dest_file.stat().st_size > 0:
                        success = True
                except Exception as exc:
                    last_error = str(exc)
                    print(f"[PLUGINS] Batch download of {plugin_name} failed: {exc}")

            if not success and fallback_addon and fallback_addon.exists():
                try:
                    self.progress.emit(base_pct + 10, f"Copying ({idx + 1}/{total}): {plugin_name} from local cache...")
                    dest_file.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(fallback_addon, dest_file)
                    success = True
                except Exception as copy_exc:
                    last_error = str(copy_exc)

            if success and dest_file.exists() and dest_file.stat().st_size > 0:
                self.progress.emit(next_pct, f"Installing ({idx + 1}/{total}): {plugin_name}...")
                try:
                    ok = self.manager.install_addon(dest_file, enable=self.enable_after)
                    if ok:
                        succeeded += 1
                    else:
                        failed += 1
                        errors.append(f"{plugin_name}: Failed to extract valid manifest from package.")
                except Exception as inst_exc:
                    failed += 1
                    errors.append(f"{plugin_name}: {inst_exc}")
            else:
                failed += 1
                errors.append(f"{plugin_name}: {last_error or 'Network download error'}")

        self.progress.emit(100, "Batch operation complete.")
        self.finished.emit(succeeded, failed, errors)


class GitHubPluginsDialog(QDialog):
    """Browses, downloads, installs, and manages add-ons directly from GitHub releases with multi-selection."""

    def __init__(self, manager: PluginManager, parent=None):
        super().__init__(parent)
        self.manager = manager
        self.repo = get_github_repo()
        self.catalog: List[Dict[str, Any]] = []
        self.download_worker: Optional[GitHubDownloadWorker] = None
        self.batch_worker: Optional[GitHubBatchDownloadWorker] = None
        self.fetch_worker: Optional[GitHubPluginsWorker] = None
        self.row_checkboxes: List[QCheckBox] = []

        self.setWindowTitle("Download Plugins & Extensions from GitHub")
        self.setMinimumSize(860, 600)
        self.resize(900, 640)
        self.setup_ui()
        self.fetch_plugins()

    def setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        header = QLabel(
            "<b>Download Plugins & Extensions from GitHub</b><br>"
            f"<span style='color: #64748b;'>Browse official extensions published on the GitHub repository releases ({self.repo}). "
            "Select individual or multiple plugins to download, install, enable, disable, or remove in batch.</span>"
        )
        layout.addWidget(header)

        self.repo_label = QLabel(f"Connecting to GitHub releases for <b>{self.repo}</b>...")
        layout.addWidget(self.repo_label)

        # Batch Selection Toolbar
        batch_bar = QHBoxLayout()
        batch_bar.setSpacing(8)

        select_all_btn = QPushButton("Select All")
        select_all_btn.clicked.connect(self.select_all_plugins)
        batch_bar.addWidget(select_all_btn)

        deselect_all_btn = QPushButton("Deselect All")
        deselect_all_btn.clicked.connect(self.deselect_all_plugins)
        batch_bar.addWidget(deselect_all_btn)

        batch_bar.addSpacing(10)

        self.batch_download_btn = QPushButton("Download & Install Selected")
        self.batch_download_btn.setStyleSheet("font-weight: bold;")
        self.batch_download_btn.clicked.connect(self.download_selected_plugins)
        batch_bar.addWidget(self.batch_download_btn)

        self.batch_enable_btn = QPushButton("Enable Selected")
        self.batch_enable_btn.clicked.connect(self.enable_selected_plugins)
        batch_bar.addWidget(self.batch_enable_btn)

        self.batch_disable_btn = QPushButton("Disable Selected")
        self.batch_disable_btn.clicked.connect(self.disable_selected_plugins)
        batch_bar.addWidget(self.batch_disable_btn)

        self.batch_uninstall_btn = QPushButton("Uninstall Selected...")
        self.batch_uninstall_btn.clicked.connect(self.uninstall_selected_plugins)
        batch_bar.addWidget(self.batch_uninstall_btn)

        batch_bar.addStretch()
        layout.addLayout(batch_bar)

        self.table = QTableWidget()
        self.table.setColumnCount(6)
        self.table.setHorizontalHeaderLabels(["Select", "Plugin", "Version", "Category", "Status", "Action"])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(5, QHeaderView.ResizeMode.Stretch)
        self.table.verticalHeader().setDefaultSectionSize(48)
        self.table.verticalHeader().setMinimumSectionSize(44)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.itemSelectionChanged.connect(self.on_selection_changed)
        self.table.cellClicked.connect(lambda row, col: self.on_selection_changed())
        layout.addWidget(self.table)

        desc_box = QGroupBox("Plugin Description")
        desc_layout = QVBoxLayout(desc_box)
        self.desc_text = QTextEdit()
        self.desc_text.setReadOnly(True)
        self.desc_text.setMinimumHeight(90)
        self.desc_text.setMaximumHeight(120)
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
        self.row_checkboxes.clear()

        for row, item in enumerate(self.catalog):
            self.table.insertRow(row)
            self.table.setRowHeight(row, 48)
            plugin_id = item["id"]
            is_installed = self.manager.is_plugin_installed(plugin_id)
            is_enabled = self.manager.is_plugin_enabled(plugin_id)

            # Column 0: Selection Checkbox
            chk = QCheckBox()
            chk.setChecked(False)
            self.row_checkboxes.append(chk)
            chk_widget = QWidget()
            chk_layout = QHBoxLayout(chk_widget)
            chk_layout.setContentsMargins(4, 2, 4, 2)
            chk_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
            chk_layout.addWidget(chk)
            self.table.setCellWidget(row, 0, chk_widget)

            # Column 1: Name Item
            name_item = QTableWidgetItem(item["name"])
            name_item.setData(Qt.ItemDataRole.UserRole, item)
            self.table.setItem(row, 1, name_item)

            # Column 2: Version
            self.table.setItem(row, 2, QTableWidgetItem(f"v{item.get('version', PROJECT_VERSION)}"))

            # Column 3: Category
            self.table.setItem(row, 3, QTableWidgetItem(str(item.get("category", "General")).capitalize()))

            # Column 4: Status
            if is_installed:
                status_text = "Installed (Enabled)" if is_enabled else "Installed (Disabled)"
            else:
                status_text = "Available"
            self.table.setItem(row, 4, QTableWidgetItem(status_text))

            # Column 5: Action Buttons
            action_widget = QWidget()
            action_layout = QHBoxLayout(action_widget)
            action_layout.setContentsMargins(6, 4, 6, 4)
            action_layout.setSpacing(8)
            action_layout.setAlignment(Qt.AlignmentFlag.AlignVCenter)

            btn_style = "QPushButton { min-height: 28px; padding: 4px 12px; }"
            if not is_installed:
                download_btn = QPushButton("Download & Install")
                download_btn.setStyleSheet("QPushButton { font-weight: bold; min-height: 28px; padding: 4px 12px; }")
                download_btn.clicked.connect(lambda _, it=item: self.download_and_install_plugin(it))
                action_layout.addWidget(download_btn)
            else:
                toggle_btn = QPushButton("Disable" if is_enabled else "Enable")
                toggle_btn.setStyleSheet(btn_style)
                toggle_btn.clicked.connect(lambda _, pid=plugin_id, cur=is_enabled: self.toggle_plugin(pid, not cur))
                action_layout.addWidget(toggle_btn)

                uninstall_btn = QPushButton("Uninstall")
                uninstall_btn.setStyleSheet(btn_style)
                uninstall_btn.clicked.connect(lambda _, pid=plugin_id, nm=item["name"]: self.uninstall_plugin(pid, nm))
                action_layout.addWidget(uninstall_btn)

            self.table.setCellWidget(row, 5, action_widget)

        if self.table.rowCount() > 0:
            self.table.selectRow(0)

    def select_all_plugins(self):
        for chk in self.row_checkboxes:
            chk.setChecked(True)
        self.table.selectAll()

    def deselect_all_plugins(self):
        for chk in self.row_checkboxes:
            chk.setChecked(False)
        self.table.clearSelection()

    def get_selected_items(self) -> List[Dict[str, Any]]:
        """Returns list of plugin items that are either checked or part of extended row selection."""
        selected_set = set()
        # Checked rows
        for row, chk in enumerate(self.row_checkboxes):
            if chk.isChecked():
                selected_set.add(row)
        # Highlighted / multi-selected rows
        for item in self.table.selectedItems():
            selected_set.add(item.row())

        result = []
        for row in sorted(selected_set):
            name_cell = self.table.item(row, 1)
            if name_cell:
                data = name_cell.data(Qt.ItemDataRole.UserRole)
                if data:
                    result.append(data)
        return result

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

        item_cell = self.table.item(row, 1)
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

    def download_selected_plugins(self):
        items = self.get_selected_items()
        uninstalled = [it for it in items if not self.manager.is_plugin_installed(it["id"])]
        if not uninstalled:
            QMessageBox.information(
                self,
                "Download Plugins",
                "Please select one or more uninstalled plugins from the list to download and install."
            )
            return

        res = QMessageBox.question(
            self,
            "Download Selected Plugins",
            f"Download and install the following {len(uninstalled)} selected plugin(s)?\n\n• " +
            "\n• ".join([it["name"] for it in uninstalled]),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.Yes,
        )
        if res != QMessageBox.StandardButton.Yes:
            return

        self.progress_bar.setValue(0)
        self.progress_bar.setVisible(True)
        self.progress_label.setText(f"Downloading {len(uninstalled)} plugins...")
        self.progress_label.setVisible(True)

        self.batch_worker = GitHubBatchDownloadWorker(uninstalled, self.manager, enable_after=True, parent=self)
        self.batch_worker.progress.connect(self.on_download_progress)
        self.batch_worker.finished.connect(self.on_batch_download_finished)
        self.batch_worker.start()

    def on_batch_download_finished(self, succeeded: int, failed: int, errors: list):
        self.progress_bar.setVisible(False)
        self.progress_label.setVisible(False)
        self.render_table()

        if self.manager.app and hasattr(self.manager.app, "refresh_plugin_menus"):
            self.manager.app.refresh_plugin_menus()

        if failed == 0:
            QMessageBox.information(
                self,
                "Batch Installation Complete",
                f"Successfully downloaded and installed {succeeded} plugin(s)!"
            )
        else:
            err_msg = "\n".join(errors)
            QMessageBox.warning(
                self,
                "Batch Installation Results",
                f"Installed {succeeded} plugin(s).\n{failed} plugin(s) encountered issues:\n\n{err_msg}"
            )

    def enable_selected_plugins(self):
        items = self.get_selected_items()
        installed = [it for it in items if self.manager.is_plugin_installed(it["id"])]
        if not installed:
            QMessageBox.information(self, "Enable Plugins", "Please select one or more installed plugins to enable.")
            return

        count = 0
        for it in installed:
            pid = it["id"]
            self.manager.set_plugin_enabled(pid, True)
            self.manager.load_plugin(pid)
            count += 1

        if self.manager.app and hasattr(self.manager.app, "refresh_plugin_menus"):
            self.manager.app.refresh_plugin_menus()
        self.render_table()
        QMessageBox.information(self, "Plugins Enabled", f"Enabled {count} selected plugin(s).")

    def disable_selected_plugins(self):
        items = self.get_selected_items()
        installed = [it for it in items if self.manager.is_plugin_installed(it["id"])]
        if not installed:
            QMessageBox.information(self, "Disable Plugins", "Please select one or more installed plugins to disable.")
            return

        count = 0
        for it in installed:
            pid = it["id"]
            self.manager.set_plugin_enabled(pid, False)
            self.manager.unload_plugin(pid)
            count += 1

        if self.manager.app and hasattr(self.manager.app, "refresh_plugin_menus"):
            self.manager.app.refresh_plugin_menus()
        self.render_table()
        QMessageBox.information(self, "Plugins Disabled", f"Disabled {count} selected plugin(s).")

    def uninstall_selected_plugins(self):
        items = self.get_selected_items()
        installed = [it for it in items if self.manager.is_plugin_installed(it["id"])]
        if not installed:
            QMessageBox.information(self, "Uninstall Plugins", "Please select one or more installed plugins to uninstall.")
            return

        names = "\n• ".join([it["name"] for it in installed])
        res = QMessageBox.question(
            self,
            "Uninstall Selected Plugins",
            f"Are you sure you want to uninstall and remove {len(installed)} selected plugin(s)?\n\n• {names}\n\n"
            "This will remove the plugin files and disable all related features.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if res == QMessageBox.StandardButton.Yes:
            for it in installed:
                self.manager.uninstall_plugin(it["id"])
            self.render_table()
            QMessageBox.information(self, "Plugins Removed", f"Successfully uninstalled {len(installed)} plugin(s).")

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
    """GUI Dialog for viewing, managing, enabling, installing, and removing plugins with multi-selection."""

    def __init__(self, manager: PluginManager, parent: Any = None):
        super().__init__(parent)
        self.manager = manager
        self.setWindowTitle("Manage Plugins & Add-ons")
        self.setMinimumSize(840, 580)
        self.resize(880, 620)
        self.setup_ui()
        self.refresh_list()

    def setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        header = QLabel(
            "<b>Installed Plugins & Extensions</b><br>"
            "<span style='color: #64748b;'>Enable, disable, export, or install optional publishing destinations and workflow extensions in batch.</span>"
        )
        layout.addWidget(header)

        # Batch Selection Toolbar
        batch_bar = QHBoxLayout()
        batch_bar.setSpacing(8)

        select_all_btn = QPushButton("Select All")
        select_all_btn.clicked.connect(self.select_all_plugins)
        batch_bar.addWidget(select_all_btn)

        deselect_all_btn = QPushButton("Deselect All")
        deselect_all_btn.clicked.connect(self.deselect_all_plugins)
        batch_bar.addWidget(deselect_all_btn)

        batch_bar.addSpacing(10)

        self.batch_enable_btn = QPushButton("Enable Selected")
        self.batch_enable_btn.clicked.connect(self.enable_selected_plugins)
        batch_bar.addWidget(self.batch_enable_btn)

        self.batch_disable_btn = QPushButton("Disable Selected")
        self.batch_disable_btn.clicked.connect(self.disable_selected_plugins)
        batch_bar.addWidget(self.batch_disable_btn)

        self.batch_uninstall_btn = QPushButton("Uninstall Selected...")
        self.batch_uninstall_btn.clicked.connect(self.uninstall_selected_plugins)
        batch_bar.addWidget(self.batch_uninstall_btn)

        self.batch_export_btn = QPushButton("Export Selected...")
        self.batch_export_btn.clicked.connect(self.export_selected_plugins)
        batch_bar.addWidget(self.batch_export_btn)

        batch_bar.addStretch()
        layout.addLayout(batch_bar)

        self.table = QTableWidget()
        self.table.setColumnCount(5)
        self.table.setHorizontalHeaderLabels(["Enabled", "Name", "Version", "Category", "Author"])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.Stretch)
        self.table.verticalHeader().setDefaultSectionSize(42)
        self.table.verticalHeader().setMinimumSectionSize(38)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.itemSelectionChanged.connect(self.on_selection_changed)
        self.table.cellClicked.connect(lambda row, col: self.on_selection_changed())
        layout.addWidget(self.table)

        self.empty_label = QLabel(
            "<i>No plugins are currently installed. Use <b>Download from GitHub...</b> to explore and install official add-ons, or click <b>Install Addons...</b> to select local files.</i>"
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
        self.desc_text.setMinimumHeight(90)
        self.desc_text.setMaximumHeight(120)
        desc_layout.addWidget(self.desc_text)
        layout.addWidget(desc_box)

        # Action bar
        btn_layout = QHBoxLayout()

        download_github_btn = QPushButton("Download from GitHub...")
        download_github_btn.setStyleSheet("font-weight: bold;")
        download_github_btn.clicked.connect(self.on_download_github)
        btn_layout.addWidget(download_github_btn)

        install_btn = QPushButton("Install Addon(s) (.rtvs-addon)...")
        install_btn.setToolTip("Select one or multiple add-on packages to install simultaneously.")
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

    def on_download_github(self):
        dlg = GitHubPluginsDialog(self.manager, self)
        dlg.exec()
        self.refresh_list()

    def select_all_plugins(self):
        self.table.selectAll()

    def deselect_all_plugins(self):
        self.table.clearSelection()

    def get_selected_plugin_ids(self) -> List[str]:
        """Returns the list of plugin_ids selected via multi-row selection."""
        selected_rows = set()
        for item in self.table.selectedItems():
            selected_rows.add(item.row())

        result = []
        for row in sorted(selected_rows):
            name_cell = self.table.item(row, 1)
            if name_cell:
                pid = name_cell.data(Qt.ItemDataRole.UserRole)
                if pid:
                    result.append(pid)
        return result

    def refresh_list(self):
        self.manager.discover_plugins()
        self.table.setRowCount(0)
        row = 0
        for plugin_id, manifest in sorted(self.manager.manifests.items(), key=lambda x: x[1].name):
            self.table.insertRow(row)
            self.table.setRowHeight(row, 42)

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
        self.batch_enable_btn.setEnabled(not is_empty)
        self.batch_disable_btn.setEnabled(not is_empty)
        self.batch_uninstall_btn.setEnabled(not is_empty)
        self.batch_export_btn.setEnabled(not is_empty)

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
            return

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

    def enable_selected_plugins(self):
        selected_ids = self.get_selected_plugin_ids()
        if not selected_ids:
            QMessageBox.information(self, "Enable Plugins", "Please select one or more plugins from the list.")
            return

        for pid in selected_ids:
            self.manager.set_plugin_enabled(pid, True)
            self.manager.load_plugin(pid)

        if self.manager.app and hasattr(self.manager.app, "refresh_plugin_menus"):
            self.manager.app.refresh_plugin_menus()
        self.refresh_list()
        QMessageBox.information(self, "Plugins Enabled", f"Enabled {len(selected_ids)} selected plugin(s).")

    def disable_selected_plugins(self):
        selected_ids = self.get_selected_plugin_ids()
        if not selected_ids:
            QMessageBox.information(self, "Disable Plugins", "Please select one or more plugins from the list.")
            return

        for pid in selected_ids:
            self.manager.set_plugin_enabled(pid, False)
            self.manager.unload_plugin(pid)

        if self.manager.app and hasattr(self.manager.app, "refresh_plugin_menus"):
            self.manager.app.refresh_plugin_menus()
        self.refresh_list()
        QMessageBox.information(self, "Plugins Disabled", f"Disabled {len(selected_ids)} selected plugin(s).")

    def uninstall_selected_plugins(self):
        selected_ids = self.get_selected_plugin_ids()
        if not selected_ids:
            QMessageBox.information(self, "Uninstall Plugins", "Please select one or more plugins from the list to uninstall.")
            return

        names = []
        for pid in selected_ids:
            m = self.manager.manifests.get(pid)
            names.append(m.name if m else pid)

        res = QMessageBox.question(
            self,
            "Uninstall Plugins",
            f"Are you sure you want to uninstall and remove {len(selected_ids)} plugin(s)?\n\n• " +
            "\n• ".join(names) +
            "\n\nThis will remove the plugin files and disable all related features.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if res == QMessageBox.StandardButton.Yes:
            for pid in selected_ids:
                self.manager.uninstall_plugin(pid)
            self.refresh_list()
            QMessageBox.information(self, "Plugins Removed", f"Successfully uninstalled {len(selected_ids)} plugin(s).")

    def export_selected_plugins(self):
        selected_ids = self.get_selected_plugin_ids()
        if not selected_ids:
            QMessageBox.information(self, "Export Addon", "Please select one or more plugins from the list to export.")
            return

        if len(selected_ids) == 1:
            pid = selected_ids[0]
            folder = self.manager.plugin_paths.get(pid)
            if not folder or not Path(folder).is_dir():
                QMessageBox.warning(self, "Export Addon", f"Plugin directory for '{pid}' not found.")
                return

            default_fn = f"{pid}.rtvs-addon"
            fn, _ = QFileDialog.getSaveFileName(
                self,
                f"Export Plugin Addon ({pid})",
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
        else:
            # Batch export multiple plugins into a destination directory
            dest_dir = QFileDialog.getExistingDirectory(
                self,
                f"Select Destination Directory for {len(selected_ids)} Add-on Packages",
                str(Path.home())
            )
            if not dest_dir:
                return

            out_path = Path(dest_dir)
            exported = 0
            for pid in selected_ids:
                folder = self.manager.plugin_paths.get(pid)
                if folder and Path(folder).is_dir():
                    target_file = out_path / f"{pid}.rtvs-addon"
                    if self.manager.package_addon(folder, target_file):
                        exported += 1

            QMessageBox.information(
                self,
                "Export Complete",
                f"Successfully exported {exported} of {len(selected_ids)} add-on package(s) to:\n{dest_dir}"
            )

    def on_install_addon(self):
        files, _ = QFileDialog.getOpenFileNames(
            self,
            "Install Plugin Add-on Package(s)",
            "",
            "RTVS Add-on Packages (*.rtvs-addon *.zip);;All Files (*.*)",
        )
        if not files:
            return

        installed_count = 0
        for fn in files:
            try:
                ok = self.manager.install_addon(fn, enable=False)
                if ok:
                    installed_count += 1
            except Exception as exc:
                print(f"[PLUGINS] Failed to install {fn}: {exc}")

        if installed_count > 0:
            res = QMessageBox.question(
                self,
                "Addons Installed",
                f"Successfully installed {installed_count} plugin package(s)!\n\nWould you like to enable them now?",
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
            QMessageBox.warning(self, "Installation Failed", "Could not install plugin packages. Make sure each package contains a valid manifest.json.")

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
