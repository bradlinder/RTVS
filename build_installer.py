#!/usr/bin/env python3
"""Build the installable Radio & TV Segmenter 1.7 application with PyInstaller.

Run this script on the target operating system (Windows installers must be
built on Windows, macOS ones on macOS -- PyInstaller does not cross-compile).
It intentionally refuses to produce a release package unless FFmpeg and
ffprobe are available at build time, because the finished application is
expected to carry its own media runtime rather than require end users to
install FFmpeg.

This build is CPU-only by design (see requirements.txt): GPU acceleration is
an optional, separately-downloaded component the user can enable from
Settings after installing, not something bundled into the installer.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DIST = ROOT / "dist"
BUILD = ROOT / "build"
APP_NAME = "RadioTVSegmenter"
ENTRY_POINT = "RadioTVSegmenter.py"
UV_VERSION = "0.12.7"
UV_URLS = {
    "win32-x86_64": f"https://github.com/astral-sh/uv/releases/download/{UV_VERSION}/uv-x86_64-pc-windows-msvc.zip",
    "win32-arm64": f"https://github.com/astral-sh/uv/releases/download/{UV_VERSION}/uv-aarch64-pc-windows-msvc.zip",
}

try:
    # Single source of truth for the version string/display name so the
    # installer and the About box never drift apart.
    from prs_shared import APP_DISPLAY_NAME, PROJECT_VERSION
except Exception:
    APP_DISPLAY_NAME = "Radio & TV Segmenter"
    PROJECT_VERSION = "1.7"

# Only the PySide6 submodules this app actually imports (verified against
# every `from PySide6.X import ...` in the source tree). The previous build
# used `--collect-all PySide6`, which pulls in the ENTIRE Qt distribution --
# QtWebEngine, Qt3D, QtCharts, QtQuick/QML, QtSql, QtBluetooth, QtPdf, and
# more -- none of which this app uses, at a large size cost. Collecting only
# what's used, plus an explicit exclude list as a backstop against
# over-eager PyInstaller hooks, is the single biggest lever for installer
# size on top of the CPU-only ML stack below.
PYSIDE6_USED_SUBMODULES = ["QtCore", "QtGui", "QtWidgets", "QtMultimedia", "QtMultimediaWidgets"]
PYSIDE6_EXCLUDES = [
    "PySide6.QtWebEngineCore", "PySide6.QtWebEngineWidgets", "PySide6.QtWebEngineQuick",
    "PySide6.QtQml", "PySide6.QtQuick", "PySide6.QtQuick3D", "PySide6.QtQuickWidgets",
    "PySide6.Qt3DCore", "PySide6.Qt3DRender", "PySide6.Qt3DInput", "PySide6.Qt3DExtras",
    "PySide6.Qt3DAnimation", "PySide6.Qt3DLogic",
    "PySide6.QtCharts", "PySide6.QtDataVisualization", "PySide6.QtGraphs", "PySide6.QtGraphsWidgets",
    "PySide6.QtBluetooth", "PySide6.QtNfc", "PySide6.QtPositioning", "PySide6.QtLocation",
    "PySide6.QtSensors", "PySide6.QtSerialPort", "PySide6.QtSerialBus",
    "PySide6.QtSql", "PySide6.QtTest", "PySide6.QtDesigner", "PySide6.QtHelp",
    "PySide6.QtPdf", "PySide6.QtPdfWidgets", "PySide6.QtWebSockets", "PySide6.QtWebChannel",
    "PySide6.QtRemoteObjects", "PySide6.QtScxml", "PySide6.QtStateMachine",
    "PySide6.QtNetworkAuth", "PySide6.QtSpatialAudio",
]


def exe_name(base: str) -> str:
    return base + (".exe" if os.name == "nt" else "")


def find_tool(name: str) -> str:
    # 1. Environment variable override
    env_dir = os.environ.get("PRS_FFMPEG_DIR")
    target_exe = exe_name(name)
    candidates = []
    
    if env_dir:
        candidates.append(Path(env_dir) / target_exe)
        candidates.append(Path(env_dir) / "bin" / target_exe)
    
    # 2. Check System PATH
    found = shutil.which(name)
    if found:
        candidates.append(Path(found))
        
    # 3. Check local project directories
    candidates.extend([
        ROOT / "bin" / target_exe,
        ROOT / "runtime" / "bin" / target_exe,
        ROOT / "ffmpeg" / "bin" / target_exe,
        ROOT / "ffmpeg" / target_exe,
    ])
    
    # 4. Check common OS installation paths
    if sys.platform == "win32":
        win_candidates = [
            Path("C:/ffmpeg/bin") / target_exe,
            Path("C:/ffmpeg") / target_exe,
            Path("C:/Program Files/ffmpeg/bin") / target_exe,
            Path("C:/Program Files/ffmpeg") / target_exe,
            Path("C:/Program Files (x86)/ffmpeg/bin") / target_exe,
            Path(os.environ.get("LOCALAPPDATA", "C:/")) / "Microsoft/WinGet/Links" / target_exe,
            Path(os.environ.get("ProgramData", "C:/")) / "chocolatey/bin" / target_exe,
            Path.home() / "scoop/shims" / target_exe,
        ]
        candidates.extend(win_candidates)
    else:
        candidates.extend([
            Path("/usr/bin") / target_exe,
            Path("/usr/local/bin") / target_exe,
            Path("/opt/homebrew/bin") / target_exe,
            Path("/snap/bin") / target_exe,
            Path.home() / ".local/bin" / target_exe,
        ])

    for candidate in candidates:
        if candidate.is_file():
            resolved = str(candidate.resolve())
            print(f"[BUILD] Found {name}: {resolved}")
            return resolved

    # 5. Interactive prompt fallback if running in an interactive terminal
    if sys.stdin.isatty():
        print(f"\n[BUILD] {name} was not found automatically in PATH or standard folders.")
        user_input = input(f"Please enter the directory containing {name} (or leave empty to exit): ").strip()
        if user_input:
            user_path = Path(user_input).expanduser()
            if (user_path / target_exe).is_file():
                return str((user_path / target_exe).resolve())
            if user_path.is_file() and user_path.name.lower().startswith(name):
                return str(user_path.resolve())

    raise SystemExit(
        f"\n[ERROR] '{name}' was not found.\n"
        "To fix this, you can:\n"
        f"  1. Place {exe_name('ffmpeg')} and {exe_name('ffprobe')} in the project's 'bin/' folder: {ROOT / 'bin'}\n"
        "  2. Or set the PRS_FFMPEG_DIR environment variable to the folder containing them.\n"
        "  3. Or install FFmpeg and add it to your system PATH.\n"
    )


def check_cpu_only_torch() -> None:
    """Check that the build venv's torch is CPU-only. This build is meant to be
    CPU-only and small; a CUDA-enabled torch wheel alone adds 2+ GB. GPU acceleration
    is an optional component provisioned on demand via Settings, not bundled here."""
    try:
        result = subprocess.run(
            [sys.executable, "-c", "import torch; print(torch.version.cuda or '')"],
            capture_output=True, text=True, check=True,
        )
        cuda_version = result.stdout.strip()
    except Exception:
        print("[BUILD] Could not determine torch's CUDA status (torch not importable in this venv?). Continuing.")
        return

    if cuda_version:
        is_ci = os.environ.get("CI", "").lower() in ("true", "1") or os.environ.get("GITHUB_ACTIONS") == "true"
        msg = (
            f"[BUILD] WARNING: torch installed in this build environment reports CUDA {cuda_version}.\n"
            "This build is intended to be CPU-only and small (<500MB). Installing CUDA packages will\n"
            "balloon the installer to >2GB and fail release asset limits.\n"
            "To fix, install CPU-only torch before building:\n"
            "  pip install 'torch>=2.0,<2.4' 'torchaudio>=2.0,<2.4' --index-url https://download.pytorch.org/whl/cpu\n"
            "  pip install -r requirements.txt -r requirements-build.txt --extra-index-url https://download.pytorch.org/whl/cpu"
        )
        if is_ci or os.environ.get("PRS_STRICT_CPU"):
            raise SystemExit(f"\n[FATAL BUILD ERROR]\n{msg}\nAborting build because CUDA was detected during release CI.")
        print(msg)
    else:
        print("[BUILD] torch in the build environment is CPU-only. Good.")


def run(cmd: list[str]) -> None:
    print("[BUILD]", " ".join(map(str, cmd)))
    subprocess.run(cmd, cwd=ROOT, check=True)


def provision_optional_runtime_tools(app_root: Path) -> None:
    """Add only the tiny helper needed to provision optional Windows runtimes.

    uv is intentionally the only extra runtime-management binary shipped in the
    base installer. Large CUDA/ML packages remain entirely on-demand. macOS does
    not ship CUDA support, so no helper is added there.
    """
    if sys.platform != "win32":
        return
    machine = os.environ.get("PROCESSOR_ARCHITECTURE", "").lower()
    arch_key = "win32-arm64" if "arm64" in machine else "win32-x86_64"
    url = UV_URLS[arch_key]
    dest_dir = app_root / "optional_runtime"
    dest_dir.mkdir(parents=True, exist_ok=True)
    uv_dest = dest_dir / "uv.exe"
    if uv_dest.exists():
        return
    archive = BUILD / "uv.zip"
    print(f"[BUILD] Downloading uv {UV_VERSION} for optional runtime provisioning…")
    urllib.request.urlretrieve(url, archive)
    with zipfile.ZipFile(archive) as zf:
        member = next((n for n in zf.namelist() if n.lower().endswith("/uv.exe") or n.lower() == "uv.exe"), None)
        if not member:
            raise SystemExit("ERROR: The downloaded uv archive did not contain uv.exe.")
        with zf.open(member) as src, uv_dest.open("wb") as dst:
            shutil.copyfileobj(src, dst)
    archive.unlink(missing_ok=True)


def prune_unneeded_bundled_files(app_root: Path) -> None:
    """Remove non-runtime files like C++ headers, test suites, debug symbols, and accidental CUDA bloat."""
    print("[BUILD] Pruning non-runtime assets and symbol bloat from bundle...")
    internal_dirs = [app_root / "_internal", app_root]

    # 1. Purge accidental CUDA/NVIDIA libraries that may have been pulled in by dependencies
    cuda_purged = 0
    cuda_lib_prefixes = (
        "libtorch_cuda", "torch_cuda", "libnvrtc", "nvrtc", "libcudnn", "cudnn",
        "libcublas", "cublas", "libcusolver", "cusolver", "libcurand", "curand",
        "libcufft", "cufft", "libnccl", "nccl", "libnvJitLink", "libnvblas",
    )
    for base in internal_dirs:
        if not base.exists():
            continue
        # Remove any nvidia package folders
        for nvidia_dir in base.glob("**/nvidia"):
            if nvidia_dir.is_dir():
                print(f"[BUILD] Purging CUDA package directory: {nvidia_dir}")
                shutil.rmtree(nvidia_dir, ignore_errors=True)
                cuda_purged += 1
        for item in list(base.rglob("*")):
            if item.is_file() and any(item.name.startswith(p) for p in cuda_lib_prefixes):
                item.unlink(missing_ok=True)
                cuda_purged += 1
    if cuda_purged:
        print(f"[BUILD] Purged {cuda_purged} accidental CUDA files/directories from bundle.")

    # 2. C++ headers, share directories, and developer includes
    header_patterns = [
        "torch/include", "torch/share", "torchaudio/include", "scipy/include",
        "PySide6/include", "PySide6/glue", "PySide6/typesystems", "PySide6/scripts",
    ]
    for base in internal_dirs:
        if not base.exists():
            continue
        for hp in header_patterns:
            target = base / Path(hp)
            if target.is_dir():
                print(f"[BUILD] Removing unneeded directory: {target}")
                shutil.rmtree(target, ignore_errors=True)

    # 3. Test directories, debug symbols, and type stubs
    pruned_files = 0
    for base in internal_dirs:
        if not base.exists():
            continue
        for item in list(base.rglob("*")):
            if item.is_file():
                if item.suffix in (".pdb", ".pyi"):
                    item.unlink(missing_ok=True)
                    pruned_files += 1
            elif item.is_dir() and item.name in ("tests", "testing", "test") and any(k in str(item).lower() for k in ("torch", "scipy", "transformers", "ctranslate2", "pyside6", "sympy", "jinja2")):
                shutil.rmtree(item, ignore_errors=True)
    if pruned_files:
        print(f"[BUILD] Pruned {pruned_files} debug/stub files from bundle.")

    # 4. Strip unneeded symbols from Linux ELF shared objects and binaries
    if sys.platform.startswith("linux") and shutil.which("strip"):
        stripped_count = 0
        for base in internal_dirs:
            if not base.exists():
                continue
            for item in list(base.rglob("*")):
                if item.is_file() and not item.is_symlink():
                    if item.suffix == ".so" or ".so." in item.name or (item.stat().st_mode & 0o111 and not item.suffix):
                        try:
                            res = subprocess.run(
                                ["strip", "--strip-unneeded", str(item)],
                                stdout=subprocess.DEVNULL,
                                stderr=subprocess.DEVNULL,
                                check=False,
                            )
                            if res.returncode == 0:
                                stripped_count += 1
                        except Exception:
                            pass
        if stripped_count:
            print(f"[BUILD] Stripped unneeded symbols from {stripped_count} Linux binaries/libraries.")


def main() -> None:
    if sys.version_info[:2] != (3, 12):
        raise SystemExit("ERROR: Build with Python 3.12. The AI dependency set is not guaranteed to support other Python versions.")
    if not shutil.which("pyinstaller"):
        raise SystemExit("ERROR: PyInstaller is not installed. Install requirements-build.txt first.")

    ffmpeg = find_tool("ffmpeg")
    ffprobe = find_tool("ffprobe")

    check_cpu_only_torch()

    shutil.rmtree(BUILD, ignore_errors=True)
    shutil.rmtree(DIST, ignore_errors=True)

    pyside6_flags = []
    for module in PYSIDE6_USED_SUBMODULES:
        pyside6_flags += ["--collect-submodules", f"PySide6.{module}"]
    
    # Heavy unused submodules, test suites, and redundant backends to exclude from base build
    general_excludes = [
        *PYSIDE6_EXCLUDES,
        "torch.testing", "torch.distributed", "torch.onnx", "torch.compiler",
        "torch.utils.benchmark", "torch.utils.tensorboard", "torch.cuda",
        "torchaudio.cuda", "triton", "nvidia",
        "scipy.spatial.tests", "scipy.stats.tests", "scipy.optimize.tests",
        "scipy.linalg.tests", "scipy.sparse.tests", "scipy.ndimage.tests",
        "pytest", "unittest.test", "test", "tests",
        "tkinter", "tcl",
    ]
    exclude_flags = []
    for module in general_excludes:
        exclude_flags += ["--exclude-module", module]

    collect_main = [
        *pyside6_flags,
        *exclude_flags,
        "--collect-all", "faster_whisper",
        "--collect-all", "ctranslate2",
        "--collect-all", "transformers",
        "--collect-all", "tokenizers",
        "--collect-all", "huggingface_hub",
        "--collect-all", "torch",
        "--collect-all", "torchaudio",
        "--collect-all", "sentencepiece",
        "--collect-all", "soundfile",
        "--collect-all", "diarize",
        "--collect-all", "keyring",
        "--collect-all", "docx",
    ]

    icon_file = ROOT / "resources" / ("icon.ico" if sys.platform == "win32" else "icon.png")
    icon_flags = ["--icon", str(icon_file)] if icon_file.exists() else []

    doc_flags = []
    for doc in ("NOTICES.txt", "LICENSE"):
        doc_file = ROOT / doc
        if doc_file.exists():
            doc_flags.extend(["--add-data", f"{doc_file}{os.pathsep}."])

    print("[BUILD] Compiling single unified application binary with PyInstaller...")
    run([
        "pyinstaller", "--noconfirm", "--clean", "--onedir", "--windowed",
        "--name", APP_NAME,
        *icon_flags,
        *doc_flags,
        *collect_main,
        str(ROOT / ENTRY_POINT),
    ])

    if sys.platform == "darwin":
        app_root = DIST / f"{APP_NAME}.app" / "Contents" / "MacOS"
    else:
        app_root = DIST / APP_NAME
    runtime_bin = app_root / "runtime" / "bin"
    workers_dir = app_root / "workers"
    resources_dir = app_root / "resources"
    runtime_bin.mkdir(parents=True, exist_ok=True)
    workers_dir.mkdir(parents=True, exist_ok=True)
    resources_dir.mkdir(parents=True, exist_ok=True)

    # Copy bundled visual resources (icons)
    if (ROOT / "resources").exists():
        for res in (ROOT / "resources").iterdir():
            if res.is_file():
                shutil.copy2(res, resources_dir / res.name)

    shutil.copy2(ffmpeg, runtime_bin / Path(ffmpeg).name)
    shutil.copy2(ffprobe, runtime_bin / Path(ffprobe).name)

    # Bundle licensing and third-party attribution documents
    for doc in ("NOTICES.txt", "LICENSE"):
        doc_file = ROOT / doc
        if doc_file.exists():
            shutil.copy2(doc_file, app_root / doc)
            if sys.platform == "darwin":
                resources_bundle = app_root.parent / "Resources"
                resources_bundle.mkdir(parents=True, exist_ok=True)
                shutil.copy2(doc_file, resources_bundle / doc)

    # Ship the worker source script alongside the unified executable.
    # The unified frozen app runs the worker directly via '--prs-worker', sharing
    # all compiled PyTorch/Whisper binaries without duplicate storage.
    # When a user installs GPU acceleration from Settings, the app runs this source
    # file with the separately-provisioned GPU environment.
    shutil.copy2(ROOT / "radio_tv_story_segmenter_worker.py", workers_dir / "radio_tv_story_segmenter_worker.py")
    provision_optional_runtime_tools(app_root)

    # Prune non-runtime assets (C++ headers, debug symbols, test suites)
    prune_unneeded_bundled_files(app_root)

    if os.name != "nt":
        for item in runtime_bin.iterdir():
            item.chmod(0o755)

    print(f"\n[BUILD] {APP_DISPLAY_NAME} v{PROJECT_VERSION} build complete: {app_root.parent if sys.platform == 'darwin' else app_root}")
    print("[BUILD] FFmpeg and ffprobe were copied into the application runtime.")
    print("[BUILD] AI worker is unified with the application executable (and worker source is available for optional GPU runtime).")
    print("[BUILD] Reminder: launch the packaged build directly (not from source) and confirm audio playback works before shipping.")


if __name__ == "__main__":
    main()
