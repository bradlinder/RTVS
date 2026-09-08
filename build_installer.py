#!/usr/bin/env python3
"""Build the installable Radio & TV Segmenter application with PyInstaller.

Run this script on the target operating system (Windows installers must be built on
Windows, macOS ones on macOS -- PyInstaller does not cross-compile). It intentionally
refuses to produce a release package unless FFmpeg and ffprobe are available at build time,
because the finished application is expected to carry its own media runtime rather than
require end users to install FFmpeg.

This build is CPU-only by design (see requirements.txt): GPU acceleration is an optional,
separately-downloaded component the user can enable from Settings after installing,
not something bundled into the installer.
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
    from prs_shared import APP_DISPLAY_NAME, PROJECT_VERSION
except Exception:
    APP_DISPLAY_NAME = "Radio & TV Segmenter"
    PROJECT_VERSION = "2.4.1"

# Only the PySide6 submodules this app actually imports
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

# Heavy internal test and benchmarking trees to exclude from packaging
TEST_AND_BENCHMARK_EXCLUDES = [
    "torch.testing._internal", "torch.utils.benchmark", "torch.utils.tensorboard",
    "torchaudio.prototype",
    "scipy.cluster.tests", "scipy.interpolate.tests", "scipy.signal.tests",
    "scipy.sparse.tests", "scipy.special.tests", "scipy.ndimage.tests",
    "scipy.optimize.tests", "scipy.linalg.tests", "scipy.stats.tests",
    "transformers.commands", "transformers.testing_utils",
    "sklearn.tests", "sklearn.datasets.tests", "sklearn.feature_extraction.tests",
    "pytest", "unittest.test", "test", "tests",
    "triton", "nvidia", "tkinter", "tcl",
]


def exe_name(base: str) -> str:
    return base + (".exe" if os.name == "nt" else "")


def find_tool(name: str) -> str:
    env_dir = os.environ.get("PRS_FFMPEG_DIR")
    target_exe = exe_name(name)
    candidates = []

    if env_dir:
        candidates.append(Path(env_dir) / target_exe)
        candidates.append(Path(env_dir) / "bin" / target_exe)

    found = shutil.which(name)
    if found:
        candidates.append(Path(found))

    candidates.extend([
        ROOT / "bin" / target_exe,
        ROOT / "runtime" / "bin" / target_exe,
        ROOT / "ffmpeg" / "bin" / target_exe,
        ROOT / "ffmpeg" / target_exe,
    ])

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
    try:
        creationflags = subprocess.CREATE_NO_WINDOW if sys.platform == 'win32' else 0
        result = subprocess.run(
            [sys.executable, "-c", "import torch; print(torch.version.cuda or '')"],
            capture_output=True, text=True, check=True,
            creationflags=creationflags,
        )
        cuda_version = result.stdout.strip()
    except Exception as exc:
        raise SystemExit(
            "[FATAL BUILD ERROR] PyTorch cannot be imported in the build environment: "
            f"{type(exc).__name__}: {exc}"
        ) from exc

    if cuda_version:
        msg = (
            f"[BUILD] WARNING: torch installed in this build environment reports CUDA {cuda_version}.\n"
            "This build is intended to be CPU-only and small (<500MB). Installing CUDA packages will\n"
            "balloon the installer to >2GB and fail release asset limits.\n\n"
            "More importantly: prune_unneeded_bundled_files() below deletes cuDNN/cuBLAS/nvRTC/NCCL\n"
            "files by name to keep a CPU build small, but it does NOT remove torch_cuda.dll/c10_cuda.dll\n"
            "themselves. Building from a CUDA-enabled torch therefore does not just produce an oversized\n"
            "installer -- it produces one where torch's C extension (torch._C) fails to load at all,\n"
            "because the CUDA DLLs it still depends on have been stripped out. This has shipped broken\n"
            "builds before (NameError: name '_C' is not defined, breaking Speaker Detection and\n"
            "Translation, which both import torch) -- so this now always aborts the build rather than\n"
            "just warning.\n\n"
            "To fix, install CPU-only torch before building:\n"
            "  pip install 'torch>=2.0,<2.4' 'torchaudio>=2.0,<2.4' --index-url https://download.pytorch.org/whl/cpu\n"
            "  pip install -r requirements.txt -r requirements-build.txt --extra-index-url https://download.pytorch.org/whl/cpu\n\n"
            "If you specifically need a CUDA build for local testing and understand the above risk,\n"
            "set PRS_ALLOW_CUDA_BUILD=1 to bypass this check."
        )
        if os.environ.get("PRS_ALLOW_CUDA_BUILD"):
            print(msg)
            print("[BUILD] PRS_ALLOW_CUDA_BUILD is set -- continuing with CUDA torch despite the risk above.")
            return
        raise SystemExit(f"\n[FATAL BUILD ERROR]\n{msg}")
    else:
        print("[BUILD] torch in the build environment is CPU-only. Good.")


def torch_windows_binary_flags() -> list[str]:
    if sys.platform != "win32":
        return []
    try:
        import importlib.util
        spec = importlib.util.find_spec("torch")
        if not spec or not spec.origin:
            raise RuntimeError("could not locate the build environment's torch package")
        torch_root = Path(spec.origin).resolve().parent
        lib_dir = torch_root / "lib"
    except Exception as exc:
        raise SystemExit(f"[FATAL BUILD ERROR] Could not locate torch/lib for PyInstaller: {exc}") from exc
    if not lib_dir.is_dir():
        raise SystemExit(f"[FATAL BUILD ERROR] Expected PyTorch native library directory was not found: {lib_dir}")

    flags: list[str] = ["--paths", str(lib_dir)]
    dlls = sorted(lib_dir.glob("*.dll"))
    required = {"c10.dll", "torch_cpu.dll", "torch_python.dll"}
    present = {p.name.lower() for p in dlls}
    missing = sorted(name for name in required if name.lower() not in present)
    if missing:
        raise SystemExit(
            "[FATAL BUILD ERROR] The CPU PyTorch wheel is missing required native DLLs in "
            f"{lib_dir}: {', '.join(missing)}"
        )
    for dll in dlls:
        flags += ["--add-binary", f"{dll}{os.pathsep}torch/lib"]
    print(f"[BUILD] Explicitly packaging {len(dlls)} PyTorch native DLLs from {lib_dir}")
    return flags


def run(cmd: list[str]) -> None:
    print("[BUILD]", " ".join(map(str, cmd)))
    creationflags = subprocess.CREATE_NO_WINDOW if sys.platform == 'win32' else 0
    subprocess.run(cmd, cwd=ROOT, check=True, creationflags=creationflags)


def provision_optional_runtime_tools(app_root: Path) -> None:
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

    BUILD.mkdir(parents=True, exist_ok=True)
    archive = BUILD / "uv.zip"
    print(f"[BUILD] Downloading uv {UV_VERSION} for optional runtime provisioning...")
    urllib.request.urlretrieve(url, archive)
    with zipfile.ZipFile(archive) as zf:
        member = next((n for n in zf.namelist() if n.lower().endswith("/uv.exe") or n.lower() == "uv.exe"), None)
        if not member:
            raise SystemExit("ERROR: The downloaded uv archive did not contain uv.exe.")
        with zf.open(member) as src, uv_dest.open("wb") as dst:
            shutil.copyfileobj(src, dst)
    archive.unlink(missing_ok=True)


def prune_unneeded_bundled_files(app_root: Path) -> None:
    print("[BUILD] Pruning non-runtime assets and symbol bloat from bundle...")
    main_internal = app_root / "_internal"
    internal_dirs = [main_internal] if main_internal.exists() else [app_root]

    cuda_purged = 0
    cuda_lib_prefixes = (
        "libnvrtc", "nvrtc", "libcudnn", "cudnn",
        "libcublas", "cublas", "libcusolver", "cusolver", "libcurand", "curand",
        "libcufft", "cufft", "libnccl", "nccl", "libnvJitLink", "libnvblas",
        "nvjitlink", "cusparse", "nvjpeg",
    )
    for base in internal_dirs:
        if not base.exists():
            continue
        for nvidia_dir in base.glob("**/nvidia"):
            if nvidia_dir.is_dir() and "workers" not in nvidia_dir.parts:
                print(f"[BUILD] Purging CUDA package directory: {nvidia_dir}")
                shutil.rmtree(nvidia_dir, ignore_errors=True)
                cuda_purged += 1
        for item in list(base.rglob("*")):
            if "workers" in item.parts:
                continue
            if item.is_file() and any(item.name.lower().startswith(p.lower()) for p in cuda_lib_prefixes):
                item.unlink(missing_ok=True)
                cuda_purged += 1

    if cuda_purged:
        print(f"[BUILD] Purged {cuda_purged} accidental CUDA files/directories from bundle.")

    unneeded_dirs = [
        "torch/include", "torch/share", "torchaudio/include", "scipy/include",
        "PySide6/include", "PySide6/glue", "PySide6/typesystems", "PySide6/scripts",
        "PySide6/translations",
        "PySide6/plugins/generic", "PySide6/plugins/sqldrivers",
        "PySide6/plugins/sensorgestures", "PySide6/plugins/position",
        "PySide6/plugins/scenegraph", "PySide6/plugins/qmltooling",
        "PySide6/plugins/networkinformation", "PySide6/plugins/geometryloaders",
        "onnxruntime/include", "sentencepiece/include", "tokenizers/include",
    ]
    for base in internal_dirs:
        if not base.exists():
            continue
        for hp in unneeded_dirs:
            target = base / Path(hp)
            if target.is_dir() and "workers" not in target.parts:
                print(f"[BUILD] Removing unneeded directory: {target}")
                shutil.rmtree(target, ignore_errors=True)

    pruned_files = 0
    test_dir_names = {"tests", "testing", "test", "benchmark", "benchmarks", "docs", "doc"}
    for base in internal_dirs:
        if not base.exists():
            continue
        for item in list(base.rglob("*")):
            if "workers" in item.parts:
                continue
            if item.is_file():
                if item.suffix in (".pdb", ".pyi", ".c", ".cpp", ".h", ".hpp", ".pyx", ".pxd"):
                    item.unlink(missing_ok=True)
                    pruned_files += 1
            elif item.is_dir() and item.name.lower() in test_dir_names:
                shutil.rmtree(item, ignore_errors=True)

    if pruned_files:
        print(f"[BUILD] Pruned {pruned_files} debug/stub/source files from bundle.")

    # Binary symbol stripping for Linux and macOS
    if sys.platform.startswith("linux") and shutil.which("strip"):
        stripped_count = 0
        for base in internal_dirs:
            if not base.exists():
                continue
            for item in list(base.rglob("*")):
                if "workers" in item.parts:
                    continue
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
    elif sys.platform == "darwin" and shutil.which("strip"):
        stripped_count = 0
        for base in internal_dirs:
            if not base.exists():
                continue
            for item in list(base.rglob("*")):
                if "workers" in item.parts:
                    continue
                if item.is_file() and not item.is_symlink() and item.suffix in (".dylib", ".so"):
                    try:
                        res = subprocess.run(
                            ["strip", "-x", str(item)],
                            stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL,
                            check=False,
                        )
                        if res.returncode == 0:
                            stripped_count += 1
                    except Exception:
                        pass
        if stripped_count:
            print(f"[BUILD] Stripped unneeded symbols from {stripped_count} macOS dynamic libraries.")


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

    torch_binary_flags = torch_windows_binary_flags()

    general_excludes = [
        *PYSIDE6_EXCLUDES,
        *TEST_AND_BENCHMARK_EXCLUDES,
    ]
    exclude_flags = []
    for module in general_excludes:
        exclude_flags += ["--exclude-module", module]

    collect_all_packages = [
        "numpy", "faster_whisper", "ctranslate2", "transformers", "tokenizers",
        "huggingface_hub", "torch", "torchaudio", "sentencepiece", "soundfile",
        "diarize", "silero_vad", "wespeakerruntime", "onnxruntime", "sherpa_onnx",
        "scipy", "sklearn", "psutil", "keyring", "docx", "pypdf", "sacremoses",
        "requests", "cryptography",
    ]
    collect_flags = []
    for pkg in collect_all_packages:
        collect_flags.extend(["--collect-all", pkg])
    for meta in ["numpy", "torch", "torchaudio", "silero_vad", "onnxruntime"]:
        collect_flags.extend(["--copy-metadata", meta])
    collect_flags.extend(["--hidden-import", "torch._C"])

    icon_file = ROOT / "resources" / ("icon.ico" if sys.platform == "win32" else "icon.png")
    icon_flags = ["--icon", str(icon_file)] if icon_file.exists() else []

    doc_flags = []
    for doc in ("NOTICES.txt", "LICENSE"):
        doc_file = ROOT / doc
        if doc_file.exists():
            doc_flags.extend(["--add-data", f"{doc_file}{os.pathsep}."])

    runtime_hook = ROOT / "installer" / "pyinstaller" / "torch_dll_hook.py"

    print("[BUILD] Compiling unified application with PyInstaller (shared ML & GUI runtime)...")
    run([
        "pyinstaller", "--noconfirm", "--onedir", "--windowed",
        "--name", APP_NAME,
        "--runtime-hook", str(runtime_hook),
        *torch_binary_flags,
        *icon_flags,
        *doc_flags,
        *pyside6_flags,
        *exclude_flags,
        *collect_flags,
        str(ROOT / ENTRY_POINT),
    ])

    if sys.platform == "darwin":
        app_root = DIST / f"{APP_NAME}.app" / "Contents" / "MacOS"
        plist_path = DIST / f"{APP_NAME}.app" / "Contents" / "Info.plist"
        if plist_path.exists():
            try:
                import plistlib
                with open(plist_path, "rb") as fp:
                    pl = plistlib.load(fp)
                pl["CFBundleDocumentTypes"] = [
                    {
                        "CFBundleTypeName": "Radio & TV Segmenter Project",
                        "CFBundleTypeRole": "Editor",
                        "CFBundleTypeExtensions": ["rtvs", "json"],
                        "CFBundleTypeIconFile": "icon.icns",
                        "LSHandlerRank": "Owner",
                    }
                ]
                with open(plist_path, "wb") as fp:
                    plistlib.dump(pl, fp)
                print(f"[BUILD] Registered .rtvs file association in {plist_path}")
            except Exception as e:
                print(f"[BUILD WARNING] Could not update Info.plist document types: {e}")
    else:
        app_root = DIST / APP_NAME

    runtime_bin = app_root / "runtime" / "bin"
    workers_dir = app_root / "workers"
    resources_dir = app_root / "resources"
    runtime_bin.mkdir(parents=True, exist_ok=True)
    workers_dir.mkdir(parents=True, exist_ok=True)
    resources_dir.mkdir(parents=True, exist_ok=True)

    if (ROOT / "resources").exists():
        for res in (ROOT / "resources").iterdir():
            if res.is_file():
                shutil.copy2(res, resources_dir / res.name)

    shutil.copy2(ffmpeg, runtime_bin / Path(ffmpeg).name)
    shutil.copy2(ffprobe, runtime_bin / Path(ffprobe).name)

    for doc in ("NOTICES.txt", "LICENSE"):
        doc_file = ROOT / doc
        if doc_file.exists():
            shutil.copy2(doc_file, app_root / doc)
            if sys.platform == "darwin":
                resources_bundle = app_root.parent / "Resources"
                resources_bundle.mkdir(parents=True, exist_ok=True)
                shutil.copy2(doc_file, resources_bundle / doc)

    # Build dedicated worker binary sharing the same runtime
    print("[BUILD] Generating dedicated AI worker entry point within the shared runtime...")
    worker_target_exe = exe_name("prs_worker")
    worker_dest = app_root / worker_target_exe
    worker_in_subdir = workers_dir / worker_target_exe

    # Compile prs_worker console executable with PyInstaller pointing to the shared onedir
    worker_build = BUILD / "worker_entry"
    worker_dist = BUILD / "worker_dist"
    shutil.rmtree(worker_build, ignore_errors=True)
    shutil.rmtree(worker_dist, ignore_errors=True)
    
    run([
        "pyinstaller", "--noconfirm", "--onedir", "--console",
        "--name", "prs_worker",
        "--distpath", str(worker_dist),
        "--workpath", str(worker_build),
        "--runtime-hook", str(runtime_hook),
        *torch_binary_flags,
        *icon_flags,
        *exclude_flags,
        *collect_flags,
        str(ROOT / "radio_tv_story_segmenter_worker.py"),
    ])

    # Copy the compiled standalone prs_worker binary into app_root and create worker shim
    generated_worker = worker_dist / "prs_worker" / worker_target_exe
    if generated_worker.exists():
        shutil.copy2(generated_worker, worker_dest)
        if sys.platform == "win32":
            shutil.copy2(generated_worker, worker_in_subdir)
        else:
            try:
                if worker_in_subdir.exists() or worker_in_subdir.is_symlink():
                    worker_in_subdir.unlink()
                worker_in_subdir.symlink_to(f"../{worker_target_exe}")
            except Exception:
                shutil.copy2(generated_worker, worker_in_subdir)
    shutil.rmtree(worker_dist, ignore_errors=True)

    provision_optional_runtime_tools(app_root)
    prune_unneeded_bundled_files(app_root)

    print("[BUILD] Running frozen AI worker self-test...")
    test_target = worker_dest if worker_dest.exists() else worker_in_subdir
    smoke = subprocess.run(
        [str(test_target), "--self-test"],
        cwd=app_root, capture_output=True, text=True,
        creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
    )
    if smoke.stdout:
        print(smoke.stdout.strip())
    if smoke.stderr:
        print(smoke.stderr.strip())
    if smoke.returncode != 0:
        raise SystemExit(
            "[FATAL BUILD ERROR] Frozen AI worker self-test failed. "
            "The installer was NOT produced. See the worker diagnostics above."
        )

    print("[BUILD] Running frozen GUI AI self-test...")
    main_test_file = app_root / "ai_self_test.txt"
    main_smoke = subprocess.run(
        [str(app_root / exe_name(APP_NAME)), "--self-test"],
        cwd=app_root, capture_output=True, text=True,
        creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
    )
    if main_test_file.exists():
        print(main_test_file.read_text(encoding="utf-8").strip())
        main_test_file.unlink(missing_ok=True)
    if main_smoke.returncode != 0:
        raise SystemExit(
            "[FATAL BUILD ERROR] Frozen GUI AI self-test failed. "
            "The installer was NOT produced."
        )

    if os.name != "nt":
        for item in runtime_bin.iterdir():
            item.chmod(0o755)
        if worker_dest.exists():
            worker_dest.chmod(0o755)
        if worker_in_subdir.exists() and not worker_in_subdir.is_symlink():
            worker_in_subdir.chmod(0o755)

    print(f"\n[BUILD] {APP_DISPLAY_NAME} v{PROJECT_VERSION} build complete: {app_root.parent if sys.platform == 'darwin' else app_root}")


if __name__ == "__main__":
    main()