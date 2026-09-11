import sys
import os
import json
import shutil
import logging
import subprocess
from pathlib import Path

logger = logging.getLogger(__name__)

UV_VERSION = "0.12.12"
UV_URLS = {
    "win32-x86_64": f"https://github.com/astral-sh/uv/releases/download/{UV_VERSION}/uv-x86_64-pc-windows-msvc.zip",
    "win32-arm64": f"https://github.com/astral-sh/uv/releases/download/{UV_VERSION}/uv-aarch64-pc-windows-msvc.zip",
    "darwin-x86_64": f"https://github.com/astral-sh/uv/releases/download/{UV_VERSION}/uv-x86_64-apple-darwin.tar.gz",
    "darwin-arm64": f"https://github.com/astral-sh/uv/releases/download/{UV_VERSION}/uv-aarch64-apple-darwin.tar.gz",
    "linux-x86_64": f"https://github.com/astral-sh/uv/releases/download/{UV_VERSION}/uv-x86_64-unknown-linux-gnu.tar.gz",
    "linux-aarch64": f"https://github.com/astral-sh/uv/releases/download/{UV_VERSION}/uv-aarch64-unknown-linux-gnu.tar.gz",
}

STANDALONE_PYTHON_TAG = "20250228"
STANDALONE_PYTHON_VERSION = "3.12.9"
STANDALONE_PYTHON_URLS = {
    "win32-x86_64": f"https://github.com/astral-sh/python-build-standalone/releases/download/{STANDALONE_PYTHON_TAG}/cpython-{STANDALONE_PYTHON_VERSION}%2B{STANDALONE_PYTHON_TAG}-x86_64-pc-windows-msvc-install_only.tar.gz",
    "win32-arm64": f"https://github.com/astral-sh/python-build-standalone/releases/download/{STANDALONE_PYTHON_TAG}/cpython-{STANDALONE_PYTHON_VERSION}%2B{STANDALONE_PYTHON_TAG}-aarch64-pc-windows-msvc-install_only.tar.gz",
    "darwin-x86_64": f"https://github.com/astral-sh/python-build-standalone/releases/download/{STANDALONE_PYTHON_TAG}/cpython-{STANDALONE_PYTHON_VERSION}%2B{STANDALONE_PYTHON_TAG}-x86_64-apple-darwin-install_only.tar.gz",
    "darwin-arm64": f"https://github.com/astral-sh/python-build-standalone/releases/download/{STANDALONE_PYTHON_TAG}/cpython-{STANDALONE_PYTHON_VERSION}%2B{STANDALONE_PYTHON_TAG}-aarch64-apple-darwin-install_only.tar.gz",
    "linux-x86_64": f"https://github.com/astral-sh/python-build-standalone/releases/download/{STANDALONE_PYTHON_TAG}/cpython-{STANDALONE_PYTHON_VERSION}%2B{STANDALONE_PYTHON_TAG}-x86_64-unknown-linux-gnu-install_only.tar.gz",
    "linux-aarch64": f"https://github.com/astral-sh/python-build-standalone/releases/download/{STANDALONE_PYTHON_TAG}/cpython-{STANDALONE_PYTHON_VERSION}%2B{STANDALONE_PYTHON_TAG}-aarch64-unknown-linux-gnu-install_only.tar.gz",
}

# Track active subprocesses spawned by feature environments or external runners
_ACTIVE_SUBPROCESSES = set()


def register_process(proc: subprocess.Popen):
    """Register an active Popen process for teardown monitoring."""
    _ACTIVE_SUBPROCESSES.add(proc)


def unregister_process(proc: subprocess.Popen):
    """Remove completed process from tracking."""
    _ACTIVE_SUBPROCESSES.discard(proc)


def kill_all_subprocesses():
    """Force terminate any lingering isolated worker subprocesses."""
    for proc in list(_ACTIVE_SUBPROCESSES):
        if proc.poll() is None:  # Process is still running
            try:
                proc.terminate()
                proc.wait(timeout=1.0)
            except (subprocess.TimeoutExpired, OSError):
                try:
                    proc.kill()
                except OSError:
                    pass
    _ACTIVE_SUBPROCESSES.clear()


# Feature configuration matrix with explicit versioning and python targets
ENV_CONFIGS = {
    "diarize": {
        "version": "1.0.2",
        "python_version": "3.12",
        "packages": [
            "numpy<2.0.0",
            "scipy",
            "soundfile",
            "torch>=2.0.0,<2.4.0",
            "torchaudio",
            "diarize==0.1.2"
        ]
    },
    "transcribe": {
        "version": "1.0.0",
        "python_version": "3.12",
        "packages": [
            "faster-whisper",
            "ctranslate2",
            "onnxruntime"
        ]
    },
    "translate": {
        "version": "2.8",
        "python_version": "3.12",
        "extra_index_url": "https://download.pytorch.org/whl/cpu",
        "packages": [
            "numpy>=1.26.0,<2.0.0",
            "psutil>=5.9,<7",
            "transformers>=4.40,<5",
            "huggingface-hub>=0.23,<2",
            "ctranslate2>=4.0,<5",
            "sentencepiece>=0.2,<1",
            "sacremoses>=0.0.53",
            "torch>=2.0.0,<2.4.0"
        ]
    },
    "gpu_transcribe": {
        # Optional, user-triggered environment (Settings > Processing > GPU
        # Acceleration). Not installed by default and not part of the base
        # installer -- this is the whole point of keeping the base install
        # CPU-only and small. Built from the CUDA wheel index rather than
        # plain PyPI, which defaults to CPU-only torch on some platforms.
        "version": "1.0.0",
        "python_version": "3.12",
        "extra_index_url": "https://download.pytorch.org/whl/cu121",
        "packages": [
            "numpy<2.0.0",
            "scipy",
            "soundfile",
            "torch>=2.0.0,<2.4.0",
            "torchaudio",
            "diarize==0.1.2",
            "faster-whisper",
            "ctranslate2",
        ]
    }
}


def detect_nvidia_gpu() -> bool:
    """Best-effort check for a usable NVIDIA GPU on this machine, so the
    Settings UI can warn before a large download that's unlikely to help."""
    nvidia_smi = shutil.which("nvidia-smi")
    if not nvidia_smi:
        return False
    try:
        creationflags = subprocess.CREATE_NO_WINDOW if sys.platform == 'win32' else 0
        result = subprocess.run(
            [nvidia_smi, "-L"], capture_output=True, text=True, timeout=5,
            creationflags=creationflags,
        )
        return result.returncode == 0 and "GPU" in result.stdout
    except Exception:
        return False



class RuntimeManager:
    """Manages isolated Python virtual environments for ML features with auto-upgrade support."""

    def __init__(self, base_dir: Path = None):
        if base_dir is None:
            if sys.platform == "win32":
                root = os.environ.get("LOCALAPPDATA") or os.environ.get("APPDATA")
                base_dir = (Path(root) if root else Path.home() / "AppData" / "Local") / "RadioTVStorySegmenter"
            elif sys.platform == "darwin":
                base_dir = Path.home() / "Library" / "Application Support" / "RadioTVStorySegmenter"
            else:
                base_dir = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share")) / "RadioTVStorySegmenter"
        self.runtimes_dir = Path(base_dir) / "runtimes"
        self.runtimes_dir.mkdir(parents=True, exist_ok=True)
        self._last_error = ""

    def get_last_error(self) -> str:
        """Returns the most recent detailed error message from environment setup or execution."""
        return self._last_error

    def get_env_dir(self, feature_name: str) -> Path:
        return self.runtimes_dir / f"{feature_name}_env"

    def get_manifest_path(self, feature_name: str) -> Path:
        return self.get_env_dir(feature_name) / "runtime_manifest.json"

    def _get_raw_executable(self, feature_name: str) -> Path:
        env_dir = self.get_env_dir(feature_name)
        if sys.platform == "win32":
            return env_dir / "Scripts" / "python.exe"
        return env_dir / "bin" / "python"

    def get_executable(self, feature_name: str) -> str:
        """Returns the path to the python executable inside the target feature environment if valid."""
        exe = self._get_raw_executable(feature_name)
        if exe.exists() and self.is_env_up_to_date(feature_name):
            return str(exe)
        # Fallback to host interpreter if feature env is not ready
        return sys.executable

    def resolve_target_python(self, target_version: str = "3.12") -> str:
        """Finds a matching Python binary on the host system for building the environment."""
        curr_ver = f"{sys.version_info.major}.{sys.version_info.minor}"
        # A PyInstaller executable is not a usable `python -m venv` interpreter.
        # Only reuse sys.executable when running from a normal Python installation.
        if curr_ver == target_version and not getattr(sys, "frozen", False):
            return sys.executable

        # Check Windows Python Launcher
        if sys.platform == "win32":
            py_launcher = shutil.which("py")
            if py_launcher:
                try:
                    creationflags = subprocess.CREATE_NO_WINDOW if sys.platform == 'win32' else 0
                    res = subprocess.run(
                        [py_launcher, f"-{target_version}", "-c", "import sys; print(sys.executable)"],
                        capture_output=True, text=True, check=True,
                        creationflags=creationflags
                    )
                    exe = res.stdout.strip()
                    if Path(exe).exists():
                        return exe
                except Exception:
                    pass

        # Standard binary search on PATH
        target_exe = shutil.which(f"python{target_version}") or shutil.which(f"python{target_version}.exe")
        if target_exe:
            return target_exe

        # System fallback
        logger.warning(f"Target Python {target_version} not found on the host.")
        return ""

    def bundled_uv_path(self) -> Path | None:
        """Return the uv binary shipped with the application across Windows, macOS, and Linux, or None if unavailable."""
        name = "uv.exe" if sys.platform == "win32" else "uv"
        candidates = [
            Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent)) / "optional_runtime" / name,
            Path(sys.executable).resolve().parent / "optional_runtime" / name,
            Path(__file__).resolve().parent / "optional_runtime" / name,
            Path.cwd() / "optional_runtime" / name,
            self.runtimes_dir / "bin" / name,
            self.runtimes_dir / name,
        ]
        for candidate in candidates:
            if candidate.is_file():
                if sys.platform != "win32":
                    try:
                        candidate.chmod(candidate.stat().st_mode | 0o755)
                    except Exception:
                        pass
                return candidate

        # Fallback to system-installed uv if available
        system_uv = shutil.which("uv")
        if system_uv:
            p = Path(system_uv)
            if p.is_file():
                return p

        return None

    def ensure_uv(self, progress_cb=None) -> Path | None:
        """Locates bundled or system uv, or automatically downloads standalone uv for the active OS/arch."""
        uv = self.bundled_uv_path()
        if uv and uv.is_file():
            return uv

        import platform
        import urllib.request
        import zipfile
        import tarfile

        machine = (os.environ.get("PROCESSOR_ARCHITECTURE", "") or platform.machine()).lower()
        is_arm = "arm" in machine or "aarch64" in machine
        if sys.platform == "win32":
            arch_key = "win32-arm64" if is_arm else "win32-x86_64"
        elif sys.platform == "darwin":
            arch_key = "darwin-arm64" if is_arm else "darwin-x86_64"
        else:
            arch_key = "linux-aarch64" if is_arm else "linux-x86_64"

        url = UV_URLS.get(arch_key)
        if not url:
            return None

        bin_dir = self.runtimes_dir / "bin"
        bin_dir.mkdir(parents=True, exist_ok=True)
        binary_name = "uv.exe" if sys.platform == "win32" else "uv"
        uv_dest = bin_dir / binary_name
        if uv_dest.is_file():
            if sys.platform != "win32":
                try:
                    uv_dest.chmod(0o755)
                except Exception:
                    pass
            return uv_dest

        archive_ext = ".zip" if url.endswith(".zip") else ".tar.gz"
        archive_path = bin_dir / f"uv_download{archive_ext}"
        try:
            if progress_cb:
                progress_cb(f"Downloading isolated runtime manager (uv {UV_VERSION})…")
            urllib.request.urlretrieve(url, archive_path)
            if archive_ext == ".zip":
                with zipfile.ZipFile(archive_path) as zf:
                    member = next((n for n in zf.namelist() if n.lower().endswith("/" + binary_name) or n.lower() == binary_name), None)
                    if member:
                        with zf.open(member) as src, uv_dest.open("wb") as dst:
                            shutil.copyfileobj(src, dst)
            else:
                with tarfile.open(archive_path, "r:gz") as tf:
                    member = next((m for m in tf.getmembers() if m.name.endswith("/" + binary_name) or m.name == binary_name), None)
                    if member:
                        extracted = tf.extractfile(member)
                        if extracted:
                            with extracted as src, uv_dest.open("wb") as dst:
                                shutil.copyfileobj(src, dst)

            if uv_dest.is_file():
                if sys.platform != "win32":
                    try:
                        uv_dest.chmod(0o755)
                    except Exception:
                        pass
                return uv_dest
        except Exception as exc:
            logger.warning("Could not auto-download uv: %s", exc)
        finally:
            archive_path.unlink(missing_ok=True)

        return None

    def _get_uv_env(self) -> dict:
        """Constructs environment dictionary with managed Python directory for uv."""
        python_dir = self.runtimes_dir / "python"
        cache_dir = self.runtimes_dir / "cache"
        data_dir = self.runtimes_dir / "data"
        python_dir.mkdir(parents=True, exist_ok=True)
        cache_dir.mkdir(parents=True, exist_ok=True)
        data_dir.mkdir(parents=True, exist_ok=True)
        env = os.environ.copy()
        env["UV_PYTHON_INSTALL_DIR"] = str(python_dir)
        env["UV_CACHE_DIR"] = str(cache_dir)
        env["UV_DATA_DIR"] = str(data_dir)
        env["UV_PYTHON_PREFERENCE"] = "only-managed"
        env["UV_LINK_MODE"] = "copy"
        return env

    def _find_extracted_python(self, target_version: str = "3.12") -> str:
        """Scan managed python directory for a working extracted python binary."""
        python_dir = self.runtimes_dir / "python"
        if not python_dir.exists():
            return ""

        target_name = "python.exe" if sys.platform == "win32" else "python"
        candidates = []
        try:
            for p in python_dir.rglob(target_name):
                if p.is_file():
                    p_parts = [part.lower() for part in p.parts]
                    if "scripts" in p_parts or "_env" in str(p):
                        continue
                    candidates.append(p)
        except Exception:
            pass

        creationflags = subprocess.CREATE_NO_WINDOW if sys.platform == 'win32' else 0
        for cand in sorted(candidates, key=lambda x: len(str(x)), reverse=True):
            try:
                res = subprocess.run(
                    [str(cand), "-c", "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')"],
                    capture_output=True, text=True, timeout=5, creationflags=creationflags
                )
                if res.returncode == 0 and res.stdout.strip() == target_version:
                    return str(cand)
            except Exception:
                continue
        return ""

    def _download_standalone_python(self, target_version: str = "3.12", progress_cb=None) -> str:
        """Directly download and extract standalone CPython distribution without symlinks."""
        import platform
        import urllib.request
        import tarfile

        machine = (os.environ.get("PROCESSOR_ARCHITECTURE", "") or platform.machine()).lower()
        is_arm = "arm" in machine or "aarch64" in machine
        if sys.platform == "win32":
            arch_key = "win32-arm64" if is_arm else "win32-x86_64"
        elif sys.platform == "darwin":
            arch_key = "darwin-arm64" if is_arm else "darwin-x86_64"
        else:
            arch_key = "linux-aarch64" if is_arm else "linux-x86_64"

        url = STANDALONE_PYTHON_URLS.get(arch_key)
        if not url:
            return ""

        dest_dir = self.runtimes_dir / "python" / f"cpython-{target_version}-standalone"
        dest_dir.mkdir(parents=True, exist_ok=True)
        archive_path = self.runtimes_dir / "python_standalone.tar.gz"

        try:
            if progress_cb:
                progress_cb(f"Downloading standalone Python {target_version}…")
            urllib.request.urlretrieve(url, archive_path)
            if progress_cb:
                progress_cb(f"Extracting standalone Python {target_version}…")
            with tarfile.open(archive_path, "r:*") as tar:
                tar.extractall(path=dest_dir)

            return self._find_extracted_python(target_version)
        except Exception as exc:
            logger.warning("Could not download standalone Python: %s", exc)
            return ""
        finally:
            archive_path.unlink(missing_ok=True)

    def ensure_managed_python(self, target_version: str = "3.12", progress_cb=None) -> str:
        """Provision a private Python runtime with uv when the host has no matching Python.

        This is used for optional and plugin feature environments. The base installer remains
        independent of system Python.
        """
        # 1. First check if a matching Python is already downloaded/extracted on disk
        existing = self._find_extracted_python(target_version)
        if existing:
            return existing

        uv = self.ensure_uv(progress_cb=progress_cb)
        env = self._get_uv_env()
        creationflags = subprocess.CREATE_NO_WINDOW if sys.platform == 'win32' else 0

        if uv and uv.is_file():
            try:
                if progress_cb:
                    progress_cb(f"Preparing private Python {target_version} runtime…")
                # Run uv python install with copy link mode
                res = subprocess.run([str(uv), "python", "install", target_version],
                                     env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                     text=True, creationflags=creationflags)

                # Check if Python is now extracted (recovers even if junction/minor link creation had an untrusted mount point error)
                found = self._find_extracted_python(target_version)
                if found:
                    return found

                # Also try uv python find
                res_find = subprocess.run([str(uv), "python", "find", target_version],
                                          env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                          text=True, creationflags=creationflags)
                exe = res_find.stdout.strip().splitlines()[-1] if res_find.stdout.strip() else ""
                if exe and Path(exe).exists():
                    return exe

                if res.returncode != 0:
                    err = (res.stderr or res.stdout or "").strip()
                    logger.warning("uv python install reported: %s", err)
            except Exception as exc:
                logger.warning("uv python install error: %s", exc)

        # 2. Re-scan extracted python directory
        found = self._find_extracted_python(target_version)
        if found:
            return found

        # 3. Direct standalone download fallback (guaranteed clean extract without symlinks/junctions)
        fallback_exe = self._download_standalone_python(target_version, progress_cb=progress_cb)
        if fallback_exe:
            return fallback_exe

        self._last_error = f"Could not provision managed Python {target_version} runtime."
        logger.error(self._last_error)
        if progress_cb:
            progress_cb(self._last_error)
        return ""

    def remove_environment(self, feature_name: str) -> bool:
        """Remove an isolated feature environment without touching its models."""
        env_dir = self.get_env_dir(feature_name)
        if not env_dir.exists():
            return True
        import stat
        import time

        def _handle_remove_readonly(func, path, exc_info):
            try:
                os.chmod(path, stat.S_IWRITE)
                func(path)
            except Exception:
                pass

        try:
            shutil.rmtree(env_dir, onerror=_handle_remove_readonly)
            if not env_dir.exists():
                return True
        except Exception as exc:
            logger.warning("First attempt to remove runtime %s failed: %s; retrying", feature_name, exc)

        time.sleep(0.5)
        try:
            # On Windows, if files are temporarily locked, rename to tombstone directory
            # so the primary path is freed immediately for environment recreation
            tombstone = env_dir.with_name(f"{env_dir.name}_del_{int(time.time())}")
            try:
                env_dir.rename(tombstone)
                try:
                    shutil.rmtree(tombstone, onerror=_handle_remove_readonly)
                except Exception:
                    pass
                return True
            except Exception:
                shutil.rmtree(env_dir, onerror=_handle_remove_readonly)
                return not env_dir.exists()
        except Exception as e2:
            logger.error("Could not remove runtime %s: %s", feature_name, e2)
            return False

    def get_runtime_executable(self, feature_name: str, progress_cb=None) -> str:
        """Ensure and return the executable for an isolated feature runtime."""
        if not self.ensure_environment(feature_name, progress_cb=progress_cb):
            return ""
        return str(self._get_raw_executable(feature_name))

    def get_plugin_requirements(self, feature_name: str, plugin_dir: Path = None) -> list:
        """Read requirements-runtime.txt from plugin directory if available, fallback to ENV_CONFIGS."""
        req_files = []
        if plugin_dir:
            req_files.append(Path(plugin_dir) / "requirements-runtime.txt")
        # Search in common plugin locations
        search_dirs = [
            Path(__file__).resolve().parent / "plugins",
            self.runtimes_dir.parent / "plugins",
        ]
        for base in search_dirs:
            req_files.append(base / feature_name / "requirements-runtime.txt")
            if feature_name == "translate":
                req_files.append(base / "translation" / "requirements-runtime.txt")

        for req_file in req_files:
            if req_file.is_file():
                try:
                    packages = []
                    with open(req_file, "r", encoding="utf-8") as f:
                        for line in f:
                            line = line.strip()
                            if line and not line.startswith("#"):
                                packages.append(line)
                    if packages:
                        return packages
                except Exception as exc:
                    logger.warning("Could not read %s: %s", req_file, exc)

        return ENV_CONFIGS.get(feature_name, {}).get("packages", [])

    def is_env_up_to_date(self, feature_name: str) -> bool:
        """Verifies if environment exists and matches current config version and specs."""
        manifest_path = self.get_manifest_path(feature_name)
        if not manifest_path.exists():
            return False

        try:
            with open(manifest_path, "r", encoding="utf-8") as f:
                data = json.load(f)

            target_config = ENV_CONFIGS.get(feature_name, {})
            target_ver = target_config.get("version", "2.8")
            target_py = target_config.get("python_version", "3.12")
            if data.get("config_version") != target_ver or data.get("target_python") != target_py:
                return False

            raw_exe = self._get_raw_executable(feature_name)
            if not raw_exe.exists():
                return False

            return True
        except Exception as e:
            logger.warning(f"Failed to read runtime manifest for {feature_name}: {e}")
            return False

    def write_manifest(self, feature_name: str, python_used: str, packages: list = None):
        """Writes configuration metadata upon successful environment creation."""
        manifest_path = self.get_manifest_path(feature_name)
        config = ENV_CONFIGS.get(feature_name, {})
        manifest_data = {
            "config_version": config.get("version", "2.8"),
            "target_python": config.get("python_version", "3.12"),
            "resolved_python_binary": python_used,
            "packages": packages if packages is not None else config.get("packages", [])
        }
        with open(manifest_path, "w", encoding="utf-8") as f:
            json.dump(manifest_data, f, indent=2)

    def ensure_environment(self, feature_name: str, force_rebuild: bool = False, progress_cb=None, plugin_dir: Path = None) -> bool:
        """Creates or upgrades an isolated feature environment."""
        self._last_error = ""
        if feature_name not in ENV_CONFIGS and not plugin_dir:
            self._last_error = f"Unknown feature environment: {feature_name}"
            logger.error(self._last_error)
            return False

        if not force_rebuild and self.is_env_up_to_date(feature_name):
            if progress_cb:
                progress_cb(f"Runtime '{feature_name}' is ready and up to date.")
            return True

        env_dir = self.get_env_dir(feature_name)
        config = ENV_CONFIGS.get(feature_name, {})
        target_ver = config.get("python_version", "3.12")
        python_binary = self.resolve_target_python(target_ver)
        if not python_binary:
            python_binary = self.ensure_managed_python(target_ver, progress_cb=progress_cb)
        if not python_binary:
            msg = f"A compatible Python {target_ver} runtime could not be located or provisioned for '{feature_name}'."
            self._last_error = self._last_error or msg
            logger.error(msg)
            if progress_cb:
                progress_cb(msg)
            return False

        if env_dir.exists():
            if progress_cb:
                progress_cb(f"Upgrading runtime '{feature_name}' (removing outdated environment)...")
            if not self.remove_environment(feature_name):
                self._last_error = f"Cannot recreate runtime '{feature_name}' because the existing environment directory at {env_dir} is locked by another process."
                logger.error(self._last_error)
                if progress_cb:
                    progress_cb(self._last_error)
                return False

        if progress_cb:
            progress_cb(f"Creating environment for '{feature_name}' using {python_binary}...")

        packages = self.get_plugin_requirements(feature_name, plugin_dir=plugin_dir)
        extra_index_url = config.get("extra_index_url")
        if not extra_index_url and feature_name == "translate":
            extra_index_url = "https://download.pytorch.org/whl/cpu"

        uv = self.ensure_uv(progress_cb=progress_cb)
        uv_env = self._get_uv_env()
        creationflags = subprocess.CREATE_NO_WINDOW if sys.platform == 'win32' else 0

        try:
            if uv and uv.is_file():
                # uv creates a venv without requiring pip to be bundled in the managed Python.
                res_venv = subprocess.run(
                    [str(uv), "venv", "--python", python_binary, "--link-mode", "copy", str(env_dir)],
                    check=True, env=uv_env, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                    text=True, creationflags=creationflags
                )
                env_py = str(self._get_raw_executable(feature_name))
                if progress_cb:
                    progress_cb(f"Installing dependencies for '{feature_name}'…")
                cmd_pip = [str(uv), "pip", "install", "--python", env_py, "--link-mode", "copy", "--no-cache", "--upgrade"]
                if extra_index_url:
                    cmd_pip += ["--extra-index-url", extra_index_url]
                cmd_pip += packages
                subprocess.run(
                    cmd_pip, check=True, env=uv_env, stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE, text=True, creationflags=creationflags
                )
            else:
                subprocess.run(
                    [python_binary, "-m", "venv", str(env_dir)],
                    check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                    text=True, creationflags=creationflags
                )
                env_py = str(self._get_raw_executable(feature_name))
                if progress_cb:
                    progress_cb(f"Installing dependencies for '{feature_name}'…")
                cmd_pip = [env_py, "-m", "pip", "install", "--no-cache-dir", "--upgrade"]
                if extra_index_url:
                    cmd_pip += ["--extra-index-url", extra_index_url]
                cmd_pip += packages
                subprocess.run(
                    cmd_pip, check=True, stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE, text=True, creationflags=creationflags
                )

            # Record manifest for future version checks
            self.write_manifest(feature_name, python_binary, packages=packages)

            if progress_cb:
                progress_cb(f"Runtime '{feature_name}' setup complete.")
            return True

        except subprocess.CalledProcessError as cpe:
            err_details = (cpe.stderr or cpe.stdout or str(cpe)).strip()
            self._last_error = f"Installation command failed (exit code {cpe.returncode}):\n{err_details}"
            logger.error(f"Failed to prepare environment '{feature_name}': {self._last_error}")
            if progress_cb:
                progress_cb(f"Error setting up '{feature_name}': {self._last_error}")
            self.remove_environment(feature_name)
            return False
        except Exception as e:
            self._last_error = str(e)
            logger.error(f"Failed to prepare environment '{feature_name}': {e}")
            if progress_cb:
                progress_cb(f"Error setting up '{feature_name}': {e}")
            self.remove_environment(feature_name)
            return False