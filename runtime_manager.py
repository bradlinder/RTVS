import sys
import os
import json
import shutil
import logging
import subprocess
from pathlib import Path

logger = logging.getLogger(__name__)

UV_VERSION = "0.12.7"

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
        "version": "1.0.0",
        "python_version": "3.12",
        "packages": [
            "transformers",
            "torch>=2.0.0,<2.4.0",
            "sentencepiece"
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
        result = subprocess.run(
            [nvidia_smi, "-L"], capture_output=True, text=True, timeout=5,
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
                    res = subprocess.run(
                        [py_launcher, f"-{target_version}", "-c", "import sys; print(sys.executable)"],
                        capture_output=True, text=True, check=True
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

    def bundled_uv_path(self) -> Path:
        """Return the optional uv binary shipped with the Windows build."""
        if sys.platform != "win32":
            return Path()
        name = "uv.exe"
        candidates = [
            Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent)) / "optional_runtime" / name,
            Path(sys.executable).resolve().parent / "optional_runtime" / name,
            Path(__file__).resolve().parent / "optional_runtime" / name,
        ]
        for candidate in candidates:
            if candidate.is_file():
                return candidate
        return Path()

    def ensure_managed_python(self, target_version: str = "3.12", progress_cb=None) -> str:
        """Provision a private Python runtime with uv when the host has no matching Python.

        This is used only for optional feature environments. The base installer remains
        independent of system Python, while GPU support can still be installed from the
        packaged application on Windows.
        """
        uv = self.bundled_uv_path()
        if not uv:
            return ""
        python_dir = self.runtimes_dir / "python"
        python_dir.mkdir(parents=True, exist_ok=True)
        env = os.environ.copy()
        env["UV_PYTHON_INSTALL_DIR"] = str(python_dir)
        env["UV_PYTHON_PREFERENCE"] = "only-managed"
        try:
            if progress_cb:
                progress_cb(f"Preparing private Python {target_version} runtime…")
            subprocess.run([str(uv), "python", "install", target_version], check=True, env=env,
                           stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
            res = subprocess.run([str(uv), "python", "find", target_version], check=True, env=env,
                                 capture_output=True, text=True)
            exe = res.stdout.strip().splitlines()[-1] if res.stdout.strip() else ""
            return exe if exe and Path(exe).exists() else ""
        except Exception as exc:
            logger.error("Could not provision managed Python %s: %s", target_version, exc)
            if progress_cb:
                progress_cb(f"Could not provision private Python {target_version}: {exc}")
            return ""

    def is_env_up_to_date(self, feature_name: str) -> bool:
        """Verifies if environment exists and matches current config version and specs."""
        manifest_path = self.get_manifest_path(feature_name)
        if not manifest_path.exists():
            return False

        try:
            with open(manifest_path, "r", encoding="utf-8") as f:
                data = json.load(f)

            target_config = ENV_CONFIGS.get(feature_name, {})
            return (
                data.get("config_version") == target_config.get("version") and
                data.get("target_python") == target_config.get("python_version")
            )
        except Exception as e:
            logger.warning(f"Failed to read runtime manifest for {feature_name}: {e}")
            return False

    def write_manifest(self, feature_name: str, python_used: str):
        """Writes configuration metadata upon successful environment creation."""
        manifest_path = self.get_manifest_path(feature_name)
        config = ENV_CONFIGS.get(feature_name, {})
        manifest_data = {
            "config_version": config.get("version", "1.0.0"),
            "target_python": config.get("python_version", "3.12"),
            "resolved_python_binary": python_used,
            "packages": config.get("packages", [])
        }
        with open(manifest_path, "w", encoding="utf-8") as f:
            json.dump(manifest_data, f, indent=2)

    def ensure_environment(self, feature_name: str, force_rebuild: bool = False, progress_cb=None) -> bool:
        """Creates or upgrades an isolated feature environment."""
        if feature_name not in ENV_CONFIGS:
            logger.error(f"Unknown feature environment: {feature_name}")
            return False

        if not force_rebuild and self.is_env_up_to_date(feature_name):
            if progress_cb:
                progress_cb(f"Runtime '{feature_name}' is ready and up to date.")
            return True

        env_dir = self.get_env_dir(feature_name)
        config = ENV_CONFIGS[feature_name]
        target_ver = config.get("python_version", "3.12")
        python_binary = self.resolve_target_python(target_ver)
        if not python_binary:
            python_binary = self.ensure_managed_python(target_ver, progress_cb=progress_cb)
        if not python_binary:
            logger.error(
                "A compatible Python runtime could not be located or provisioned for optional feature '%s'.",
                feature_name,
            )
            if progress_cb:
                progress_cb(
                    f"Python {target_ver} could not be provisioned. Optional feature installation was stopped."
                )
            return False

        if env_dir.exists():
            if progress_cb:
                progress_cb(f"Upgrading runtime '{feature_name}' (removing outdated environment)...")
            shutil.rmtree(env_dir, ignore_errors=True)

        if progress_cb:
            progress_cb(f"Creating environment for '{feature_name}' using {python_binary}...")

        try:
            uv = self.bundled_uv_path()
            if uv:
                # uv creates a venv without requiring pip to be bundled in the managed Python.
                subprocess.run([str(uv), "venv", "--python", python_binary, str(env_dir)], check=True)
                env_py = str(self._get_raw_executable(feature_name))
                if progress_cb:
                    progress_cb(f"Installing dependencies for '{feature_name}'…")
                cmd_pip = [str(uv), "pip", "install", "--python", env_py, "--no-cache", "--upgrade"]
            else:
                subprocess.run([python_binary, "-m", "venv", str(env_dir)], check=True)
                env_py = str(self._get_raw_executable(feature_name))
                if progress_cb:
                    progress_cb(f"Installing dependencies for '{feature_name}'…")
                cmd_pip = [env_py, "-m", "pip", "install", "--no-cache-dir", "--upgrade"]
            extra_index_url = config.get("extra_index_url")
            if extra_index_url:
                cmd_pip += ["--extra-index-url", extra_index_url]
            cmd_pip += config["packages"]
            subprocess.run(cmd_pip, check=True)

            # Record manifest for future version checks
            self.write_manifest(feature_name, python_binary)
            
            if progress_cb:
                progress_cb(f"Runtime '{feature_name}' setup complete.")
            return True

        except Exception as e:
            logger.error(f"Failed to prepare environment '{feature_name}': {e}")
            if progress_cb:
                progress_cb(f"Error setting up '{feature_name}': {e}")
            # Clean up broken virtualenv directory on failure so we don't leave corrupt binaries
            shutil.rmtree(env_dir, ignore_errors=True)
            return False